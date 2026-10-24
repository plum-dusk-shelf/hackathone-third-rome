"""Асинхронный DAP-клиент (Debug Adapter Protocol) поверх TCP.

Только транспорт: кадры, seq, ответы, события. Логика отладки — в java_debug_session.py.
ВАЖНО: обработчик событий вызывается из цикла чтения, поэтому он не должен сам делать
await client.request(...) — для этого запускайте asyncio.create_task(...).
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable

from server.wire import encode, read_message

log = logging.getLogger("dap")


class DapError(Exception):
    def __init__(self, message: str, command: str | None = None, response: dict | None = None):
        super().__init__(message)
        self.command = command
        self.response = response  # полный ответ адаптера (success, message, body…)


class DapClient:
    def __init__(
        self,
        on_event: Callable[[str, dict], Awaitable[None]],
        on_request: Callable[[str, dict], Awaitable[dict]] | None = None,
    ):
        self._on_event = on_event
        self._on_request = on_request
        self._seq = 0
        self._pending: dict[int, tuple[str, asyncio.Future]] = {}
        self._reader = self._writer = None
        self._task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()
        self._closed = False

    async def connect(self, host: str, port: int, timeout: float = 10) -> None:
        self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        self._task = asyncio.create_task(self._read_loop())

    # ---------- отправка ----------
    async def _send(self, command: str, arguments: dict | None) -> tuple[int, asyncio.Future]:
        if self._writer is None or self._closed:
            raise DapError("нет соединения с адаптером", command)
        self._seq += 1
        seq = self._seq
        fut = asyncio.get_running_loop().create_future()
        self._pending[seq] = (command, fut)
        msg: dict[str, Any] = {"seq": seq, "type": "request", "command": command}
        if arguments is not None:
            msg["arguments"] = arguments
        try:
            async with self._write_lock:  # сообщения не перемешиваются при параллельных вызовах
                self._writer.write(encode(msg))
                await self._writer.drain()
        except (ConnectionError, OSError) as e:
            self._pending.pop(seq, None)
            raise DapError(f"ошибка записи: {e}", command) from e
        return seq, fut

    async def send(self, command: str, arguments: dict | None = None) -> asyncio.Future:
        """Отправить запрос и вернуть Future ответа (не ждать). Нужно для launch."""
        return (await self._send(command, arguments))[1]

    async def request(self, command: str, arguments: dict | None = None, timeout: float = 30) -> dict:
        seq, fut = await self._send(command, arguments)
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(seq, None)  # не копим «зависшие» запросы
            raise DapError(f"таймаут {timeout}с", command) from None

    # ---------- приём ----------
    async def _dispatch(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "response":
            entry = self._pending.pop(msg.get("request_seq"), None)
            if not entry:
                return
            command, fut = entry
            if fut.done():
                return
            if msg.get("success"):
                fut.set_result(msg.get("body") or {})
            else:
                fut.set_exception(DapError(msg.get("message") or "запрос отклонён", command, msg))
        elif kind == "event":
            await self._on_event(str(msg.get("event")), msg.get("body") or {})
        elif kind == "request":
            command = str(msg.get("command") or "")
            try:
                if self._on_request is None:
                    raise DapError("unsupported")
                body = await self._on_request(command, msg.get("arguments") or {})
                await self._respond(msg, success=True, body=body)
            except Exception as e:
                await self._respond(msg, success=False, message=str(e))
        else:
            log.warning("неизвестный тип сообщения: %r", msg)

    async def _respond(
        self,
        request: dict,
        *,
        success: bool,
        body: dict | None = None,
        message: str | None = None,
    ) -> None:
        self._seq += 1
        response = {
            "seq": self._seq,
            "type": "response",
            "request_seq": request.get("seq"),
            "command": request.get("command"),
            "success": success,
        }
        if body is not None:
            response["body"] = body
        if message:
            response["message"] = message
        async with self._write_lock:
            self._writer.write(encode(response))
            await self._writer.drain()

    async def _read_loop(self) -> None:
        reason = "адаптер отключился"
        try:
            while True:
                msg = await read_message(self._reader)
                if not isinstance(msg, dict):
                    continue
                try:
                    await self._dispatch(msg)
                except Exception:  # ошибка обработчика не должна убивать чтение
                    log.exception("ошибка обработки сообщения %r", msg.get("event") or msg.get("command"))
        except (EOFError, asyncio.IncompleteReadError, ConnectionError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception as e:  # битый кадр/JSON — поток рассинхронизирован
            reason = f"ошибка протокола: {e}"
            log.exception("read loop")
        finally:
            for command, fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(DapError(reason, command))
            self._pending.clear()
            if not self._closed:
                try:
                    await self._on_event("__closed__", {})
                except Exception:
                    log.exception("on_event(__closed__)")

    async def close(self) -> None:
        self._closed = True
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._writer = self._task = None
