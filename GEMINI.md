# ExoCore Extension

A Windows companion application for the ExoCore ecosystem, providing seamless text capture and integration with both the ExoCore backend and Obsidian vaults.

## Project Overview

ExoCore Extension runs as a system tray application that listens for global hotkeys to capture text from the user's current context. It bridges the gap between local applications (PDF readers, browsers, terminals) and the ExoCore LLM agents.

### Key Features
- **Contextual Capture**: Uses Windows UI Automation to extract text from the active window or falls back to clipboard capture.
- **ExoCore Integration**: Sends captured context and user prompts to the ExoCore backend (`G045` preset) for intelligent processing and memory injection.
- **Obsidian Vault Sync**: Can save captures locally as formatted Markdown notes with frontmatter metadata.
- **Interactive UI**: Provides lightweight Tkinter-based overlays for entering prompts and viewing LLM responses.

### Tech Stack
- **Language**: Python 3.10+
- **UI**: `pystray` (System Tray), `tkinter` (Overlays)
- **OS Integration**: `uiautomation`, `pywin32`, `keyboard`, `pyperclip`
- **Networking**: `requests` (REST API)

## Project Structure

```text
/
├── main.py              # Entry point: Tray icon & Hotkey management
├── config.py            # Central configuration (URLs, Paths, Hotkeys)
├── requirements.txt     # Project dependencies
├── capture/             # Text extraction logic
│   ├── clipboard.py     # Clipboard-based capture
│   └── uiautomation_capture.py # Active window text extraction
├── sender/              # Backend communication
│   └── exocore_client.py # Client for ExoCore context injection API
├── ui/                  # User Interface components
│   ├── overlay.py       # Input prompt overlay
│   └── response_popup.py # LLM response display
└── vault/               # Local storage logic
    └── obsidian_writer.py # Markdown note generation for Obsidian
```

## Building and Running

### Prerequisites
- Windows OS (required for UI Automation and Win32 APIs)
- Python 3.10 or higher

### Installation
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure your environment in `config.py`:
   - Set `VAULT_PATH` to your Obsidian vault directory.
   - Set `EXOCORE_BASE_URL` if your backend is not local.

### Execution
Run the application from the root directory:
```bash
python main.py
```
The application will appear in the system tray.

### Usage
- **Ctrl+Alt+A**: Capture selected text via clipboard.
- **Ctrl+Alt+S**: Capture text from the active window using UI Automation.

## Development Conventions

- **Concurrency**: Hotkey handlers are executed in daemon threads to keep the system tray and UI responsive.
- **Error Handling**: Failures in capture or backend communication are logged to the console; the UI should degrade gracefully (e.g., falling back to clipboard if UIA fails).
- **Extensibility**: 
  - New capture methods should be added to the `capture/` directory.
  - New target storages should be added to the `vault/` or a similar directory.
- **Testing**:
  - TODO: Implement a test suite for API communication and note rendering.
  - Manual testing is currently required for UI Automation due to dependency on active window states.
