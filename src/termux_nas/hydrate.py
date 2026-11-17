"""Experimental read-only local cache for the PRoot NAS path hook.

The cache is a private backing directory for traced processes, not a mount.
Writes and cache coherence are not implemented.
"""

import os
import shutil
import socketserver
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path


class Hydrator:
    def __init__(self, mount: Path, backend, metadata_ttl: float = 2.0):
        self.mount = mount
        self.backend = backend
        self.metadata_ttl = metadata_ttl
        self.hydrated: set[str] = set()
        self.kinds: dict[str, bool] = {}
        self.listed_until: dict[str, float] = {}
        self.missing_until: dict[str, float] = {}
        self.lock = threading.Lock()

    def ensure(self, raw_path: str, action: str) -> None:
        absolute = Path(os.path.normpath(raw_path))
        if not absolute.is_relative_to(self.mount):
            return
        relative = absolute.relative_to(self.mount).as_posix()
        if relative == ".":
            relative = ""
        with self.lock:
            now = time.monotonic()
            if self.missing_until.get(relative, 0) > now:
                raise FileNotFoundError(relative)
            directory = self.kinds.get(relative)
            if directory is None:
                try:
                    directory = self.backend.is_dir(relative)
                except FileNotFoundError:
                    self.missing_until[relative] = now + self.metadata_ttl
                    raise
                self.kinds[relative] = directory
            if directory:
                if self.listed_until.get(relative, 0) > now:
                    return
                absolute.mkdir(parents=True, exist_ok=True)
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
                        child.mkdir(exist_ok=True)
                    elif not child.exists():
                        with child.open("xb") as output:
                            output.truncate(entry["size"])
                self.listed_until[relative] = time.monotonic() + self.metadata_ttl
                return

            absolute.parent.mkdir(parents=True, exist_ok=True)
            if action == "O" and relative not in self.hydrated:
                descriptor, temporary = tempfile.mkstemp(prefix=".nas-", dir=absolute.parent)
                try:
                    with os.fdopen(descriptor, "wb") as output, self.backend.read(relative) as source:
                        shutil.copyfileobj(source, output)
                    os.replace(temporary, absolute)
                    self.hydrated.add(relative)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            elif not absolute.exists():
                with absolute.open("xb") as output:
                    output.truncate(self.backend.stat_size(relative))


class HydrationHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        action = self._read_exact(1)
        raw_length = self._read_exact(4)
        if action not in (b"O", b"M") or raw_length is None:
            return
        length = struct.unpack("!I", raw_length)[0]
        if length > 4096:
            self.request.sendall(b"2")
            return
        raw_path = self._read_exact(length)
        if raw_path is None:
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
