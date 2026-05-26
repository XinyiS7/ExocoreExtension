import json
from unittest.mock import patch, MagicMock
from core.api_client import ExocoreClient


class TestInjectContextMetadata:
    def test_metadata_field_is_sent(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            client = ExocoreClient(agent_name="Alessandro")
            client.inject_context(
                captured_text="error text",
                user_prompt="",
                capture_method="terminal",
                target_storage="session_memory",
                mode="agent_audit",
                custom_title="Pane 2 Error",
                metadata={
                    "pane_id": "2",
                    "current_dir": "/home/user",
                    "cache_file_reference": "/tmp/cache/pane_2.log",
                },
            )

            call_payload = mock_post.call_args[1]["json"]
            assert "metadata" in call_payload
            assert call_payload["metadata"]["pane_id"] == "2"
            assert call_payload["metadata"]["cache_file_reference"] == "/tmp/cache/pane_2.log"

    def test_metadata_is_optional(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            client = ExocoreClient(agent_name="Alessandro")
            client.inject_context(
                captured_text="hello",
                user_prompt="",
                capture_method="clipboard",
                target_storage="external_session",
                mode="zero_tool",
            )

            call_payload = mock_post.call_args[1]["json"]
            assert "metadata" not in call_payload


class TestChatStream:
    def test_chat_stream_yields_sse_events(self):
        mock_sse_data = [
            'data: {"token": "Hello"}',
            'data: {"token": " world"}',
            'data: {"token": "!"}',
            'data: [DONE]',
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/event-stream"}
        mock_resp.iter_lines.return_value = mock_sse_data

        with patch("requests.post", return_value=mock_resp) as mock_post:
            client = ExocoreClient(agent_name="Alessandro")
            events = list(client.chat_stream(
                session_id="wezterm_session_01",
                host_pane_id="0",
                user_input="fix the git conflict",
            ))

            call_payload = mock_post.call_args[1]["json"]
            assert call_payload["agent"] == "Alessandro"
            assert call_payload["session_id"] == "wezterm_session_01"
            assert call_payload["host_pane_id"] == "0"
            assert len(events) == 3
            assert events[0] == {"token": "Hello"}

    def test_chat_stream_handles_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")

        with patch("requests.post", return_value=mock_resp):
            client = ExocoreClient(agent_name="Alessandro")
            events = list(client.chat_stream(
                session_id="test", host_pane_id="0", user_input="test"
            ))
            assert events == []
