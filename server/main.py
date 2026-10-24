"""WebUI-отладчик Java: браузер <-WebSocket-> этот сервер <-DAP-> java-debug <-JDWP-> JVM."""
import asyncio
import os
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    from .java_debug_session import JavaDebugSession, detect_main_class
    from .jdtls import JdtlsClient
except ImportError:
    from java_debug_session import JavaDebugSession, detect_main_class
    from jdtls import JdtlsClient

ROOT = Path(os.environ.get("WORKSPACE", Path(__file__).parent / "workspace")).resolve()
WEB = Path(__file__).parent.parent / "web"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "PUT"],
    allow_headers=["Content-Type"],
)
jdtls = JdtlsClient(str(ROOT))


def safe(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if ROOT not in p.parents:
        raise HTTPException(400, "bad path")
    return p


@app.get("/api/files")
def files():
    ignored = {".git", ".jdtls-data", ".venv", ".venv-new", "build", "dist", "node_modules", "tools", "venv"}
    java_files = []
    for current, dirs, names in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in ignored]
        java_files.extend(
            (Path(current) / name).relative_to(ROOT).as_posix()
            for name in names
            if name.endswith(".java")
        )
    return sorted(java_files)

@app.get("/api/main-class")
def main_class(path: str):
    p = safe(path)
    if not p.suffix == ".java":
        raise HTTPException(400, "не .java")
    try:
        return {
            "fqcn": detect_main_class(p),
            "path": p.relative_to(ROOT).as_posix(),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    
@app.get("/api/file")
def read_file(path: str):
    return {"text": safe(path).read_text("utf-8")}


@app.put("/api/file")
async def write_file(body: dict):
    safe(body["path"]).write_text(body["text"], "utf-8")
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    async def emit(msg: dict):
        await ws.send_json(msg)

    session = JavaDebugSession(emit, ROOT, jdtls)
    try:
        while True:
            msg = await ws.receive_json()
            try:
                await session.handle(msg)
            except Exception as e:  # ошибка одной команды не должна рвать соединение
                await session.emit(type="error", text=f"{type(e).__name__}: {e}")
    except WebSocketDisconnect:
        pass
    finally:
        await session.stop()

@app.on_event("startup")
async def warmup():
    async def _warm():
        try:
            await jdtls.start()
            logging.getLogger("app").info("JDT LS прогрет")
        except Exception:
            logging.getLogger("app").exception("Прогрев JDT LS не удался")
    asyncio.create_task(_warm())

if (WEB / "index.html").is_file():
    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

if WEB.is_dir():
    app.mount("/static", StaticFiles(directory=WEB), name="static")
