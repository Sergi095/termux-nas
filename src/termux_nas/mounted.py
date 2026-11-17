"""Run a Termux shell with a process-scoped, read-only NAS directory."""

import os
import shutil
import stat
import subprocess
import tempfile
import threading
from pathlib import Path

from .config import validate_mount_name
from .hydrate import HydrationServer, Hydrator


def _patched_proot(explicit: str | None) -> Path:
    candidates = [explicit, os.environ.get("TERMUX_NAS_PROOT"), str(Path.home() / "repos/proot-nasfs/src/proot")]
    for candidate in candidates:
        if candidate:
            path = Path(candidate).expanduser().resolve()
            if path.is_file() and os.access(path, os.X_OK):
                return path
            if candidate == explicit:
                raise ValueError(f"Patched PRoot is not executable: {path}")
    raise ValueError("Build the patched PRoot in ~/repos/proot-nasfs, or pass --proot PATH")


def _environment(mount: Path, socket_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PROOT_NAS_MOUNT"] = str(mount)
    environment["PROOT_NAS_SOCKET"] = str(socket_path)
    prefix = environment.get("PREFIX")
    if prefix:
        app_loader = Path(prefix).parent / "applib" / "libproot-loader.so"
        if app_loader.is_file():
            environment.setdefault("PROOT_LOADER", str(app_loader.resolve()))
    return environment


def run_mounted_shell(backend, mount_name: str, proot_path: str | None = None,
                      command: list[str] | None = None) -> int:
    """Show a NAS tree at ~/mount_name for processes launched by patched PRoot."""
    validate_mount_name(mount_name)
    proot = _patched_proot(proot_path)
    bash = shutil.which("bash")
    if bash is None:
        raise ValueError("bash is required for nas-mount")
    home = Path.home()
    mount = home / mount_name
    if os.path.lexists(mount):
        raise ValueError(f"{mount} already exists; choose another mount name")

    with tempfile.TemporaryDirectory(prefix="termux-nas-mount-") as temporary:
        socket_path = Path(temporary) / "nas.sock"
        mount.mkdir(mode=0o700)
        try:
            with HydrationServer(str(socket_path), Hydrator(mount, backend)) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    environment = _environment(mount, socket_path)
                    # A previous experimental PRoot build allows writes to its
                    # local cache. Refuse it before presenting the NAS as mounted.
                    ls = shutil.which("ls")
                    chmod = shutil.which("chmod")
                    if ls is None or chmod is None:
                        raise ValueError("ls and chmod are required for nas-mount")
                    read_check = subprocess.run(
                        [str(proot), "-r", "/", ls, str(mount)],
                        env=environment, cwd=home, stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE, text=True,
                    )
                    if read_check.returncode:
                        raise ValueError(f"PRoot could not read the NAS folder: {read_check.stderr.strip()}")
                    write_check = subprocess.run(
                        [str(proot), "-r", "/", chmod, "711", str(mount)],
                        env=environment, cwd=home, stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE, text=True,
                    )
                    if write_check.returncode == 0 or stat.S_IMODE(mount.stat().st_mode) != 0o700:
                        raise ValueError("Patched PRoot lacks the read-only guard; rebuild it with the latest patch")
                    if command is None:
                        print(f"NAS is available at {mount} in this shell (read only). Exit to disconnect.")
                    return subprocess.call(
                        [str(proot), "-r", "/", *(command or [bash, "-i"])],
                        env=environment, cwd=home,
                    )
                finally:
                    server.shutdown()
                    thread.join(timeout=2)
        finally:
            if mount.is_dir() and not mount.is_symlink():
                os.chmod(mount, 0o700)
                shutil.rmtree(mount)
