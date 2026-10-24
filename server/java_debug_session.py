"""Сценарии отладки Java поверх DapClient. Не зависит от веб-фреймворка: вывод идёт через emit()."""
import asyncio
import codecs
import locale
import os
import re
import logging
from pathlib import Path
from typing import Awaitable, Callable

try:
    from .dap_client import DapClient, DapError
    from .jdtls import JdtlsClient
except ImportError:
    from server.dap_client import DapClient, DapError
    from server.jdtls import JdtlsClient

log = logging.getLogger("session")
Emit = Callable[[dict], Awaitable[None]]

def detect_main_class(java_file: Path) -> str:
    text = java_file.read_text("utf-8", errors="replace")
    pkg = re.search(r'^\s*package\s+([\w.]+)\s*;', text, re.M)
    cls = re.search(r'\b(?:public\s+)?(?:final\s+)?class\s+(\w+)', text)
    if not cls:
        raise ValueError(f"в {java_file.name} не найден class")
    return f"{pkg.group(1)}.{cls.group(1)}" if pkg else cls.group(1)

class JavaDebugSession:
    def __init__(self, emit: Emit, root: Path, jdtls: JdtlsClient):
        self._emit = emit
        self.root = root
        self.build = root / "build"
        self.jdtls = jdtls
        self.dap: DapClient | None = None
        self.initialized = asyncio.Event()
        self.thread_id: int | None = None
        self.is_stopped = False
        self.program: asyncio.subprocess.Process | None = None
        self.program_output_task: asyncio.Task | None = None

    async def emit(self, **msg):
        try:
            await self._emit(msg)
        except Exception:
            pass

    def resolve(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if self.root not in p.parents:
            raise ValueError("путь вне рабочей папки")
        return p

    def _resolve_main(self, raw: str) -> str:
        s = raw.strip().replace("\\", "/")
        if s.endswith(".java") or "/" in s:
            if not s.endswith(".java"):
                s += ".java"
            p = self.resolve(s)
            if not p.exists():
                raise ValueError(f"файл не найден: {s}")
            return detect_main_class(p)
        return s
    
    async def on_event(self, event: str, body: dict):
        if event == "initialized":
            self.initialized.set()
        elif event == "stopped":
            self.thread_id = body.get("threadId", self.thread_id)
            self.is_stopped = True
            asyncio.create_task(self.report_stop(body))  # не блокируем цикл чтения
        elif event == "continued":
            self.is_stopped = False
            await self.emit(type="continued")
        elif event == "output":
            await self.emit(type="output", category=body.get("category", "console"), text=body.get("output", ""))
        elif event in ("terminated", "exited", "__closed__"):
            self.is_stopped = False
            await self.emit(type="terminated")

    async def report_stop(self, body: dict):
        try:
            st = await self.dap.request("stackTrace", {"threadId": self.thread_id, "levels": 50})
        except DapError as e:
            await self.emit(type="error", text=f"stackTrace: {e}")
            return
        except Exception as e:
            log.exception("stackTrace failed")
            await self.emit(type="error", text=f"stackTrace: {type(e).__name__}: {e}")
            return

        frames = []
        for f in st.get("stackFrames", []):
            src = f.get("source") or {}
            path = src.get("path") or ""
            if path and path.startswith(str(self.root)):
                try:
                    path = Path(path).relative_to(self.root).as_posix()
                except ValueError:
                    pass
            frames.append({
                "id": f.get("id"),
                "name": f.get("name") or "?",
                "path": path,
                "line": f.get("line") or 0,
            })
        await self.emit(type="stopped", reason=body.get("reason", ""), threadId=self.thread_id, frames=frames)
        if frames and frames[0]["id"] is not None:
            try:
                await self.scopes(frames[0]["id"])
            except Exception as e:
                log.exception("scopes failed")
                await self.emit(type="error", text=f"scopes: {type(e).__name__}: {e}")

    async def scopes(self, frame_id: int):
        r = await self.dap.request("scopes", {"frameId": frame_id})
        await self.emit(type="scopes", frameId=frame_id, scopes=[
            {"name": s["name"], "ref": s["variablesReference"]} for s in r.get("scopes", [])])

    async def on_dap_request(self, command: str, arguments: dict) -> dict:
        if command != "runInTerminal":
            raise ValueError(f"неподдерживаемый DAP reverse request: {command}")
        if self.program and self.program.returncode is None:
            raise RuntimeError("Java-процесс уже запущен")

        args = arguments.get("args")
        if not isinstance(args, list) or not args:
            raise ValueError("runInTerminal не передал команду Java")
        cwd = arguments.get("cwd") or str(self.root)
        env = os.environ.copy()
        env.update(arguments.get("env") or {})

        self.program = await asyncio.create_subprocess_exec(
            *(str(arg) for arg in args),
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.program_output_task = asyncio.create_task(self._read_program_output())
        await self.emit(type="terminalStarted", processId=self.program.pid)
        return {"processId": self.program.pid}

    async def _read_program_output(self):
        process = self.program
        if not process or not process.stdout:
            return
        encoding = locale.getpreferredencoding(False) if os.name == "nt" else "utf-8"
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        pending = ""
        try:
            while True:
                try:
                    data = await asyncio.wait_for(process.stdout.read(1024), timeout=0.3)
                except asyncio.TimeoutError:
                    data = None
                if data is None:
                    if pending:
                        await self.emit(type="output", category="stdout", text=pending)
                        pending = ""
                    continue
                if not data:
                    break
                pending += decoder.decode(data)
                lines = pending.split("\n")
                pending = lines.pop()
                for line in lines:
                    if line.endswith("\r"):
                        line = line[:-1]
                    await self.emit(type="output", category="stdout", text=f"{line}\n")
            pending += decoder.decode(b"", final=True)
            if pending:
                await self.emit(type="output", category="stdout", text=pending)
            await process.wait()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("Java process output reader failed")
            await self.emit(type="error", text=f"ошибка чтения вывода Java: {e}")

    async def send_program_input(self, text: str):
        process = self.program
        if not process or process.returncode is not None or not process.stdin:
            raise RuntimeError("Java-процесс не ожидает ввода")
        process.stdin.write(text.encode("utf-8"))
        await process.stdin.drain()
        await self.emit(
            type="inputAccepted",
            text="Ввод передан Java. Если выполнение остановлено на breakpoint, нажмите «Продолжить».",
        )

    # ---------- жизненный цикл ----------
    def _source_roots(self) -> list[str]:
        ignored = {".git", ".jdtls-data", ".venv", ".venv-new", "build", "dist", "node_modules", "tools", "venv"}
        roots = {self.root}
        for current, dirs, names in os.walk(self.root):
            dirs[:] = [name for name in dirs if name not in ignored]
            if any(name.endswith(".java") for name in names):
                roots.add(Path(current))
        return [str(path) for path in sorted(roots)]

    async def compile(self, main_path: Path) -> bool:
        self.build.mkdir(exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "javac", "-g", "-d", str(self.build), "-sourcepath",
            os.pathsep.join(self._source_roots()), str(main_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        if proc.returncode:
            await self.emit(type="output", category="stderr", text=out.decode(errors="replace"))
        return proc.returncode == 0

    def _main_file(self, original: str, fqcn: str) -> Path | None:
        """Возвращает путь к .java-файлу с main-классом."""
        s = original.strip().replace("\\", "/")
        # 1. Если пришёл путь — используем напрямую
        if s.endswith(".java") or "/" in s:
            if not s.endswith(".java"):
                s += ".java"
            p = self.resolve(s)
            return p if p.exists() else None

        # 2. Если пришёл FQCN — сканируем workspace/src
        simple = fqcn.rsplit(".", 1)[-1] + ".java"
        for p in (self.root / "src").rglob(simple):
            return p
        return None
    
    async def start(self, main_class: str, breakpoints: dict[str, list[int]]):
        await self.stop()
        original = main_class
        try:
            fqcn = self._resolve_main(main_class)
        except Exception as e:
            await self.emit(type="error", text=str(e))
            return await self.emit(type="terminated")
        main_path = self._main_file(original, fqcn)
        if main_path is None:
            await self.emit(type="error", text=f"не найден файл для {fqcn}")
            return await self.emit(type="terminated")
        await self.emit(type="status", text="Компиляция…")
        if not await self.compile(main_path):
            return await self.emit(type="terminated")
        await self.emit(type="status", text=f"Главный класс: {fqcn}")

        await self.emit(type="status", text="Запуск Java Language Server…")
        await self.jdtls.start()

        await self.jdtls.did_open(main_path)
        await asyncio.sleep(1.0)

        port = await self.jdtls.start_debug_session()
        self.initialized.clear()
        self.is_stopped = False
        self.thread_id = None
        self.program = None
        self.dap = DapClient(self.on_event, self.on_dap_request)
        await self.dap.connect("127.0.0.1", port)
        await self.dap.request("initialize", {
            "clientID": "webdebug", "clientName": "WebDebug", "adapterID": "java", "pathFormat": "path",
            "mainClass": fqcn,
            "linesStartAt1": True, "columnsStartAt1": True, "supportsVariableType": True,
            "supportsRunInTerminalRequest": True})
        launch = await self.dap.send("launch", {   # ответ придёт после configurationDone
            "type": "java", "request": "launch", "name": "WebDebug",
            "mainClass": fqcn, "classPaths": [str(self.build)], "cwd": str(self.root),
            "projectName": "jdt.ls-java-project",
            "console": "integratedTerminal", "stopOnEntry": False, "encoding": "UTF-8"})
        await asyncio.wait_for(self.initialized.wait(), 30)  # настройка — только после initialized
        for path, lines in breakpoints.items():
            await self.set_breakpoints(path, lines)
        await self.dap.request("setExceptionBreakpoints", {"filters": []})
        await self.dap.request("configurationDone")
        await asyncio.wait_for(launch, 30)
        await self.emit(type="started")

    async def stop(self):
        self.is_stopped = False
        self.thread_id = None
        dap, self.dap = self.dap, None
        if dap:
            try:
                await dap.request("disconnect", {"terminateDebuggee": True}, timeout=5)
            except Exception:
                pass
            await dap.close()
        process, self.program = self.program, None
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        output_task, self.program_output_task = self.program_output_task, None
        if output_task:
            if not output_task.done():
                output_task.cancel()
            await asyncio.gather(output_task, return_exceptions=True)

    async def set_breakpoints(self, path: str, lines: list[int]):
        r = await self.dap.request("setBreakpoints", {
            "source": {"path": str(self.resolve(path))}, "breakpoints": [{"line": l} for l in lines]})
        await self.emit(type="breakpoints", path=path, items=[
            {"line": b.get("line"), "verified": b.get("verified", False)} for b in r.get("breakpoints", [])])

    # ---------- команды ----------
    async def handle(self, m: dict):
        cmd = m["cmd"]
        if cmd == "start":
            return await self.start(m["mainClass"], m.get("breakpoints", {}))
        if cmd == "stop":
            await self.stop()
            return await self.emit(type="terminated")
        if cmd == "input":
            await self.send_program_input(m.get("text", ""))
            return
        if not self.dap:
            if cmd == "setBreakpoints":
                return  # без сессии точки хранит UI и передаст при start
            return await self.emit(type="error", text="Сессия отладки не запущена")
        tid = {"threadId": self.thread_id}
        if cmd == "setBreakpoints":
            await self.set_breakpoints(m["path"], m["lines"])
        elif cmd in ("continue", "next", "stepIn", "stepOut", "pause"):
            requires_stopped = cmd in ("continue", "next", "stepIn", "stepOut")
            if requires_stopped and not self.is_stopped:
                return await self.emit(
                    type="commandRejected",
                    command=cmd,
                    paused=False,
                    text="Поток Java сейчас выполняется. Дождитесь breakpoint, прежде чем продолжать или делать шаг.",
                )
            if cmd == "pause" and self.is_stopped:
                return await self.emit(
                    type="commandRejected",
                    command=cmd,
                    paused=True,
                    text="Поток Java уже остановлен.",
                )
            if self.thread_id is None:
                return await self.emit(
                    type="commandRejected",
                    command=cmd,
                    paused=self.is_stopped,
                    text="Отладчик ещё не получил поток Java. Дождитесь запуска программы.",
                )
            try:
                await self.dap.request(cmd, tid)
            except DapError as e:
                if cmd in ("continue", "next", "stepIn", "stepOut") and "not suspended" in str(e).lower():
                    self.is_stopped = False
                    return await self.emit(
                        type="commandRejected",
                        command=cmd,
                        paused=False,
                        text=f"{e}. Поток уже выполняется; дождитесь следующей паузы.",
                    )
                raise
            if cmd in ("continue", "next", "stepIn", "stepOut"):
                self.is_stopped = False
        elif cmd == "selectFrame":
            await self.scopes(m["frameId"])
        elif cmd == "variables":
            request_id = m.get("requestId")
            try:
                r = await self.dap.request("variables", {"variablesReference": m["ref"]})
                await self.emit(type="variables", requestId=request_id, ref=m["ref"], items=[
                    {"name": v["name"], "value": v["value"], "vtype": v.get("type", ""),
                     "ref": v.get("variablesReference", 0)} for v in r.get("variables", [])])
            except DapError as e:
                await self.emit(type="variables", requestId=request_id, ref=m["ref"],
                                items=[], error=str(e))
        elif cmd == "evaluate":
            expr = (m.get("expr") or "").strip()
            if not expr:
                await self.emit(type="evaluate", id=m.get("id"), result=None, error="пустое выражение")
                return
            try:
                r = await self.dap.request("evaluate", {
                    "expression": expr, "frameId": m.get("frameId"), "context": m.get("context", "repl")})
                await self.emit(type="evaluate", id=m.get("id"),
                                result=r.get("result", ""), ref=r.get("variablesReference", 0))
            except DapError as e:
                await self.emit(type="evaluate", id=m.get("id"), result=None, error=str(e))
