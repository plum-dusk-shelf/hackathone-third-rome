"""example2.py — компилирует Java-код из Python-строки и возвращает переменные кадра в JSON.

Идея:
  * на вход — Java-исходник строкой (+ опционально индекс строки останова или маркер `// BREAK`);
  * файл пишется в workspace/src как <Class>.java (javac требует это для public class);
  * если файл уже существовал — его содержимое сохраняется и восстанавливается после запуска;
  * компилируется ТОЛЬКО main_file, зависимости javac подтягивает через -sourcepath;
  * поднимается JDT LS → DAP-сессия на каждый вызов (без singleton);
  * останавливаемся на точке останова;
  * рекурсивно собираем переменные верхнего кадра и пишем JSON.

Библиотека:
    from example2 import run_java_string_to_json
    path = await run_java_string_to_json(
        root=Path("workspace"),
        source=JAVA_CODE,
        stop_line=5,
        out="vars.json",
    )

CLI:
    python example2.py --root workspace --stop-line 5 --out vars.json <<'JAVA'
    public class Main {
        public static void main(String[] a) {
            int x = 41;
            int y = x + 1;
            System.out.println(y);
        }
    }
    JAVA
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from server.dap_client import DapClient, DapError
from server.jdtls import JdtlsClient

log = logging.getLogger("example")


# ---------- преобразование значений ----------

def _coerce(value: str, vtype: str = "") -> Any:
    """'42' → 42, '"hi"' → 'hi', 'true' → True, 'null' → None."""
    if value is None:
        return None
    v = value.strip()
    if v == "null":
        return None
    if v == "true":
        return True
    if v == "false":
        return False
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
                out.append(await _dump_ref(dap, child, depth=depth + 1,
                    max_depth=max_depth, max_items=max_items, visited=visited))
            else:
                out.append(_coerce(v.get("value", ""), v.get("type", "")))
        return out
    out: dict[str, Any] = {}
    for v in items:
        name = v.get("name", "?")
        child = v.get("variablesReference", 0)
        if child:
            out[name] = await _dump_ref(dap, child, depth=depth + 1,
                max_depth=max_depth, max_items=max_items, visited=visited)
        else:
            out[name] = _coerce(v.get("value", ""), v.get("type", ""))
    return out


async def dump_frame(dap: DapClient, frame_id: int, *, max_depth: int = 10) -> dict:
    r = await dap.request("scopes", {"frameId": frame_id})
    result: dict = {"frameId": frame_id, "scopes": {}}
    for scope in r.get("scopes", []):
        ref = scope.get("variablesReference", 0)
        name = scope.get("name", "?")
        result["scopes"][name] = (
            await _dump_ref(dap, ref, max_depth=max_depth) if ref else {})
    return result


async def dump_frame_to_json(dap: DapClient, frame_id: int, path: str,
                             *, max_depth: int = 10) -> str:
    data = await dump_frame(dap, frame_id, max_depth=max_depth)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p.resolve())


# ---------- разбор Java-строки ----------

_BREAK_MARK = re.compile(r"//\s*(?:BREAK|breakpoint)\b", re.IGNORECASE)

# бэкапы перезаписанных пользовательских файлов: путь → исходное содержимое (или None)
_BACKUPS: dict[Path, bytes | None] = {}


def _find_package(src: str) -> str | None:
    m = re.search(r'^\s*package\s+([\w.]+)\s*;', src, re.M)
    return m.group(1) if m else None


def _find_public_class(src: str) -> str | None:
    m = re.search(r'\bpublic\s+(?:final\s+)?class\s+(\w+)', src)
    if m:
        return m.group(1)
    m = re.search(r'\bclass\s+(\w+)', src)
    return m.group(1) if m else None


def _detect_stop_line(src: str) -> int | None:
    for i, line in enumerate(src.splitlines(), 1):
        if _BREAK_MARK.search(line):
            return i
    return None


def _strip_break_markers(src: str) -> str:
    return "\n".join(
        _BREAK_MARK.sub("", line) if _BREAK_MARK.search(line) else line
        for line in src.splitlines())


# ---------- DAP-сессия (без singleton) ----------

class LazyDapSession:
    """Один JDT LS + один DAP. Создаётся на каждый asyncio.run().

    ВАЖНО: не singleton. asyncio.Event/Lock привязаны к конкретному loop;
    при повторном asyncio.run() старые Event'ы падают с
    'is bound to a different event loop'. Поэтому каждый call() создаёт
    новый LazyDapSession в текущем loop.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.jdtls = JdtlsClient(str(self.root))
        self.dap: DapClient | None = None
        self.thread_id: int | None = None
        self.frame_id: int | None = None
        self._initialized = asyncio.Event()
        self._stopped = asyncio.Event()

    async def _on_event(self, event: str, body: dict) -> None:
        if event == "initialized":
            self._initialized.set()
        elif event == "stopped":
            self.thread_id = body.get("threadId", self.thread_id)
            self._stopped.set()
        elif event == "terminated":
            log.warning("DAP: terminated")
            self._stopped.set()

    async def _compile(self, main_file: Path) -> None:
        """Компилирует ТОЛЬКО main_file. Зависимости javac подтянет
        через -sourcepath от self.root (каталог main_file)."""
        build = self.root / "build"
        build.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            "javac", "-g", "-d", str(build),
            "-sourcepath", str(self.root),
            str(main_file),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        if proc.returncode:
            raise RuntimeError("javac failed:\n" + out.decode("utf-8", errors="replace"))

    async def run(self, fqcn: str, main_file: Path, stop_line: int | None) -> int:
        """Компилирует, стартует JDT LS/DAP, ставит точку останова, ждёт stopped,
        возвращает frame_id верхнего кадра."""
        await self._compile(main_file)
        await self.jdtls.start()
        await self.jdtls.did_open(main_file)
        await asyncio.sleep(1.0)

        port = await self.jdtls.start_debug_session()
        self._initialized.clear()
        self._stopped.clear()
        self.dap = DapClient(self._on_event)
        await self.dap.connect("127.0.0.1", port)
        await self.dap.request("initialize", {
            "clientID": "example", "clientName": "example",
            "adapterID": "java", "pathFormat": "path",
            "mainClass": fqcn,
            "linesStartAt1": True, "columnsStartAt1": True,
            "supportsVariableType": True, "supportsRunInTerminalRequest": False,
        })
        launch_fut = await self.dap.send("launch", {
            "type": "java", "request": "launch", "name": "example",
            "mainClass": fqcn, "classPaths": [str(self.root / "build")],
            "cwd": str(self.root), "projectName": "jdt.ls-java-project",
            "console": "internalConsole",
            "stopOnEntry": stop_line is None,
            "encoding": "UTF-8",
        })
        await asyncio.wait_for(self._initialized.wait(), 30)
        if stop_line is not None:
            await self.dap.request("setBreakpoints", {
                "source": {"path": str(main_file)},
                "breakpoints": [{"line": stop_line}]})
        await self.dap.request("setExceptionBreakpoints", {"filters": []})
        await self.dap.request("configurationDone")
        await asyncio.wait_for(launch_fut, 30)

        await asyncio.wait_for(self._stopped.wait(), 60)
        if self.dap is None:
            raise RuntimeError("DAP закрылся до остановки")
        st = await self.dap.request("stackTrace", {
            "threadId": self.thread_id, "levels": 50})
        frames = st.get("stackTrace", st.get("stackFrames", []))
        if not frames:
            raise RuntimeError("stackTrace пуст — программа завершилась?")
        self.frame_id = frames[0]["id"]
        return self.frame_id

    async def close(self) -> None:
        if self.dap:
            try:
                await self.dap.request("disconnect", {"terminateDebuggee": True}, timeout=5)
            except Exception:
                pass
            await self.dap.close()
            self.dap = None


# ---------- главный вход ----------

def _materialize_source(root: Path, source: str) -> tuple[Path, str, int | None]:
    """Пишет исходник в src/, возвращает (путь, fqcn, stop_line)."""
    package = _find_package(source)
    cls = _find_public_class(source)
    if not cls:
        raise ValueError("в исходнике не найден class")

    stop_line = _detect_stop_line(source)
    cleaned = _strip_break_markers(source) if stop_line else source

    rel_dir = Path(*package.split(".")) if package else Path()
    target = root / "src" / rel_dir / f"{cls}.java"
    target.parent.mkdir(parents=True, exist_ok=True)

    _BACKUPS[target] = target.read_bytes() if target.exists() else None
    target.write_text(cleaned, encoding="utf-8")

    fqcn = f"{package}.{cls}" if package else cls
    return target, fqcn, stop_line


async def run_java_string_to_json(
    root: Path | str,
    source: str,
    *,
    stop_line: int | None = None,
    out: str | Path = "variables.json",
    max_depth: int = 10,
) -> str:
    """Компилирует переданный Java-исходник, останавливается на точке останова
    (явный stop_line → маркер `// BREAK` → вход в main) и пишет переменные в JSON."""
    root = Path(root).resolve()
    main_file, fqcn, detected = _materialize_source(root, source)
    stop = stop_line if stop_line is not None else detected

    session = LazyDapSession(root)          # прямое создание, не get()
    try:
        frame_id = await session.run(fqcn, main_file, stop)
        return await dump_frame_to_json(session.dap, frame_id, str(out),
                                        max_depth=max_depth)
    finally:
        try:
            await session.close()
        except Exception:
            pass
        backup = _BACKUPS.pop(main_file, None)
        try:
            if backup is None:
                main_file.unlink()
            else:
                main_file.write_bytes(backup)
        except OSError:
            pass


# ---------- CLI ----------

async def _main_cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="workspace", type=Path)
    ap.add_argument("--stop-line", type=int, default=None,
                    help="1-based индекс строки останова (иначе // BREAK, иначе вход в main)")
    ap.add_argument("--out", default="variables.json")
    ap.add_argument("src_file", nargs="?", help="файл с Java-кодом (по умолчанию stdin)")
    args = ap.parse_args()

    if args.src_file:
        source = Path(args.src_file).read_text("utf-8")
    else:
        source = sys.stdin.read()
    if not source.strip():
        print("пустой исходник", file=sys.stderr)
        return 2

    path = await run_java_string_to_json(
        args.root, source, stop_line=args.stop_line, out=args.out)
    print(f"saved: {path}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(asyncio.run(_main_cli()))