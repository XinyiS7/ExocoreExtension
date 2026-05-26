"""
Settings window, launched from the system tray.
Updates config.py directly.
"""
import tkinter as tk
from tkinter import filedialog, messagebox
import re
import os
import sys
from core.agent_registry import agent_registry
from config import COLORS, FONTS
from ..config import VAULT_PATH
from extensions.dst_bridge.config import DST_CLUSTER_PATH

MODE_OPTIONS = ["zero_tool", "lite_private", "special_extend", "grounding"]


def show_settings():
    root = tk.Tk()
    root.title("ExoCore | Settings")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg=COLORS["bg"])

    w, h = 520, 640
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Header
    header = tk.Frame(root, bg=COLORS["panel"], height=40)
    header.pack(fill="x")
    tk.Label(header, text="SETTINGS", bg=COLORS["panel"], fg=COLORS["accent"],
             font=FONTS["title"]).pack(side="left", padx=15, pady=8)

    # Main
    main = tk.Frame(root, bg=COLORS["bg"], padx=20, pady=20)
    main.pack(fill="both", expand=True)

    # Agent Management
    tk.Label(main, text="AGENTS & MODES", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).pack(anchor="w", pady=(0, 5))

    agent_scroll_frame = tk.Frame(main, bg=COLORS["surface"])
    agent_scroll_frame.pack(fill="both", expand=True, pady=(0, 10))

    canvas = tk.Canvas(agent_scroll_frame, bg=COLORS["surface"], highlightthickness=0, height=140)
    scrollbar = tk.Scrollbar(agent_scroll_frame, orient="vertical", command=canvas.yview)
    agent_container = tk.Frame(canvas, bg=COLORS["surface"], padx=5, pady=5)

    agent_container.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=agent_container, anchor="nw", width=460)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Deep-copy so edits don't mutate live config until Save
    current_configs = agent_registry.get_all()

    def refresh_agents():
        for widget in agent_container.winfo_children():
            widget.destroy()

        for i, cfg in enumerate(current_configs):
            f = tk.Frame(agent_container, bg=COLORS["surface"])
            f.pack(fill="x", pady=3)

            tk.Label(f, text=cfg["name"], width=18, anchor="w",
                     bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"]).pack(side="left", padx=(4, 8))

            mv = tk.StringVar(value=cfg.get("mode", "zero_tool"))
            
            # Closure to capture index
            def make_on_change(idx):
                return lambda val: current_configs[idx].update({"mode": val})

            mode_menu = tk.OptionMenu(f, mv, *MODE_OPTIONS, command=make_on_change(i))
            mode_menu.config(bg=COLORS["panel"], fg=COLORS["text"], font=FONTS["sans"],
                             relief="flat", highlightthickness=0, width=12)
            mode_menu["menu"].config(bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"])
            mode_menu.pack(side="left")

            if len(current_configs) > 1:
                btn = tk.Button(f, text=" × ", command=lambda idx=i: delete_agent(idx),
                                bg=COLORS["surface"], fg="#ff6b6b", font=("Arial", 10, "bold"),
                                relief="flat", activebackground=COLORS["panel"])
                btn.pack(side="right", padx=4)

    def delete_agent(idx: int):
        current_configs.pop(idx)
        refresh_agents()

    refresh_agents()

    # Add New Agent
    add_frame = tk.Frame(main, bg=COLORS["surface"], padx=6, pady=6)
    add_frame.pack(fill="x", pady=(0, 10))

    tk.Label(add_frame, text="New", bg=COLORS["surface"], fg=COLORS["muted"],
             font=FONTS["sans"]).pack(side="left", padx=(2, 6))

    new_name_var = tk.StringVar()
    new_name_entry = tk.Entry(add_frame, textvariable=new_name_var, width=14,
                              bg=COLORS["panel"], fg=COLORS["text"],
                              font=FONTS["sans"], relief="flat")
    new_name_entry.pack(side="left", padx=(0, 6))

    new_mode_var = tk.StringVar(value="zero_tool")
    new_mode_menu = tk.OptionMenu(add_frame, new_mode_var, *MODE_OPTIONS)
    new_mode_menu.config(bg=COLORS["panel"], fg=COLORS["text"], font=FONTS["sans"],
                         relief="flat", highlightthickness=0, width=12)
    new_mode_menu["menu"].config(bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"])
    new_mode_menu.pack(side="left", padx=(0, 6))

    def add_agent():
        name = new_name_var.get().strip()
        if not name:
            messagebox.showwarning("Invalid", "Agent name cannot be empty.", parent=root)
            return
        if name in [c["name"] for c in current_configs]:
            messagebox.showwarning("Duplicate", f"Agent '{name}' already exists.", parent=root)
            return
        current_configs.append({"name": name, "mode": new_mode_var.get()})
        new_name_var.set("")
        new_mode_var.set("zero_tool")
        refresh_agents()

    tk.Button(add_frame, text="Add", command=add_agent,
              bg=COLORS["accent"], fg=COLORS["bg"],
              font=FONTS["sans"], relief="flat", padx=10).pack(side="right")

    # Default Agent
    tk.Label(main, text="DEFAULT AGENT", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).pack(anchor="w", pady=(0, 5))
    agent_names = [cfg["name"] for cfg in current_configs]
    default_name = agent_registry.get_default_name()
    default_val = default_name if default_name in agent_names else (agent_names[0] if agent_names else "")
    agent_var = tk.StringVar(value=default_val)
    
    agent_menu_frame = tk.Frame(main, bg=COLORS["bg"])
    agent_menu_frame.pack(fill="x", pady=(0, 15))
    
    agent_menu = tk.OptionMenu(agent_menu_frame, agent_var, *agent_names)
    agent_menu.config(bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], relief="flat", highlightthickness=0)
    agent_menu.pack(fill="x")

    # Vault Selection
    tk.Label(main, text="OBSIDIAN VAULT PATH", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).pack(anchor="w", pady=(0, 5))

    vault_frame = tk.Frame(main, bg=COLORS["bg"])
    vault_frame.pack(fill="x", pady=(0, 10))

    vault_var = tk.StringVar(value=VAULT_PATH)
    vault_entry = tk.Entry(vault_frame, textvariable=vault_var, bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], relief="flat")
    vault_entry.pack(side="left", fill="x", expand=True)

    def browse_vault():
        path = filedialog.askdirectory(initialdir=vault_var.get())
        if path:
            path = path.replace("\\", "/")
            vault_var.set(path)

    tk.Button(vault_frame, text=" ... ", command=browse_vault, bg=COLORS["panel"], fg=COLORS["text"], font=FONTS["sans"], relief="flat").pack(side="left", padx=(5, 0))

    # DST Selection
    tk.Label(main, text="DST CLUSTER PATH", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).pack(anchor="w", pady=(0, 5))

    dst_frame = tk.Frame(main, bg=COLORS["bg"])
    dst_frame.pack(fill="x")

    dst_var = tk.StringVar(value=DST_CLUSTER_PATH)
    dst_entry = tk.Entry(dst_frame, textvariable=dst_var, bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], relief="flat")
    dst_entry.pack(side="left", fill="x", expand=True)

    def browse_dst():
        path = filedialog.askdirectory(initialdir=dst_var.get())
        if path:
            path = path.replace("\\", "/")
            dst_var.set(path)

    tk.Button(dst_frame, text=" ... ", command=browse_dst, bg=COLORS["panel"], fg=COLORS["text"], font=FONTS["sans"], relief="flat").pack(side="left", padx=(5, 0))

    # Save logic
    def on_save():
        new_agent = agent_var.get()
        names_now = [c["name"] for c in current_configs]
        if new_agent not in names_now and names_now:
            new_agent = names_now[0]

        new_vault = vault_var.get().replace("\\", "/")
        new_dst = dst_var.get().replace("\\", "/")

        try:
            # Agent configs — persisted atomically via the registry (no regex)
            agent_registry.replace_all(current_configs)
            agent_registry.set_default_agent(new_agent)

            # Path configs — still edited in config.py (moved to per-extension
            # config files in Phase 2)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = None
            for _ in range(5):
                candidate = os.path.join(base_dir, "config.py")
                if os.path.exists(candidate):
                    config_path = candidate
                    break
                base_dir = os.path.dirname(base_dir)

            if not config_path:
                raise FileNotFoundError("Could not locate config.py")

            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()

            # VAULT_PATH
            if 'VAULT_PATH = r"' in content:
                content = re.sub(r'VAULT_PATH\s*=\s*r".*?"', f'VAULT_PATH = r"{new_vault}"', content)
            else:
                content = re.sub(r'VAULT_PATH\s*=\s*".*?"', f'VAULT_PATH = "{new_vault}"', content)

            # DST_CLUSTER_PATH
            if 'DST_CLUSTER_PATH = r"' in content:
                content = re.sub(r'DST_CLUSTER_PATH\s*=\s*r".*?"', f'DST_CLUSTER_PATH = r"{new_dst}"', content)
            else:
                content = re.sub(r'DST_CLUSTER_PATH\s*=\s*".*?"', f'DST_CLUSTER_PATH = "{new_dst}"', content)

            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)

            messagebox.showinfo("Success", "Settings saved successfully.", parent=root)
            root.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}", parent=root)


    # Footer
    footer = tk.Frame(root, bg=COLORS["bg"], pady=10)
    footer.pack(fill="x", side="bottom")

    tk.Button(footer, text="SAVE", command=on_save, bg=COLORS["accent"], fg=COLORS["bg"],
              font=FONTS["title"], relief="flat", activebackground="#fff", padx=20).pack(side="right", padx=20)
    tk.Button(footer, text="CANCEL", command=root.destroy, bg=COLORS["panel"], fg=COLORS["muted"], font=FONTS["sans"], relief="flat").pack(side="right")

    root.mainloop()
