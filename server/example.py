"""example.py — выгрузка всех переменных кадра отладки в JSON.

Использование как библиотеки:
    from example import dump_frame_to_json
    await dump_frame_to_json(self.dap, frame_id, "variables.json")

CLI (для теста на живой DAP-сессии):
    python example.py <dap_port> <frame_id> [out.json]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from dap_client import DapClient, DapError


# ---------- преобразование значений ----------

def _coerce(value: str, vtype: str = "") -> Any:
    """'42' → 42, '\"hi\"' → 'hi', 'true' → True, 'null' → None."""
    if value is None:
        return None
    v = value.strip()
    if v == "null":
        return None
    if v == "true":
        return True
    if v == "false":
        return False

    # строки java-debug приходят в двойных кавычках
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        try:
            return json.loads(v)
        except Exception:
            return v[1:-1]

    # char
    if len(v) == 3 and v[0] == "'" and v[2] == "'":
        return v[1]

    # числа — с учётом типа
    try:
        if "long" in vtype.lower() or v.endswith("L") or v.endswith("l"):
            return int(v.rstrip("Ll"))
        if "." in v or "e" in v.lower() or "float" in vtype.lower() or "double" in vtype.lower():
            return float(v)
        return int(v)
    except (ValueError, TypeError):
        return v


def _is_array(items: list[dict]) -> bool:
    return bool(items) and all(v.get("name", "").startswith("[") for v in items)


# ---------- рекурсивный обход ----------

async def _dump_ref(
    dap: DapClient,
    ref: int,
    *,
    depth: int = 0,
    max_depth: int = 10,
    max_items: int = 1000,
    visited: set[int] | None = None,
) -> Any:
    if visited is None:
        visited = set()
    if ref in visited:
        return f"<cycle: ref {ref}>"
    if depth > max_depth:
        return f"<max depth {max_depth}>"

    visited.add(ref)
    try:
        r = await dap.request("variables", {"variablesReference": ref})
    except DapError as e:
        return f"<error: {e}>"

    items = r.get("variables", [])[:max_items]
    if not items:
        return []

    if _is_array(items):
        out = []
        for v in items:
            child = v.get("variablesReference", 0)
            if child:
                out.append(await _dump_ref(dap, child,
                    depth=depth + 1, max_depth=max_depth, max_items=max_items, visited=visited))
            else:
                out.append(_coerce(v.get("value", ""), v.get("type", "")))
        return out

    out: dict[str, Any] = {}
    for v in items:
        name = v.get("name", "?")
        child = v.get("variablesReference", 0)
        if child:
            out[name] = await _dump_ref(dap, child,
                depth=depth + 1, max_depth=max_depth, max_items=max_items, visited=visited)
        else:
            out[name] = _coerce(v.get("value", ""), v.get("type", ""))
    return out


# ---------- публичный API ----------

async def dump_frame(dap: DapClient, frame_id: int, *, max_depth: int = 10) -> dict:
    """Собирает {scope_name: {переменные}} для кадра."""
    r = await dap.request("scopes", {"frameId": frame_id})
    result: dict = {"frameId": frame_id, "scopes": {}}
    for scope in r.get("scopes", []):
        ref = scope.get("variablesReference", 0)
        name = scope.get("name", "?")
        result["scopes"][name] = (
            await _dump_ref(dap, ref, max_depth=max_depth) if ref else {}
        )
    return result


async def dump_frame_to_json(
    dap: DapClient, frame_id: int, path: str, *, max_depth: int = 10,
) -> str:
    """Собирает переменные кадра и пишет в JSON-файл."""
    data = await dump_frame(dap, frame_id, max_depth=max_depth)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p.resolve())


# ---------- CLI ----------

async def _main_cli() -> int:
    if len(sys.argv) < 3:
        print("usage: python example.py <dap_port> <frame_id> [out.json]")
        return 1
    port = int(sys.argv[1])
    frame_id = int(sys.argv[2])
    out = sys.argv[3] if len(sys.argv) > 3 else "variables.json"

    async def _noop(event: str, body: dict) -> None:
        pass

    dap = DapClient(_noop)
    await dap.connect("127.0.0.1", port)
    try:
        path = await dump_frame_to_json(dap, frame_id, out)
        print(f"saved: {path}")
    finally:
        await dap.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main_cli()))