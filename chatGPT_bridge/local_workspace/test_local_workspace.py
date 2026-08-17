"""local_workspace_mcp 单元测试 — monkeypatch ROOT 到临时目录，不碰真实库/真实 root。"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "D:/Alicia/ExoCore_Project/ExoCore-Extension/chatGPT_bridge/local_workspace")

import local_workspace_mcp as lw

tmp = Path(tempfile.mkdtemp(prefix="lw_test_"))
lw.ROOT = tmp

passed = 0
failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")

# --- 路径沙箱 ---
print("== path sandbox ==")
(tmp / "a" / "b").mkdir(parents=True)
(tmp / "alpha.txt").write_text("alpha", encoding="utf-8")
check("resolve relative", lw._resolve("a/b") == (tmp / "a" / "b"))
check("resolve nested rel", lw._resolve("alpha.txt") == (tmp / "alpha.txt"))
try:
    lw._resolve("../escape")
    check("reject .. escape", False)
except ValueError:
    check("reject .. escape", True)
try:
    lw._resolve("C:/Windows/win.ini")
    check("reject abs escape", False)
except ValueError:
    check("reject abs escape", True)
check("resolve abs inside", lw._resolve(str(tmp / "alpha.txt")) == (tmp / "alpha.txt"))

# --- write_file / read_file ---
print("== write/read ==")
r = lw.write_file("notes.txt", "line1\nline2\nline3\n")
check("write created", "created" in r, r)
check("file exists", (tmp / "notes.txt").exists())
r2 = lw.write_file("notes.txt", "only\n")
check("write overwritten", "overwritten" in r2 and r2.count("\n") == 0, r2)
r3 = lw.read_file("notes.txt")
check("read content", "only" in r3 and "1 lines" in r3, r3)
(tmp / "big.txt").write_text("\n".join(f"row{i}" for i in range(3000)), encoding="utf-8")
r4 = lw.read_file("big.txt")
check("read default limit exact-cap", "row1999" in r4 and "row2999" not in r4, r4[-60:])
r4 = lw.read_file("big.txt", limit=5000)
check("read beyond cap truncated", "truncated" in r4 and "row2999" not in r4, r4[-60:])
r5 = lw.read_file("big.txt", tail=True, limit=5)
check("read tail", "row2999" in r5 and "row0" not in r5, r5[-60:])
r6 = lw.read_file("missing.txt")
check("read missing", "not a file" in r6, r6)

# --- edit_file ---
print("== edit_file ==")
(tmp / "code.py").write_text("def foo():\n    return 1\n\ndef bar():\n    x = foo()\n    return x\n", encoding="utf-8")
edits = json.dumps([
    {"old_text": "    return 1", "new_text": "    return 42"},
    {"old_text": "x = foo()", "new_text": "y = foo()"},
])
r = lw.edit_file("code.py", edits)
check("edit multi-hunk ok", "2 hunk(s)" in r, r)
content = (tmp / "code.py").read_text(encoding="utf-8")
check("edit applied", "return 42" in content and "y = foo()" in content)
check("edit kept rest", "def bar()" in content)
r = lw.edit_file("code.py", json.dumps([{"old_text": "def ", "new_text": "async def "}]))
check("edit non-unique rejected", "matched 2 times" in r, r)
check("edit non-unique untouched", "async def foo" not in (tmp / "code.py").read_text(encoding="utf-8"))
r = lw.edit_file("code.py", json.dumps([{"old_text": "zzz_nope", "new_text": "x"}]))
check("edit missing rejected", "not found" in r, r)
r = lw.edit_file("code.py", "not json")
check("edit bad json", "bad JSON" in r, r)
r = lw.edit_file("code.py", json.dumps([
    {"old_text": "    return 42", "new_text": "A"},
    {"old_text": "return 42", "new_text": "B"},
]))
check("edit overlap rejected", "overlap" in r, r)
r = lw.edit_file("../escape.py", json.dumps([{"old_text": "a", "new_text": "b"}]))
check("edit escape rejected", "escapes" in r, r)

# --- bash_readonly ---
print("== bash_readonly ==")
(tmp / "probe.txt").write_text("hello", encoding="utf-8")
r = lw.bash_readonly("pwd")
check("bash cwd locked", str(lw.ROOT).replace("\\\\", "/").replace("\\", "/").lower() in r.lower(), r[:120])
r = lw.bash_readonly("cat probe.txt")
check("bash read works", "hello" in r, r)
r = lw.bash_readonly("rg -n 'row100' big.txt")
check("bash rg works", "row100" in r, r)
r = lw.bash_readonly("sleep 5", timeout=1)
check("bash timeout", "timed out" in r, r)

# --- list_dir ---
print("== list_dir ==")
r = lw.list_dir(".", depth=2)
check("list_dir shows files+dirs", "[f] alpha.txt" in r and "[d] a/" in r, r[:200])
r = lw.list_dir(".", pattern="*.txt")
check("list_dir pattern", "[f] alpha.txt" in r and "code.py" not in r, r[:200])

print(f"\n== {passed} passed, {failed} failed ==")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if failed else 0)