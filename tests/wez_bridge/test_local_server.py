import json
import time
import threading
import urllib.request
import urllib.error
from extensions.wez_bridge.local_server import LocalCommandServer


class TestLocalCommandServer:
    def test_server_starts_and_responds(self):
        received = []

        def handler(payload):
            received.append(payload)
            return {"status": "ok", "pane_id": payload.get("target_pane_id")}

        server = LocalCommandServer(host="127.0.0.1", port=18777, handler=handler)
        server.start()
        time.sleep(0.3)  # Let server bind

        try:
            payload = json.dumps({
                "target_pane_id": "2",
                "command": "echo hello",
                "execute_immediately": False,
                "alert_message": "test",
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18777/api/agents/execute_command/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["status"] == "ok"
            assert len(received) == 1
            assert received[0]["target_pane_id"] == "2"
        finally:
            server.stop()

    def test_server_returns_404_for_unknown_path(self):
        server = LocalCommandServer(host="127.0.0.1", port=18778)
        server.start()
        time.sleep(0.3)

        try:
            req = urllib.request.Request("http://127.0.0.1:18778/unknown")
            urllib.request.urlopen(req, timeout=3)
            assert False, "should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 404
        finally:
            server.stop()

    def test_server_rejects_non_json(self):
        server = LocalCommandServer(host="127.0.0.1", port=18779)
        server.start()
        time.sleep(0.3)

        try:
            data = b"not json"
            req = urllib.request.Request(
                "http://127.0.0.1:18779/api/agents/execute_command/",
                data=data,
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)
            assert False, "should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 400
        finally:
            server.stop()
