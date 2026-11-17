import contextlib
import io
import unittest

from termux_nas.shell import NASShell


class FakeBackend:
    def is_dir(self, path):
        return path in ("", "Photos", "Photos/2026")

    def listdir(self, path):
        return {"": ["Photos"], "Photos": ["2026"], "Photos/2026": ["pic.jpg"]}[path]


class ShellTests(unittest.TestCase):
    def test_cd_and_ls(self):
        shell = NASShell(FakeBackend())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            shell.execute("cd ~/nas/Photos")
            shell.execute("ls")
            shell.execute("cd 2026")
            shell.execute("pwd")
        self.assertEqual(shell.cwd, "Photos/2026")
        self.assertEqual(out.getvalue(), "2026\n~/nas/Photos/2026\n")

    def test_failed_cd_keeps_current_directory(self):
        shell = NASShell(FakeBackend())
        with contextlib.redirect_stderr(io.StringIO()):
            shell.execute("cd missing")
        self.assertEqual(shell.cwd, "")


if __name__ == "__main__":
    unittest.main()
