import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from termux_nas.mounted import run_mounted_shell


class FakeBackend:
    def is_dir(self, path):
        if path == "":
            return True
        if path == "hello.txt":
            return False
        raise FileNotFoundError(path)

    def entries(self, path):
        return [{"name": "hello.txt", "mode": "-rw-r--r--", "size": 12}]

    def stat_size(self, path):
        return 12

    def read(self, path):
        return io.BytesIO(b"NAS content\n")


class MountedShellTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"), "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_normal_commands_see_both_trees_and_writes_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / "local.txt").write_text("local content\n", encoding="utf-8")
            bash = shutil.which("bash")
            script = 'cd "$HOME/nas" && find . -type f && cat hello.txt && cat "$HOME/local.txt" && ! cp "$HOME/local.txt" "$HOME/nas/new.txt"'
            with patch.dict(os.environ, {"HOME": str(home)}):
                status = run_mounted_shell(FakeBackend(), "nas", os.environ["TERMUX_NAS_TEST_PROOT"], [bash, "-c", script])
            self.assertEqual(status, 0)
            self.assertFalse((home / "nas").exists())


if __name__ == "__main__":
    unittest.main()
