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
