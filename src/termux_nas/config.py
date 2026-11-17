"""Save connection details locally; never save SMB passwords."""

import json
import os
import re
import tempfile
from pathlib import Path


def config_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "termux-nas" / "connections.json"


def load() -> dict[str, dict[str, object]]:
    path = config_file()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid connections file")
    return data


def save(connections: dict[str, dict[str, object]]) -> None:
    path = config_file()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".connections-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(connections, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def validate(name: str, host: str, share: str | None, user: str, port: int, mount_name: str = "nas") -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("Connection name must use letters, digits, dots, dashes or underscores")
    if not host or any(char in host for char in "/\\\x00"):
        raise ValueError("Invalid NAS host")
    if share is not None and (not share or any(char in share for char in "/\\\x00")):
        raise ValueError("Invalid SMB share")
    if not user:
        raise ValueError("SMB username is required")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    validate_mount_name(mount_name)


def validate_mount_name(mount_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", mount_name) or mount_name in (".", ".."):
        raise ValueError("Mount name must be a single directory name")


def normalize_mount_path(folder: str) -> str:
    if not folder or any(char in folder for char in "\x00\n\r"):
        raise ValueError("Invalid mount folder path")
    path = Path(os.path.abspath(os.path.expanduser(folder)))
    if path == Path("/"):
        raise ValueError("The filesystem root cannot be a NAS folder")
    return str(path)
