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


class TestSessionEndpoints:
    """Tests for new session management endpoints."""

    def test_create_session_endpoint(self):
        received = []

        def handler(payload):
            received.append(payload)
            return {"status": "ok", "session_id": "sess_test_001"}

        server = LocalCommandServer(host="127.0.0.1", port=18781, handler=handler)
        server.register_route("session_new", handler)
        server.start()
        time.sleep(0.3)

        try:
            payload = json.dumps({
                "first_user_message": "帮我看看这个报错",
                "metadata": {"pane_id": "2"},
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18781/api/agents/session/new/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["status"] == "ok"
            assert body["session_id"] == "sess_test_001"
            assert len(received) == 1
            assert received[0]["first_user_message"] == "帮我看看这个报错"
        finally:
            server.stop()

    def test_resume_session_endpoint(self):
        received = []

        def handler(payload):
            received.append(payload)
            return {"status": "ok", "session_id": payload.get("session_id"), "messages": []}

        server = LocalCommandServer(host="127.0.0.1", port=18782, handler=handler)
        server.register_route("session_resume", handler)
        server.start()
        time.sleep(0.3)

        try:
            payload = json.dumps({
                "session_id": "sess_abc",
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18782/api/agents/session/resume/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["session_id"] == "sess_abc"
            assert len(received) == 1
            assert received[0]["session_id"] == "sess_abc"
        finally:
            server.stop()

    def test_list_sessions_endpoint(self):
        def handler():
            return {"sessions": [{"session_id": "sess_1", "summary": "test"}]}

        server = LocalCommandServer(host="127.0.0.1", port=18783)
        server.register_route("sessions_list", handler)
        server.start()
        time.sleep(0.3)

        try:
            req = urllib.request.Request(
                "http://127.0.0.1:18783/api/agents/sessions/",
                method="GET",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert "sessions" in body
            assert body["sessions"][0]["session_id"] == "sess_1"
        finally:
            server.stop()

    def test_send_message_endpoint(self):
        received = []

        def handler(payload):
            received.append(payload)
            return {"status": "ok", "routed": True}

        server = LocalCommandServer(host="127.0.0.1", port=18784, handler=handler)
        server.register_route("send_message", handler)
        server.start()
        time.sleep(0.3)

        try:
            payload = json.dumps({
                "from_agent": "G045",
                "target_pane_id": "2",
                "message": "构建完成，可以测试了",
                "msg_type": "notification",
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18784/api/agents/send_message/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["status"] == "ok"
            assert body["routed"] is True
            assert len(received) == 1
            assert received[0]["from_agent"] == "G045"
        finally:
            server.stop()


class TestLocalServerRouting:
    """Verify correct routing to different handlers based on path."""

    def test_different_paths_go_to_different_handlers(self):
        calls = {}

        def send_msg_handler(payload):
            calls["send_message"] = payload
            return {"status": "ok"}

        def session_new_handler(payload):
            calls["session_new"] = payload
            return {"status": "ok"}

        server = LocalCommandServer(host="127.0.0.1", port=18785)
        server.register_route("send_message", send_msg_handler)
        server.register_route("session_new", session_new_handler)
        server.start()
        time.sleep(0.3)

        try:
            # Test send_message routing
            payload1 = json.dumps({
                "from_agent": "test", "target_pane_id": "1", "message": "hi"
            }).encode("utf-8")
            req1 = urllib.request.Request(
                "http://127.0.0.1:18785/api/agents/send_message/",
                data=payload1,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req1, timeout=3)
            assert "send_message" in calls
            assert calls["send_message"]["from_agent"] == "test"

            # Test session_new routing
            payload2 = json.dumps({
                "first_user_message": "hello"
            }).encode("utf-8")
            req2 = urllib.request.Request(
                "http://127.0.0.1:18785/api/agents/session/new/",
                data=payload2,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req2, timeout=3)
            assert "session_new" in calls
            assert calls["session_new"]["first_user_message"] == "hello"

        finally:
            server.stop()
