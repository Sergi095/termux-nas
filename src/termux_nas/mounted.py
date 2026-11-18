"""Run a Termux shell with a process-scoped NAS directory."""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from .config import validate_mount_name
from .hydrate import HydrationServer, Hydrator


def _patched_proot(explicit: str | None) -> Path:
    installed = Path(os.environ["PREFIX"]) / "libexec/termux-nas/proot" if os.environ.get("PREFIX") else None
    candidates = [explicit, os.environ.get("TERMUX_NAS_PROOT"), installed,
                  Path.home() / "repos/proot-nasfs/src/proot"]
    for candidate in candidates:
        if candidate:
            path = Path(candidate).expanduser().resolve()
            if path.is_file() and os.access(path, os.X_OK):
                return path
            if candidate == explicit:
                raise ValueError(f"Patched PRoot is not executable: {path}")
    raise ValueError("Run bash install.sh to install the patched PRoot, or pass --proot PATH")


def _environment(mount: Path, socket_path: Path, marker: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PROOT_NAS_MOUNT"] = str(mount)
    environment["PROOT_NAS_SOCKET"] = str(socket_path)
    environment["PROOT_NAS_DIRTY_MARKER"] = str(marker)
    prefix = environment.get("PREFIX")
    if prefix:
        app_loader = Path(prefix).parent / "applib" / "libproot-loader.so"
        if app_loader.is_file():
            environment.setdefault("PROOT_LOADER", str(app_loader.resolve()))
    return environment


def run_mounted_shell(backend, mount_name: str, proot_path: str | None = None,
                      command: list[str] | None = None, mount_path: str | None = None) -> int:
    """Show a NAS tree at an empty folder for processes launched by patched PRoot."""
    validate_mount_name(mount_name)
    proot = _patched_proot(proot_path)
    bash = shutil.which("bash")
    if bash is None:
        raise ValueError("bash is required for nas-mount")
    home = Path.home()
    chosen = os.path.expanduser(mount_path) if mount_path else str(home / mount_name)
    mount = Path(os.path.abspath(chosen))
    if mount.is_symlink():
        raise ValueError(f"Mount folder must not be a symlink: {mount}")
    if mount.exists():
        if not mount.is_dir() or any(mount.iterdir()):
            raise ValueError(f"Mount folder must be an empty directory: {mount}")
        created_mount = False
    else:
        mount.mkdir(mode=0o700)
        created_mount = True
        try:
            mount.chmod(0o700)
        except OSError:
            pass
    original_mode = stat.S_IMODE(mount.stat().st_mode)

    with tempfile.TemporaryDirectory(prefix="termux-nas-mount-") as temporary:
        Path(temporary).chmod(0o700)
        socket_path = Path(temporary) / "nas.sock"
        marker = Path(temporary) / "nas.dirty"
        rcfile = Path(temporary) / "bashrc"
        rcfile.write_text(
            'if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n'
            '_nas_sync_prompt() { local previous=$?; if [ -e "$PROOT_NAS_DIRTY_MARKER" ]; then command nas _sync "$PROOT_NAS_SOCKET"; fi; return "$previous"; }\n'
            'PROMPT_COMMAND="_nas_sync_prompt${PROMPT_COMMAND:+; $PROMPT_COMMAND}"\n',
            encoding="utf-8",
        )
        hydrator = Hydrator(mount, backend, marker=marker)
        preserve_cache = False
        try:
            with HydrationServer(str(socket_path), hydrator) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    environment = _environment(mount, socket_path, marker)
                    # Unsupported metadata writes must remain blocked by PRoot.
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
                    if write_check.returncode == 0 or stat.S_IMODE(mount.stat().st_mode) != original_mode:
                        raise ValueError("Patched PRoot lacks the metadata guard; rebuild it with the latest patch")
                    probe_roots = [mount]
                    if hasattr(backend, "write_probe_roots"):
                        probe_roots.extend(mount / name for name in backend.write_probe_roots())
                    for root in probe_roots:
                        probe = root / f".nas-write-probe-{os.getpid()}"
                        try:
                            write_probe = subprocess.run(
                                [str(proot), "-r", "/", bash, "-c", 'printf x > "$1"', "bash", str(probe)],
                                env=environment, cwd=home, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True,
                            )
                            if write_probe.returncode or not probe.is_file() or not marker.exists():
                                detail = write_probe.stderr.strip()
                                raise ValueError(f"PRoot cannot write to NAS folder {root}: {detail or 'write probe failed'}")
                        finally:
                            probe.unlink(missing_ok=True)
                    hydrator.sync()
                    if command is None:
                        print(f"NAS is available at {mount}. Changes sync after each command and on exit.")
                    shell_status = subprocess.call(
                        [str(proot), "-r", "/", *(command or [bash, "--rcfile", str(rcfile), "-i"])],
                        env=environment, cwd=home,
                    )
                    try:
                        hydrator.sync()
                    except Exception as error:
                        preserve_cache = True
                        print(f"nas: sync failed: {error}; unsynced files remain at {mount}", file=sys.stderr)
                        return shell_status or 1
                    return shell_status
                finally:
                    server.shutdown()
                    thread.join(timeout=2)
        finally:
            if not preserve_cache and not hydrator.dirty and mount.is_dir() and not mount.is_symlink():
                hydrator.cleanup()
                if created_mount:
                    try:
                        mount.rmdir()
                    except OSError:
                        pass
