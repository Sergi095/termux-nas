# termux-nas

Experimental, rootless SMB folder for Termux. `nas-mount` simulates a read-only mount inside a PRoot-traced Bash session. Ordinary commands such as `cd`, `find`, `ls`, `cat`, and `cp` from the NAS to local storage use normal filesystem paths. Your Termux home and installed commands are visible in that same session.

This is a process-scoped filesystem view, not an Android kernel mount. A command cannot change the filesystem view of the already-running parent shell. Run `nas-mount`, work in the Bash session it opens, then type `exit` to disconnect. Outside that session, `~/nas` is only a partial local cache. The temporary directory is removed on normal exit.

## Install the experimental version

Use the `proot-spike` branch. If you already built the first PRoot patch, update that source tree with the small incremental patch and rebuild:

```sh
cd ~/repos/termux-nas
git switch proot-spike
git pull --ff-only

cd ~/repos/proot-nasfs
git apply ~/repos/termux-nas/experiments/proot/upgrade-readonly.patch
make -C src

cd ~/repos/termux-nas
python -m pip install .
nas-mount --help
```

For a fresh PRoot source tree, follow [the full build instructions](experiments/proot/README.md). The PRoot binary is found automatically at `~/repos/proot-nasfs/src/proot`; use `nas-mount --proot PATH` if it lives elsewhere. Google Play Termux's bundled executable PRoot loader is detected automatically.

## Connect

If you already saved a connection with `nas add`, check its name with `nas list`. Otherwise add one:

```sh
nas add home --host 192.168.1.10 --share Shared --user your_username
nas-mount home
```

The default directory name is `~/nas`. Change it with `nas set-mount home media`, or use `--mount-name media` with `nas add`. The SMB password is requested when connecting and is not stored in the connection file.

Inside the session:

```sh
cd ~/nas
find . -type f
ls -lah
cat Photos/notes.txt
cp Photos/picture.jpg ~/storage/downloads/picture.jpg
cd ~
ls
exit
```

Writes to the NAS path are blocked with a read-only filesystem error. The bridge has no write synchronization or cache refresh yet. This branch was tested against a local SMB2 server on Linux and with a local fixture on an Android 17 aarch64 phone; a live NAS connection on the phone still needs verification.

If `~/nas` already exists, `nas-mount` refuses to replace it. Use another mount name. An abrupt process kill can leave the temporary local directory behind; inspect it before removing it. The older `nas shell` command remains a limited Bash-command preview and does not provide the filesystem view described here.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

The SMB adapter uses the [smbprotocol `smbclient` API](https://github.com/jborean93/smbprotocol). The PRoot hook asks a private Unix socket service to populate a local cache before ordinary filesystem operations continue.
