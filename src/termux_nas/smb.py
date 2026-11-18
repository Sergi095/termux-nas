"""Small adapter around smbprotocol's high-level smbclient API."""

import errno
import importlib
import shutil
import stat as stat_module
import sys
from importlib.metadata import distribution
from typing import BinaryIO


def _smbclient_module():
    """Load smbprotocol's package ahead of Impacket's bin/smbclient.py script."""
    package_root = str(distribution("smbprotocol").locate_file(""))
    sys.path.insert(0, package_root)
    try:
        client = importlib.import_module("smbclient")
    finally:
        sys.path.pop(0)
    if not hasattr(client, "register_session"):
        raise ImportError(f"Expected smbprotocol's smbclient package, got {client.__file__}")
    return client


def _rpc_connection(host: str, user: str, password: str, port: int):
    from impacket.smbconnection import SMBConnection

    domain, separator, username = user.partition("\\")
    if not separator:
        username, domain = user, ""
    connection = SMBConnection(host, host, sess_port=port, timeout=15)
    connection.login(username, password, domain)
    return connection


class SMBBackend:
    def __init__(self, host: str, share: str, user: str, password: str, port: int = 445):
        from smbprotocol.header import NtStatus

        self._client = _smbclient_module()
        self._root = "\\\\" + host + "\\" + share
        self._host = host
        self._share = share
        self._user = user
        self._password = password
        self._port = port
        # smbclient can follow a DFS referral to another server. Pass these
        # credentials on every call so the referred server can authenticate.
        self._session_kwargs = {"username": user, "password": password, "port": port}
        self._missing_statuses = {
            NtStatus.STATUS_NO_SUCH_FILE,
            NtStatus.STATUS_OBJECT_NAME_NOT_FOUND,
            NtStatus.STATUS_OBJECT_PATH_NOT_FOUND,
        }
        self._client.register_session(host, **self._session_kwargs)

    def _unc(self, path: str) -> str:
        return self._root + ("\\" + path.replace("/", "\\") if path else "")

    def _stat(self, path: str):
        try:
            return self._client.stat(self._unc(path), **self._session_kwargs)
        except OSError as error:
            if getattr(error, "ntstatus", None) in self._missing_statuses:
                raise FileNotFoundError(path) from error
            raise

    def is_dir(self, path: str) -> bool:
        return stat_module.S_ISDIR(self._stat(path).st_mode)

    def stat_size(self, path: str) -> int:
        return self._stat(path).st_size

    def version(self, path: str) -> tuple[int, int]:
        details = self._stat(path)
        return details.st_size, details.st_mtime_ns

    def listdir(self, path: str) -> list[str]:
        return sorted(self._client.listdir(self._unc(path), **self._session_kwargs), key=str.casefold)

    def entries(self, path: str) -> list[dict]:
        result = []
        for entry in self._client.scandir(self._unc(path), **self._session_kwargs):
            if entry.is_symlink():
                continue
            info = getattr(entry, "smb_info", None)
            if info is not None:
                is_directory = entry.is_dir(follow_symlinks=False)
                mode = "drwxr-xr-x" if is_directory else "-rw-r--r--"
                size = info.end_of_file
                mtime = info.last_write_time.timestamp()
            elif entry.is_dir(follow_symlinks=False):
                # Older smbclient releases omit smb_info. The directory entry
                # still carries its type; stat on a restricted DFS link can
                # fail even though the parent namespace is listable.
                mode = "drwxr-xr-x"
                size = 0
                mtime = 0
            else:
                child = path.rstrip("/") + "/" + entry.name if path else entry.name
                details = self._stat(child)
                mode = stat_module.filemode(details.st_mode)
                size = details.st_size
                mtime = details.st_mtime
            result.append({
                "name": entry.name,
                "mode": mode,
                "size": size,
                "mtime": mtime,
            })
        return sorted(result, key=lambda item: item["name"].casefold())

    def read(self, path: str) -> BinaryIO:
        return self._client.open_file(self._unc(path), mode="rb", **self._session_kwargs)

    def read_range(self, path: str, offset: int, size: int) -> bytes:
        with self._client.open_file(self._unc(path), mode="rb", buffering=0, **self._session_kwargs) as source:
            source.seek(offset)
            return source.read(size)

    def write_range(self, path: str, offset: int, data: bytes) -> int:
        with self._client.open_file(self._unc(path), mode="r+b", buffering=0, **self._session_kwargs) as target:
            target.seek(offset)
            written = 0
            while written < len(data):
                count = target.write(data[written:])
                if count is None or count <= 0:
                    raise OSError("SMB write did not make progress")
                written += count
            target.flush()
            return written

    def create_file(self, path: str) -> None:
        with self._client.open_file(self._unc(path), mode="xb", buffering=0, **self._session_kwargs):
            pass

    def truncate(self, path: str, size: int) -> None:
        with self._client.open_file(self._unc(path), mode="r+b", buffering=0, **self._session_kwargs) as target:
            target.truncate(size)

    def write(self, path: str) -> BinaryIO:
        return self._client.open_file(self._unc(path), mode="xb", **self._session_kwargs)

    def upload(self, path: str, source: BinaryIO, overwrite: bool) -> None:
        mode = "r+b" if overwrite else "xb"
        with self._client.open_file(self._unc(path), mode=mode, **self._session_kwargs) as output:
            if overwrite:
                output.seek(0)
                output.truncate(0)
            shutil.copyfileobj(source, output)

    def mkdir(self, path: str) -> None:
        self._client.mkdir(self._unc(path), **self._session_kwargs)

    def remove(self, path: str) -> None:
        self._client.remove(self._unc(path), **self._session_kwargs)

    def rmdir(self, path: str) -> None:
        self._client.rmdir(self._unc(path), **self._session_kwargs)

    def rename(self, source: str, destination: str) -> None:
        connection = _rpc_connection(self._host, self._user, self._password, self._port)
        try:
            connection.rename(self._share, source.replace("/", "\\"), destination.replace("/", "\\"))
        finally:
            connection.logoff()


class SMBAllSharesBackend:
    """Expose accessible disk shares as directories below one virtual root."""

    def __init__(self, host: str, user: str, password: str, port: int = 445):
        try:
            connection = _rpc_connection(host, user, password, port)
            shares = connection.listShares()
        except Exception as error:
            raise ValueError(f"Could not list shares on {host}; use --share for a single share: {error}") from error
        finally:
            if "connection" in locals():
                try:
                    connection.logoff()
                except Exception:
                    pass

        self._shares: dict[str, SMBBackend] = {}
        for entry in shares:
            name = str(entry["shi1_netname"]).rstrip("\x00")
            share_type = int(entry["shi1_type"]) & 0xFFFF
            if (share_type != 0 or name.upper() == "IPC$" or not name or
                    any(char in name for char in "/\\\x00")):
                continue
            backend = SMBBackend(host, name, user, password, port)
            try:
                if backend.is_dir(""):
                    self._shares[name] = backend
            except OSError:
                # Servers often advertise shares this account cannot access.
                continue
        if not self._shares:
            raise ValueError(f"No accessible file shares found on {host}; specify --share if discovery is disabled")

    def write_probe_roots(self) -> list[str]:
        return list(self._shares)

    def _select(self, path: str) -> tuple[SMBBackend, str]:
        share, _, child = path.partition("/")
        backend = self._shares.get(share)
        if backend is None:
            raise FileNotFoundError(path)
        return backend, child

    def is_dir(self, path: str) -> bool:
        if not path:
            return True
        backend, child = self._select(path)
        return True if not child else backend.is_dir(child)

    def entries(self, path: str) -> list[dict]:
        if not path:
            return [{"name": name, "mode": "drwxr-xr-x", "size": 0, "mtime": 0}
                    for name in sorted(self._shares, key=str.casefold)]
        backend, child = self._select(path)
        return backend.entries(child)

    def listdir(self, path: str) -> list[str]:
        if not path:
            return sorted(self._shares, key=str.casefold)
        backend, child = self._select(path)
        return backend.listdir(child)

    def stat_size(self, path: str) -> int:
        backend, child = self._select(path)
        return backend.stat_size(child)

    def version(self, path: str) -> tuple[int, int]:
        backend, child = self._select(path)
        return backend.version(child)

    def read(self, path: str) -> BinaryIO:
        backend, child = self._select(path)
        return backend.read(child)

    def read_range(self, path: str, offset: int, size: int) -> bytes:
        backend, child = self._select(path)
        return backend.read_range(child, offset, size)

    def write_range(self, path: str, offset: int, data: bytes) -> int:
        backend, child = self._select(path)
        if not child:
            raise PermissionError("Cannot write to an SMB share root")
        return backend.write_range(child, offset, data)

    def create_file(self, path: str) -> None:
        backend, child = self._select(path)
        if not child:
            raise PermissionError("Cannot create an SMB share")
        backend.create_file(child)

    def truncate(self, path: str, size: int) -> None:
        backend, child = self._select(path)
        if not child:
            raise PermissionError("Cannot truncate an SMB share")
        backend.truncate(child, size)

    def write(self, path: str) -> BinaryIO:
        backend, child = self._select(path)
        return backend.write(child)

    def upload(self, path: str, source: BinaryIO, overwrite: bool) -> None:
        backend, child = self._select(path)
        if not child:
            raise PermissionError("Cannot replace an SMB share")
        backend.upload(child, source, overwrite)

    def mkdir(self, path: str) -> None:
        backend, child = self._select(path)
        if not child:
            raise PermissionError("Cannot create an SMB share")
        backend.mkdir(child)

    def remove(self, path: str) -> None:
        backend, child = self._select(path)
        if not child:
            raise PermissionError("Cannot delete an SMB share")
        backend.remove(child)

    def rmdir(self, path: str) -> None:
        backend, child = self._select(path)
        if not child:
            raise PermissionError("Cannot delete an SMB share")
        backend.rmdir(child)

    def rename(self, source: str, destination: str) -> None:
        source_backend, source_child = self._select(source)
        destination_backend, destination_child = self._select(destination)
        if source_backend is not destination_backend:
            raise OSError(errno.EXDEV, "Cannot rename across SMB shares")
        if not source_child or not destination_child:
            raise PermissionError("Cannot rename an SMB share")
        source_backend.rename(source_child, destination_child)
