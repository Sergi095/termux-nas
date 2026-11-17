"""Small adapter around smbprotocol's high-level smbclient API."""

import stat as stat_module
from typing import BinaryIO


class SMBBackend:
    def __init__(self, host: str, share: str, user: str, password: str, port: int = 445):
        import smbclient
        from smbprotocol.header import NtStatus

        self._client = smbclient
        self._root = "\\\\" + host + "\\" + share
        self._port = port
        self._missing_statuses = {
            NtStatus.STATUS_NO_SUCH_FILE,
            NtStatus.STATUS_OBJECT_NAME_NOT_FOUND,
            NtStatus.STATUS_OBJECT_PATH_NOT_FOUND,
        }
        smbclient.register_session(host, username=user, password=password, port=port)

    def _unc(self, path: str) -> str:
        return self._root + ("\\" + path.replace("/", "\\") if path else "")

    def _stat(self, path: str):
        try:
            return self._client.stat(self._unc(path), port=self._port)
        except OSError as error:
            if getattr(error, "ntstatus", None) in self._missing_statuses:
                raise FileNotFoundError(path) from error
            raise

    def is_dir(self, path: str) -> bool:
        return stat_module.S_ISDIR(self._stat(path).st_mode)

    def stat_size(self, path: str) -> int:
        return self._stat(path).st_size

    def listdir(self, path: str) -> list[str]:
        return sorted(self._client.listdir(self._unc(path), port=self._port), key=str.casefold)

    def entries(self, path: str) -> list[dict]:
        result = []
        for entry in self._client.scandir(self._unc(path), port=self._port):
            child = path.rstrip("/") + "/" + entry.name if path else entry.name
            details = self._stat(child)
            result.append({
                "name": entry.name,
                "mode": stat_module.filemode(details.st_mode),
                "size": details.st_size,
                "mtime": details.st_mtime,
            })
        return sorted(result, key=lambda item: item["name"].casefold())

    def read(self, path: str) -> BinaryIO:
        return self._client.open_file(self._unc(path), mode="rb", port=self._port)

    def write(self, path: str) -> BinaryIO:
        return self._client.open_file(self._unc(path), mode="xb", port=self._port)
