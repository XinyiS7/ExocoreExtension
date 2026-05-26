from abc import ABC, abstractmethod
from pystray import MenuItem
from typing import Callable


class BaseExtension(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the extension."""
        pass

    @abstractmethod
    def start(self):
        """Called when the extension is loaded/started."""
        pass

    @abstractmethod
    def stop(self):
        """Called when the extension is stopped."""
        pass

    @abstractmethod
    def get_menu_items(self) -> list[MenuItem]:
        """Return a list of pystray.MenuItem for the tray icon menu."""
        pass

    def get_settings_ui(self) -> Callable[[], None] | None:
        """Return a callable that launches this extension's settings UI, or None.

        The tray launcher calls the first non-None result to populate the
        top-level 'Settings...' menu item. Extensions that provide settings
        should override this.
        """
        return None

    def get_assigned_agent_name(self, registry=None) -> str:
        """Return the agent name assigned to this extension.

        Resolution order:
        1. Registry override (agent_registry.json extension_assignments)
        2. self.default_agent (set by extension's config.py)
        3. Global default agent (registry.get_default_name())
        """
        if registry is None:
            from core.agent_registry import agent_registry
            registry = agent_registry
        assigned = registry.get_extension_agent(self.name)
        if assigned:
            return assigned
        if hasattr(self, 'default_agent') and self.default_agent:
            return self.default_agent
        return registry.get_default_name()
