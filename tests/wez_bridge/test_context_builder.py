import time
from extensions.wez_bridge.session_manager import SessionManager, Message
from extensions.wez_bridge.context_builder import ContextBuilder


class TestContextBuilder:
    def setup_method(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.sm = SessionManager(session_dir=self.tmpdir)
        self.cb = ContextBuilder()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_build_full_context_has_required_fields(self):
        session = self.sm.create_session("hello world", {"pane_id": "2"})
        self.sm.add_message(
            session.session_id,
            Message(role="agent", content="hi there", metadata={}),
        )
        context = self.cb.build_full_context(session, host_pane_id="2")
        assert "session_id" in context
        assert context["session_id"] == session.session_id
        assert "summary" in context
        assert context["summary"] == session.summary
        assert "messages" in context
        assert len(context["messages"]) == 2
        assert "metadata" in context

    def test_build_full_context_truncates_messages(self):
        session = self.sm.create_session("test", {})
        for i in range(60):
            self.sm.add_message(
                session.session_id,
                Message(role="system", content=f"msg_{i}", metadata={}),
            )
        context = self.cb.build_full_context(session, host_pane_id="1")
        assert len(context["messages"]) <= 50

    def test_build_inject_payload_wraps_context(self):
        session = self.sm.create_session("fix the bug", {"pane_id": "3"})
        context = self.cb.build_full_context(session, host_pane_id="3")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
            mode="wez_bridge",
            custom_title="Multi-turn Session",
        )
        assert payload["agent"] == "Alessandro"
        assert payload["source"] == "terminal"
        assert payload["target_storage"] == "external_session"
        assert payload["mode"] == "wez_bridge"
        # Messages go in dedicated field, not stuffed into captured_text
        assert "messages" in payload
        assert len(payload["messages"]) > 0
        assert payload["messages"][0]["role"] == "user"
        # captured_text is plain text fallback only
        assert "captured_text" in payload
        # metadata is separate, session_id is at context top-level
        assert "metadata" in payload
        assert "pane_id" in payload["metadata"]

    def test_build_inject_payload_includes_pane_id_in_metadata(self):
        session = self.sm.create_session("test", {"pane_id": "7"})
        context = self.cb.build_full_context(session, host_pane_id="7")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
            mode="wez_bridge",
        )
        assert payload["metadata"]["pane_id"] == "7"

    def test_build_inject_payload_sets_mode_to_wez_bridge(self):
        session = self.sm.create_session("test", {})
        context = self.cb.build_full_context(session, host_pane_id="1")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
        )
        assert payload["mode"] == "wez_bridge"

    def test_captured_text_is_plain_fallback(self):
        session = self.sm.create_session("plain text only", {})
        context = self.cb.build_full_context(session, host_pane_id="1")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
        )
        # captured_text should be a plain string, not JSON
        assert isinstance(payload["captured_text"], str)
        assert not payload["captured_text"].startswith("{")

    def test_sync_cache_stores_reference(self):
        self.cb.sync_cache("cache_abc123")
        assert self.cb._cache_reference == "cache_abc123"

    def test_build_full_context_includes_cache_when_present(self):
        self.cb.sync_cache("cache_xyz")
        session = self.sm.create_session("test", {})
        context = self.cb.build_full_context(session, host_pane_id="1")
        assert context["metadata"]["cache_reference"] == "cache_xyz"

    def test_truncate_message_content(self):
        long_text = "x" * 5000
        truncated = self.cb._truncate_content(long_text)
        assert len(truncated) <= 4000
        assert truncated.endswith("...")

    def test_external_session_id_in_payload(self):
        session = self.sm.create_session("test", {"external_session_id": "ext_abc123"})
        context = self.cb.build_full_context(session, host_pane_id="1")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
        )
        assert payload["external_session_id"] == "ext_abc123"
