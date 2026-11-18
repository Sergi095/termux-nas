import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from termux_nas.hydrate import HydrationServer, Hydrator


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
    def test_repeated_authentication_error_is_logged_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            output = io.StringIO()
            with HydrationServer(str(Path(temporary) / "nas.sock"), Hydrator(mount, FakeBackend())) as server:
                with redirect_stderr(output):
                    server.report_error("filesystem bridge", RuntimeError("SpnegoError (1): (16)"))
                    server.report_error("filesystem bridge", RuntimeError("SpnegoError (1): (16)"))
            self.assertEqual(output.getvalue().count("SpnegoError (1): (16)"), 1)

    def test_created_share_directory_remains_writable_with_restrictive_umask(self):
        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            hydrator = Hydrator(mount, FakeBackend())
            old_umask = os.umask(0o222)
            try:
                hydrator.ensure(str(mount), "M")
            finally:
                os.umask(old_umask)
            self.assertTrue(os.access(mount / "Photos", os.W_OK | os.X_OK))
            self.assertTrue(os.access(mount / "hello.txt", os.W_OK))

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

    def test_large_remote_file_is_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            backend = FakeBackend()
            hydrator = Hydrator(mount, backend, max_download_bytes=6, free_space_reserve=0)
            hydrator.ensure(str(mount), "M")
            with self.assertRaisesRegex(OSError, "session download limit"):
                hydrator.ensure(str(mount / "hello.txt"), "O")
            self.assertEqual(backend.reads, [])
            self.assertEqual(hydrator.downloaded_bytes, 0)

    def test_download_respects_remaining_phone_space(self):
        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            backend = FakeBackend()
            hydrator = Hydrator(mount, backend, max_download_bytes=100,
                                free_space_reserve=20)
            hydrator.ensure(str(mount), "M")
            with patch("termux_nas.hydrate.shutil.disk_usage",
                       return_value=SimpleNamespace(free=26)):
                with self.assertRaisesRegex(OSError, "leave less than"):
                    hydrator.ensure(str(mount / "hello.txt"), "O")
            self.assertEqual(backend.reads, [])

    def test_download_stops_if_remote_file_exceeds_reported_size(self):
        class GrowingBackend(FakeBackend):
            def read(self, path):
                self.reads.append(path)
                return io.BytesIO(b"content is longer than reported")

        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            backend = GrowingBackend()
            hydrator = Hydrator(mount, backend, max_download_bytes=8, free_space_reserve=0)
            hydrator.ensure(str(mount), "M")
            with self.assertRaisesRegex(OSError, "session download limit"):
                hydrator.ensure(str(mount / "hello.txt"), "O")
            self.assertEqual(hydrator.downloaded_bytes, 0)
            self.assertFalse(any(mount.glob(".nas-*")))

    def test_file_timestamp_stays_stable_during_hydration(self):
        class TimestampBackend(FakeBackend):
            def entries(self, path):
                return [{"name": "hello.txt", "mode": "-rw-r--r--", "size": 7,
                         "mtime": 1_700_000_000}]

        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            hydrator = Hydrator(mount, TimestampBackend())
            hydrator.ensure(str(mount), "M")
            original_mtime = (mount / "hello.txt").stat().st_mtime_ns
            hydrator.ensure(str(mount / "hello.txt"), "O")
            self.assertEqual((mount / "hello.txt").stat().st_mtime_ns, original_mtime)

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

    def test_deleted_local_temporary_file_is_not_recreated(self):
        class MissingFileBackend(FakeBackend):
            def is_dir(self, path):
                if path == ".edit.swp":
                    raise FileNotFoundError(path)
                return super().is_dir(path)

            def stat_size(self, path):
                if path == ".edit.swp":
                    raise FileNotFoundError(path)
                return super().stat_size(path)

        with tempfile.TemporaryDirectory() as temporary:
            mount = Path(temporary) / "mount"
            mount.mkdir()
            hydrator = Hydrator(mount, MissingFileBackend())
            swap = mount / ".edit.swp"
            hydrator.ensure(str(swap), "W")
            swap.touch()
            hydrator.ensure(str(swap), "P")
            swap.unlink()
            with self.assertRaises(FileNotFoundError):
                hydrator.ensure(str(swap), "M")
            self.assertFalse(swap.exists())

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
