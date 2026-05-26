import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Optional
from .config import LOCAL_SERVER_HOST, LOCAL_SERVER_PORT


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
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                if inner.path != "/api/agents/execute_command/":
                    inner.send_error(404, "Not Found")
                    return
                content_length = int(inner.headers.get("Content-Length", 0))
                body = inner.rfile.read(content_length)
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    inner.send_error(400, "Invalid JSON")
                    return

                if outer._handler:
                    result = outer._handler(payload)
                else:
                    result = {"status": "received"}

                inner.send_response(200)
                inner.send_header("Content-Type", "application/json")
                inner.end_headers()
                inner.wfile.write(json.dumps(result).encode("utf-8"))

            def do_GET(inner):
                inner.send_error(404, "Not Found")

            def log_message(inner, format, *args):
                pass  # Suppress HTTP request logging noise

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
