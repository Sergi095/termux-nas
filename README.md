# termux-nas

Private, rootless SMB browsing experiment for Termux.

**Project target:** make a NAS folder behave like a filesystem for ordinary CLI programs launched inside `nas shell`, without rooting Android. The current Bash-command preview does **not** meet this target yet. Development is moving to a PRoot-style syscall bridge; see [virtual filesystem design](docs/virtual-filesystem.md).

## Current status

`nas shell` now launches an interactive **Bash** session and loads your `~/.bashrc`. Your Termux home, installed commands, and Android storage paths stay available. One configured folder under your home (default `~/nas`) is routed to an SMB share for `cd`, `ls` (including `-a`, `-l`, and `-h`), `cat`, and single-file `cp` commands. The folder name is configurable per connection.

This is a shell-level preview, **not a filesystem mount**. Programs that directly open a NAS path, such as `nano`, `find`, or `command ls`, currently see only a temporary local shadow directory. The shell bridge handles only the commands listed above. No Android NAS connection has been tested yet.

## Install privately on your phone

Clone or copy this private repository into Termux home, then run:

```sh
pkg install python python-cryptography bash
cd ~/repos/termux-nas
python -m pip install .
nas --help
```

To update an existing install after pulling changes:

```sh
cd ~/repos/termux-nas
git pull
python -m pip install .
```

You do not need to publish a package or APK. If `pip` fails while building `cryptography`, install `python-cryptography` from Termux first.

## Connect

```sh
nas add home --host 192.168.1.10 --share Shared --user your_username --mount-name media
nas list
nas shell home
```

Existing connections created before `--mount-name` was added default to `~/nas`. Change one without re-entering the server details:

```sh
nas set-mount home media
```

The SMB password is requested when `nas shell` starts. It stays in that process's memory and is not written to the connection file.

Inside `nas shell`, local paths and commands work through Bash, while the configured NAS folder uses SMB for supported operations:

```sh
cd ~/storage/shared
ls
cd ~/Documents
cat local.txt
cd ~/media
ls
ls -lah
cd Photos
cat notes.txt
cp picture.jpg ~/storage/downloads/picture.jpg
cp ~/Documents/new.txt ~/media/Photos/new.txt
exit
```

Run `termux-setup-storage` once if `~/storage` is not present. Single-file `cp` refuses to overwrite a destination. A failed network transfer can leave a partial destination file; remove it before retrying.

The NAS folder is a temporary symlink into a private shadow directory. It is removed when `nas shell` exits. If a file or directory already has that name in your Termux home, choose another name with `nas set-mount` rather than deleting it.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

The SMB adapter uses the [smbprotocol high-level `smbclient` API](https://github.com/jborean93/smbprotocol). The Bash session talks to a private Unix socket served by the parent `nas` process. Passwords are not passed as command-line arguments or stored in that socket's files.
