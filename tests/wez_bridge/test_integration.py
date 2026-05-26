"""Integration smoke tests — verify all components wire together correctly."""
import json
import time
from unittest.mock import MagicMock, patch
from extensions.wez_bridge.extension import WezBridgeExtension
from extensions.wez_bridge.wezterm_cli import WezTermCLI
from extensions.wez_bridge.sentinel import Sentinel
from extensions.wez_bridge.commander import Commander
from extensions.wez_bridge.local_server import LocalCommandServer
from extensions.wez_bridge.cache_manager import CacheManager


class TestIntegration:
    def test_full_pipeline_sentinel_to_exocore(self):
        """Mocked full pipeline: ExoCore sends execute_command -> Commander injects."""
        cli = WezTermCLI()
        cli.send_text = MagicMock(return_value=True)  # mock wezterm CLI availability
        cache = CacheManager(cache_root="/tmp/wez_test_cache")
        cmdr = Commander(cli=cli)

        sentinel = Sentinel(cli=cli, cache=cache, host_pane_id="0")
        server = LocalCommandServer(port=18780)

        received_commands = []

        def cmd_handler(payload):
            received_commands.append(payload)
            ok = cmdr.draft_cli_command(
                pane_id=payload["target_pane_id"],
                command=payload["command"],
            )
            return {"status": "ok" if ok else "failed"}

        server._handler = cmd_handler
        server.start()
        time.sleep(0.3)

        try:
            import urllib.request
            payload = json.dumps({
                "target_pane_id": "2",
                "command": "git reset --hard HEAD~1",
                "execute_immediately": False,
                "alert_message": "detected merge conflict",
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18780/api/agents/execute_command/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())

            assert body["status"] == "ok"
            assert len(received_commands) == 1
            assert received_commands[0]["command"] == "git reset --hard HEAD~1"

        finally:
            server.stop()

    def test_extension_lifecycle_no_crash(self):
        """Extension should start and stop without exceptions."""
        with patch("extensions.wez_bridge.extension.WezTermCLI") as mock_cli_class, \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            mock_cli = mock_cli_class.return_value
            mock_cli.get_host_pane_id.return_value = "0"

            ext = WezBridgeExtension()
            ext.start()
            assert ext._started is True
            ext.stop()
            assert ext._started is False
