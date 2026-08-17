"""
local_workspace_mcp.py — 文件面 MCP server：给 ChatGPT 端索哥的受控文件工具集。

- read_file(path, offset=1, limit=2000)      读文件（UTF-8，可带行号）
- write_file(path, content)                  全量写 / 新建（UTF-8，自动建父目录）
- edit_file(path, edits_json)                精确文本替换，一次多块，全成或不动
- bash_readonly(cmd, timeout=30)             只读契约 bash（cd ROOT && cmd）
- list_dir(path, pattern=None, depth=1)      列目录

设计原则：
- 无任意命令变更能力：bash 只读契约，执行类命令一律走 wezterm pane
- 路径沙箱：所有 path 参数 resolve 后必须落在 ROOT 内（.. / 绝对路径逃逸直接拒绝）
- 写必须走工具（write_file / edit_file），不存在第二个写入口
- 与 wezterm_mcp.py 同款 mcp 2.0.0 MCPServer（原生兼容 OpenAI connector 的
  server/discover 动态注册，见 chatGPT_bridge/README.md「已知坑」）
- ROOT 来自 --root argv，绝不依赖进程 cwd（tunnel-client 拉起时 cwd 不可控）

运行：<wezterm-mcp-bridge venv>/python.exe local_workspace_mcp.py
      --root D:/Alicia/ExoCore_Project
"""
import argparse
import fnmatch
import json
import os
import shutil
import subprocess
from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer(name="local-workspace", version="1.0.0")

DEFAULT_ROOT = "D:/Alicia/ExoCore_Project"
GIT_BASH = r"C:/Program Files/Git/bin/bash.exe"
OUTPUT_LINE_CAP = 2000
OUTPUT_BYTE_CAP = 100_000

ROOT = Path(DEFAULT_ROOT).resolve()


# ---------------------------------------------------------------------------
# 路径沙箱
# ---------------------------------------------------------------------------

def _within(root: Path, p: Path) -> bool:
    """Windows 上大小写不敏感地判断 p 是否落在 root 内（含相等）。"""
    rp = str(p.resolve())
    rr = str(root.resolve())
    if os.name == "nt":
        rp, rr = rp.lower(), rr.lower()
    return rp == rr or rp.startswith(rr.rstrip("/\\") + os.sep)


def _resolve(path: str) -> Path:
    """解析用户路径并强制约束在 ROOT 内；越界直接抛 ValueError。"""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    rp = p.resolve()
    if not _within(ROOT, rp):
        raise ValueError(f"path escapes workspace root {ROOT}: {path!r}")
    return rp


def _rel(p: Path) -> str:
    """返回相对 ROOT 的 POSIX 风格相对路径，便于展示。"""
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _write_text(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _clip(text: str, hint: str) -> str:
    """按行数 / 字节数截断输出，并附说明。"""
    lines = text.split("\n")
    if len(lines) > OUTPUT_LINE_CAP:
        truncated = "\n".join(lines[:OUTPUT_LINE_CAP])
        return f"{hint}\n{truncated}\n... [truncated: {len(lines) - OUTPUT_LINE_CAP} more lines]"
    if len(text) > OUTPUT_BYTE_CAP:
        return f"{hint}\n{text[:OUTPUT_BYTE_CAP]}\n... [truncated: {len(text) - OUTPUT_BYTE_CAP} more bytes]"
    return f"{hint}\n{text}"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

@mcp.tool()
def read_file(path: str, offset: int = 1, limit: int = 2000, tail: bool = False) -> str:
    """读取工作区内文件（UTF-8，行号前缀）。

    path: 相对工作区根（如 "ExoCore/core/models.py"）或工作区内的绝对路径；
         .. 越界会被拒绝。
    offset: 起始行号（1 基），默认 1。
    limit: 最多返回行数，默认 2000，最大 10000。
    tail: true 时读取文件末尾 limit 行（忽略 offset）。
    读文件时先确认编码；返回内容可能被截断并附说明。
    """
    try:
        rp = _resolve(path)
    except ValueError as e:
        return f"[read_file] {e}"
    if not rp.is_file():
        return f"[read_file] not a file: {path}"
    try:
        text = _read_text(rp)
    except (UnicodeDecodeError, OSError) as e:
        return f"[read_file] read failed ({e.__class__.__name__}): {e}"
    lines = text.rstrip("\n").split("\n")
    if tail:
        chunk = lines[-limit:]
    else:
        chunk = lines[offset - 1 : offset - 1 + limit]
    numbered = "\n".join(f"{offset + i:6d}  {ln}" for i, ln in enumerate(chunk))
    hint = f"[file: {_rel(rp)}] ({len(lines)} lines total)"
    return _clip(numbered, hint)


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """全量写入 / 新建工作区内文件（UTF-8）。父目录不存在会自动创建。

    path: 相对工作区根或工作区内绝对路径；.. 越界会被拒绝。
    content: 完整新内容。这是粗暴覆盖工具——精确局部修改请用 edit_file。
    """
    try:
        rp = _resolve(path)
    except ValueError as e:
        return f"[write_file] {e}"
    existed = rp.exists()
    try:
        _write_text(rp, content)
    except OSError as e:
        return f"[write_file] write failed: {e}"
    nlines = len(content.split("\n"))
    size = len(content.encode("utf-8"))
    action = "overwritten" if existed else "created"
    return f"[write_file] {action}: {_rel(rp)} ({nlines} lines, {size} bytes)"


@mcp.tool()
def edit_file(path: str, edits_json: str) -> str:
    """精确文本替换，一次多块，全部命中才写入（全成或不动）。

    path: 相对工作区根或工作区内绝对路径；.. 越界会被拒绝。
    edits_json: JSON 数组字符串，每项 {old_text, new_text}：
        - old_text 必须在原文件中唯一命中（原样匹配，含缩进/换行）；
          不唯一会报错列出命中次数，请扩大上下文（带前后行）后重试。
        - new_text 为空串表示删除该段。
        - 多个 edit 互不重叠；任一失败则整个文件保持原样。
    示例: [{"old_text": "foo()", "new_text": "bar() // replaced"},
          {"old_text": "baz", "new_text": "qux"}]
    适合大文件局部修改；git diff 干净，不产生模糊匹配错位。
    """
    try:
        rp = _resolve(path)
    except ValueError as e:
        return f"[edit_file] {e}"
    if not rp.is_file():
        return f"[edit_file] not a file: {path}"
    try:
        edits = json.loads(edits_json)
        if not isinstance(edits, list) or not edits:
            return "[edit_file] edits_json must be a non-empty JSON array"
        for ed in edits:
            if not isinstance(ed, dict) or "old_text" not in ed:
                return "[edit_file] each edit needs {old_text, new_text}"
    except json.JSONDecodeError as e:
        return f"[edit_file] bad JSON: {e}"
    try:
        text = _read_text(rp)
    except (UnicodeDecodeError, OSError) as e:
        return f"[edit_file] read failed ({e.__class__.__name__}): {e}"

    # 先在原始文本上找全部命中，确保唯一、不重叠
    spans = []  # (start, end, new_text)
    for ed in edits:
        old = ed.get("old_text", "")
        new = ed.get("new_text", "")
        if old == "":
            return "[edit_file] old_text must not be empty"
        idx, count = [], 0
        start = 0
        while True:
            pos = text.find(old, start)
            if pos < 0:
                break
            idx.append(pos)
            count += 1
            start = pos + 1
        if count == 0:
            return f"[edit_file] old_text not found: {old[:60]!r}"
        if count > 1:
            ctx = text[idx[0] : idx[0] + 80].replace("\n", "\\n")
            return f"[edit_file] old_text matched {count} times (need unique): {old[:40]!r} ... first hit near {ctx!r}"
        spans.append((idx[0], idx[0] + len(old), new))

    spans.sort()
    for i in range(1, len(spans)):
        if spans[i][0] < spans[i - 1][1]:
            return "[edit_file] edits overlap each other; keep them disjoint"

    # 从后往前应用，避免 index 位移
    out = text
    for start, end, new in reversed(spans):
        out = out[:start] + new + out[end:]
    try:
        _write_text(rp, out)
    except OSError as e:
        return f"[edit_file] write failed (file untouched): {e}"
    return f"[edit_file] ok: {len(spans)} hunk(s) applied to {_rel(rp)}"


@mcp.tool()
def bash_readonly(cmd: str, timeout: int = 30) -> str:
    """在工作区根目录执行只读 shell 命令（只读契约）。

    仅用于查询：rg / grep / ls / cat / tail / git status / git diff / git log /
    find / pwd 等。禁止任何变更类命令（写入、删除、安装、构建、提交等）——
    执行类操作请通过 wezterm pane（send_to_pane）进行。
    命令在 ROOT 下以 `cd ROOT && <cmd>` 方式运行（不依赖进程 cwd）。
    """
    if not 1 <= timeout <= 120:
        return "[bash_readonly] timeout must be 1..120"
    bash = shutil.which("bash") or (GIT_BASH if os.path.exists(GIT_BASH) else "bash")
    posix_root = str(ROOT).replace("\\", "/")
    script = f"cd {posix_root} && {cmd}"
    try:
        proc = subprocess.run(
            [bash, "-lc", script],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"[bash_readonly] timed out after {timeout}s (read-only contract)"
    except FileNotFoundError:
        return "[bash_readonly] bash binary not found"
    out = proc.stdout or ""
    if proc.stderr:
        out += "\n[stderr]\n" + proc.stderr
    hint = f"[bash_readonly] rc={proc.returncode} | cwd={posix_root}"
    return _clip(out, hint)


@mcp.tool()
def list_dir(path: str = ".", pattern: str = None, depth: int = 1) -> str:
    """列出工作区内目录内容。

    path: 相对工作区根或工作区内绝对路径。
    pattern: 可选，glob 过滤文件名（如 "*.py"）。
    depth: 递归深度（1=只列直接子项，最大 3）。
    输出每行: [d] 目录名/ 或 [f] 文件名 (大小)。
    """
    try:
        rp = _resolve(path)
    except ValueError as e:
        return f"[list_dir] {e}"
    if not rp.is_dir():
        return f"[list_dir] not a directory: {path}"
    depth = max(1, min(int(depth), 3))
    lines = []
    root_prefix = rp

    def walk(dirp: Path, level: int) -> None:
        try:
            entries = sorted(dirp.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError as e:
            lines.append(f"[error] {_rel(dirp)}: {e}")
            return
        for e in entries:
            if pattern and not fnmatch.fnmatch(e.name, pattern):
                continue
            rel = e.relative_to(root_prefix).as_posix()
            if e.is_dir():
                lines.append(f"[d] {rel}/")
                if level < depth:
                    walk(e, level + 1)
            else:
                try:
                    size = e.stat().st_size
                except OSError:
                    size = -1
                lines.append(f"[f] {rel} ({size} B)")

    walk(rp, 1)
    if not lines:
        return f"[list_dir] empty: {_rel(rp)}/"
    return f"[list_dir] {_rel(rp)}/ ({len(lines)} entries)\n" + "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="local-workspace MCP server")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="workspace root (default: %(default)s)")
    args = parser.parse_args()
    global ROOT
    ROOT = Path(args.root).resolve()
    if not ROOT.is_dir():
        raise SystemExit(f"--root is not a directory: {ROOT}")
    mcp.run()


if __name__ == "__main__":
    main()