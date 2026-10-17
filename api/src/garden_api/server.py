"""HTTP transport: authentication, request limits, keep-alive.

Built on the standard library's http.server. Routing and validation live in
api.py.
"""

from __future__ import annotations

import hmac
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .api import Api, Response

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 4096
IDLE_TIMEOUT_SECONDS = 60


class GardenServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], api: Api, api_key: str = "") -> None:
        super().__init__(address, RequestHandler)
        self.api = api
        self.api_key = api_key


class RequestHandler(BaseHTTPRequestHandler):
    server: GardenServer
    protocol_version = "HTTP/1.1"  # keep-alive: no new TCP handshake per request
    disable_nagle_algorithm = True  # don't delay small responses
    timeout = IDLE_TIMEOUT_SECONDS
    server_version = "garden-api"
    sys_version = ""

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def _handle(self, method: str) -> None:
        if not self._authorized():
            # Unread bodies would desync the connection, so close it instead.
            self.close_connection = True
            return self._send(Response.error(401, "unauthorized"))

        length = self._content_length()
        if length is None:
            self.close_connection = True
            return self._send(Response.error(400, "invalid Content-Length"))
        if length > MAX_BODY_BYTES:
            self.close_connection = True
            return self._send(Response.error(413, "request body too large"))

        body = self.rfile.read(length) if length else b""
        path = urlsplit(self.path).path.rstrip("/") or "/"
        self._send(self.server.api.handle(method, path, body))

    def _authorized(self) -> bool:
        expected = self.server.api_key
        if not expected:
            return True
        provided = self.headers.get("X-API-Key", "")
        return hmac.compare_digest(provided.encode(), expected.encode())

    def _content_length(self) -> int | None:
        raw = self.headers.get("Content-Length", "0")
        if not (raw.isascii() and raw.isdigit()):  # rejects signs, spaces, non-ASCII digits
            return None
        return int(raw)

    def _send(self, response: Response) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("Cache-Control", "no-store")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("%s %s", self.address_string(), format % args)
