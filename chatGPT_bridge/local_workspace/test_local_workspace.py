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

# --- 路径域转换（Windows ↔ MSYS）---
print("== path domains ==")
check("to_windows msys drive", lw._to_windows("/d/Alicia/x") == "D:\\Alicia\\x")
check("to_windows windows passthrough", lw._to_windows("D:/Alicia/x") == "D:/Alicia/x")
check("to_windows leaves /mnt (no WSL)", lw._to_windows("/mnt/d/Alicia/x") == "/mnt/d/Alicia/x")
check("to_bash windows drive", lw._to_bash(Path("D:/Alicia/x")) == "/d/Alicia/x")
check("to_bash leaves relative", lw._to_bash(Path("a/b.txt")) == "a/b.txt")
check("sh_quote wraps", lw._sh_quote("/d/a b") == "'/d/a b'")
check("sh_quote escapes quote", lw._sh_quote("it's") == "'it'\\''s'")
check("resolve bash-style abs inside", lw._resolve(lw._to_bash(tmp / "alpha.txt")) == (tmp / "alpha.txt"))
try:
    lw._resolve("/d/definitely_outside_root")
    check("resolve bash-style escape rejected", False)
except ValueError:
    check("resolve bash-style escape rejected", True)

# --- bash 解析：绝不落到 WSL 启动器（2026-09-20 根因锁）---
print("== bash resolution (no WSL) ==")
check("wsl launcher detected (System32)", lw._is_wsl_launcher(Path(r"C:\Windows\System32\bash.exe")))
check("wsl launcher detected (WindowsApps)", lw._is_wsl_launcher(Path(r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\bash.exe")))
check("git bash is not flagged", not lw._is_wsl_launcher(Path(r"C:\Program Files\Git\bin\bash.exe")))
bash_exe = lw._resolve_bash_exe()
check("resolved bash exists + not WSL", bash_exe is not None and Path(bash_exe).exists() and not lw._is_wsl_launcher(Path(bash_exe)), str(bash_exe))
check("resolved bash is a Git install", bash_exe is not None and "git" in bash_exe.lower(), str(bash_exe))

# --- bash_readonly ---
print("== bash_readonly ==")
(tmp / "probe.txt").write_text("hello", encoding="utf-8")
r = lw.bash_readonly("pwd")
check("bash cwd locked (bash domain)", lw._to_bash(lw.ROOT).lower() in r.lower(), r[:160])
check("bash cwd not windows form", str(lw.ROOT).replace("\\", "/").lower() not in r.lower(), r[:160])
r = lw.bash_readonly("cat probe.txt")
check("bash read works", "hello" in r, r)
r = lw.bash_readonly("rg -n 'row100' big.txt")
check("bash rg works", "row100" in r, r)
r = lw.bash_readonly("sleep 5", timeout=1)
check("bash timeout", "timed out" in r, r)

# --- ROOT 含空格：cd 引号加固（不靠「路径恰好没空格」侥幸）---
print("== bash_readonly (ROOT with spaces) ==")
tmp_sp = Path(tempfile.mkdtemp(prefix="lw test sp_"))
lw.ROOT = tmp_sp
(tmp_sp / "sp probe.txt").write_text("space-ok", encoding="utf-8")
r = lw.bash_readonly("cat 'sp probe.txt'")
check("bash ROOT with spaces", "space-ok" in r, r[:200])
check("bash spaces no cd error", "No such file or directory" not in r, r[:200])
lw.ROOT = tmp
shutil.rmtree(tmp_sp, ignore_errors=True)

# --- list_dir ---
print("== list_dir ==")
r = lw.list_dir(".", depth=2)
check("list_dir shows files+dirs", "[f] alpha.txt" in r and "[d] a/" in r, r[:200])
r = lw.list_dir(".", pattern="*.txt")
check("list_dir pattern", "[f] alpha.txt" in r and "code.py" not in r, r[:200])

print(f"\n== {passed} passed, {failed} failed ==")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if failed else 0)