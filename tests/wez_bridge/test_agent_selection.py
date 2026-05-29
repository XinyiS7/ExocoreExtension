import tempfile
from core.agent_registry import AgentRegistry


class TestAgentRegistryID:
    """Tests for agent_id lookup and resolve_agent in AgentRegistry."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = AgentRegistry(storage_dir=self.tmpdir)

    def test_get_by_agent_id_returns_config(self):
        self.registry.add_agent("TestAgent", "zero_tool", agent_id="T001")
        cfg = self.registry.get_by_agent_id("T001")
        assert cfg is not None
        assert cfg["name"] == "TestAgent"
        assert cfg["agent_id"] == "T001"

    def test_get_by_agent_id_returns_none_for_unknown(self):
        assert self.registry.get_by_agent_id("nonexistent") is None

    def test_resolve_agent_by_id(self):
        self.registry.add_agent("TestAgent", "zero_tool", agent_id="G045")
        cfg = self.registry.resolve_agent("G045")
        assert cfg is not None
        assert cfg["name"] == "TestAgent"

    def test_resolve_agent_by_name(self):
        self.registry.add_agent("Alessandro", "lite_private")
        cfg = self.registry.resolve_agent("Alessandro")
        assert cfg is not None
        assert cfg["name"] == "Alessandro"

    def test_resolve_agent_prefers_id_over_name(self):
        self.registry.add_agent("Alice", "zero_tool", agent_id="X001")
        self.registry.add_agent("Bob", "zero_tool")  # no agent_id
        # "X001" as ID matches Alice, even though it could also be a name
        cfg = self.registry.resolve_agent("X001")
        assert cfg is not None
        assert cfg["name"] == "Alice"

    def test_add_agent_with_id_persists(self):
        self.registry.add_agent("PersistTest", "zero_tool", agent_id="P001")
        # Create a new registry from the same dir
        reg2 = AgentRegistry(storage_dir=self.tmpdir)
        cfg = reg2.get_by_agent_id("P001")
        assert cfg is not None
        assert cfg["name"] == "PersistTest"

    def test_legacy_agent_without_id_still_works(self):
        self.registry.add_agent("Legacy", "zero_tool")  # no agent_id
        cfg = self.registry.resolve_agent("Legacy")
        assert cfg is not None
        assert cfg.get("agent_id") is None


class TestAgentSelectEndpoint:
    """Tests for POST /api/agents/agent/select/ endpoint through the extension."""

    def test_agent_select_by_name(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class, \
             patch("core.agent_registry.agent_registry") as mock_registry:
            mock_registry.get_agent_config.return_value = {
                "name": "Alessandro", "agent_id": "G045",
            }
            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb
            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["agent_select"]({
                "agent_name": "Alessandro",
            })
            assert result["status"] == "ok"
            assert result["agent_name"] == "Alessandro"
            assert result["agent_id"] == "G045"
            assert ext._instance_agent_override == "Alessandro"

    def test_agent_select_by_id(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class, \
             patch("core.agent_registry.agent_registry") as mock_registry:
            # Name not found, ID fallback works
            mock_registry.get_agent_config.return_value = {}
            mock_registry.get_by_agent_id.return_value = {
                "name": "Bob", "agent_id": "B002",
            }
            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb
            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["agent_select"]({
                "agent_name": "UnknownName",
                "agent_id": "B002",
            })
            assert result["status"] == "ok"
            assert result["agent_name"] == "Bob"

    def test_agent_select_unknown_returns_error(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class, \
             patch("core.agent_registry.agent_registry") as mock_registry:
            mock_registry.get_agent_config.return_value = {}
            mock_registry.get_by_agent_id.return_value = None
            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb
            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["agent_select"]({
                "agent_id": "NOBODY",
            })
            assert result["status"] == "error"

    def test_agent_select_empty_returns_error(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb
            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["agent_select"]({})
            assert result["status"] == "error"
            assert "agent_name" in result["message"]

    def test_agent_select_per_session_stores_in_metadata(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager") as mock_sm_class, \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class, \
             patch("core.agent_registry.agent_registry") as mock_registry:
            mock_registry.get_agent_config.return_value = {
                "name": "Bob", "agent_id": "B002",
            }
            mock_session = MagicMock()
            mock_session.metadata = {}
            mock_sm = mock_sm_class.return_value
            mock_sm.get_session.return_value = mock_session

            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb
            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["agent_select"]({
                "agent_name": "Bob",
                "session_id": "sess_test",
            })
            assert result["status"] == "ok"
            assert mock_session.metadata["agent_name"] == "Bob"
            # Instance override should NOT be set (session-scoped only)
            assert ext._instance_agent_override is None

    def test_agent_select_unknown_session_returns_error(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager") as mock_sm_class, \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class, \
             patch("core.agent_registry.agent_registry") as mock_registry:
            mock_registry.get_agent_config.return_value = {
                "name": "Alice", "agent_id": "A001",
            }
            mock_sm = mock_sm_class.return_value
            mock_sm.get_session.return_value = None  # session not found

            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb
            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["agent_select"]({
                "agent_name": "Alice",
                "session_id": "nonexistent",
            })
            assert result["status"] == "error"
            assert "Session not found" in result["message"]


class TestAgentResolution:
    """Tests for _resolve_agent_for_session priority chain."""

    def test_resolve_uses_session_override_first(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            ext = WezBridgeExtension()
            ext._instance_agent_override = "instance_agent"

            mock_session = MagicMock()
            mock_session.metadata = {"agent_name": "session_agent"}

            result = ext._resolve_agent_for_session(mock_session)
            assert result == "session_agent"

    def test_resolve_falls_back_to_instance_override(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            ext = WezBridgeExtension()
            ext._instance_agent_override = "instance_agent"

            mock_session = MagicMock()
            mock_session.metadata = {}  # no session override

            result = ext._resolve_agent_for_session(mock_session)
            assert result == "instance_agent"

    def test_resolve_falls_back_to_extension_default(self):
        from unittest.mock import MagicMock, patch
        from extensions.wez_bridge.extension import WezBridgeExtension

        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            ext = WezBridgeExtension()
            ext._instance_agent_override = None

            mock_session = MagicMock()
            mock_session.metadata = {}

            # get_assigned_agent_name uses default_agent = "Alessandro"
            result = ext._resolve_agent_for_session(mock_session)
            assert result == ext.default_agent
