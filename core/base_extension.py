from abc import ABC, abstractmethod
from pystray import MenuItem

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
