import io
import unittest

from termux_nas.config import validate
from termux_nas.smb import SMBAllSharesBackend


class FakeShare:
    def is_dir(self, path):
        return path == "Photos"

    def entries(self, path):
        return [{"name": "hello.txt", "mode": "-rw-r--r--", "size": 5}]

    def read(self, path):
        return io.BytesIO(path.encode())


class AllSharesTests(unittest.TestCase):
    def test_optional_share_and_virtual_root(self):
        validate("server", "nas.local", None, "user", 445)
        backend = SMBAllSharesBackend.__new__(SMBAllSharesBackend)
        backend._shares = {"Shared": FakeShare()}
        self.assertTrue(backend.is_dir(""))
        self.assertEqual(backend.entries("")[0]["name"], "Shared")
        self.assertTrue(backend.is_dir("Shared/Photos"))
        self.assertEqual(backend.entries("Shared/Photos")[0]["name"], "hello.txt")
        self.assertEqual(backend.read("Shared/Photos/hello.txt").read(), b"Photos/hello.txt")
        with self.assertRaises(FileNotFoundError):
            backend.is_dir("Unknown")


if __name__ == "__main__":
    unittest.main()
