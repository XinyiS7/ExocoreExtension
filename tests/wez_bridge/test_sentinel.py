from unittest.mock import MagicMock, patch, call
from extensions.wez_bridge.sentinel import Sentinel


class TestSentinelErrorDetection:
    """Unit tests for Sentinel's static analysis methods (no WezTerm needed)."""

    def test_detect_error_keyword_traceback(self):
        text = "Traceback (most recent call last):\n  File 'x.py', line 5\nValueError: bad"
        assert Sentinel.has_error_keywords(text) is True

    def test_detect_error_keyword_fatal(self):
        assert Sentinel.has_error_keywords("fatal: not a git repository") is True

    def test_detect_error_keyword_clean_output(self):
        assert Sentinel.has_error_keywords("$ npm install\nadded 42 packages") is False

    def test_detect_error_keyword_normal_prompt(self):
        assert Sentinel.has_error_keywords("user@host:~$ ") is False

    def test_entropy_below_threshold_prompt(self):
        # ">>> " has 3 unique chars and is clearly low-entropy
        assert Sentinel.is_low_entropy(">>> ", threshold=10) is True

    def test_entropy_above_threshold_error(self):
        error_text = "Traceback (most recent call last):\n" * 10
        assert Sentinel.is_low_entropy(error_text, threshold=10) is False

    def test_truncate_output(self):
        long_text = "x" * 3000
        result = Sentinel.truncate(long_text, max_chars=2000)
        assert len(result) == 2000
        assert result == long_text[-2000:]

    def test_truncate_short_output_unchanged(self):
        short = "hello"
        assert Sentinel.truncate(short, max_chars=2000) == "hello"


class TestSentinelPolling:
    """Integration-style tests with mocked WezTermCLI."""

    def test_poll_detects_error_and_triggers_callback(self):
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
            {"pane_id": 1, "title": "workspace", "is_active": False},
        ]
        mock_cli.get_text.return_value = "npm ERR! code ERESOLVE\nnpm ERR! Fix the upstream dependency conflict"

        mock_cache = MagicMock()
        mock_cache.dump.return_value = r"D:\Alicia\ExoCoreData\cache\pane_1_20260526_120000.log"

        triggered = []

        def on_alert(pane_id, cache_path, snippet):
            triggered.append((pane_id, cache_path, snippet))

        sentinel = Sentinel(
            cli=mock_cli,
            cache=mock_cache,
            host_pane_id="0",
            on_alert=on_alert,
            poll_interval=0.01,
        )
        sentinel._poll_once()

        assert len(triggered) == 1
        pane_id, cache_path, snippet = triggered[0]
        assert pane_id == "1"
        assert "pane_1" in cache_path

    def test_poll_skips_host_pane(self):
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
        ]

        sentinel = Sentinel(
            cli=mock_cli,
            cache=MagicMock(),
            host_pane_id="0",
            poll_interval=0.01,
        )
        sentinel._poll_once()

        mock_cli.get_text.assert_not_called()

    def test_poll_skips_clean_pane(self):
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
            {"pane_id": 2, "title": "clean workspace", "is_active": False},
        ]
        mock_cli.get_text.return_value = "> "

        triggered = []
        sentinel = Sentinel(
            cli=mock_cli,
            cache=MagicMock(),
            host_pane_id="0",
            on_alert=lambda pid, cp, sn: triggered.append(pid),
            poll_interval=0.01,
        )
        sentinel._poll_once()

        assert len(triggered) == 0

    def test_poll_does_not_false_alert_on_first_sight(self):
        """A pane with normal content should not trigger on its first poll."""
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
            {"pane_id": 3, "title": "new pane", "is_active": False},
        ]
        mock_cli.get_text.return_value = "user@host:~/project$ ls -la"

        triggered = []
        sentinel = Sentinel(
            cli=mock_cli,
            cache=MagicMock(),
            host_pane_id="0",
            on_alert=lambda pid, cp, sn: triggered.append(pid),
            poll_interval=0.01,
        )
        sentinel._poll_once()
        assert len(triggered) == 0  # First sight — no alert
