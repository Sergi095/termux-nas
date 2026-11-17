"""Serve NAS operations to commands in a normal Bash session.

The socket is private to the current Termux user. This is command routing,
not a kernel filesystem mount.
"""

import json
import os
import shutil
import socket
import socketserver
import sys
from datetime import datetime
from pathlib import Path


def normalize(cwd: str, requested: str) -> str:
    if requested == "~":
        requested = str(Path.home())
    elif requested.startswith("~/"):
        requested = str(Path.home() / requested[2:])
    return os.path.normpath(requested if os.path.isabs(requested) else os.path.join(cwd, requested))


def remote_path(absolute: str, mount: str) -> str | None:
    absolute = os.path.normpath(absolute)
    mount = os.path.normpath(mount)
    if absolute == mount:
        return ""
    if absolute.startswith(mount + os.sep):
        return absolute[len(mount) + 1 :].replace(os.sep, "/")
    return None


class BridgeServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, socket_path: str, backend, mount: str):
        self.backend = backend
        self.mount = mount
        super().__init__(socket_path, BridgeHandler)

    def dispatch(self, request: dict) -> tuple[dict, object | None]:
        action = request["action"]
        path = request.get("path", "")
        remote = remote_path(path, self.mount)
        if remote is None:
            raise ValueError("Path is outside the NAS folder")
        if action == "isdir":
            return {"ok": True, "value": self.backend.is_dir(remote)}, None
        if action == "ls":
            if request.get("long"):
                return {"ok": True, "entries": self.backend.entries(remote)}, None
            return {"ok": True, "names": self.backend.listdir(remote)}, None
        if action == "cat":
            return {"ok": True, "stream": True}, self.backend.read(remote)
        if action == "cp":
            destination = request["destination"]
            dest_remote = remote_path(destination, self.mount)
            if dest_remote is None and os.path.isdir(destination):
                destination = os.path.join(destination, os.path.basename(remote))
            elif dest_remote is not None:
                try:
                    if self.backend.is_dir(dest_remote):
                        dest_remote = "/".join(filter(None, (dest_remote, os.path.basename(remote))))
                except FileNotFoundError:
                    pass
            with self.backend.read(remote) as source:
                if dest_remote is None:
                    with open(destination, "xb") as target:
                        shutil.copyfileobj(source, target)
                else:
                    with self.backend.write(dest_remote) as target:
                        shutil.copyfileobj(source, target)
            return {"ok": True}, None
        if action == "put":
            source = request["source"]
            if remote_path(source, self.mount) is not None:
                raise ValueError("Source must be a local file")
            try:
                if self.backend.is_dir(remote):
                    remote = "/".join(filter(None, (remote, os.path.basename(source))))
            except FileNotFoundError:
                pass
            with open(source, "rb") as local, self.backend.write(remote) as target:
                shutil.copyfileobj(local, target)
            return {"ok": True}, None
        raise ValueError(f"Unknown action: {action}")


class BridgeHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        header_sent = False
        try:
            request = json.loads(self.rfile.readline())
            header, stream = self.server.dispatch(request)
            self.wfile.write((json.dumps(header) + "\n").encode())
            header_sent = True
            if stream is not None:
                with stream:
                    shutil.copyfileobj(stream, self.wfile)
        except Exception as error:
            if not header_sent:
                try:
                    self.wfile.write((json.dumps({"ok": False, "error": str(error)}) + "\n").encode())
                except OSError:
                    pass


def request(action: str, **fields):
    socket_path = os.environ.get("TERMUX_NAS_SOCKET")
    if not socket_path:
        raise ValueError("This command works only inside nas shell")
    connection = socket.socket(socket.AF_UNIX)
    connection.connect(socket_path)
    connection.sendall((json.dumps({"action": action, **fields}) + "\n").encode())
    connection.shutdown(socket.SHUT_WR)
    reader = connection.makefile("rb")
    header = json.loads(reader.readline())
    if not header.get("ok"):
        reader.close()
        connection.close()
        raise OSError(header.get("error", "NAS request failed"))
    return connection, reader, header


def helper(argv: list[str]) -> int:
    if not argv:
        raise ValueError("Missing helper command")
    command, *args = argv
    if command == "_normalize" and len(args) == 2:
        print(normalize(args[0], args[1]))
        return 0
    if command == "_isdir" and len(args) == 1:
        conn, reader, header = request("isdir", path=args[0])
        reader.close()
        conn.close()
        return 0 if header["value"] else 1
    if command == "_ls" and len(args) == 2:
        path, flags = args
        if any(flag not in "alh1" for flag in flags):
            raise ValueError("Remote ls supports only -a, -l, -h and -1")
        conn, reader, header = request("ls", path=path, long="l" in flags)
        if "l" in flags:
            for entry in header["entries"]:
                if entry["name"].startswith(".") and "a" not in flags:
                    continue
                size = entry["size"]
                if "h" in flags:
                    for unit in ("B", "K", "M", "G", "T"):
                        if size < 1024 or unit == "T":
                            size = f"{size:.1f}{unit}" if unit != "B" else f"{size}B"
                            break
                        size /= 1024
                stamp = datetime.fromtimestamp(entry["mtime"]).strftime("%b %d %H:%M")
                print(f"{entry['mode']} {str(size):>8} {stamp} {entry['name']}")
        else:
            for name in header["names"]:
                if not name.startswith(".") or "a" in flags:
                    print(name)
        reader.close()
        conn.close()
        return 0
    if command == "_cat" and len(args) == 1:
        conn, reader, _ = request("cat", path=args[0])
        shutil.copyfileobj(reader, sys.stdout.buffer)
        reader.close()
        conn.close()
        return 0
    if command == "_cp" and len(args) == 2:
        mount = os.environ["TERMUX_NAS_MOUNT"]
        source, destination = args
        if remote_path(source, mount) is not None:
            action, fields = "cp", {"path": source, "destination": destination}
        elif remote_path(destination, mount) is not None:
            action, fields = "put", {"source": source, "path": destination}
        else:
            raise ValueError("At least one path must be on the NAS")
        conn, reader, _ = request(action, **fields)
        reader.close()
        conn.close()
        return 0
    raise ValueError("Invalid NAS helper arguments")
