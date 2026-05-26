import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Optional
from .config import LOCAL_SERVER_HOST, LOCAL_SERVER_PORT


class _Handler(BaseHTTPRequestHandler):
    """HTTP request handler for LocalCommandServer.

    ``handler_callback`` is set by :meth:`LocalCommandServer.start` before
    the server is created so that ``do_POST`` can dispatch to the
    caller-supplied callback without relying on a closure.
    """
    handler_callback = None

    def do_POST(self):
        if self.path != "/api/agents/execute_command/":
            self.send_error(404, "Not Found")
            return
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        cb = self.__class__.handler_callback
        if cb:
            try:
                result = cb(payload)
            except Exception as exc:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": str(exc)}).encode("utf-8")
                )
                return
        else:
            result = {"status": "received"}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode("utf-8"))

    def do_GET(self):
        self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        pass  # Suppress HTTP request logging noise


class LocalCommandServer:
    """Micro HTTP server bound to 127.0.0.1 that receives execute_command
    dispatches from the ExoCore backend.

    Only one endpoint is served:
        POST /api/agents/execute_command/
    """

    def __init__(
        self,
        host: str = LOCAL_SERVER_HOST,
        port: int = LOCAL_SERVER_PORT,
        handler: Optional[Callable] = None,
    ):
        self._host = host
        self._port = port
        self._handler = handler
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._httpd is not None:
            return
        _Handler.handler_callback = self._handler
        self._httpd = HTTPServer((self._host, self._port), _Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="WezBridgeHTTPServer"
        )
        self._thread.start()
        print(f"[LocalCommandServer] Listening on {self._host}:{self._port}")

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    @property
    def address(self) -> str:
        return f"http://{self._host}:{self._port}"
