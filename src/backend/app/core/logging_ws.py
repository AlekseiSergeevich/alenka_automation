import asyncio
import logging
from fastapi import WebSocket

class WSLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.websockets: set[WebSocket] = set()
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    def emit(self, record):
        if not self.websockets or not self.loop:
            return
        try:
            msg = self.format(record)
            for ws in list(self.websockets):
                asyncio.run_coroutine_threadsafe(ws.send_text(msg), self.loop)
        except Exception:
            self.handleError(record)

ws_log_handler = WSLogHandler()
formatter = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')
ws_log_handler.setFormatter(formatter)
# Attach to the root logger to capture uvicorn and httpx logs as well
root_logger = logging.getLogger()
root_logger.addHandler(ws_log_handler)
root_logger.setLevel(logging.INFO)

uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.addHandler(ws_log_handler)
