import os
import io
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from termux_nas.bash import RCFILE
from termux_nas.bridge import BridgeServer, normalize, remote_path
from termux_nas.session import run_shell


class FakeBackend:
    def __init__(self):
        self.uploaded = {}

    def is_dir(self, path):
        return path in ("", "Photos")

    def listdir(self, path):
        return {"": ["Photos"], "Photos": ["pic.jpg"]}[path]

    def entries(self, path):
        return [{"name": name, "mode": "drwxr-xr-x" if name == "Photos" else "-rw-r--r--", "size": 5, "mtime": 0} for name in self.listdir(path)]

    def read(self, path):
        if path == "Photos/pic.jpg":
            return io.BytesIO(b"photo")
        raise FileNotFoundError(path)

    def write(self, path):
        backend = self

        class Output(io.BytesIO):
            def close(self):
                backend.uploaded[path] = self.getvalue()
                super().close()

        return Output()


class BridgeTests(unittest.TestCase):
    def test_path_classification(self):
        self.assertEqual(remote_path("/home/u/nas/Photos", "/home/u/nas"), "Photos")
        self.assertIsNone(remote_path("/home/u/nas2", "/home/u/nas"))
        self.assertEqual(normalize("/home/u/nas/Photos", ".."), "/home/u/nas")

    def test_real_bash_keeps_local_and_remote_navigation(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "home"
            home.mkdir()
            (home / "local.txt").write_text("local", encoding="utf-8")
            shadow = Path(root) / "shadow"
            shadow.mkdir()
            mount = home / "media"
            mount.symlink_to(shadow, target_is_directory=True)
            rcfile = Path(root) / "bashrc"
            rcfile.write_text(RCFILE, encoding="utf-8")
            socket_path = str(Path(root) / "bridge.sock")
            backend = FakeBackend()
            with BridgeServer(socket_path, backend, str(mount)) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                env = os.environ.copy()
                env["HOME"] = str(home)
                env["TERMUX_NAS_MOUNT"] = str(mount)
                env["TERMUX_NAS_SOCKET"] = socket_path
                env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
                process = subprocess.run(
                    ["bash", "--rcfile", str(rcfile), "-ic", 'cd "$TERMUX_NAS_MOUNT"; pwd; ls; ls -la; cd Photos; pwd; ls; cat pic.jpg; cp pic.jpg "$HOME/download.jpg"; cd "$HOME"; cat local.txt; cp local.txt "$TERMUX_NAS_MOUNT/upload.txt"'],
                    env=env,
                    cwd=home,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=15,
                )
                server.shutdown()
                thread.join(timeout=2)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn(str(mount) + "\nPhotos\n", process.stdout)
            self.assertIn("drwxr-xr-x", process.stdout)
            self.assertIn(str(mount / "Photos") + "\npic.jpg\n", process.stdout)
            self.assertIn("pic.jpg\nphoto", process.stdout)
            self.assertTrue(process.stdout.endswith("local"))
            self.assertEqual((home / "download.jpg").read_bytes(), b"photo")
            self.assertEqual(backend.uploaded["upload.txt"], b"local")

    def test_shell_session_removes_temporary_mount_link(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "home"
            home.mkdir()

            def inspect_call(argv, env):
                self.assertTrue((home / "media").is_symlink())
                self.assertEqual(env["TERMUX_NAS_MOUNT"], str(home / "media"))
                self.assertTrue(Path(env["TERMUX_NAS_SOCKET"]).exists())
                return 0

            with patch.dict(os.environ, {"HOME": str(home)}), patch("termux_nas.session.subprocess.call", side_effect=inspect_call):
                self.assertEqual(run_shell(FakeBackend(), "media"), 0)
            self.assertFalse(os.path.lexists(home / "media"))


if __name__ == "__main__":
    unittest.main()
