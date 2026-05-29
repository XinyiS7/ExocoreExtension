import os
import time
import tempfile
from extensions.wez_bridge.session_manager import (
    SessionManager, Session, Message,
)


class TestSessionManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sm = SessionManager(session_dir=self.tmpdir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- Session creation ---

    def test_create_session_returns_session(self):
        session = self.sm.create_session(
            first_user_message="帮我看看这个数据库报错是什么原因",
            metadata={"pane_id": "2", "agent_name": "Alessandro"},
        )
        assert isinstance(session, Session)
        assert session.session_id.startswith("sess_")
        assert len(session.messages) == 1
        assert session.messages[0].role == "user"

    def test_summary_is_first_20_chars_of_first_message(self):
        session = self.sm.create_session(
            first_user_message="12345678901234567890extra",
            metadata={},
        )
        assert session.summary == "12345678901234567890"
        assert len(session.summary) <= 20

    def test_summary_handles_short_message(self):
        session = self.sm.create_session(
            first_user_message="hi",
            metadata={},
        )
        assert session.summary == "hi"

    def test_summary_strips_whitespace(self):
        session = self.sm.create_session(
            first_user_message="   short message with spaces   ",
            metadata={},
        )
        assert session.summary == "short message with s"

    # --- Add message ---

    def test_add_message_appends_to_session(self):
        session = self.sm.create_session("hello world", {})
        self.sm.add_message(
            session.session_id,
            Message(role="agent", content="你好！有什么可以帮助你的？", metadata={}),
        )
        got = self.sm.get_session(session.session_id)
        assert len(got.messages) == 2
        assert got.messages[1].role == "agent"

    def test_add_message_updates_last_active(self):
        session = self.sm.create_session("hello", {})
        before = session.last_active
        time.sleep(0.01)
        self.sm.add_message(
            session.session_id,
            Message(role="system", content="done", metadata={}),
        )
        after = self.sm.get_session(session.session_id).last_active
        assert after > before

    def test_add_message_to_unknown_session_raises(self):
        try:
            self.sm.add_message(
                "nonexistent",
                Message(role="user", content="hi", metadata={}),
            )
            assert False, "should have raised"
        except KeyError:
            pass

    # --- List sessions ---

    def test_list_sessions_returns_recent_only(self):
        s1 = self.sm.create_session("first message here", {"pane_id": "1"})
        s2 = self.sm.create_session("second message goes", {"pane_id": "2"})
        sessions = self.sm.list_sessions()
        ids = [s.session_id for s in sessions]
        assert s1.session_id in ids
        assert s2.session_id in ids

    def test_list_sessions_sorted_by_last_active_desc(self):
        s1 = self.sm.create_session("aaa", {})
        time.sleep(0.02)
        s2 = self.sm.create_session("bbb", {})
        sessions = self.sm.list_sessions()
        assert sessions[0].session_id == s2.session_id

    # --- Cleanup (48h TTL) ---

    def test_cleanup_removes_expired_sessions(self):
        session = self.sm.create_session("test", {})
        # Artificially age the session
        session.last_active = time.time() - 200_000  # ~55h ago
        session.created_at = time.time() - 200_000
        self.sm._save_session(session)

        removed = self.sm.cleanup_expired()
        assert removed >= 1
        assert self.sm.get_session(session.session_id) is None

    def test_cleanup_keeps_recent_sessions(self):
        session = self.sm.create_session("test", {})
        removed = self.sm.cleanup_expired()
        assert removed == 0
        assert self.sm.get_session(session.session_id) is not None

    # --- Delete session ---

    def test_delete_session_removes_from_memory_and_disk(self):
        session = self.sm.create_session("test", {})
        self.sm.delete_session(session.session_id)
        assert self.sm.get_session(session.session_id) is None
        # File should also be gone
        import glob
        files = glob.glob(os.path.join(self.tmpdir, f"*{session.session_id}*"))
        assert len(files) == 0

    # --- Persistence ---

    def test_persist_and_restore(self):
        s1 = self.sm.create_session("hello world test message", {"pane_id": "3"})
        self.sm.add_message(
            s1.session_id,
            Message(role="agent", content="reply text", metadata={}),
        )
        sid = s1.session_id

        # Create a new SessionManager pointing to the same dir
        sm2 = SessionManager(session_dir=self.tmpdir)
        restored = sm2.get_session(sid)
        assert restored is not None
        assert restored.summary == s1.summary
        assert len(restored.messages) == 2
        assert restored.messages[1].content == "reply text"

    def test_ensure_session_dir_created(self):
        new_dir = os.path.join(self.tmpdir, "nested", "sessions")
        sm = SessionManager(session_dir=new_dir)
        session = sm.create_session("test", {})
        assert os.path.exists(new_dir)


class TestMessage:
    def test_message_has_timestamp_by_default(self):
        msg = Message(role="user", content="hi", metadata={})
        assert msg.timestamp > 0
        assert msg.timestamp <= time.time()

    def test_message_to_dict_and_back(self):
        msg = Message(role="sentinel", content="alert!", metadata={"pane_id": "2"})
        d = msg.to_dict()
        restored = Message.from_dict(d)
        assert restored.role == msg.role
        assert restored.content == msg.content
        assert restored.metadata == msg.metadata
        assert restored.timestamp == msg.timestamp
