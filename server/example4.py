"""
example4.py — останавливается на строке в указанном .java и возвращает
переменные верхнего кадра в нормализованном виде.

Нормализует значения java-debug:
  * String        -> "hi"        (декодер JDK 8 и JDK 9+, LATIN1/UTF16)
  * пустой массив -> []          ("String[0]@9" -> [])
  * byte[]/char[] -> list чисел  (если не String)
  * объекты       -> dict        (с защитой от циклов и лимитом глубины)

Публичный API:
    from example4 import call, call_sync
    data = await call("C:/.../BigMess.java", 134)

CLI:
    python example4.py <path/to/BigMess.java> <stop_line> [--max-depth N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from server.dap_client import DapClient, DapError
from server.example2 import LazyDapSession
from server.java_debug_session import detect_main_class


# ======================== decode java.lang.String ========================

def _as_int(x: Any) -> int | None:
    if isinstance(x, int):
        return x
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, str):
        s = x.strip().rstrip("Ll")
        try:
            return int(s, 0)
        except ValueError:
            return None
    return None


def _as_bytes(field: Any) -> bytes | None:
    """byte[] в любом виде: {'0':104,'1':105} или [104,105]."""
    if field is None:
        return None
    if isinstance(field, list):
        out = bytearray()
        for v in field:
            n = _as_int(v)
            if n is None:
                return None
            out.append(n & 0xFF)
        return bytes(out)
    if isinstance(field, dict):
        pairs = []
        for k, v in field.items():
            try:
                idx = int(k.strip("[]"))
            except ValueError:
                return None
            n = _as_int(v)
            if n is None:
                return None
            pairs.append((idx, n))
        pairs.sort()
        return bytes((n & 0xFF) for _, n in pairs)
    return None


def _as_chars(field: Any) -> list[int] | None:
    """char[] как список UTF-16 code units."""
    if field is None:
        return None
    if isinstance(field, list):
        vals = field
    elif isinstance(field, dict):
        pairs = []
        for k, v in field.items():
            try:
                idx = int(k.strip("[]"))
            except ValueError:
                return None
            n = _as_int(v)
            if n is None:
                return None
            pairs.append((idx, n))
        pairs.sort()
        vals = [n for _, n in pairs]
    else:
        return None
    out = []
    for v in vals:
        n = _as_int(v)
        if n is None:
            return None
        out.append(n & 0xFFFF)
    return out


def looks_like_java_string(d: Any) -> bool:
    if not isinstance(d, dict) or "value" not in d:
        return False
    if "coder" in d:
        return True
    if set(d) & {"offset", "count"}:
        return True
    return isinstance(d.get("value"), (list, dict))


def decode_java_string(d: dict) -> str | None:
    """{'coder':0,'value':{'0':104,'1':105}} -> 'hi'."""
    if not isinstance(d, dict) or "value" not in d:
        return None

    coder = _as_int(d.get("coder"))
    offset = _as_int(d.get("offset")) or 0
    count = _as_int(d.get("count"))
    raw = d.get("value")

    if coder is not None:                     # JDK 9+
        if coder == 0:                        # LATIN1
            b = _as_bytes(raw)
            if b is None:
                return None
            if count is not None:
                b = b[offset:offset + count]
            return b.decode("latin-1")
        if coder == 1:                        # UTF16LE
            b = _as_bytes(raw)
            if b is None:
                return None
            if count is not None:
                b = b[offset * 2:(offset + count) * 2]
            if len(b) % 2:
                return None
            return b.decode("utf-16-le", errors="surrogatepass")
        return None

    # JDK 8-: char[]
    chars = _as_chars(raw)
    if chars is None:
        return None
    if count is not None:
        chars = chars[offset:offset + count]
    return "".join(chr(c) for c in chars)


# ======================== coerce примитивов ========================

_ARR = re.compile(r'^([\w.$]+)\[(\d+)\]@\d+$')


def _coerce(value: str | None, vtype: str = "") -> Any:
    if value is None:
        return None
    v = value.strip()
    if v == "null":
        return None
    if v == "true":
        return True
    if v == "false":
        return False

    m = _ARR.match(v)
    if m:
        return [None] * int(m.group(2))

    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        try:
            return json.loads(v)
        except Exception:
            return v[1:-1]

    if len(v) == 3 and v[0] == "'" and v[2] == "'":
        return v[1]

    try:
        if "long" in vtype.lower() or v.endswith(("L", "l")):
            return int(v.rstrip("Ll"))
        if "." in v or "e" in v.lower() or "float" in vtype.lower() or "double" in vtype.lower():
            return float(v)
        return int(v)
    except (ValueError, TypeError):
        return v


def _is_array(items: list[dict]) -> bool:
    return bool(items) and all(v.get("name", "").startswith("[") for v in items)


# ======================== рекурсивный обход ========================

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

    # 1) java.lang.String — распознаём по полям и декодируем
    as_dict: dict[str, Any] = {}
    for v in items:
        name = v.get("name", "?")
        child = v.get("variablesReference", 0)
        if child:
            as_dict[name] = await _dump_ref(dap, child, depth=depth + 1,
                max_depth=max_depth, max_items=max_items, visited=visited)
        else:
            as_dict[name] = _coerce(v.get("value", ""), v.get("type", ""))
    if looks_like_java_string(as_dict):
        s = decode_java_string(as_dict)
        if s is not None:
            return s

    # 2) Массивы
    if _is_array(items):
        out = []
        for v in items:
            child = v.get("variablesReference", 0)
            out.append(await _dump_ref(dap, child, depth=depth + 1,
                max_depth=max_depth, max_items=max_items, visited=visited)
                if child else _coerce(v.get("value", ""), v.get("type", "")))
        return out

    # 3) Обычные объекты
    return as_dict


async def dump_frame(dap: DapClient, frame_id: int, *, max_depth: int = 10) -> dict:
    r = await dap.request("scopes", {"frameId": frame_id})
    result: dict = {"frameId": frame_id, "scopes": {}}
    for scope in r.get("scopes", []):
        ref = scope.get("variablesReference", 0)
        name = scope.get("name", "?")
        result["scopes"][name] = (
            await _dump_ref(dap, ref, max_depth=max_depth) if ref else {}
        )
    return result


# ======================== shutdown jdtls ========================

async def _shutdown_jdtls(jdtls, timeout: float = 5.0) -> None:
    """Гасит JDT LS так, чтобы BaseSubprocessTransport.__del__ не сработал
    после loop.close() (иначе 'RuntimeError: Event loop is closed')."""
    proc = getattr(jdtls, "proc", None)
    if proc is None:
        return
    jdtls.proc = None

    for attr in ("_read_task", "_stderr_task"):
        t = getattr(jdtls, attr, None)
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    stdin = getattr(proc, "stdin", None)
    if stdin is not None and not stdin.is_closing():
        try:
            stdin.close()
        except Exception:
            pass

    try:
        proc.terminate()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()

    transport = getattr(proc, "_transport", None)
    if transport is not None:
        try:
            transport.close()
        except Exception:
            pass


# ======================== публичная функция call ========================

async def call(
    java_path: str | Path,
    stop_line: int,
    *,
    root: str | Path | None = None,
    max_depth: int = 10,
) -> dict:
    """Останавливается на строке stop_line (1-based) в указанном .java
    и возвращает нормализованные переменные верхнего кадра.

    root по умолчанию = папка файла (Path(java_path).parent).
    Аргумент root оставлен для совместимости, но по умолчанию игнорируется.
    """
    src = Path(java_path)
    if not src.is_absolute():
        src = (Path.cwd() / src).resolve()
    if not src.exists():
        raise FileNotFoundError(src)

    root_path = Path(root).resolve() if root else src.parent

    fqcn = detect_main_class(src)

    session = LazyDapSession(root_path)          # прямое создание, не get()
    try:
        frame_id = await session.run(fqcn, src, stop_line)
        return await dump_frame(session.dap, frame_id, max_depth=max_depth)
    finally:
        try:
            await session.close()
        except Exception:
            pass
        await _shutdown_jdtls(session.jdtls)


def call_sync(
    java_path: str | Path,
    stop_line: int,
    *,
    root: str | Path | None = None,
    max_depth: int = 10,
) -> dict:
    """Синхронная обёртка над call()."""
    return asyncio.run(call(java_path, stop_line, root=root, max_depth=max_depth))


# ======================== CLI ========================

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("java_path", help="путь к .java")
    ap.add_argument("stop_line", type=int, help="1-based номер строки останова")
    ap.add_argument("--root", default=None,
                    help="корень workspace (по умолчанию — папка файла)")
    ap.add_argument("--max-depth", type=int, default=10)
    args = ap.parse_args()

    data = await call(
        args.java_path,
        args.stop_line,
        root=args.root,
        max_depth=args.max_depth,
    )
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())