from unittest.mock import MagicMock, patch
from extensions.wez_bridge.extension import WezBridgeExtension


class TestWezBridgeExtension:
    def test_name_is_wezterm_bridge(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"):
            ext = WezBridgeExtension()
            assert "WezTerm" in ext.name

    def test_start_starts_all_components(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI") as mock_cli, \
             patch("extensions.wez_bridge.extension.CacheManager") as mock_cache, \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv, \
             patch("extensions.wez_bridge.extension.Sentinel") as mock_sentinel, \
             patch("extensions.wez_bridge.extension.Commander") as mock_cmdr:
            ext = WezBridgeExtension()
            ext.start()

            mock_srv.return_value.start.assert_called_once()
            mock_sentinel.return_value.start.assert_called_once()

    def test_stop_stops_all_components(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv, \
             patch("extensions.wez_bridge.extension.Sentinel") as mock_sentinel, \
             patch("extensions.wez_bridge.extension.Commander"):
            ext = WezBridgeExtension()
            ext.start()
            ext.stop()

            mock_srv.return_value.stop.assert_called_once()
            mock_sentinel.return_value.stop.assert_called_once()

    def test_get_menu_items_includes_status(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"):
            ext = WezBridgeExtension()
            items = ext.get_menu_items()
            assert len(items) >= 1
