from unittest.mock import MagicMock, patch
from extensions.wez_bridge.extension import WezBridgeExtension


class TestWezBridgeExtension:
    def test_name_is_wezterm_bridge(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            ext = WezBridgeExtension()
            assert "WezTerm" in ext.name

    def test_start_registers_all_routes_and_starts_components(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI") as mock_cli_class, \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel") as mock_sentinel_class, \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.get_host_pane_id.return_value = "2"
            mock_srv = mock_srv_class.return_value

            ext = WezBridgeExtension()
            ext.start()

            mock_srv.start.assert_called_once()
            mock_sentinel_class.return_value.start.assert_called_once()
            # Should register 5 routes
            assert mock_srv.register_route.call_count >= 5

    def test_stop_stops_all_components(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel") as mock_sentinel_class, \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            ext = WezBridgeExtension()
            ext.start()
            ext.stop()

            mock_srv_class.return_value.stop.assert_called_once()
            mock_sentinel_class.return_value.stop.assert_called_once()

    def test_create_session_route(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager") as mock_sm_class, \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            mock_sm = mock_sm_class.return_value
            mock_session = MagicMock()
            mock_session.session_id = "sess_new_001"
            mock_session.summary = "test summary"
            mock_sm.create_session.return_value = mock_session

            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb
            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["session_new"]({
                "first_user_message": "帮我看看这个报错",
                "metadata": {"pane_id": "2"},
            })
            assert result["status"] == "ok"
            assert result["session_id"] == "sess_new_001"
            mock_sm.create_session.assert_called_once_with(
                first_user_message="帮我看看这个报错",
                metadata={"pane_id": "2", "agent_name": "Alessandro"},
            )

    def test_send_message_route_routes_to_pane_and_displays(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter") as mock_mr_class, \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            mock_mr = mock_mr_class.return_value
            mock_mr.route_to_pane.return_value = True
            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb
            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["send_message"]({
                "from_agent": "G045",
                "target_pane_id": "2",
                "message": "构建完成",
                "msg_type": "notification",
            })
            assert result["status"] == "ok"
            mock_mr.route_to_pane.assert_called_once_with(
                target_pane_id="2",
                message="构建完成",
                from_agent="G045",
            )
            mock_mr.display_incoming.assert_called_once_with("G045", "构建完成")

    def test_get_menu_items_includes_status(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            ext = WezBridgeExtension()
            items = ext.get_menu_items()
            assert len(items) >= 1
