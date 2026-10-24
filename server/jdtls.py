"""Минимальный LSP-клиент для Eclipse JDT LS + Microsoft java-debug plugin."""
import asyncio
import glob
import json
import logging
import os
import shlex
from pathlib import Path

try:
    from .wire import encode, read_message
except ImportError:
    from server.wire import encode, read_message

log = logging.getLogger("jdtls")

TOOLS = Path(__file__).parent.parent / "tools"


def _jdtls_cmd() -> list[str]:
    env = os.environ.get("JDTLS_CMD")
    if env:
        return shlex.split(env, posix=os.name != "nt")

    bin_dir = TOOLS / "jdtls" / "bin"
    if os.name == "nt":
        bat = bin_dir / "jdtls.bat"
        if bat.exists():
            return ["cmd", "/c", str(bat)]
    else:
        sh = bin_dir / "jdtls"
        if sh.exists():
            return [str(sh)]

    raise RuntimeError(
        f"JDT LS не найден в {bin_dir}. Выполните в корне проекта: python setup_tools.py")


def _debug_jar() -> str:
    pattern = os.environ.get("DEBUG_PLUGIN_JAR") or str(TOOLS / "com.microsoft.java.debug.plugin-*.jar")
    jars = sorted(glob.glob(pattern))
    if not jars:
        raise RuntimeError("Плагин java-debug не найден. Выполните в корне проекта: python setup_tools.py")
    return os.path.abspath(jars[-1])


class JdtlsClient:
    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace)
        self._seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._ready = asyncio.Event()
        self.proc = None
        self._read_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        if self.proc:
            return
        cmd = _jdtls_cmd()
        data_dir = os.path.join(self.workspace, ".jdtls-data")
        jar = _debug_jar()
        log.info("JDT LS cmd: %s", cmd)
        log.info("JDT LS debug jar: %s", jar)
        log.info("JDT LS data dir: %s", data_dir)

        self.proc = await asyncio.create_subprocess_exec(
            *cmd, "-data", data_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._read_task = asyncio.create_task(self._read_loop(), name="jdtls-read")
        self._stderr_task = asyncio.create_task(self._drain_stderr(), name="jdtls-stderr")

        uri = Path(self.workspace).as_uri()
        try:
            result = await self.request("initialize", {
                "processId": os.getpid(), "rootUri": uri,
                "workspaceFolders": [{"uri": uri, "name": "workspace"}],
                "capabilities": {},
                "initializationOptions": {
                    "bundles": [jar],
                    "settings": {"java": {"project": {"sourcePaths": ["src"]}}},
                },
            }, timeout=120)
            log.info("JDT LS initialize ok")
            await self._notify("initialized", {})
            try:
                await asyncio.wait_for(self._ready.wait(), 180)
                log.info("JDT LS ready")
            except asyncio.TimeoutError:
                log.warning("JDT LS не прислал ServiceReady/Started за 180с, продолжаем")
        except Exception:
            log.exception("JDT LS initialize failed")
            raise

    async def start_debug_session(self) -> int:
        port = await self.request(
            "workspace/executeCommand",
            {"command": "vscode.java.startDebugSession"},
            timeout=60)
        if not isinstance(port, int):
            raise RuntimeError(f"startDebugSession вернул {port!r}")
        log.info("JDT LS DAP port: %d", port)
        return port

    async def _write(self, msg: dict) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("JDT LS не запущен")
        async with self._write_lock:
            self.proc.stdin.write(encode(msg))
            await self.proc.stdin.drain()

    async def _notify(self, method: str, params: dict) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: dict, timeout: float = 30):
        self._seq += 1
        fut = asyncio.get_running_loop().create_future()
        self._pending[self._seq] = fut
        await self._write({"jsonrpc": "2.0", "id": self._seq, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(self._seq, None)
            raise

    async def _drain_stderr(self) -> None:
        """JDT LS пишет много полезного в stderr — собираем и логируем."""
        try:
            while True:
                line = await self.proc.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    log.info("jdtls: %s", text)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("jdtls stderr drain failed")

    async def did_open(self, file_path: Path) -> None:
        """Сообщает JDT LS, что файл открыт — это триггерит создание invisible project."""
        uri = file_path.as_uri()
        text = file_path.read_text("utf-8", errors="replace")
        await self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "java",
                "version": 1,
                "text": text,
            }
        })
        log.info("JDT LS didOpen: %s", uri)
    
    async def _read_loop(self) -> None:
        try:
            while True:
                msg = await read_message(self.proc.stdout)
                if "method" in msg and "id" in msg:
                    items = msg.get("params", {}).get("items", [])
                    result = ([None] * len(items)
                              if msg["method"] == "workspace/configuration" else None)
                    await self._write({"jsonrpc": "2.0", "id": msg["id"], "result": result})
                elif "method" in msg:
                    if (msg["method"] == "language/status"
                            and msg["params"].get("type") in ("ServiceReady", "Started")):
                        self._ready.set()
                elif "id" in msg:
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(RuntimeError(json.dumps(msg["error"])))
                        else:
                            fut.set_result(msg.get("result"))
        except asyncio.CancelledError:
            raise
        except (EOFError, asyncio.IncompleteReadError):
            log.warning("JDT LS закрыл stdout")
            self._ready.set()
        except Exception:
            log.exception("JDT LS read loop упал")
            self._ready.set()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("JDT LS read loop died"))
            self._pending.clear()