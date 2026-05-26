import os
import shutil
import tempfile
import time

import pytest
from extensions.wez_bridge.cache_manager import CacheManager


class TestCacheManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cm = CacheManager(cache_root=self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dump_creates_file(self):
        filepath = self.cm.dump(pane_id="2", content="error output here")
        assert os.path.exists(filepath)
        assert "pane_2_" in filepath
        assert filepath.endswith(".log")

    def test_dump_content_is_exact(self):
        content = "line1\nline2\nTraceback error\n"
        filepath = self.cm.dump(pane_id="2", content=content)
        assert self.cm.load(filepath) == content

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
        assert removed == 1
        assert not os.path.exists(old_path)
        assert os.path.exists(recent_path)

    def test_ensures_cache_dir_exists(self):
        new_dir = os.path.join(self.tmpdir, "nested", "cache")
        cm = CacheManager(cache_root=new_dir)
        path = cm.dump(pane_id="1", content="test")
        assert os.path.exists(path)

    def test_cleanup_only_removes_pane_logs(self):
        # Create old non-pane file — should NOT be removed
        non_pane_path = os.path.join(self.tmpdir, "other_file.txt")
        with open(non_pane_path, "w") as f:
            f.write("not a pane log")
        old_time = time.time() - 7200
        os.utime(non_pane_path, (old_time, old_time))

        # Create old pane file — should be removed
        old_pane_path = os.path.join(self.tmpdir, "pane_99_old.log")
        with open(old_pane_path, "w") as f:
            f.write("old pane")
        os.utime(old_pane_path, (old_time, old_time))

        # Create recent pane file — should be kept
        recent_path = self.cm.dump(pane_id="4", content="recent")

        removed = self.cm.cleanup(max_age_seconds=3600)
        assert removed == 1
        assert os.path.exists(non_pane_path), "Non-pane file should not be removed"
        assert not os.path.exists(old_pane_path), "Old pane file should be removed"
        assert os.path.exists(recent_path)

    def test_load_returns_content(self):
        content = "hello world\nsecond line\n"
        filepath = self.cm.dump(pane_id="42", content=content)
        loaded = self.cm.load(filepath)
        assert loaded == content

    def test_load_raises_on_missing(self):
        missing_path = os.path.join(self.tmpdir, "nonexistent.log")
        with pytest.raises(FileNotFoundError):
            self.cm.load(missing_path)
