"""
Local HTTP server — receives commands and messages from ExoCore / CLI agents.

Endpoints:
    POST /api/agents/execute_command/   — ExoCore dispatch to Commander
    POST /api/agents/send_message/      — Superior/CLI agent → target pane
    POST /api/agents/session/new/       — Create a new session
    POST /api/agents/session/resume/    — Resume an existing session
    GET  /api/agents/sessions/          — List recent sessions

Route handlers are registered via :meth:`register_route` and dispatched by
path. The legacy ``handler`` constructor param maps to ``execute_command``.
"""
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Optional
from .config import LOCAL_SERVER_HOST, LOCAL_SERVER_PORT


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """Multi-route HTTP handler.

    Route callbacks are set on the CLASS before starting the server.
    Each route key maps to a callable:

    - ``execute_command``: callable(payload: dict) -> dict
    - ``send_message``:    callable(payload: dict) -> dict
    - ``session_new``:     callable(payload: dict) -> dict
    - ``session_resume``:  callable(payload: dict) -> dict
    - ``sessions_list``:   callable() -> dict
    """

    routes: dict = {}

    def do_POST(self):
        path = self.path.rstrip("/")

        route_key = None
        if path == "/api/agents/execute_command":
            route_key = "execute_command"
        elif path == "/api/agents/send_message":
            route_key = "send_message"
        elif path == "/api/agents/session/new":
            route_key = "session_new"
        elif path == "/api/agents/session/resume":
            route_key = "session_resume"
        elif path == "/api/agents/agent/select":
            route_key = "agent_select"
        elif path == "/api/agents/chat":
            route_key = "chat"
        elif path == "/api/agents/sentinel/toggle":
            route_key = "sentinel_toggle"
        elif path == "/api/agents/cache/release":
            route_key = "cache_release"
        else:
            self.send_error(404, "Not Found")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        cb = self.__class__.routes.get(route_key)
        if cb is None:
            self.send_error(404, "No handler registered")
            return

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

        self._send_json(200, result)

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/api/agents/sessions":
            cb = self.__class__.routes.get("sessions_list")
            if cb is None:
                self.send_error(404, "No handler registered")
                return
            try:
                result = cb()
            except Exception as exc:
                self.send_error(500, str(exc))
                return
            self._send_json(200, result)
        else:
            self.send_error(404, "Not Found")

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress HTTP request logging noise


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class LocalCommandServer:
    """Micro HTTP server bound to 127.0.0.1.

    Routes:
        POST /api/agents/execute_command/   — execute_command handler
        POST /api/agents/send_message/      — send_message handler
        POST /api/agents/session/new/       — session_new handler
        POST /api/agents/session/resume/    — session_resume handler
        GET  /api/agents/sessions/          — sessions_list handler
    """

    def __init__(
        self,
        host: str = LOCAL_SERVER_HOST,
        port: int = LOCAL_SERVER_PORT,
        handler: Optional[Callable] = None,
    ):
        self._host = host
        self._port = port
        self._handler = handler  # legacy handler, maps to execute_command
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._pending_routes: dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._httpd is not None:
            return

        # Build route table: constructor handler + any registered routes
        _Handler.routes = {}
        if self._handler:
            _Handler.routes["execute_command"] = self._handler
        for key, cb in self._pending_routes.items():
            _Handler.routes[key] = cb

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

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------

    def register_route(
        self,
        route_key: str,
        callback: Callable,
    ) -> None:
        """Register a route callback.

        Args:
            route_key: One of "execute_command", "send_message",
                       "session_new", "session_resume", "sessions_list".
            callback: Callable matching the route signature.
        """
        self._pending_routes[route_key] = callback

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def address(self) -> str:
        return f"http://{self._host}:{self._port}"
