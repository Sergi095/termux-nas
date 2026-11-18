import io
import os
import shlex
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
    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"),
                         "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_restricted_dfs_child_does_not_break_root_listing(self):
        class DfsBackend:
            def __init__(self):
                self.restricted_lookups = 0

            def is_dir(self, path):
                if path in ("", "Allowed", "Restricted"):
                    return True
                if path == "Allowed/readme.txt":
                    return False
                raise FileNotFoundError(path)

            def entries(self, path):
                if path == "":
                    return [{"name": "Allowed", "mode": "drwxr-xr-x", "size": 0},
                            {"name": "Restricted", "mode": "drwxr-xr-x", "size": 0}]
                if path == "Allowed":
                    return [{"name": "readme.txt", "mode": "-rw-r--r--", "size": 4}]
                self.restricted_lookups += 1
                raise PermissionError("SMB access denied for Restricted")

            def stat_size(self, path):
                if path == "Allowed/readme.txt":
                    return 4
                raise FileNotFoundError(path)

            def read_range(self, path, offset, size):
                return b"okay"[offset:offset + size]

        with tempfile.TemporaryDirectory() as temporary:
            backend = DfsBackend()
            output = Path(temporary) / "listing.txt"
            script = (f'ls -l "$HOME/nas" > {shlex.quote(str(output))} && '
                      f'cd "$HOME/nas/Allowed" && cat readme.txt >> {shlex.quote(str(output))}')
            with patch.dict(os.environ, {"HOME": temporary}):
                status = run_mounted_shell(
                    backend, "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                    [shutil.which("bash"), "-c", script], streaming=True,
                )
            self.assertEqual(status, 0)
            self.assertIn("Allowed", output.read_text())
            self.assertIn("Restricted", output.read_text())
            self.assertTrue(output.read_text().endswith("okay"))
            self.assertEqual(backend.restricted_lookups, 0)

    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"), "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_streaming_reads_end_of_huge_file_without_downloading_it(self):
        size = 500 * 1024**3

        class HugeBackend(FakeBackend):
            def __init__(self):
                super().__init__()
                self.ranges = []
                self.suffix = b"tail"

            def is_dir(self, path):
                if path == "":
                    return True
                if path == "huge.bin":
                    return False
                raise FileNotFoundError(path)

            def entries(self, path):
                return [{"name": "huge.bin", "mode": "-rw-r--r--", "size": size}]

            def stat_size(self, path):
                if path == "huge.bin":
                    return size
                raise FileNotFoundError(path)

            def read(self, path):
                raise AssertionError("Full download must not run")

            def read_range(self, path, offset, count):
                self.ranges.append((path, offset, count))
                return self.suffix if offset == size - 4 else b""

            def write_range(self, path, offset, data):
                if path != "huge.bin" or offset != size - 4:
                    raise AssertionError("Unexpected remote write")
                self.suffix = data
                return len(data)

        with tempfile.TemporaryDirectory() as temporary:
            backend = HugeBackend()
            script = ('import os; f=open(os.path.expanduser("~/nas/huge.bin"), "r+b", buffering=0); '
                      f'f.seek({size - 4}); print(f.read(4).decode()); '
                      f'os.pwrite(f.fileno(), b"edit", {size - 4}); '
                      f'print(os.pread(f.fileno(), 4, {size - 4}).decode()); '
                      'print(os.fstat(f.fileno()).st_blocks)')
            output = Path(temporary) / "range-output.txt"
            with patch.dict(os.environ, {"HOME": temporary}):
                status = run_mounted_shell(
                    backend, "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                    [shutil.which("bash"), "-c",
                     f'python -c {shlex.quote(script)} > {shlex.quote(str(output))}'],
                    streaming=True,
                )
            self.assertEqual(status, 0)
            self.assertEqual(output.read_text().splitlines()[:2], ["tail", "edit"])
            self.assertLess(int(output.read_text().splitlines()[2]) * 512, 1024 * 1024)
            self.assertEqual(backend.suffix, b"edit")
            self.assertEqual(backend.ranges, [("huge.bin", size - 4, 4),
                                              ("huge.bin", size - 4, 4)])

    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT"), "set TERMUX_NAS_TEST_PROOT to run the PRoot integration test")
    def test_streaming_overwrites_existing_remote_bytes(self):
        class RangeBackend(FakeBackend):
            def __init__(self):
                super().__init__()
                self.data = bytearray(b"old\n")
                self.writes = []

            def is_dir(self, path):
                if path == "":
                    return True
                if path == "file.txt":
                    return False
                raise FileNotFoundError(path)

            def entries(self, path):
                return [{"name": "file.txt", "mode": "-rw-r--r--", "size": len(self.data)}]

            def stat_size(self, path):
                if path == "file.txt":
                    return len(self.data)
                raise FileNotFoundError(path)

            def read(self, path):
                raise AssertionError("Full download must not run")

            def read_range(self, path, offset, count):
                return bytes(self.data[offset:offset + count])

            def write_range(self, path, offset, data):
                self.writes.append((path, offset, data))
                self.data[offset:offset + len(data)] = data
                return len(data)

            def truncate(self, path, size):
                del self.data[size:]

            def upload(self, path, source, overwrite):
                raise AssertionError("Whole-file upload must not run")

        with tempfile.TemporaryDirectory() as temporary:
            backend = RangeBackend()
            script = ('import os,mmap,errno; p=os.path.expanduser("~/nas/file.txt"); '
                      'f=open(p,"r+b",buffering=0); f.seek(1); f.write(b"X"); '
                      'os.pwrite(f.fileno(),b"Y",2); f.truncate(3); '
                      'f.seek(0); print(f.read(3).decode())\n'
                      'try:\n mmap.mmap(f.fileno(),1,access=mmap.ACCESS_READ)\n'
                      'except OSError as error:\n'
                      ' assert error.errno == errno.EOPNOTSUPP, error\n'
                      ' print("mmap blocked")\n'
                      'else:\n raise AssertionError("mmap returned local placeholder bytes")\n'
                      'try:\n os.fchmod(f.fileno(),0o777)\n'
                      'except OSError as error:\n'
                      ' assert error.errno == errno.EOPNOTSUPP, error\n'
                      ' print("fchmod blocked")\n'
                      'else:\n raise AssertionError("fchmod changed only local permissions")')
            output = Path(temporary) / "range-output.txt"
            with patch.dict(os.environ, {"HOME": temporary}):
                status = run_mounted_shell(
                    backend, "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                    [shutil.which("bash"), "-c",
                     f'python -c {shlex.quote(script)} > {shlex.quote(str(output))}'],
                    streaming=True,
                )
            self.assertEqual(status, 0)
            self.assertEqual(output.read_text().splitlines(), ["oXY", "mmap blocked", "fchmod blocked"])
            self.assertEqual(backend.writes, [("file.txt", 1, b"X"), ("file.txt", 2, b"Y")])
            self.assertEqual(backend.data, b"oXY")

    @unittest.skipUnless(os.environ.get("TERMUX_NAS_TEST_PROOT") and shutil.which("vi"),
                         "set TERMUX_NAS_TEST_PROOT and install vi to test remote editing")
    def test_streaming_vi_edits_without_whole_file_transfer(self):
        class RangeBackend(FakeBackend):
            def __init__(self):
                super().__init__()
                self.files = {"existing.txt": bytearray(b"old\n")}

            def is_dir(self, path):
                if path == "":
                    return True
                if path in self.files:
                    return False
                raise FileNotFoundError(path)

            def entries(self, path):
                return [{"name": name, "mode": "-rw-r--r--", "size": len(data)}
                        for name, data in self.files.items()]

            def stat_size(self, path):
                if path not in self.files:
                    raise FileNotFoundError(path)
                return len(self.files[path])

            def read(self, path):
                raise AssertionError("Full download must not run")

            def upload(self, path, source, overwrite):
                raise AssertionError("Whole-file upload must not run")

            def read_range(self, path, offset, count):
                return bytes(self.files[path][offset:offset + count])

            def write_range(self, path, offset, data):
                content = self.files.setdefault(path, bytearray())
                if len(content) < offset:
                    content.extend(b"\0" * (offset - len(content)))
                content[offset:offset + len(data)] = data
                return len(data)

            def create_file(self, path):
                if path in self.files:
                    raise FileExistsError(path)
                # The ordinary Termux path must stay empty while this PRoot
                # session creates a file in its private bind directory.
                self.assert_guest_mount_empty()
                self.files[path] = bytearray()

            def truncate(self, path, size):
                content = self.files[path]
                if size < len(content):
                    del content[size:]
                elif size > len(content):
                    content.extend(b"\0" * (size - len(content)))

            def remove(self, path):
                del self.files[path]

            def rename(self, source, destination):
                self.files[destination] = self.files.pop(source)

        with tempfile.TemporaryDirectory() as temporary:
            backend = RangeBackend()
            backend.assert_guest_mount_empty = lambda: self.assertEqual(
                list((Path(temporary) / "nas").iterdir()), [])
            script = ('cd "$HOME/nas" && '
                      'vi -Nu NONE -es new.txt -c "normal! ihello" -c wq && '
                      'vi -Nu NONE -es existing.txt -c "normal! ggInew " -c wq && '
                      'printf copy > copy.txt && '
                      'cp copy.txt cloned.txt && '
                      'mv cloned.txt moved.txt && '
                      'rm copy.txt')
            with patch.dict(os.environ, {"HOME": temporary}):
                status = run_mounted_shell(
                    backend, "nas", os.environ["TERMUX_NAS_TEST_PROOT"],
                    [shutil.which("bash"), "-c", script], streaming=True,
                )
            self.assertEqual(status, 0)
            self.assertEqual(bytes(backend.files["new.txt"]), b"hello\n")
            self.assertEqual(bytes(backend.files["existing.txt"]), b"new old\n")
            self.assertEqual(bytes(backend.files["moved.txt"]), b"copy")
            self.assertEqual(set(backend.files), {"new.txt", "existing.txt", "moved.txt"})
            self.assertFalse((Path(temporary) / "nas").exists())

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
                      'strace -o "$HOME/vi.trace" -e trace=unlink,unlinkat,openat,write,pwrite64,close,fsync,ftruncate vi -V9"$HOME/vim-new.log" -Nu NONE -es new.txt -c "normal! ihello" -c wq && '
                      'vi -V9"$HOME/vim-existing.log" -Nu NONE -es existing.txt -c "normal! ggInew " -c wq')
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
