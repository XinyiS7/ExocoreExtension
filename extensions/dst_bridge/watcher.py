import os
import time
import threading


class DSTWatcher:
    """
    Tails a DST log file and invokes line_callback for each matching line.

    file_path: str or callable() -> str
        If callable, it is re-evaluated whenever the monitored file disappears
        (e.g. save reload, server restart), enabling dynamic path tracking.

    line_callback: callable(str) -> None
        Receives each raw line that passes line_filter.

    line_filter: callable(str) -> bool  (optional)
        Only lines for which this returns True are forwarded to line_callback.
        Defaults to accepting every non-empty line.

    name: str
        Label used in log output.
    """

    def __init__(self, file_path, line_callback, line_filter=None, name="DSTWatcher"):
        self._path_resolver = file_path if callable(file_path) else (lambda p=file_path: p)
        self.line_callback = line_callback
        self.line_filter = line_filter or (lambda line: bool(line.strip()))
        self.name = name
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._tail_log, daemon=True, name=self.name).start()

    def stop(self):
        self.running = False

    def _tail_log(self):
        while self.running:
            path = self._path_resolver()
            print(f"[{self.name}] Monitoring: {path}")

            # Wait for file to exist, re-resolving path each cycle in case save changes
            while self.running and not os.path.exists(path):
                time.sleep(2)
                path = self._path_resolver()

            if not self.running:
                break

            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(0, os.SEEK_END)
                    print(f"[{self.name}] Tailing from offset {f.tell()}")

                    while self.running:
                        line = f.readline()
                        if not line:
                            # File may have been rotated / save reloaded
                            if not os.path.exists(path):
                                print(f"[{self.name}] File gone — re-resolving path...")
                                break
                            # Detect truncation: DST recreates server_log.txt on server restart.
                            # If the on-disk size is smaller than our read position, the file
                            # was replaced — break to re-open from the new end.
                            try:
                                if os.path.getsize(path) < f.tell():
                                    print(f"[{self.name}] File truncated (server restart?) — re-opening...")
                                    break
                            except OSError:
                                break
                            # Windows: seek to current position to flush read cache,
                            # otherwise new writes from another process won't be seen.
                            f.seek(f.tell())
                            time.sleep(0.5)
                            continue

                        if self.line_filter(line):
                            try:
                                self.line_callback(line)
                            except Exception as e:
                                print(f"[{self.name}] Callback error: {e}")
            except Exception as e:
                print(f"[{self.name}] Read error: {e}")
                time.sleep(2)
