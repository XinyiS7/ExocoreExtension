"""
Polished prompt overlay with ExoCore visual identity.
Fixed visibility issues by avoiding ttk styles in dark mode.
"""
import os
import tkinter as tk
from tkinter import filedialog
from config import COLORS, FONTS, VAULT_PATH, EXOCORE_AGENT_NAME, AVAILABLE_AGENTS


def ask_prompt(preview_text: str, source_app: str) -> dict | None:
    result = {}

    root = tk.Tk()
    root.title("ExoCore | Context Injection")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg=COLORS["bg"])

    w, h = 560, 480
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Header
    header = tk.Frame(root, bg=COLORS["panel"], height=44)
    header.pack(fill="x")
    tk.Label(header, text="EXOCORE CONTEXT CAPTURE", bg=COLORS["panel"], fg=COLORS["accent"], 
             font=FONTS["title"]).pack(side="left", padx=15, pady=10)

    # Main Container
    main = tk.Frame(root, bg=COLORS["bg"], padx=20, pady=10)
    main.pack(fill="both", expand=True)

    # Source & Preview
    tk.Label(main, text=f"SOURCE: {source_app}", fg=COLORS["muted"], font=FONTS["mono"], bg=COLORS["bg"]).pack(anchor="w")
    
    preview = tk.Text(main, height=5, wrap="word", bg=COLORS["surface"], fg=COLORS["text"], 
                      font=FONTS["sans"], relief="flat", insertbackground=COLORS["accent"], padx=10, pady=5)
    preview.pack(fill="x", pady=(5, 15))
    preview.insert("1.0", preview_text[:400] + ("..." if len(preview_text) > 400 else ""))
    preview.config(state="disabled")

    # Options grid
    grid = tk.Frame(main, bg=COLORS["bg"])
    grid.pack(fill="x")
    grid.columnconfigure(1, weight=1)

    # Row 0: Title
    tk.Label(grid, text="TITLE", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
    
    title_frame = tk.Frame(grid, bg=COLORS["bg"])
    title_frame.grid(row=0, column=1, sticky="ew", pady=4, columnspan=2)
    title_frame.columnconfigure(0, weight=1)

    title_entry = tk.Entry(title_frame, bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], insertbackground=COLORS["accent"], relief="flat")
    title_entry.grid(row=0, column=0, sticky="ew")
    title_entry.insert(0, source_app)

    # Suggestion Listbox (hidden by default)
    suggestion_list = tk.Listbox(root, bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], 
                                 relief="flat", borderwidth=0, highlightthickness=1, highlightcolor=COLORS["accent"])
    
    def update_suggestions(event):
        # Don't trigger on arrow keys
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
            
        text = title_entry.get().strip().lower()
        suggestion_list.delete(0, tk.END)
        
        if not text:
            suggestion_list.place_forget()
            return

        try:
            files = [f[:-3] for f in os.listdir(vault_var.get()) if f.endswith(".md")]
            matches = [f for f in files if f.lower().startswith(text)]
            
            if matches:
                # Position listbox below the title entry
                # Use root-relative coordinates
                x = title_frame.winfo_rootx() - root.winfo_rootx()
                y = title_frame.winfo_rooty() - root.winfo_rooty() + title_frame.winfo_height()
                
                suggestion_list.place(x=x, y=y, width=title_frame.winfo_width(), height=min(100, len(matches) * 20))
                for m in matches[:5]: # Show top 5
                    suggestion_list.insert(tk.END, m)
                suggestion_list.lift()
            else:
                suggestion_list.place_forget()
        except:
            suggestion_list.place_forget()

    def on_suggestion_select(event):
        if suggestion_list.curselection():
            selected = suggestion_list.get(suggestion_list.curselection())
            title_entry.delete(0, tk.END)
            title_entry.insert(0, selected)
            suggestion_list.place_forget()

    def on_down_arrow(event):
        if suggestion_list.winfo_viewable():
            suggestion_list.focus_set()
            suggestion_list.selection_set(0)

    title_entry.bind("<KeyRelease>", update_suggestions)
    title_entry.bind("<FocusOut>", lambda e: root.after(200, suggestion_list.place_forget))
    title_entry.bind("<Down>", on_down_arrow)
    suggestion_list.bind("<Double-Button-1>", on_suggestion_select)
    suggestion_list.bind("<Return>", on_suggestion_select)

    # Row 1: Agent & Note Type
    tk.Label(grid, text="AGENT", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).grid(row=1, column=0, sticky="w", pady=4)
    
    agent_frame = tk.Frame(grid, bg=COLORS["bg"])
    agent_frame.grid(row=1, column=1, sticky="w", pady=4)

    agent_var = tk.StringVar(value=EXOCORE_AGENT_NAME)
    agent_entry = tk.Entry(agent_frame, textvariable=agent_var, bg=COLORS["surface"], fg=COLORS["accent"], font=FONTS["sans"], relief="flat", width=15, insertbackground=COLORS["accent"])
    agent_entry.pack(side="left")

    def set_agent(val):
        agent_var.set(val)

    agent_opt = tk.OptionMenu(agent_frame, agent_var, *AVAILABLE_AGENTS, command=set_agent)
    agent_opt.config(bg=COLORS["panel"], fg=COLORS["text"], font=("Arial", 8), relief="flat", highlightthickness=0, width=1)
    agent_opt["menu"].config(bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"])
    agent_opt.pack(side="left", padx=(2, 0))

    tk.Label(grid, text=" TYPE", anchor="e", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).grid(row=1, column=2, sticky="e", padx=(10, 5))
    note_type_var = tk.StringVar(value="reading_note")
    type_menu = tk.OptionMenu(grid, note_type_var, "reading_note", "debug_session")
    type_menu.config(bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], relief="flat", activebackground=COLORS["panel"], activeforeground=COLORS["accent"], highlightthickness=0)
    type_menu["menu"].config(bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"])
    type_menu.grid(row=1, column=3, sticky="e", pady=4)

    # Row 2: Vault
    tk.Label(grid, text="VAULT", anchor="w", bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).grid(row=2, column=0, sticky="w", pady=4)
    
    vault_frame = tk.Frame(grid, bg=COLORS["bg"])
    vault_frame.grid(row=2, column=1, columnspan=3, sticky="ew", pady=4)
    
    vault_var = tk.StringVar(value=VAULT_PATH)
    vault_entry = tk.Entry(vault_frame, textvariable=vault_var, bg=COLORS["surface"], fg=COLORS["muted"], font=FONTS["sans"], state="readonly", relief="flat")
    vault_entry.pack(side="left", fill="x", expand=True)
    
    def browse_vault():
        path = filedialog.askdirectory(initialdir=vault_var.get())
        if path:
            vault_var.set(path)
            
    tk.Button(vault_frame, text=" ... ", command=browse_vault, bg=COLORS["panel"], fg=COLORS["text"], font=FONTS["sans"], relief="flat").pack(side="left", padx=(5, 0))

    # Prompt
    tk.Label(main, text="INSTRUCTION / PROMPT", fg=COLORS["accent"], font=FONTS["title"], bg=COLORS["bg"]).pack(anchor="w", pady=(15, 0))
    prompt_entry = tk.Text(main, height=3, wrap="word", bg=COLORS["surface"], fg=COLORS["text"], font=FONTS["sans"], insertbackground=COLORS["accent"], relief="flat", padx=10, pady=5)
    prompt_entry.pack(fill="x", pady=5)
    prompt_entry.focus_set()

    # Footer
    footer = tk.Frame(root, bg=COLORS["bg"], pady=10)
    footer.pack(fill="x", side="bottom")

    send_var = tk.BooleanVar(value=True)
    tk.Checkbutton(footer, text="Inject to ExoCore", variable=send_var, bg=COLORS["bg"], fg=COLORS["text"], 
                   font=FONTS["sans"], selectcolor=COLORS["panel"], activebackground=COLORS["bg"], activeforeground=COLORS["accent"]).pack(side="left", padx=20)

    def on_send(event=None):
        result["prompt"] = prompt_entry.get("1.0", "end").strip()
        result["note_type"] = note_type_var.get()
        result["send_to_exocore"] = send_var.get()
        result["custom_title"] = title_entry.get().strip()
        result["vault_path"] = vault_var.get()
        result["agent_name"] = agent_var.get().strip()
        root.destroy()

    def on_cancel(event=None):
        root.destroy()

    tk.Button(footer, text="SEND (Ctrl+Enter)", command=on_send, bg=COLORS["accent"], fg=COLORS["bg"], 
              font=FONTS["title"], relief="flat", activebackground="#fff", padx=10).pack(side="right", padx=20)
    tk.Button(footer, text="CANCEL", command=on_cancel, bg=COLORS["panel"], fg=COLORS["muted"], font=FONTS["sans"], relief="flat").pack(side="right")

    root.bind("<Control-Return>", on_send)
    root.bind("<Escape>", on_cancel)
    root.mainloop()

    return result if result else None
