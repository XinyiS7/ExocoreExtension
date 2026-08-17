"""
wezterm_mcp.py — 极薄 MCP server：把 wezterm cli 包装成 4 个 MCP 工具。

- list_panes()                    列窗格
- read_pane(pane_id, tail_lines)  读窗格文本
- send_to_pane(pane_id, text, submit)  发文字（submit=true 才回车执行）
- flush_pane(pane_id)             发 Ctrl+C 清空输入缓冲区

设计原则：
- 无任意命令执行能力，只有"列 / 读 / 发文字 / 清场"四件事
- submit 默认 false（HITL 门：只填输入框，不回车）
- 回车用 \\r（Windows / Git Bash 上 \\n 不触发提交，血泪教训见
  extensions/wez_bridge/wezterm_cli.py）
- 只依赖 mcp SDK + 标准库，独立单文件，供 tunnel-client 直接 stdio 拉起

运行：python.exe wezterm_mcp.py   （默认 stdio transport）
"""
import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path

# mcp 2.0.0 的 MCPServer（FastMCP 的继任者）原生支持 OpenAI connector
# 的 `server/discover` 动态注册探测——1.28 的 FastMCP 会因为不认识这个
# 方法而 pydantic 报错，导致 ChatGPT 会话中途 tool 注册失效
# (见 README「已知坑」)。在隔离 venv (C:/Users/Alicia/.venvs/wezterm-mcp-bridge)
# 里运行：profile 的 mcp-command 指向该 venv 的 python。
from mcp.server import MCPServer

mcp = MCPServer(name="wezterm-pane", version="1.0.2")

WEZTERM_CLI = shutil.which("wezterm") or shutil.which("wezterm.exe") or "wezterm"
TIMEOUT = 5.0


# 探活句柄权限：PROCESS_QUERY_LIMITED_INFORMATION 足以查存活
_OPEN_PROCESS = ctypes.windll.kernel32.OpenProcess
_CLOSE_HANDLE = ctypes.windll.kernel32.CloseHandle
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _sock_dir() -> Path:
    home = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home) / ".local" / "share" / "wezterm"


def _pid_alive(pid: int) -> bool:
    """Windows 进程存活检查：OpenProcess 成功即存活（零 spawn）。"""
    handle = _OPEN_PROCESS(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    _CLOSE_HANDLE(handle)
    return True


def _socket_pid(sock: Path) -> "int | None":
    """从 gui-sock-<pid> 文件名提取 PID；格式不符返回 None。"""
    name = sock.name
    if not name.startswith("gui-sock-"):
        return None
    suffix = name[len("gui-sock-"):]
    return int(suffix) if suffix.isdigit() else None


def _resolve_wezterm_socket() -> "Path | None":
    """发现当前可用的 WezTerm GUI socket（每次调用现算，不缓存）。

    WezTerm GUI 会把 WEZTERM_UNIX_SOCKET 注入每个 pane 的 shell 环境，
    但从 pane 内被某些 spawner（anyio stdio_client、tunnel-client）拉起的
    进程会被过滤掉该变量；没有它时 wezterm cli 在 Windows 上靠扫描
    gui-sock-* 文件自行发现 socket，多 GUI / 死实例残留场景下会连错。

    本实现（对齐 ExoCore 本体 2026-07-31 修复模式）：
    - 候选 = gui-sock-* 按 mtime 从新到旧（新窗口优先）；
    - 探活 = 文件名内嵌 PID 的进程存活检查（OpenProcess，微秒级、
      不 spawn 任何进程——wezterm cli 连死 socket 时反而会尝试拉起
      新 mux-server 并挂起，绝不能拿它当探活手段）；
    - env 里的 WEZTERM_UNIX_SOCKET 仅作为额外候选（MCP 常驻进程
      的 env 是旧的，重开窗口后不可直接信任）。
    """
    try:
        socks = sorted(
            _sock_dir().glob("gui-sock-*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        socks = []

    # env 候选补全为完整路径（cli 只认完整路径，裸文件名会挂起）
    env_val = os.environ.get("WEZTERM_UNIX_SOCKET")
    if env_val:
        env_path = Path(env_val)
        if not env_path.is_absolute():
            env_path = _sock_dir() / env_path
        if env_path not in socks and env_path.name.startswith("gui-sock-"):
            socks.append(env_path)

    for sock in socks:
        pid = _socket_pid(sock)
        if pid is not None and _pid_alive(pid):
            return sock
    return None


def _run_cli(*args: str) -> tuple[int, str, str]:
    """Run `wezterm cli <args>`, return (returncode, stdout, stderr)."""
    sock = _resolve_wezterm_socket()
    proc_env = dict(os.environ)
    if sock:
        proc_env["WEZTERM_UNIX_SOCKET"] = str(sock)
    try:
        proc = subprocess.run(
            [WEZTERM_CLI, "cli", *args],
            capture_output=True, text=True, timeout=TIMEOUT,
            env=proc_env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "[error] wezterm cli timed out"
    except FileNotFoundError:
        return -1, "", "[error] wezterm binary not found on PATH"


@mcp.tool()
def list_panes() -> str:
    """列出所有 WezTerm 窗格。

    返回 JSON 数组，每项含 pane_id / win_id / title / is_active / cwd / size 等字段。
    任何后续 read_pane / send_to_pane / flush_pane 都必须先用本工具拿到 pane_id。
    """
    code, out, err = _run_cli("list", "--format", "json")
    if code != 0 or not out.strip():
        return json.dumps(
            {"error": f"wezterm cli list failed (code {code})",
             "stdout": out, "stderr": err}
        )
    return out


@mcp.tool()
def read_pane(pane_id: int, tail_lines: int = 50) -> str:
    """读取指定窗格的文本内容。

    pane_id: 来自 list_panes()。
    tail_lines: 只返回末尾 N 行（默认 50）；传 0 返回全部。
    发文字前必须先读，确认 pane 当前状态。
    """
    code, out, err = _run_cli("get-text", "--pane-id", str(pane_id))
    if code != 0:
        return f"[read_pane] get-text failed (code {code}): {out} {err}"
    if tail_lines > 0:
        lines = out.rstrip("\n").split("\n")
        out = "\n".join(lines[-tail_lines:])
    return f"[pane {pane_id}]\n{out}"


@mcp.tool()
def send_to_pane(pane_id: int, text: str, submit: bool = False) -> str:
    """向指定窗格键入文字。

    pane_id: 来自 list_panes()。
    text: 要键入的内容（单行；含换行会按逐键键入处理）。
    submit: false=只填进输入框不执行（安全默认）；true=额外发回车执行。

    流程要求：read → send(submit=false) → read 确认 → send(submit=true)。
    """
    code, out, err = _run_cli("send-text", "--pane-id", str(pane_id), "--no-paste", text)
    if code != 0:
        return f"[send_to_pane] failed (code {code}): {out} {err}"
    if submit:
        code2, out2, err2 = _run_cli("send-text", "--pane-id", str(pane_id), "--no-paste", "\r")
        if code2 != 0:
            return f"[send_to_pane] text typed but ENTER failed (code {code2}): {out2} {err2}"
    return f"[send_to_pane] ok: pane {pane_id} <- {'submitted' if submit else 'typed only'}: {text!r}"


@mcp.tool()
def flush_pane(pane_id: int) -> str:
    """向指定窗格发送 Ctrl+C，清空当前输入缓冲区，恢复干净提示符。

    当 pane 可能处于脏状态（残留输入、上条命令未结束）时，
    在 send_to_pane 之前先用本工具清场。
    """
    code, out, err = _run_cli("send-text", "--pane-id", str(pane_id), "--no-paste", "\x03")
    if code != 0:
        return f"[flush_pane] failed (code {code}): {out} {err}"
    return f"[flush_pane] Ctrl+C sent to pane {pane_id}"


if __name__ == "__main__":
    mcp.run()
