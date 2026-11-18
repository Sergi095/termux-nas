import io
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from termux_nas.smb import SMBBackend


class SmbCredentialsTests(unittest.TestCase):
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
