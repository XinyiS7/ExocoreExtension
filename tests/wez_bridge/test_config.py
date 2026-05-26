import os
from extensions.wez_bridge import config


class TestConfig:
    def test_cache_dir_absolute(self):
        assert os.path.isabs(config.CACHE_DIR)

    def test_sentinel_interval_positive(self):
        assert config.SENTINEL_POLL_INTERVAL_SEC > 0

    def test_local_server_binds_localhost(self):
        assert config.LOCAL_SERVER_HOST == "127.0.0.1"

    def test_error_keywords_not_empty(self):
        assert len(config.SENTINEL_ERROR_KEYWORDS) > 0

    def test_agent_name_is_alessandro(self):
        assert config.AGENT_NAME == "Alessandro"
