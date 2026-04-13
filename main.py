import pystray
from PIL import Image, ImageDraw
import sys
import os
import importlib
import pkgutil
import threading

from core.base_extension import BaseExtension
from config import COLORS, EXOCORE_AGENT_NAME

def _get_extensions() -> list[BaseExtension]:
    extensions = []
    ext_path = os.path.join(os.path.dirname(__file__), "extensions")
    print(f"[ExoCore] Searching for extensions in: {ext_path}")
    
    if not os.path.exists(ext_path):
        print(f"[ExoCore] ERROR: Extensions path does not exist!")
        return []

    for loader, module_name, is_pkg in pkgutil.iter_modules([ext_path]):
        print(f"[ExoCore] Found module candidate: {module_name} (is_pkg: {is_pkg})")
        if is_pkg:
            full_module_name = f"extensions.{module_name}.extension"
            try:
                module = importlib.import_module(full_module_name)
                # Look for classes that inherit from BaseExtension
                found_in_module = False
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, BaseExtension) and attr is not BaseExtension:
                        extensions.append(attr())
                        found_in_module = True
                        print(f"[ExoCore] Successfully loaded extension class: {attr_name} from {module_name}")
                if not found_in_module:
                    print(f"[ExoCore] Warning: No BaseExtension subclass found in {full_module_name}")
            except Exception as e:
                import traceback
                print(f"[ExoCore] Failed to load extension {module_name}: {e}")
                traceback.print_exc()
    return extensions

def _make_tray_icon() -> Image.Image:
    # A more "ExoCore" looking icon: Gold circle on dark gray
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 56, 56], fill=COLORS["panel"])
    d.ellipse([16, 16, 48, 48], outline=COLORS["accent"], width=3)
    return img

def main():
    extensions = _get_extensions()
    
    for ext in extensions:
        print(f"[ExoCore] Starting extension: {ext.name}")
        ext.start()

    def on_quit(icon):
        for ext in extensions:
            ext.stop()
        icon.stop()

    from extensions.clipboard_capture.ui.settings import show_settings

    # Build menu
    menu_items = [
        pystray.MenuItem("Settings...", lambda icon, item: threading.Thread(target=show_settings, daemon=True).start()),
        pystray.Menu.SEPARATOR,
    ]
    for ext in extensions:
        menu_items.extend(ext.get_menu_items())
        menu_items.append(pystray.Menu.SEPARATOR)

    menu_items.append(pystray.MenuItem("Quit", on_quit))

    icon = pystray.Icon(
        "ExoCoreExtension",
        _make_tray_icon(),
        f"ExoCore Extension ({len(extensions)} loaded)",
        menu=pystray.Menu(*menu_items),
    )

    print(f"[ExoCore Extension Hub] Active. Primary Agent: {EXOCORE_AGENT_NAME}")
    icon.run()

if __name__ == "__main__":
    main()
