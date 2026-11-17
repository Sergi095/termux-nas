"""Verify unmodified find/ls/cat under the experimental PRoot hook."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python run_host_demo.py /path/to/patched/proot", file=sys.stderr)
        return 2
    proot = Path(sys.argv[1]).resolve()
    fixture_server = Path(__file__).with_name("fixture_server.py")
    package_root = Path(__file__).resolve().parents[2] / "src"
    with tempfile.TemporaryDirectory(prefix="nasfs-host-demo-") as directory:
        root = Path(directory)
        source = root / "source"
        mount = root / "mount"
        (source / "Photos").mkdir(parents=True)
        mount.mkdir()
        (source / "hello.txt").write_text("from NAS fixture\n", encoding="utf-8")
        (source / "Photos" / "pic.txt").write_text("picture\n", encoding="utf-8")
        (root / "local.txt").write_text("local Termux file\n", encoding="utf-8")
        socket_path = root / "nas.sock"
        environment = os.environ.copy()
        # Google Play Termux cannot execute the loader extracted under its
        # writable tmp directory. Its APK ships an executable loader instead.
        prefix = environment.get("PREFIX")
        if prefix:
            app_loader = Path(prefix).parent / "applib" / "libproot-loader.so"
            if app_loader.is_file():
                environment.setdefault("PROOT_LOADER", str(app_loader.resolve()))
        environment.update({
            "PYTHONPATH": str(package_root),
            "NASFS_MOUNT": str(mount),
            "NASFS_SOURCE": str(source),
            "NASFS_SOCKET": str(socket_path),
            "PROOT_NAS_MOUNT": str(mount),
            "PROOT_NAS_SOCKET": str(socket_path),
        })
        server = subprocess.Popen([sys.executable, str(fixture_server)], env=environment)
        try:
            for _ in range(100):
                if socket_path.exists():
                    break
                if server.poll() is not None:
                    raise RuntimeError("Fixture server exited before creating the socket")
                time.sleep(0.02)
            else:
                raise TimeoutError("Fixture server did not create the socket")

            cases = [
                ([shutil.which("find"), str(mount), "-type", "f", "-print"], "Photos/pic.txt"),
                ([shutil.which("ls"), "-la", str(mount)], "hello.txt"),
                ([shutil.which("cat"), str(mount / "hello.txt")], "from NAS fixture"),
                ([shutil.which("bash"), "-c", 'cd "$1" && pwd && cat "$2"', "bash", str(mount), str(root / "local.txt")], "local Termux file"),
            ]
            for command, expected in cases:
                result = subprocess.run([str(proot), "-r", "/", *command], env=environment, text=True, capture_output=True, timeout=20)
                if result.returncode or expected not in result.stdout:
                    raise AssertionError(f"{command}: {result.returncode}\n{result.stdout}\n{result.stderr}")
            print("PASS: unmodified find, ls, cat and bash cd see NAS and local files")
            return 0
        finally:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
