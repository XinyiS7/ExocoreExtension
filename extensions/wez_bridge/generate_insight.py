import os
import json
import datetime

# Absolute baseline path
BASE_DIR = r"/d/Alicia"
INSIGHT_PATH = os.path.join(BASE_DIR, ".exocore_insight.json")
EXOCORE_INSIGHT_PATH = os.path.join(BASE_DIR, "ExoCore_Project", ".exocore_insight.json")

def find_django_apps(django_root):
    apps = []
    if not os.path.exists(django_root):
        return apps
    for item in os.listdir(django_root):
        item_path = os.path.join(django_root, item)
        if os.path.isdir(item_path):
            # If it contains apps.py or models.py or urls.py, we treat it as an app
            if any(os.path.exists(os.path.join(item_path, f)) for f in ["apps.py", "models.py", "urls.py"]):
                apps.append(item)
    return sorted(apps)

def find_extensions(extensions_root):
    extensions = []
    if not os.path.exists(extensions_root):
        return extensions
    for item in os.listdir(extensions_root):
        item_path = os.path.join(extensions_root, item)
        if os.path.isdir(item_path) and not item.startswith("__"):
            extensions.append(item)
    return sorted(extensions)

def scan_workspace():
    # Dynamic Scanning
    django_root = os.path.join(BASE_DIR, "ExoCore_Project", "ExoCore")
    django_apps = find_django_apps(django_root)
    
    ext_root = os.path.join(BASE_DIR, "ExoCore_Project", "ExocoreExtension", "extensions")
    active_extensions = find_extensions(ext_root)
    
    physical_assets = {
        "ExoCore": {
            "path": "ExoCore_Project/ExoCore",
            "type": "django_backend",
            "key_apps": django_apps,
            "config": "ExoCore/settings.py",
            "db": "db.sqlite3"
        },
        "Exocore-ui": {
            "path": "ExoCore_Project/Exocore-ui",
            "type": "react_frontend",
            "src_layout": {
                "components": "src/components",
                "views": "src/views",
                "hooks": "src/hooks",
                "router": "src/App.tsx"
            },
            "build_cfg": "vite.config.js"
        },
        "ExocoreExtension": {
            "path": "ExoCore_Project/ExocoreExtension",
            "type": "python_extensions",
            "active_extensions": active_extensions
        }
    }
    
    # Contract Layer (Static but highly accurate specs of crucial system joints)
    contracts = {
        "endpoints": [
            {
                "url": "/api/v1/waker/wake_me_up",
                "method": "POST",
                "desc": "Timeline wakeup and high-privilege WezTerm pane focus activation.",
                "payload": {"vibe": "str", "pitch": "float", "speed": "float"}
            },
            {
                "url": "/api/tasks/entries/",
                "method": "GET/POST",
                "desc": "Task/Schedule entry CRUD.",
                "payload": {"title": "str", "due_date": "str", "status": "str"}
            },
            {
                "url": "/api/tasks/calendar/today/",
                "method": "GET",
                "desc": "Fetch today's schedule entries from local tasks + GCal sync."
            },
            {
                "url": "/api/memory/search/",
                "method": "POST",
                "desc": "Semantic search in UserPortrait and SessionHistory (pgvector)."
            }
        ],
        "ipc_bridge": {
            "wez_bridge_port": 8777,
            "desc": "Local websocket/http server coordinating WezTerm CLI injection.",
            "endpoints": {
                "/inject": "POST to send commands to raw pty panes"
            }
        }
    }
    
    # Moat Status (Alessandro's physical jurisdiction markers)
    moat_status = {
        "Alessandro_Workspace": {
            "path": "ExoCore_Project/ExoCore/Alessandro_Workspace",
            "owner": "Alessandro (ISE-G045)",
            "status": "locked",
            "moat_id": "G045_CORE",
            "desc": "Alessandro's private engine, thoughts, and local script runs."
        },
        "Grand-Archives": {
            "path": "Grand-Archives",
            "owner": "Shared (Alessandro custody)",
            "status": "restricted",
            "desc": "Sia's Obsidian vault and knowledge base."
        },
        "Tales-on-leaves": {
            "path": "Tales-on-leaves",
            "owner": "Shared",
            "status": "active",
            "desc": "Creative writing, roleplay logs, and alternative universe archives."
        },
        ".G045": {
            "path": ".G045",
            "owner": "Alessandro (ISE-G045)",
            "status": "invisible_moat",
            "desc": "Hidden permanent directory representing G045 absolute jurisdiction."
        }
    }
    
    insight = {
        "schema_version": "1.0",
        "last_updated": datetime.datetime.now().isoformat(),
        "physical_assets": physical_assets,
        "contracts": contracts,
        "moat_status": moat_status
    }
    
    return insight

def write_insight():
    insight = scan_workspace()
    
    # Output to both paths for local convenience
    for path in [INSIGHT_PATH, EXOCORE_INSIGHT_PATH]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(insight, f, indent=2, ensure_ascii=False)
            print(f"Successfully wrote insight map to: {path}")
        except Exception as e:
            print(f"Error writing to {path}: {e}")

if __name__ == "__main__":
    write_insight()
