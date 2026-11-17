# termux-nas

`termux-nas` is a private, rootless Termux package for browsing an SMB NAS with ordinary commands. It provides `nas` and `nas-mount` commands. Run `nas mount` to open a Bash session where the NAS appears as a read-only folder alongside your normal Termux files, commands, and Android storage.

The folder is a simulated filesystem view provided by PRoot. It exists only for commands started inside the `nas mount` session. Exiting the session disconnects it; an already-running ordinary Termux shell cannot see the live NAS folder.

## Install in Termux

You need access to this private GitHub repository and a working Termux installation. Clone it once, then run the installer:

```sh
pkg install -y git
mkdir -p ~/repos
git clone https://github.com/Sergi095/termux-nas.git ~/repos/termux-nas
cd ~/repos/termux-nas
bash install.sh
nas --help
```

Authenticate with GitHub when cloning if prompted. The installer adds the `nas` commands to Termux, installs Python dependencies, and builds the patched PRoot binary automatically. You do not need a separate PRoot checkout. After installation, run `nas` from any directory. The installer detects the executable PRoot loader shipped with Google Play Termux.

If you already have the repository, update the installed package with:

```sh
cd ~/repos/termux-nas
git fetch origin
git switch main
git pull --ff-only
bash install.sh
```

The installer skips rebuilding PRoot when its source version and patch have not changed.

## Add a NAS connection

Replace the host and username with your NAS details. With no `--share` option, the account's accessible file shares appear as folders under `~/nas`:

```sh
nas add home --host 192.168.1.10 --user your_username
nas list
nas mount home
cd ~/nas
ls
cd Shared
```

To show only one share directly at `~/nas`, specify it when adding the connection:

```sh
nas add home --host 192.168.1.10 --share Shared --user your_username
nas mount home
cd ~/nas
```

`home` is the connection name; choose any name you like. The SMB password is requested when connecting and is not saved. Share discovery uses the SMB server's share listing and skips shares that are not accessible to the account. Some servers disable share listing; on those servers use `--share`. If you have only one saved connection, `nas mount` can omit the name. `nas remove home` forgets the connection.

By default the NAS appears at `~/nas` inside the session. You can change its default folder name under your Termux home:

```sh
nas set-mount home media
nas mount home
cd ~/media
```

You can use another accessible empty folder, including one you created yourself. Save that path for future sessions:

```sh
mkdir ~/other-folder
nas set-mount home ~/other-folder
nas mount home
cd ~/other-folder
```

For one session without changing the saved path, use `nas mount home --at ~/other-folder`. Paths may be relative, absolute, or start with `~`. If the folder does not exist, its parent must already exist; `nas mount` creates the folder and removes it on exit. If you created an empty folder first, the folder remains after exit. A folder containing files is refused so its contents are never replaced. `nas-mount home --at ~/other-folder` is an alias for `nas mount home --at ~/other-folder`.

## Use the NAS folder

While the `nas mount` Bash session is open:

```sh
cd ~/nas
ls -lah
find . -type f
cat Photos/notes.txt
cp Photos/picture.jpg ~/storage/downloads/picture.jpg
cd ~
ls
exit
```

Use your chosen folder instead of `~/nas` if you changed it. The NAS folder is read-only; copying files from the NAS to local storage works, while writing to the NAS path is blocked. Your other Termux and Android storage paths remain available in the session.

Directory listings are reused for two seconds to reduce SMB requests. Opened files are cached until you exit, so a file changed on the NAS by another device may need a new `nas mount` session before you see the change. PRoot adds overhead to filesystem operations, so this shell is slower than ordinary Termux. The SMB bridge has been tested against a local SMB2 server on Linux; the PRoot fixture has been tested on an Android 17 aarch64 phone. A live NAS connection on that phone still needs verification.

## Remove the package

```sh
python -m pip uninstall termux-nas
rm -r "$PREFIX/libexec/termux-nas"
```

The saved connections remain in `~/.config/termux-nas/connections.json` unless you remove that file. The repository checkout can be deleted separately.

## Development

The Python package uses the [smbprotocol `smbclient` API](https://github.com/jborean93/smbprotocol). The PRoot hook asks a private Unix socket service to populate local cache files before ordinary filesystem operations continue. Manual PRoot build details are in [experiments/proot/README.md](experiments/proot/README.md).

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```
