import io
import tempfile
import unittest
from pathlib import Path

from termux_nas.hydrate import Hydrator


class FakeBackend:
    def __init__(self):
        self.reads = []

    def is_dir(self, path):
        return path in ("", "Photos")

    def entries(self, path):
        names = {"": [("Photos", True), ("hello.txt", False)], "Photos": [("pic.txt", False)]}[path]
        return [{"name": name, "mode": "drwxr-xr-x" if directory else "-rw-r--r--", "size": 7} for name, directory in names]

    def stat_size(self, path):
        return 7

    def read(self, path):
        self.reads.append(path)
        return io.BytesIO(b"content")


class HydratorTests(unittest.TestCase):
    def test_directory_then_file_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            backend = FakeBackend()
            hydrator = Hydrator(mount, backend)
            hydrator.ensure(str(mount), "O")
            self.assertTrue((mount / "Photos").is_dir())
            self.assertEqual((mount / "hello.txt").stat().st_size, 7)
            self.assertEqual(backend.reads, [])
            hydrator.ensure(str(mount / "hello.txt"), "O")
            self.assertEqual((mount / "hello.txt").read_bytes(), b"content")
            self.assertEqual(backend.reads, ["hello.txt"])


if __name__ == "__main__":
    unittest.main()
