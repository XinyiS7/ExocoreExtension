"""Tests for BaseExtension.get_assigned_agent_name()."""
from core.base_extension import BaseExtension


class FakeRegistry:
    def __init__(self, assignments=None, default_name="Alessandro"):
        self._assignments = assignments or {}
        self._default_name = default_name

    def get_extension_agent(self, name):
        return self._assignments.get(name)

    def get_default_name(self):
        return self._default_name


class TestGetAssignedAgentName:
    def test_returns_explicit_assignment_when_set(self):
        class TestExt(BaseExtension):
            @property
            def name(self):
                return "Test Extension"
            def start(self):
                pass
            def stop(self):
                pass
            def get_menu_items(self):
                return []

        ext = TestExt()
        registry = FakeRegistry(assignments={"Test Extension": "Bob"})
        assert ext.get_assigned_agent_name(registry) == "Bob"

    def test_falls_back_to_default_agent_attr_when_no_registry_override(self):
        class TestExt(BaseExtension):
            @property
            def name(self):
                return "My Extension"
            def start(self):
                pass
            def stop(self):
                pass
            def get_menu_items(self):
                return []

        ext = TestExt()
        ext.default_agent = "Charlie"
        registry = FakeRegistry(default_name="Alice")
        assert ext.get_assigned_agent_name(registry) == "Charlie"

    def test_falls_back_to_global_default_when_no_assignment_or_attr(self):
        class TestExt(BaseExtension):
            @property
            def name(self):
                return "Unknown Extension"
            def start(self):
                pass
            def stop(self):
                pass
            def get_menu_items(self):
                return []

        ext = TestExt()
        registry = FakeRegistry(default_name="Alice")
        assert ext.get_assigned_agent_name(registry) == "Alice"

    def test_explicit_assignment_wins_over_default_agent_attr(self):
        class TestExt(BaseExtension):
            @property
            def name(self):
                return "Test Extension"
            def start(self):
                pass
            def stop(self):
                pass
            def get_menu_items(self):
                return []

        ext = TestExt()
        ext.default_agent = "ConfigDefault"
        registry = FakeRegistry(
            assignments={"Test Extension": "RegistryOverride"},
            default_name="GlobalDefault"
        )
        assert ext.get_assigned_agent_name(registry) == "RegistryOverride"
