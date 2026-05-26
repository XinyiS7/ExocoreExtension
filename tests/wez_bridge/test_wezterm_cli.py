import json
import subprocess
from unittest.mock import patch, MagicMock
from extensions.wez_bridge.wezterm_cli import WezTermCLI


class TestListPanes:
    def test_list_panes_parses_json(self):
        mock_output = json.dumps([
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
            {"pane_id": 1, "title": "workspace", "is_active": False},
        ])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=mock_output, stderr=""
            )
            cli = WezTermCLI()
            panes = cli.list_panes()
            assert len(panes) == 2
            assert panes[0]["pane_id"] == 0
            assert panes[1]["title"] == "workspace"

    def test_list_panes_returns_empty_on_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="wezterm", timeout=5)
            cli = WezTermCLI()
            panes = cli.list_panes()
            assert panes == []

    def test_list_panes_returns_empty_on_file_not_found(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("wezterm not installed")
            cli = WezTermCLI()
            panes = cli.list_panes()
            assert panes == []

    def test_list_panes_returns_empty_on_malformed_json(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="not valid json {{{", stderr=""
            )
            cli = WezTermCLI()
            panes = cli.list_panes()
            assert panes == []


class TestGetText:
    def test_get_text_returns_stdout(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="line1\nline2\nline3\n", stderr=""
            )
            cli = WezTermCLI()
            text = cli.get_text(pane_id=1)
            assert text == "line1\nline2\nline3\n"

    def test_get_text_truncates_to_last_n_lines(self):
        lines = [f"line{i}" for i in range(100)]
        stdout = "\n".join(lines) + "\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=stdout, stderr=""
            )
            cli = WezTermCLI()
            text = cli.get_text(pane_id=1, tail_lines=5)
            assert text.split("\n") == lines[-5:] + [""]

    def test_get_text_returns_empty_on_timeout(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="wezterm", timeout=5)
            cli = WezTermCLI()
            text = cli.get_text(pane_id=1)
            assert text == ""

    def test_get_text_returns_empty_on_file_not_found(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("wezterm not installed")
            cli = WezTermCLI()
            text = cli.get_text(pane_id=1)
            assert text == ""


class TestSendText:
    def test_send_text_no_newline(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            cli = WezTermCLI()
            result = cli.send_text(pane_id=2, text="npm install")
            assert result is True
            call_args = mock_run.call_args[0][0]
            assert "--no-paste" in call_args
            assert "npm install" in call_args
            assert "\n" not in call_args[-1]

    def test_send_text_returns_false_on_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="wezterm", timeout=5)
            cli = WezTermCLI()
            result = cli.send_text(pane_id=2, text="bad")
            assert result is False

    def test_send_text_returns_false_on_file_not_found(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("wezterm not installed")
            cli = WezTermCLI()
            result = cli.send_text(pane_id=2, text="cmd")
            assert result is False


class TestSendEnter:
    def test_send_enter(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            cli = WezTermCLI()
            result = cli.send_enter(pane_id=2)
            assert result is True


class TestGetHostPaneId:
    def test_returns_active_pane_id(self):
        mock_output = json.dumps([
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
            {"pane_id": 1, "title": "workspace", "is_active": False},
        ])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=mock_output, stderr=""
            )
            cli = WezTermCLI()
            result = cli.get_host_pane_id()
            assert result == "0"

    def test_falls_back_to_first_pane_when_none_active(self):
        mock_output = json.dumps([
            {"pane_id": 3, "title": "idle", "is_active": False},
            {"pane_id": 5, "title": "also idle", "is_active": False},
        ])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=mock_output, stderr=""
            )
            cli = WezTermCLI()
            result = cli.get_host_pane_id()
            assert result == "3"

    def test_returns_none_when_no_panes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="[]", stderr=""
            )
            cli = WezTermCLI()
            result = cli.get_host_pane_id()
            assert result is None
