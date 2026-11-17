"""Run a real Bash shell with a private SMB command bridge."""

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from .bash import RCFILE
from .bridge import BridgeServer


def run_shell(backend, mount_name: str) -> int:
    bash = shutil.which("bash")
    if bash is None:
        raise ValueError("bash is required for nas shell")
    mount = Path.home() / mount_name
    if os.path.lexists(mount):
        raise ValueError(f"{mount} already exists; choose another --mount-name")

    with tempfile.TemporaryDirectory(prefix="termux-nas-") as temporary:
        directory = Path(temporary)
        shadow = directory / "shadow"
        shadow.mkdir()
        socket_path = str(directory / "bridge.sock")
        rcfile = directory / "bashrc"
        rcfile.write_text(RCFILE, encoding="utf-8")
        mount.symlink_to(shadow, target_is_directory=True)
        try:
            with BridgeServer(socket_path, backend, str(mount)) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                environment = os.environ.copy()
                environment["TERMUX_NAS_SOCKET"] = socket_path
                environment["TERMUX_NAS_MOUNT"] = str(mount)
                try:
                    return subprocess.call([bash, "--rcfile", str(rcfile), "-i"], env=environment)
                finally:
                    server.shutdown()
                    thread.join(timeout=2)
        finally:
            if mount.is_symlink() and os.readlink(mount) == str(shadow):
                mount.unlink()
