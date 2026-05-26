import os
import tempfile
import time
from extensions.wez_bridge.cache_manager import CacheManager


class TestCacheManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cm = CacheManager(cache_root=self.tmpdir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dump_creates_file(self):
        filepath = self.cm.dump(pane_id="2", content="error output here")
        assert os.path.exists(filepath)
        assert "pane_2_" in filepath
        assert filepath.endswith(".log")

    def test_dump_content_is_exact(self):
        content = "line1\nline2\nTraceback error\n"
        filepath = self.cm.dump(pane_id="2", content=content)
        with open(filepath, "r", encoding="utf-8") as f:
            assert f.read() == content

    def test_cleanup_removes_old_files(self):
        # Create a file with old timestamp
        old_path = os.path.join(self.tmpdir, "pane_3_old.log")
        with open(old_path, "w") as f:
            f.write("old")
        # Set mtime to 2 hours ago
        old_time = time.time() - 7200
        os.utime(old_path, (old_time, old_time))

        # Create a recent file
        recent_path = self.cm.dump(pane_id="4", content="recent")

        # Cleanup files older than 1 hour
        removed = self.cm.cleanup(max_age_seconds=3600)
        assert removed >= 1
        assert not os.path.exists(old_path)
        assert os.path.exists(recent_path)

    def test_ensures_cache_dir_exists(self):
        new_dir = os.path.join(self.tmpdir, "nested", "cache")
        cm = CacheManager(cache_root=new_dir)
        path = cm.dump(pane_id="1", content="test")
        assert os.path.exists(path)
