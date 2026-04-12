"""
Response popup — shows G045/Alessandro's reply after ExoCore processes the injection.
Allows saving the reply back to the Obsidian note.
"""
import tkinter as tk
from tkinter import scrolledtext
from typing import Callable
from config import COLORS, FONTS


def show_response(
    captured_text: str,
    user_prompt: str,
    agent_name: str,
    agent_reply: str,
    custom_title: str,
    on_save_callback: Callable[[str], None] | None = None,
) -> None:
    """
    Display the reply.
    """
    root = tk.Tk()
    root.title(f"{agent_name} — {custom_title}")
    root.attributes("-topmost", True)
    root.configure(bg=COLORS["bg"])

    w, h = 640, 520
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Title bar
    header = tk.Frame(root, bg=COLORS["panel"], height=40)
    header.pack(fill="x")
    tk.Label(header, text=f"REPLY FROM {agent_name.upper()}", bg=COLORS["panel"], fg=COLORS["accent"], 
             font=FONTS["title"]).pack(side="left", padx=15, pady=8)

    # Q&A text area
    text_area = scrolledtext.ScrolledText(
        root,
        wrap="word",
        font=FONTS["sans"],
        bg=COLORS["surface"],
        fg=COLORS["text"],
        relief="flat",
        padx=12,
        pady=10,
    )
    text_area.pack(fill="both", expand=True, padx=20, pady=10)

    # Insert text blocks
    _insert_block(text_area, "Quote", captured_text[:600] + ("..." if len(captured_text) > 600 else ""))
    _insert_block(text_area, "Prompt", user_prompt)
    _insert_block(text_area, agent_name, agent_reply)
    text_area.config(state="disabled")

    # Buttons
    footer = tk.Frame(root, bg=COLORS["bg"], pady=10)
    footer.pack(fill="x", side="bottom")

    def copy_reply():
        root.clipboard_clear()
        root.clipboard_append(agent_reply)

    def close_and_save():
        if on_save_callback:
            on_save_callback(agent_reply)
        root.destroy()

    if on_save_callback:
        tk.Button(footer, text="CLOSE & SAVE", command=close_and_save, bg=COLORS["accent"], fg=COLORS["bg"], 
                  font=FONTS["title"], relief="flat", activebackground="#fff", padx=10).pack(side="right", padx=20)
    
    tk.Button(footer, text="COPY REPLY", command=copy_reply, bg=COLORS["panel"], fg=COLORS["text"], 
              font=FONTS["sans"], relief="flat").pack(side="right", padx=(0, 20 if not on_save_callback else 10))
    
    tk.Button(footer, text="DISCARD & CLOSE", command=root.destroy, bg=COLORS["bg"], fg=COLORS["muted"], 
              font=FONTS["sans"], relief="flat").pack(side="left", padx=20)

    root.bind("<Escape>", lambda _: root.destroy())
    root.mainloop()


def _insert_block(widget: scrolledtext.ScrolledText, label: str, content: str) -> None:
    widget.insert("end", f"[{label.upper()}]\n", "label")
    widget.insert("end", content.strip() + "\n\n")
    widget.tag_config("label", font=FONTS["title"], foreground=COLORS["accent"])
