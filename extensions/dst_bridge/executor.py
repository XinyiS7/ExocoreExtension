import subprocess
import os

class DSTExecutor:
    """
    Executes Lua commands in the DST server.
    Currently assumes we can write to a named pipe or a process's stdin.
    """
    def __init__(self, method="print"):
        self.method = method # "stdin" | "pipe" | "print" (for debug)

    def execute(self, lua_code: str):
        """Send Lua code to game console."""
        print(f"[DST Executor] Executing: {lua_code}")
        
        if self.method == "print":
            return
        
        # Future: Implement real stdin writing here
        # Example for a specific process name or PID
        # os.system(f"echo '{lua_code}' > /proc/<pid>/fd/0") 
