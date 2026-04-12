import os
import json
import time
import threading

class DSTWatcher:
    """
    Tails the DST log file and extracts state JSON marked with [EXO_STATE].
    """
    def __init__(self, file_path: str, callback):
        self.file_path = file_path
        self.callback = callback
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._tail_log, daemon=True).start()

    def stop(self):
        self.running = False

    def _tail_log(self):
        print(f"[DST Watcher] Monitoring log: {self.file_path}")
        
        # Wait for file to exist
        while self.running and not os.path.exists(self.file_path):
            time.sleep(2)

        with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
            # Go to the end of the file
            f.seek(0, os.SEEK_END)
            print(f"[DST Watcher] Started tailing from offset {f.tell()}")
            
            while self.running:
                line = f.readline()
                if not line:
                    time.sleep(0.5) # Sleep briefly if no new line
                    continue
                
                if "[EXO_STATE]" in line:
                    try:
                        # Extract JSON part
                        json_str = line.split("[EXO_STATE]")[1].strip()
                        data = json.loads(json_str)
                        self.callback(data)
                    except Exception as e:
                        print(f"[DST Watcher] Error parsing log line: {e}")
