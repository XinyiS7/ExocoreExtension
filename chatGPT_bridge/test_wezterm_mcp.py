"""wezterm_mcp socket 发现单元测试 — mock _sock_dir / _pid_alive，不碰真实 socket/进程。

覆盖修复点（Plan 2026-08-17_fix_wezterm_mcp_socket_rediscovery.md）：
  T1: 候选「死 pid 新 + 活 pid 旧」→ 选中活 pid（mtime 优先但跳过死）
  T2: env 残留死值 → 不被采纳，glob 胜出
  T3: 全死 → None；_run_cli 返回 error 不挂起不 spawn
  T4: _run_cli 传给 subprocess 的 env 含 WEZTERM_UNIX_SOCKET=完整路径
  T5: 无候选（目录空 / OSError）→ None，_run_cli 仍返回 error 而非崩溃
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# 测试运行器可能无 mcp SDK：先注入假 mcp.server 再导入目标模块
sys.path.insert(0, "D:/Alicia/ExoCore_Project/ExoCore-Extension/chatGPT_bridge")
if "mcp" not in sys.modules:
    fake_mcp = mock.MagicMock()
    fake_mcp.server.return_value = fake_mcp
    sys.modules["mcp"] = fake_mcp
    sys.modules["mcp.server"] = fake_mcp

import wezterm_mcp as wm


class SocketResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wzm_test_"))
        self._orig_sock_dir = wm._sock_dir
        self._orig_pid_alive = wm._pid_alive
        self._orig_env = dict(os.environ)
        wm._sock_dir = lambda: self.tmp
        os.environ.pop("WEZTERM_UNIX_SOCKET", None)

    def tearDown(self):
        wm._sock_dir = self._orig_sock_dir
        wm._pid_alive = self._orig_pid_alive
        os.environ.clear()
        os.environ.update(self._orig_env)

    def _make_sock(self, name: str, mtime_age_days: float):
        """创建带 mtime 的假 socket 文件。"""
        p = self.tmp / name
        p.write_text("", encoding="utf-8")
        os.utime(p, (0, 0) if False else None)  # 占位，下面重设
        import time
        st = time.time() - mtime_age_days * 86400
        os.utime(p, (st, st))
        return p

    def test_t1_new_dead_skipped_old_alive_chosen(self):
        """死 pid 的 socket mtime 更新也跳过，选活 pid。"""
        old_alive = self._make_sock("gui-sock-1111", mtime_age_days=2)
        new_dead = self._make_sock("gui-sock-2222", mtime_age_days=0)

        def fake_alive(pid):
            return pid == 1111

        wm._pid_alive = fake_alive
        result = wm._resolve_wezterm_socket()
        self.assertEqual(result, old_alive)
        self.assertNotEqual(result, new_dead)

    def test_t2_stale_env_ignored_glob_wins(self):
        """env 残留死值不被采纳，glob 活候选胜出。"""
        live = self._make_sock("gui-sock-3333", mtime_age_days=1)
        os.environ["WEZTERM_UNIX_SOCKET"] = "gui-sock-9999"  # 死 pid，且文件不存在
        wm._pid_alive = lambda pid: pid == 3333
        result = wm._resolve_wezterm_socket()
        self.assertEqual(result, live)

    def test_t2b_env_live_value_is_extra_candidate(self):
        """env 值指向存活 socket（即使 glob 漏掉）也应被采纳。"""
        # glob 目录为空，env 指向一个存活 pid 的完整路径
        sock_path = self.tmp / "gui-sock-4444"
        os.environ["WEZTERM_UNIX_SOCKET"] = str(sock_path)
        self._make_sock("gui-sock-4444", mtime_age_days=1)
        wm._pid_alive = lambda pid: pid == 4444
        result = wm._resolve_wezterm_socket()
        self.assertEqual(result, sock_path)

    def test_t3_all_dead_returns_none(self):
        """全死 → None，_run_cli 返回 error 不挂起不 spawn。"""
        self._make_sock("gui-sock-5555", mtime_age_days=0)
        wm._pid_alive = lambda pid: False
        self.assertIsNone(wm._resolve_wezterm_socket())

        # _run_cli 走 timeout/无 env 分支：mock 掉 subprocess.run 确认不 hang
        with mock.patch.object(
            wm.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
        ) as m:
            code, out, err = wm._run_cli("list", "--format", "json")
        self.assertEqual(code, -1)
        self.assertIn("timed out", err)
        m.assert_called_once()
        # env 不应含 WEZTERM_UNIX_SOCKET（无可信 socket）
        env_arg = m.call_args.kwargs.get("env") or m.call_args[1].get("env")
        self.assertNotIn("WEZTERM_UNIX_SOCKET", env_arg)

    def test_t4_env_injected_with_full_path(self):
        """选中 socket 后 subprocess env 含完整路径 WEZTERM_UNIX_SOCKET。"""
        live = self._make_sock("gui-sock-6666", mtime_age_days=0)
        wm._pid_alive = lambda pid: pid == 6666

        proc = mock.MagicMock()
        proc.returncode = 0
        proc.stdout = "[]"
        proc.stderr = ""
        with mock.patch.object(wm.subprocess, "run", return_value=proc) as m:
            code, out, err = wm._run_cli("list", "--format", "json")
        self.assertEqual(code, 0)
        env_arg = m.call_args.kwargs.get("env") or m.call_args[1].get("env")
        self.assertEqual(env_arg["WEZTERM_UNIX_SOCKET"], str(live.resolve()))
        # cli 只认完整路径：值必须是绝对路径
        self.assertTrue(
            Path(env_arg["WEZTERM_UNIX_SOCKET"]).is_absolute(),
            "WEZTERM_UNIX_SOCKET 必须是完整路径",
        )

    def test_t5_empty_dir_and_oserror(self):
        """空目录 / OSError → None；_run_cli 仍返回 error 不崩溃。"""
        wm._pid_alive = lambda pid: True
        self.assertIsNone(wm._resolve_wezterm_socket())

        with mock.patch.object(
            wm.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
        ):
            code, _, err = wm._run_cli("list")
        self.assertEqual(code, -1)

        # OSError 分支（模拟 sock_dir 不可读）
        def boom():
            raise OSError("nope")

        wm._sock_dir = boom
        self.assertIsNone(wm._resolve_wezterm_socket())


if __name__ == "__main__":
    unittest.main(verbosity=2)