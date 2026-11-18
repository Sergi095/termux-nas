"""Local cache and write-through journal for the PRoot NAS path hook.

The cache is a private backing directory for traced processes, not a mount.
SMB changes are synchronized when a command finishes and when the shell exits.
"""

import errno
import os
import shutil
import socket
import socketserver
import struct
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RemoteEntry:
    directory: bool
    inode: tuple[int, int]
    signature: tuple[int, int] | None
    version: tuple[int, int] | None = None


class Hydrator:
    def __init__(self, mount: Path, backend, metadata_ttl: float = 2.0, marker: Path | None = None,
                 max_download_bytes: int = 256 * 1024 * 1024,
                 free_space_reserve: int = 512 * 1024 * 1024,
                 streaming: bool = False):
        self.mount = mount
        self.backend = backend
        self.metadata_ttl = metadata_ttl
        self.marker = marker
        self.max_download_bytes = max_download_bytes
        self.free_space_reserve = free_space_reserve
        self.downloaded_bytes = 0
        self.streaming = streaming
        self.hydrated: set[str] = set()
        self.kinds: dict[str, bool] = {}
        self.listed_until: dict[str, float] = {}
        self.missing_until: dict[str, float] = {}
        self.created: set[Path] = set()
        self.remote: dict[str, RemoteEntry] = {}
        self.touched: set[str] = set()
        self.dirty = False
        self.lock = threading.RLock()

    @staticmethod
    def _allow_cache_write(path: Path, directory: bool = False) -> None:
        try:
            path.chmod(0o700 if directory else 0o600)
        except OSError:
            # Some Android shared-storage providers do not support chmod.
            pass

    def _remember(self, relative: str, path: Path, directory: bool, replace: bool = False) -> None:
        if relative in self.remote and not replace:
            return
        details = path.stat()
        signature = None if directory else (details.st_size, details.st_mtime_ns)
        self.remote[relative] = RemoteEntry(directory, (details.st_dev, details.st_ino), signature)

    def _mkdir(self, directory: Path) -> None:
        if directory == self.mount or directory.is_dir():
            return
        self._mkdir(directory.parent)
        directory.mkdir(mode=0o700)
        self.created.add(directory)
        self._allow_cache_write(directory, directory=True)

    def cleanup(self) -> None:
        """Remove bridge-owned cache entries without deleting other folder contents."""
        with self.lock:
            for path in sorted(self.created, key=lambda item: len(item.parts), reverse=True):
                try:
                    if path.is_dir() and not path.is_symlink():
                        path.rmdir()
                    else:
                        path.unlink()
                except (FileNotFoundError, OSError):
                    # A nonempty directory may now contain files created outside
                    # the traced shell; leave those files in place.
                    pass

    def _local_entries(self) -> dict[str, RemoteEntry]:
        result = {}
        for directory, names, files in os.walk(self.mount):
            for name in [*names, *files]:
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError(f"Symbolic links are not supported in the NAS folder: {path}")
                details = path.stat()
                is_directory = path.is_dir()
                relative = path.relative_to(self.mount).as_posix()
                signature = None if is_directory else (details.st_size, details.st_mtime_ns)
                result[relative] = RemoteEntry(is_directory, (details.st_dev, details.st_ino), signature)
        return result

    def _rename_known(self, source: str, destination: str) -> None:
        updated = {}
        for path, entry in self.remote.items():
            if path == source or path.startswith(source + "/"):
                updated[destination + path[len(source):]] = entry
            elif path != destination and not path.startswith(destination + "/"):
                updated[path] = entry
        self.remote = updated
        created = set()
        for path in self.created:
            relative = path.relative_to(self.mount).as_posix()
            if relative == source or relative.startswith(source + "/"):
                created.add(self.mount / (destination + relative[len(source):]))
            else:
                created.add(path)
        self.created = created

    def sync(self) -> None:
        """Apply local command results to SMB; leave the cache in place on error."""
        with self.lock:
            if not self.dirty:
                return
            if self.streaming:
                self._sync_streaming()
                return
            local = self._local_entries()
            by_inode = {entry.inode: path for path, entry in local.items()}

            # Rename directories first so remote descendants move together.
            for directory in (True, False):
                for source, entry in list(self.remote.items()):
                    if source not in self.remote or entry.directory != directory or source in local:
                        continue
                    destination = by_inode.get(entry.inode)
                    if not destination or destination == source:
                        continue
                    self.backend.rename(source, destination)
                    self._rename_known(source, destination)

            for path, entry in sorted(local.items(), key=lambda item: item[0].count("/")):
                if entry.directory and path not in self.remote:
                    self.backend.mkdir(path)
                    self.remote[path] = entry
                    self.created.add(self.mount / path)

            for path, entry in local.items():
                if entry.directory:
                    continue
                previous = self.remote.get(path)
                if (path not in self.touched and previous and
                        previous.inode == entry.inode and previous.signature == entry.signature):
                    continue
                if previous and previous.version is not None and self.backend.version(path) != previous.version:
                    raise OSError(f"NAS file changed outside this session: {path}")
                with (self.mount / path).open("rb") as source:
                    self.backend.upload(path, source, overwrite=previous is not None)
                if hasattr(self.backend, "version"):
                    try:
                        entry.version = self.backend.version(path)
                    except OSError:
                        pass
                self.remote[path] = entry
                self.created.add(self.mount / path)

            for path, entry in sorted(list(self.remote.items()), key=lambda item: item[0].count("/"), reverse=True):
                if path in local:
                    continue
                if entry.directory:
                    self.backend.rmdir(path)
                else:
                    self.backend.remove(path)
                del self.remote[path]
                self.kinds.pop(path, None)
                self.hydrated.discard(path)

            self.listed_until.clear()
            self.missing_until.clear()
            self.touched.clear()
            self.dirty = False
            if self.marker is not None:
                self.marker.unlink(missing_ok=True)

    def _sync_streaming(self) -> None:
        """Sync namespace changes without copying any placeholder file contents."""
        local = self._local_entries()
        by_inode = {entry.inode: path for path, entry in local.items()}
        for directory in (True, False):
            for source, entry in list(self.remote.items()):
                if source not in self.remote or entry.directory != directory or source in local:
                    continue
                destination = by_inode.get(entry.inode)
                if destination and destination != source:
                    self.backend.rename(source, destination)
                    self._rename_known(source, destination)
        for path, entry in sorted(local.items(), key=lambda item: item[0].count("/")):
            if path in self.remote:
                continue
            if entry.directory:
                self.backend.mkdir(path)
            else:
                self.backend.create_file(path)
            self.remote[path] = entry
            self.created.add(self.mount / path)
        for path, entry in sorted(list(self.remote.items()), key=lambda item: item[0].count("/"), reverse=True):
            if path in local:
                continue
            if entry.directory:
                self.backend.rmdir(path)
            else:
                self.backend.remove(path)
            del self.remote[path]
            self.kinds.pop(path, None)
            self.hydrated.discard(path)
        self.touched.clear()
        self.dirty = False
        if self.marker is not None:
            self.marker.unlink(missing_ok=True)

    def ensure(self, raw_path: str, action: str) -> None:
        absolute = Path(os.path.normpath(raw_path))
        if not absolute.is_relative_to(self.mount):
            return
        relative = absolute.relative_to(self.mount).as_posix()
        if relative == ".":
            relative = ""
        with self.lock:
            now = time.monotonic()
            if action in ("W", "P", "R"):
                self.dirty = True
            if action == "W" and relative and not self.streaming:
                self.touched.add(relative)
            if relative and absolute.exists():
                self.missing_until.pop(relative, None)
            if relative in self.remote and not absolute.exists() and action not in ("W", "P", "R"):
                raise FileNotFoundError(relative)
            if action not in ("W", "P", "R") and self.missing_until.get(relative, 0) > now:
                raise FileNotFoundError(relative)
            directory = self.kinds.get(relative)
            if directory is None:
                if absolute.exists() and relative:
                    self.kinds[relative] = absolute.is_dir()
                    directory = self.kinds[relative]
                    if relative not in self.remote:
                        if not directory:
                            self.hydrated.add(relative)
                        return
            if directory is None:
                try:
                    directory = self.backend.is_dir(relative)
                except FileNotFoundError:
                    if action in ("W", "P", "R") and relative:
                        self.ensure(str(absolute.parent), "M")
                        return
                    self.missing_until[relative] = now + self.metadata_ttl
                    raise
                self.kinds[relative] = directory
            if directory:
                if relative and relative not in self.remote:
                    return
                if relative and action in ("P", "R"):
                    return
                if self.listed_until.get(relative, 0) > now or (self.dirty and relative in self.listed_until):
                    return
                self._mkdir(absolute)
                if relative:
                    self._remember(relative, absolute, True)
                for entry in self.backend.entries(relative):
                    name = entry["name"]
                    if name in (".", "..") or any(char in name for char in "/\\\x00"):
                        continue
                    child = absolute / name
                    child_relative = f"{relative}/{name}" if relative else name
                    child_is_dir = entry["mode"].startswith("d")
                    self.kinds[child_relative] = child_is_dir
                    self.missing_until.pop(child_relative, None)
                    if child_is_dir:
                        self._mkdir(child)
                    elif not child.exists():
                        with child.open("xb") as output:
                            output.truncate(entry["size"])
                        if entry.get("mtime") is not None:
                            os.utime(child, (entry["mtime"], entry["mtime"]))
                        self.created.add(child)
                        self._allow_cache_write(child)
                    self._remember(child_relative, child, child_is_dir)
                self.listed_until[relative] = time.monotonic() + self.metadata_ttl
                return

            if action == "P":
                if absolute.exists():
                    self._remember(relative, absolute, False)
                return
            self._mkdir(absolute.parent)
            if self.streaming:
                if not absolute.exists():
                    try:
                        size = self.backend.stat_size(relative)
                    except FileNotFoundError:
                        if action in ("W", "P", "R"):
                            return
                        raise
                    with absolute.open("xb") as output:
                        output.truncate(size)
                    self.created.add(absolute)
                    self._allow_cache_write(absolute)
                    self._remember(relative, absolute, False)
                return
            if action in ("O", "W", "R") and relative not in self.hydrated:
                size = self.backend.stat_size(relative)
                remaining = self.max_download_bytes - self.downloaded_bytes
                if size > remaining:
                    raise OSError(errno.EFBIG,
                                  f"NAS file {relative} is too large for the "
                                  f"{self.max_download_bytes // (1024 * 1024)} MiB session download limit")
                if shutil.disk_usage(absolute.parent).free < size + self.free_space_reserve:
                    raise OSError(errno.ENOSPC,
                                  f"NAS file {relative} would leave less than "
                                  f"{self.free_space_reserve // (1024 * 1024)} MiB free")
                visible_stat = absolute.stat() if absolute.exists() else None
                descriptor, temporary = tempfile.mkstemp(prefix=".nas-", dir=absolute.parent)
                try:
                    copied = 0
                    with os.fdopen(descriptor, "wb") as output, self.backend.read(relative) as source:
                        while chunk := source.read(1024 * 1024):
                            if len(chunk) > remaining - copied:
                                raise OSError(errno.EFBIG, f"NAS file {relative} exceeded the session download limit")
                            if shutil.disk_usage(absolute.parent).free < len(chunk) + self.free_space_reserve:
                                raise OSError(errno.ENOSPC, f"NAS file {relative} would exhaust phone storage")
                            output.write(chunk)
                            copied += len(chunk)
                    if visible_stat is not None:
                        os.utime(temporary, ns=(visible_stat.st_atime_ns, visible_stat.st_mtime_ns))
                    os.replace(temporary, absolute)
                    self.downloaded_bytes += copied
                    self._allow_cache_write(absolute)
                    self.hydrated.add(relative)
                    self.created.add(absolute)
                    self._remember(relative, absolute, False, replace=True)
                    if hasattr(self.backend, "version"):
                        try:
                            self.remote[relative].version = self.backend.version(relative)
                        except OSError:
                            pass
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            elif not absolute.exists():
                # Check the server before creating a placeholder.  A deleted
                # local temporary file can still have a cached kind here;
                # opening it first would resurrect it as an empty file when
                # the server reports that it does not exist.
                size = self.backend.stat_size(relative)
                with absolute.open("xb") as output:
                    output.truncate(size)
                self.created.add(absolute)
                self._allow_cache_write(absolute)
                self._remember(relative, absolute, False)

    def read_range(self, raw_path: str, offset: int, size: int) -> bytes:
        if not self.streaming or offset < 0 or size < 0 or size > 1024 * 1024:
            raise ValueError("Invalid NAS range request")
        absolute = Path(os.path.normpath(raw_path))
        if not absolute.is_relative_to(self.mount):
            raise ValueError("NAS range path is outside the mount")
        relative = absolute.relative_to(self.mount).as_posix()
        return self.backend.read_range(relative, offset, size)

    def write_range(self, raw_path: str, offset: int, data: bytes) -> int:
        if not self.streaming or offset < 0 or len(data) > 1024 * 1024:
            raise ValueError("Invalid NAS range write")
        absolute = Path(os.path.normpath(raw_path))
        if not absolute.is_relative_to(self.mount):
            raise ValueError("NAS range path is outside the mount")
        relative = absolute.relative_to(self.mount).as_posix()
        with self.lock:
            written = self.backend.write_range(relative, offset, data)
            if absolute.exists():
                end = offset + written
                if absolute.stat().st_size < end:
                    os.truncate(absolute, end)
                if relative not in self.remote:
                    self._remember(relative, absolute, False)
                    self.created.add(absolute)
            return written

    def open_commit(self, raw_path: str, flags: int) -> None:
        if not self.streaming:
            raise ValueError("Remote open is only valid in streaming mode")
        absolute = Path(os.path.normpath(raw_path))
        if not absolute.is_relative_to(self.mount):
            raise ValueError("Remote open path is outside the mount")
        relative = absolute.relative_to(self.mount).as_posix()
        with self.lock:
            try:
                self.backend.stat_size(relative)
                exists = True
            except FileNotFoundError:
                exists = False
            if flags & os.O_CREAT:
                if exists and flags & os.O_EXCL:
                    raise FileExistsError(relative)
                if not exists:
                    self.backend.create_file(relative)
                    exists = True
            if flags & os.O_TRUNC:
                if not exists:
                    raise FileNotFoundError(relative)
                self.backend.truncate(relative, 0)
            if absolute.exists() and relative not in self.remote:
                self._remember(relative, absolute, False)
                self.created.add(absolute)

    def truncate_range(self, raw_path: str, size: int) -> None:
        if not self.streaming or size < 0:
            raise ValueError("Invalid NAS truncate request")
        absolute = Path(os.path.normpath(raw_path))
        if not absolute.is_relative_to(self.mount):
            raise ValueError("NAS truncate path is outside the mount")
        relative = absolute.relative_to(self.mount).as_posix()
        with self.lock:
            self.backend.truncate(relative, size)
            os.truncate(absolute, size)


class HydrationHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        action = self._read_exact(1)
        raw_length = self._read_exact(4)
        if action == b"S" and raw_length == b"\x00\x00\x00\x00":
            try:
                self.server.hydrator.sync()
                self.request.sendall(b"0")
            except Exception as error:
                message = str(error).encode("utf-8", errors="replace")[:4096]
                self.request.sendall(b"2" + struct.pack("!I", len(message)) + message)
            return
        if action not in (b"O", b"M", b"W", b"P", b"R", b"D", b"U", b"F", b"T") or raw_length is None:
            return
        length = struct.unpack("!I", raw_length)[0]
        if length > 4096:
            self.request.sendall(b"2")
            return
        raw_path = self._read_exact(length)
        if raw_path is None:
            return
        if action == b"F":
            raw_flags = self._read_exact(4)
            if raw_flags is None:
                return
            try:
                self.server.hydrator.open_commit(raw_path.decode("utf-8"),
                                                 struct.unpack("!I", raw_flags)[0])
                self.request.sendall(b"0")
            except Exception as error:
                print(f"nas-mount: remote open failed: {error}", file=sys.stderr)
                self.request.sendall(b"2")
            return
        if action == b"T":
            raw_size = self._read_exact(8)
            if raw_size is None:
                return
            try:
                self.server.hydrator.truncate_range(raw_path.decode("utf-8"),
                                                    struct.unpack("!Q", raw_size)[0])
                self.request.sendall(b"0")
            except Exception as error:
                print(f"nas-mount: remote truncate failed: {error}", file=sys.stderr)
                self.request.sendall(b"2")
            return
        if action in (b"D", b"U"):
            raw_range = self._read_exact(12)
            if raw_range is None:
                return
            offset, requested = struct.unpack("!QI", raw_range)
            if requested > 1024 * 1024:
                self.request.sendall(b"2")
                return
            try:
                if action == b"D":
                    data = self.server.hydrator.read_range(raw_path.decode("utf-8"), offset, requested)
                    self.request.sendall(b"0" + struct.pack("!I", len(data)) + data)
                else:
                    data = self._read_exact(requested)
                    if data is None:
                        return
                    written = self.server.hydrator.write_range(raw_path.decode("utf-8"), offset, data)
                    self.request.sendall(b"0" + struct.pack("!I", written))
            except Exception as error:
                print(f"nas-mount: remote I/O failed: {error}", file=sys.stderr)
                self.request.sendall(b"2")
            return
        try:
            self.server.hydrator.ensure(raw_path.decode("utf-8"), action.decode("ascii"))
            self.request.sendall(b"0")
        except FileNotFoundError:
            self.request.sendall(b"1")
        except Exception as error:
            print(f"nas-mount: filesystem bridge error: {error}", file=sys.stderr)
            self.request.sendall(b"2")

    def _read_exact(self, count: int) -> bytes | None:
        data = bytearray()
        while len(data) < count:
            part = self.request.recv(count - len(data))
            if not part:
                return None
            data.extend(part)
        return bytes(data)


class HydrationServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, socket_path: str, hydrator: Hydrator):
        self.hydrator = hydrator
        super().__init__(socket_path, HydrationHandler)


def request_sync(socket_path: str) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.sendall(b"S\x00\x00\x00\x00")
        reply = client.recv(1)
        if reply == b"0":
            return
        if reply != b"2":
            raise OSError("NAS sync service did not respond")
        raw_length = bytearray()
        while len(raw_length) < 4:
            part = client.recv(4 - len(raw_length))
            if not part:
                raise OSError("NAS sync service closed unexpectedly")
            raw_length.extend(part)
        length = struct.unpack("!I", raw_length)[0]
        message = bytearray()
        while len(message) < length:
            part = client.recv(length - len(message))
            if not part:
                raise OSError("NAS sync service closed unexpectedly")
            message.extend(part)
        raise OSError(message.decode("utf-8", errors="replace"))
