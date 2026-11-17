import io
import os
import tempfile
import unittest
from pathlib import Path

from termux_nas.hydrate import Hydrator


class FakeBackend:
    def __init__(self):
        self.reads = []
        self.dir_checks = 0
        self.listings = 0

    def is_dir(self, path):
        self.dir_checks += 1
        return path in ("", "Photos")

    def entries(self, path):
        self.listings += 1
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

    def test_repeated_directory_checks_use_cached_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            backend = FakeBackend()
            hydrator = Hydrator(mount, backend)
            for _ in range(20):
                hydrator.ensure(str(mount), "M")
            self.assertEqual(backend.dir_checks, 1)
            self.assertEqual(backend.listings, 1)

    def test_cleanup_preserves_unrelated_files_in_existing_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "other-folder"
            mount.mkdir()
            hydrator = Hydrator(mount, FakeBackend())
            hydrator.ensure(str(mount), "M")
            (mount / "my-file.txt").write_text("keep me", encoding="utf-8")
            hydrator.cleanup()
            self.assertEqual((mount / "my-file.txt").read_text(encoding="utf-8"), "keep me")
            self.assertFalse((mount / "Photos").exists())
            self.assertFalse((mount / "hello.txt").exists())

    def test_new_local_directory_clears_previous_missing_lookup(self):
        class MissingBackend(FakeBackend):
            def is_dir(self, path):
                if path == "new-dir":
                    raise FileNotFoundError(path)
                return super().is_dir(path)

        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            hydrator = Hydrator(mount, MissingBackend())
            with self.assertRaises(FileNotFoundError):
                hydrator.ensure(str(mount / "new-dir"), "M")
            hydrator.ensure(str(mount / "new-dir"), "P")
            (mount / "new-dir").mkdir()
            hydrator.ensure(str(mount / "new-dir"), "M")

    def test_external_change_prevents_overwrite(self):
        class ConflictBackend(FakeBackend):
            def __init__(self):
                super().__init__()
                self.remote_version = (7, 1)
                self.uploads = []

            def version(self, path):
                return self.remote_version

            def upload(self, path, source, overwrite):
                self.uploads.append(path)

        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            backend = ConflictBackend()
            hydrator = Hydrator(mount, backend)
            hydrator.ensure(str(mount), "M")
            hydrator.ensure(str(mount / "hello.txt"), "O")
            original = (mount / "hello.txt").stat()
            backend.remote_version = (7, 2)
            hydrator.ensure(str(mount / "hello.txt"), "W")
            (mount / "hello.txt").write_text("changes", encoding="utf-8")
            os.utime(mount / "hello.txt", ns=(original.st_atime_ns, original.st_mtime_ns))
            with self.assertRaisesRegex(OSError, "changed outside"):
                hydrator.sync()
            self.assertEqual(backend.uploads, [])
            self.assertEqual((mount / "hello.txt").read_text(encoding="utf-8"), "changes")


if __name__ == "__main__":
    unittest.main()
