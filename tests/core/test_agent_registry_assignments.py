"""Tests for AgentRegistry extension assignment API and schema migration."""
import json
import os
import tempfile
from core.agent_registry import AgentRegistry


class TestSchemaMigration:
    def test_old_flat_list_is_migrated_to_new_format(self):
        old_data = [
            {"name": "Alessandro", "mode": "lite_private", "model": "gemini-2.5-flash"},
            {"name": "TestAgent", "mode": "zero_tool"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "agent_registry.json")
            with open(old_path, "w", encoding="utf-8") as f:
                json.dump(old_data, f)
            registry = AgentRegistry(storage_dir=tmpdir)
            agents = registry.get_all()
            assert len(agents) == 2
            assert agents[0]["name"] == "Alessandro"
            with open(old_path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            assert isinstance(parsed, dict)
            assert parsed["version"] == 2
            assert len(parsed["agents"]) == 2

    def test_old_format_loads_empty_assignments(self):
        old_data = [{"name": "Alessandro", "mode": "lite_private"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "agent_registry.json")
            with open(old_path, "w", encoding="utf-8") as f:
                json.dump(old_data, f)
            registry = AgentRegistry(storage_dir=tmpdir)
            assert registry.get_all_extension_assignments() == {}

    def test_new_format_loads_directly(self):
        new_data = {
            "version": 2,
            "agents": [{"name": "Alessandro", "mode": "lite_private"}],
            "extension_assignments": {"WezTerm Bridge": "Alessandro"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "agent_registry.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(new_data, f)
            registry = AgentRegistry(storage_dir=tmpdir)
            assert len(registry.get_all()) == 1
            assert registry.get_extension_agent("WezTerm Bridge") == "Alessandro"

    def test_missing_file_seeds_default_agent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            agents = registry.get_all()
            assert len(agents) >= 1
            assert agents[0]["name"] == "Alessandro"
            assert registry.get_all_extension_assignments() == {}


class TestExtensionAssignments:
    def test_get_extension_agent_returns_none_when_not_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            assert registry.get_extension_agent("Unknown Extension") is None

    def test_set_and_get_extension_agent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.set_extension_agent("My Extension", "TestAgent")
            assert registry.get_extension_agent("My Extension") == "TestAgent"

    def test_set_extension_agent_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.set_extension_agent("WezTerm Bridge", "Alessandro")
            registry2 = AgentRegistry(storage_dir=tmpdir)
            assert registry2.get_extension_agent("WezTerm Bridge") == "Alessandro"

    def test_clearing_extension_agent_removes_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.set_extension_agent("Ext A", "Agent1")
            registry.set_extension_agent("Ext A", "")
            assert registry.get_extension_agent("Ext A") is None

    def test_get_all_extension_assignments_returns_copy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.set_extension_agent("Ext A", "Agent1")
            assignments = registry.get_all_extension_assignments()
            assignments["Ext A"] = "hacked"
            assert registry.get_extension_agent("Ext A") == "Agent1"

    def test_existing_public_api_still_works(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.add_agent("Alice", "zero_tool")
            registry.add_agent("Bob", "lite_private")
            names = registry.list_names()
            assert "Alice" in names
            assert "Bob" in names
            assert registry.get_default_name() in names
            assert registry.get_agent_config("Alice")["mode"] == "zero_tool"
            registry.set_default_agent("Alice")
            assert registry.get_default_name() == "Alice"
