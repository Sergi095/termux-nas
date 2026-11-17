"""Small adapter around smbprotocol's high-level smbclient API."""

import stat as stat_module
from typing import BinaryIO


class SMBBackend:
    def __init__(self, host: str, share: str, user: str, password: str, port: int = 445):
        import smbclient

        self._client = smbclient
        self._root = "\\\\" + host + "\\" + share
        smbclient.register_session(host, username=user, password=password, port=port)

    def _unc(self, path: str) -> str:
        return self._root + ("\\" + path.replace("/", "\\") if path else "")

    def is_dir(self, path: str) -> bool:
        return stat_module.S_ISDIR(self._client.stat(self._unc(path)).st_mode)

    def stat_size(self, path: str) -> int:
        return self._client.stat(self._unc(path)).st_size

    def listdir(self, path: str) -> list[str]:
        return sorted(self._client.listdir(self._unc(path)), key=str.casefold)

    def entries(self, path: str) -> list[dict]:
        result = []
        for entry in self._client.scandir(self._unc(path)):
            details = entry.stat()
            result.append({
                "name": entry.name,
                "mode": stat_module.filemode(details.st_mode),
                "size": details.st_size,
                "mtime": details.st_mtime,
            })
        return sorted(result, key=lambda item: item["name"].casefold())

    def read(self, path: str) -> BinaryIO:
        return self._client.open_file(self._unc(path), mode="rb")

    def write(self, path: str) -> BinaryIO:
        return self._client.open_file(self._unc(path), mode="xb")
