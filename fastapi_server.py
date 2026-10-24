import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

try:
    from winpty import PtyProcess
    HAS_PTY = True
except ImportError:
    HAS_PTY = False

app = FastAPI()
IS_WIN = (os.name == "nt")

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.websocket("/ws/{terminal_id}")
async def websocket_endpoint(websocket: WebSocket, terminal_id: str):
    await websocket.accept()
    
    if IS_WIN and HAS_PTY:
        proc = PtyProcess.spawn(["powershell.exe", "-NoLogo", "-NoExit"], cwd="C:\\", dimensions=(30, 120))
    else:
        await websocket.send_text("Терминал доступен только на Windows с pywinpty.\r\n")
        await websocket.close()
        return

    import asyncio
    loop = asyncio.get_event_loop()

    async def pty_to_ws():
        try:
            while proc.isalive():
                data = await loop.run_in_executor(None, proc.read, 1024)
                if data:
                    await websocket.send_text(data)
                await asyncio.sleep(0.01)
        except Exception:
            pass

    async def ws_to_pty():
        try:
            while proc.isalive():
                msg = await websocket.receive_text()
                proc.write(msg)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    read_task = asyncio.create_task(pty_to_ws())
    write_task = asyncio.create_task(ws_to_pty())

    await asyncio.wait([read_task, write_task], return_when=asyncio.FIRST_COMPLETED)

    if proc.isalive():
        proc.terminate()