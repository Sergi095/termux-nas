import io
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from smbprotocol.exceptions import SMBOSError
from smbprotocol.header import NtStatus

from termux_nas.smb import SMBBackend


class SmbCredentialsTests(unittest.TestCase):
    def test_restricted_dfs_child_does_not_abort_parent_scan(self):
        client = Mock()
        allowed = Mock(name="Allowed")
        allowed.name = "Allowed"
        allowed.smb_info = None
        allowed.is_symlink.return_value = False
        allowed.is_dir.return_value = True
        restricted = Mock(name="Restricted")
        restricted.name = "Restricted"
        restricted.smb_info = None
        restricted.is_symlink.return_value = False
        restricted.is_dir.return_value = True
        client.scandir.return_value = [allowed, restricted]

        def remote_stat(path, **kwargs):
            if path.endswith("\\Restricted"):
                raise SMBOSError(NtStatus.STATUS_ACCESS_DENIED, path)
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_size=0, st_mtime=0)

        client.stat.side_effect = remote_stat
        with patch("termux_nas.smb._smbclient_module", return_value=client):
            backend = SMBBackend("files.example.org", "shares", "user@example.org", "test-password")
            entries = backend.entries("")
        self.assertEqual([entry["name"] for entry in entries], ["Allowed", "Restricted"])

    def test_operations_carry_credentials_for_dfs_target(self):
        client = Mock()
        client.stat.return_value = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755)
        client.scandir.return_value = []
        client.listdir.return_value = []
        client.open_file.side_effect = lambda *args, **kwargs: io.BytesIO(b"data")
        with patch("termux_nas.smb._smbclient_module", return_value=client):
            backend = SMBBackend("files.example.org", "Shared", "user@example.org", "test-password")
            self.assertTrue(backend.is_dir(""))
            backend.entries("")
            backend.listdir("")
            self.assertEqual(backend.read_range("file.txt", 1, 2), b"at")

        expected = {"username": "user@example.org", "password": "test-password", "port": 445}
        for method in (client.register_session, client.stat, client.scandir,
                       client.listdir, client.open_file):
            for key, value in expected.items():
                self.assertEqual(method.call_args.kwargs[key], value)


if __name__ == "__main__":
    unittest.main()
