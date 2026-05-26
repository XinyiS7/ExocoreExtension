from unittest.mock import MagicMock
from extensions.wez_bridge.commander import Commander


class TestCommander:
    def test_draft_cli_command_injects_without_newline(self):
        mock_cli = MagicMock()
        mock_cli.send_text.return_value = True

        cmdr = Commander(cli=mock_cli)
        result = cmdr.draft_cli_command(pane_id="2", command="npm install --legacy-peer-deps")

        assert result is True
        mock_cli.send_text.assert_called_once_with(
            "2", "npm install --legacy-peer-deps"
        )
        mock_cli.send_enter.assert_not_called()

    def test_draft_cli_command_returns_false_on_failure(self):
        mock_cli = MagicMock()
        mock_cli.send_text.return_value = False

        cmdr = Commander(cli=mock_cli)
        result = cmdr.draft_cli_command(pane_id="99", command="bad")

        assert result is False

    def test_execute_immediately_sends_enter(self):
        mock_cli = MagicMock()
        mock_cli.send_text.return_value = True
        mock_cli.send_enter.return_value = True

        cmdr = Commander(cli=mock_cli)
        result = cmdr.draft_cli_command(
            pane_id="2", command="ls -la", execute_immediately=True
        )

        assert result is True
        mock_cli.send_enter.assert_called_once_with("2")

    def test_list_panes_delegates_to_cli(self):
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI"},
            {"pane_id": 1, "title": "workspace"},
        ]

        cmdr = Commander(cli=mock_cli)
        panes = cmdr.list_panes()

        assert len(panes) == 2
        mock_cli.list_panes.assert_called_once()
