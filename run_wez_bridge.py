"""
Standalone entry point for WezTerm HITL Bridge.

Boots the wez_bridge without the pystray tray launcher.
Handles SIGINT/SIGTERM for clean shutdown.

Usage:
    python run_wez_bridge.py
    python run_wez_bridge.py --port 18777
    python run_wez_bridge.py --host 0.0.0.0 --port 8777
"""
import argparse
import os
import signal
import sys
import time

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def main():
    parser = argparse.ArgumentParser(description="WezTerm Bridge (standalone)")
    parser.add_argument(
        "--host", default=None,
        help="Override LOCAL_SERVER_HOST (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Override LOCAL_SERVER_PORT (default: 8777)",
    )
    args = parser.parse_args()

    # Apply overrides before importing the extension (config loads eagerly)
    if args.host or args.port is not None:
        from extensions.wez_bridge import config as wb_config
        if args.host:
            wb_config.LOCAL_SERVER_HOST = args.host
        if args.port is not None:
            wb_config.LOCAL_SERVER_PORT = args.port

    from extensions.wez_bridge.extension import WezBridgeExtension

    ext = WezBridgeExtension()
    shutdown = [False]  # list trick for closure mutability

    def _signal_handler(signum, frame):
        if shutdown[0]:
            sys.exit(1)  # second signal = force exit
        shutdown[0] = True
        name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\n[run_wez_bridge] {name} received, shutting down...")
        ext.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        ext.start()
        print(f"[run_wez_bridge] WezTerm Bridge running. Ctrl+C to stop.")
        while not shutdown[0]:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        ext.stop()
        print("[run_wez_bridge] Shutdown complete.")


if __name__ == "__main__":
    main()
