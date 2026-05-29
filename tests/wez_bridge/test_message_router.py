from unittest.mock import MagicMock, patch
from extensions.wez_bridge.message_router import MessageRouter


class TestMessageRouter:
    def setup_method(self):
        self.mock_cli = MagicMock()
        self.mock_session_manager = MagicMock()
        self.mock_context_builder = MagicMock()
        self.router = MessageRouter(
            cli=self.mock_cli,
            session_manager=self.mock_session_manager,
            context_builder=self.mock_context_builder,
        )

    # --- Route to pane ---

    def test_route_to_pane_sends_text(self):
        self.mock_cli.send_text.return_value = True
        result = self.router.route_to_pane(
            target_pane_id="3",
            message="hello from superior",
            from_agent="G045",
        )
        assert result is True
        self.mock_cli.send_text.assert_called_once()
        call_arg = self.mock_cli.send_text.call_args[0][1]
        assert "hello from superior" in call_arg
        assert "G045" in call_arg

    def test_route_to_pane_returns_false_on_failure(self):
        self.mock_cli.send_text.return_value = False
        result = self.router.route_to_pane(
            target_pane_id="99",
            message="test",
            from_agent="unknown",
        )
        assert result is False

    # --- Route to ExoCore ---

    @patch("extensions.wez_bridge.message_router.requests.post")
    def test_route_to_exocore_builds_context_and_posts(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "reply": "ok",
            "external_session_id": "ext_001",
        }
        mock_post.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.session_id = "sess_test"
        mock_session.summary = "test summary"
        mock_session.metadata = {"pane_id": "2"}

        self.mock_context_builder.build_full_context.return_value = {
            "session_id": "sess_test",
            "summary": "test summary",
            "messages": [],
            "metadata": {},
        }
        self.mock_context_builder.build_inject_payload.return_value = {
            "agent": "Alessandro",
            "captured_text": "...",
            "messages": [],
            "mode": "wez_bridge",
        }

        result = self.router.route_to_exocore(
            session=mock_session,
            trigger="sentinel_alert",
            agent_name="Alessandro",
            host_pane_id="2",
        )
        assert result is True
        self.mock_context_builder.build_full_context.assert_called_once()
        mock_post.assert_called_once()

    @patch("extensions.wez_bridge.message_router.requests.post")
    def test_route_to_exocore_handles_post_failure(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")

        mock_session = MagicMock()
        mock_session.session_id = "sess_test"
        self.mock_context_builder.build_full_context.return_value = {
            "session_id": "sess_test",
            "messages": [],
            "metadata": {},
        }
        self.mock_context_builder.build_inject_payload.return_value = {}

        result = self.router.route_to_exocore(
            session=mock_session,
            trigger="sentinel_alert",
            agent_name="Alessandro",
            host_pane_id="2",
        )
        assert result is False

    @patch("extensions.wez_bridge.message_router.requests.post")
    def test_route_to_exocore_stores_external_session_id(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "reply": "ok",
            "external_session_id": "ext_xyz789",
            "compacted_up_to": 10,
            "cache_reference": "gemini_file_abc",
        }
        mock_post.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.session_id = "sess_test"
        mock_session.summary = "test"
        mock_session.metadata = {}

        self.mock_context_builder.build_full_context.return_value = {
            "session_id": "sess_test",
            "messages": [],
            "metadata": {},
        }
        self.mock_context_builder.build_inject_payload.return_value = {}

        self.router.route_to_exocore(
            session=mock_session,
            trigger="user_message",
            agent_name="Alessandro",
            host_pane_id="2",
        )
        assert mock_session.metadata["external_session_id"] == "ext_xyz789"
        assert mock_session.metadata["compacted_up_to"] == 10
        self.mock_context_builder.sync_cache.assert_called_once_with("gemini_file_abc")

    # --- Display incoming ---

    def test_display_incoming_prints_formatted_message(self, capsys):
        self.router.display_incoming(
            from_agent="G045",
            message="Build completed successfully",
        )
        captured = capsys.readouterr()
        assert "G045" in captured.out
        assert "Build completed successfully" in captured.out
