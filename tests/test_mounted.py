import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from termux_nas.mounted import run_mounted_shell


class FakeBackend:
    def __init__(self):
        self.uploads = {}

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

    def upload(self, path, source, overwrite):
        self.uploads[path] = source.read()


class MountedShellTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"), "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_huge_file_is_not_downloaded(self):
        class HugeBackend(FakeBackend):
            def __init__(self):
                super().__init__()
                self.reads = []

            def is_dir(self, path):
                if path == "huge.bin":
                    return False
                if path == "":
                    return True
                raise FileNotFoundError(path)

            def entries(self, path):
                return [{"name": "huge.bin", "mode": "-rw-r--r--", "size": 500 * 1024**3}]

            def stat_size(self, path):
                if path == "huge.bin":
                    return 500 * 1024**3
                raise FileNotFoundError(path)

            def read(self, path):
                self.reads.append(path)
                return io.BytesIO(b"")

        with tempfile.TemporaryDirectory() as temporary:
            backend = HugeBackend()
            with patch.dict(os.environ, {"HOME": temporary}):
                status = run_mounted_shell(
                    backend, "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                    [shutil.which("bash"), "-c", 'cat "$HOME/nas/huge.bin" >/dev/null'],
                )
            self.assertNotEqual(status, 0)
            self.assertEqual(backend.reads, [])

    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"), "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_all_shares_folder_is_writable(self):
        class AllSharesBackend:
            def __init__(self):
                self.uploads = {}

            def write_probe_roots(self):
                return ["Shared"]

            def is_dir(self, path):
                if path in ("", "Shared"):
                    return True
                raise FileNotFoundError(path)

            def entries(self, path):
                if path == "":
                    return [{"name": "Shared", "mode": "drwxr-xr-x", "size": 0}]
                return []

            def upload(self, path, source, overwrite):
                self.uploads[path] = source.read()

        with tempfile.TemporaryDirectory() as temporary:
            backend = AllSharesBackend()
            with patch.dict(os.environ, {"HOME": temporary}):
                status = run_mounted_shell(
                    backend, "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                    [shutil.which("bash"), "-c", 'cd "$HOME/nas/Shared" && printf test > file.txt'],
                )
            self.assertEqual(status, 0)
            self.assertEqual(backend.uploads["Shared/file.txt"], b"test")

    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT") and shutil.which("vi"),
                         "set TERMUX_NAS_TEST_PROOT and install vi to run the editor integration test")
    def test_normal_vi_can_create_file_without_stale_swap(self):
        class AllSharesBackend:
            def __init__(self):
                self.uploads = {}

            def write_probe_roots(self):
                return ["Shared"]

            def is_dir(self, path):
                if path in ("", "Shared"):
                    return True
                raise FileNotFoundError(path)

            def entries(self, path):
                if path == "":
                    return [{"name": "Shared", "mode": "drwxr-xr-x", "size": 0}]
                return [{"name": "existing.txt", "mode": "-rw-r--r--", "size": 4}]

            def stat_size(self, path):
                if path == "Shared/existing.txt":
                    return 4
                raise FileNotFoundError(path)

            def read(self, path):
                if path == "Shared/existing.txt":
                    return io.BytesIO(b"old\n")
                raise FileNotFoundError(path)

            def upload(self, path, source, overwrite):
                self.uploads[path] = source.read()

        with tempfile.TemporaryDirectory() as temporary:
            backend = AllSharesBackend()
            script = ('cd "$HOME/nas/Shared" && '
                      'vi -Nu NONE -es new.txt -c "normal! ihello" -c wq && '
                      'vi -Nu NONE -es existing.txt -c "normal! ggInew " -c wq')
            with patch.dict(os.environ, {"HOME": temporary}):
                status = run_mounted_shell(
                    backend, "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                    [shutil.which("bash"), "-c", script],
                )
            self.assertEqual(status, 0)
            self.assertEqual(backend.uploads["Shared/new.txt"], b"hello\n")
            self.assertEqual(backend.uploads["Shared/existing.txt"], b"new old\n")
            self.assertFalse(any(name.endswith((".swp", ".swo", ".swx")) for name in backend.uploads))

    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"), "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_normal_commands_read_local_and_remote_and_upload(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / "local.txt").write_text("local content\n", encoding="utf-8")
            bash = shutil.which("bash")
            script = 'cd "$HOME/nas" && find . -type f && cat hello.txt && cat "$HOME/local.txt" && cp "$HOME/local.txt" "$HOME/nas/new.txt"'
            backend = FakeBackend()
            with patch.dict(os.environ, {"HOME": str(home)}):
                status = run_mounted_shell(backend, "nas", os.environ["TERMUX_NAS_TEST_PROOT"], [bash, "-c", script])
            self.assertEqual(status, 0)
            self.assertEqual(backend.uploads["new.txt"], b"local content\n")
            self.assertFalse((home / "nas").exists())

    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"), "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_failed_upload_keeps_local_copy(self):
        class DeniedBackend(FakeBackend):
            def upload(self, path, source, overwrite):
                raise PermissionError("NAS account cannot write")

        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            bash = shutil.which("bash")
            with patch.dict(os.environ, {"HOME": str(home)}):
                status = run_mounted_shell(DeniedBackend(), "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                                           [bash, "-c", 'printf "save me" > "$HOME/nas/new.txt"'])
            self.assertNotEqual(status, 0)
            self.assertEqual((home / "nas" / "new.txt").read_text(), "save me")

    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"), "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_existing_custom_folder_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            mount = home / "other-folder"
            mount.mkdir()
            bash = shutil.which("bash")
            script = 'cd "$HOME/other-folder" && cat hello.txt'
            with patch.dict(os.environ, {"HOME": str(home)}):
                status = run_mounted_shell(FakeBackend(), "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                                           [bash, "-c", script], mount_path=str(mount))
            self.assertEqual(status, 0)
            self.assertTrue(mount.is_dir())
            self.assertEqual(list(mount.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
