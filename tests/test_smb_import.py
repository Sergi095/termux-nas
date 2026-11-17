"""Regression test for Impacket's bin/smbclient.py shadowing smbprotocol."""

import os
from pathlib import Path
import subprocess
import sys


def test_import_smbclient_with_script_ahead_of_site_packages(tmp_path):
    script_dir = tmp_path / "bin"
    script_dir.mkdir()
    (script_dir / "smbclient.py").write_text("# Another package's command-line script\n")
    source_dir = Path(__file__).resolve().parents[1] / "src"
    environment = {**os.environ, "PYTHONPATH": str(source_dir)}
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
sys.path.insert(0, sys.argv[1])
from termux_nas.smb import _smbclient_module
client = _smbclient_module()
assert client.__file__.endswith('smbclient/__init__.py'), client.__file__
assert callable(client.register_session)
""", str(script_dir)],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
