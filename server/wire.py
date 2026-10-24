"""Общий формат кадров DAP/LSP: заголовки Content-Length + JSON."""
import json
import logging

log = logging.getLogger("wire")


def encode(msg: dict) -> bytes:
    body = json.dumps(msg, separators=(",", ":")).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


async def read_message(reader) -> dict:
    length = None
    while True:
        raw = await reader.readline()
        if not raw:
            raise EOFError("stream closed")
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            # JDT LS на русской Windows пишет лог-строки в stdout в cp1251.
            # Это шум, не часть LSP-фрейма — пропускаем.
            log.warning("LSP: пропущена не-UTF8 строка: %r", raw[:120])
            continue
        if not text:
            # пустая строка = конец заголовков. Если Content-Length ещё не нашли,
            # это шум до первого фрейма — ищем дальше.
            if length is None:
                continue
            break
        key, _, val = text.partition(":")
        if key.strip().lower() == "content-length":
            try:
                length = int(val.strip())
            except ValueError:
                log.warning("LSP: битый Content-Length: %r", text)
                length = None
    body = await reader.readexactly(length)
    return json.loads(body)