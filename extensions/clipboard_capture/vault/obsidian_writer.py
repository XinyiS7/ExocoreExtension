"""
Write captured context as Markdown notes into the Obsidian vault.
Includes smart filename matching and AI reply appending.
"""
import os
import re
import uuid
from datetime import datetime
from config import VAULT_PATH


NOTE_TYPES = ("reading_note", "debug_session")


def save_note(
    content: str,
    user_prompt: str,
    source_app: str,
    note_type: str = "reading_note",
    custom_title: str | None = None,
    target_path: str | None = None,
) -> str:
    """
    Save the initial capture and prompt to the Obsidian vault.
    If a note with the same title already exists, appends the new capture to it.
    """
    base_path = target_path or VAULT_PATH
    
    if note_type not in NOTE_TYPES:
        note_type = "reading_note"

    timestamp = datetime.now()
    title = custom_title or source_app
    
    # Check for existing file with exact name
    safe_title = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in title).strip()
    safe_title = safe_title.replace(" ", "_")
    filename = f"{safe_title[:40]}.md"
    filepath = os.path.join(base_path, filename)

    try:
        os.makedirs(base_path, exist_ok=True)
        
        if os.path.exists(filepath):
            # Append mode: add a separator and the new capture block
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(f"\n\n---\n### New Capture [{timestamp.strftime('%Y-%m-%d %H:%M:%S')}]\n")
                f.write(f"**Alicia:** {user_prompt}\n\n")
                f.write(f"> {content.strip()}\n")
        else:
            # Create mode
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(_render_note(content, user_prompt, title, note_type, timestamp))
        
        return filepath
    except Exception as e:
        raise IOError(f"Failed to save note to {filepath}: {e}")


def append_reply(filepath: str | None, base_path: str, title: str, agent_name: str, reply: str) -> None:
    """
    Appends the AI's reply to the saved note. 
    If filepath is invalid, attempts to find the latest note matching the title.
    """
    target_file = filepath

    # Fallback: Find the most recent file matching the title
    if not target_file or not os.path.exists(target_file):
        safe_title = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in title).strip()
        safe_title = safe_title.replace(" ", "_")
        base_name = f"{safe_title[:40]}"
        
        latest_file = None
        latest_time = 0
        
        if os.path.exists(base_path):
            for fname in os.listdir(base_path):
                if fname.startswith(base_name) and fname.endswith(".md"):
                    full_p = os.path.join(base_path, fname)
                    mtime = os.path.getmtime(full_p)
                    if mtime > latest_time:
                        latest_time = mtime
                        latest_file = full_p
                        
        target_file = latest_file

    if not target_file:
        raise IOError(f"Could not find a note to append to for title '{title}' in {base_path}")

    try:
        with open(target_file, "a", encoding="utf-8") as f:
            f.write(f"\n### {agent_name} Reply\n{reply}\n\n***\n")
    except Exception as e:
        raise IOError(f"Failed to append reply to {target_file}: {e}")


def _render_note(
    content: str,
    user_prompt: str,
    source_app: str,
    note_type: str,
    ts: datetime,
) -> str:
    tag = "reading-note" if note_type == "reading_note" else "debug-session"
    time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    uid = f"{ts.strftime('%Y%m%d')}-{uuid.uuid4().hex[:4]}"
    
    # Structure: YAML -> Quote -> Time -> User Message
    return f"""---
exocore_uid: {uid}
created: {ts.isoformat()}
modified: {ts.isoformat()}
scope: Alicia
status: active
sync: False
tags: [exocore-extension, {tag}]
source_app: {source_app}
---

# {source_app}

> {content.strip()}

[{time_str}]

**Alicia:** {user_prompt}
"""
