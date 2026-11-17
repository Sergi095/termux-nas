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

    def listdir(self, path: str) -> list[str]:
        return sorted(self._client.listdir(self._unc(path)), key=str.casefold)

    def read(self, path: str) -> BinaryIO:
        return self._client.open_file(self._unc(path), mode="rb")

    def write(self, path: str) -> BinaryIO:
        return self._client.open_file(self._unc(path), mode="xb")
