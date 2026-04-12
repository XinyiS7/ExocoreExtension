"""
Settings window, launched from the system tray.
Updates config.py directly.
"""
import tkinter as tk
from tkinter import filedialog, messagebox
import re
import os
from config import COLORS, FONTS, VAULT_PATH, EXOCORE_AGENT_NAME, AVAILABLE_AGENTS


def show_settings():
    root = tk.Tk()
    root.title("ExoCore | Settings")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg=COLORS["bg"])

    w, h = 480, 500
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

    # Agent Selection & Management
    tk.Label(main, text="AGENTS", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).pack(anchor="w", pady=(0, 5))
    
    agent_container = tk.Frame(main, bg=COLORS["surface"], padx=5, pady=5)
    agent_container.pack(fill="x", pady=(0, 10))

    current_agents = list(AVAILABLE_AGENTS)
    
    def refresh_agents():
        for widget in agent_container.winfo_children():
            widget.destroy()
        
        for agent in current_agents:
            f = tk.Frame(agent_container, bg=COLORS["surface"])
            f.pack(fill="x", pady=2)
            tk.Label(f, text=agent, bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"]).pack(side="left")
            
            if len(current_agents) > 1: # Prevent deleting last agent
                btn = tk.Button(f, text=" × ", command=lambda a=agent: delete_agent(a), 
                                bg=COLORS["surface"], fg="#ff6b6b", font=("Arial", 10, "bold"), 
                                relief="flat", activebackground=COLORS["panel"])
                btn.pack(side="right")

    def delete_agent(name):
        if name in current_agents:
            current_agents.remove(name)
            refresh_agents()

    refresh_agents()

    # Default Agent
    tk.Label(main, text="DEFAULT AGENT", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).pack(anchor="w", pady=(0, 5))
    agent_var = tk.StringVar(value=EXOCORE_AGENT_NAME if EXOCORE_AGENT_NAME in current_agents else current_agents[0])
    agent_menu = tk.OptionMenu(main, agent_var, *current_agents) # Note: this won't auto-update if list changes, but we'll fix on save
    agent_menu.config(bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], relief="flat", highlightthickness=0)
    agent_menu.pack(fill="x", pady=(0, 15))

    # Vault Selection
    tk.Label(main, text="DEFAULT VAULT PATH", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).pack(anchor="w", pady=(0, 5))
    
    vault_frame = tk.Frame(main, bg=COLORS["bg"])
    vault_frame.pack(fill="x")
    
    vault_var = tk.StringVar(value=VAULT_PATH)
    vault_entry = tk.Entry(vault_frame, textvariable=vault_var, bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], relief="flat")
    vault_entry.pack(side="left", fill="x", expand=True)
    
    def browse_vault():
        path = filedialog.askdirectory(initialdir=vault_var.get())
        if path:
            vault_var.set(path)
            
    tk.Button(vault_frame, text=" ... ", command=browse_vault, bg=COLORS["panel"], fg=COLORS["text"], font=FONTS["sans"], relief="flat").pack(side="left", padx=(5, 0))

    # Save logic
    def on_save():
        new_agent = agent_var.get()
        if new_agent not in current_agents:
            new_agent = current_agents[0]
            
        new_vault = vault_var.get().replace("\\", "\\\\")
        agent_list_str = str(current_agents)
        
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.py")
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            content = re.sub(r'EXOCORE_AGENT_NAME\s*=\s*".*?"', f'EXOCORE_AGENT_NAME = "{new_agent}"', content)
            content = re.sub(r'AVAILABLE_AGENTS\s*=\s*\[.*?\]', f'AVAILABLE_AGENTS = {agent_list_str}', content)
            content = re.sub(r'VAULT_PATH\s*=\s*r".*?"', f'VAULT_PATH = r"{new_vault}"', content)
            
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
