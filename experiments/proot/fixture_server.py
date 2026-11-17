"""Serve a local directory through the same hydration protocol as the SMB backend."""

import os
from pathlib import Path

from termux_nas.hydrate import HydrationServer, Hydrator


class LocalBackend:
    def __init__(self, source: Path):
        self.source = source

    def _path(self, relative: str) -> Path:
        path = self.source / relative
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    def is_dir(self, relative: str) -> bool:
        return self._path(relative).is_dir()

    def entries(self, relative: str) -> list[dict]:
        return [
            {
                "name": child.name,
                "mode": "d" if child.is_dir() else "-",
                "size": child.stat().st_size,
            }
            for child in self._path(relative).iterdir()
        ]

    def stat_size(self, relative: str) -> int:
        return self._path(relative).stat().st_size

    def read(self, relative: str):
        return self._path(relative).open("rb")


def main() -> None:
    source = Path(os.environ["NASFS_SOURCE"])
    mount = Path(os.environ["NASFS_MOUNT"])
    socket_path = os.environ["NASFS_SOCKET"]
    with HydrationServer(socket_path, Hydrator(mount, LocalBackend(source))) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
