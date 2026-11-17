# termux-nas

`termux-nas` is a rootless Termux package for browsing an SMB NAS with ordinary commands. It provides `nas` and `nas-mount` commands. Run `nas mount` to open a Bash session where the NAS appears as a folder alongside your normal Termux files, commands, and Android storage.

The folder is a simulated filesystem view provided by PRoot. It exists only for commands started inside the `nas mount` session. Exiting the session disconnects it; an already-running ordinary Termux shell cannot see the live NAS folder. Common file changes are sent to SMB after each interactive shell command and again when the session exits.

## Install in Termux

Install Termux from [F-Droid](https://f-droid.org/packages/com.termux/), [GitHub Releases](https://github.com/termux/termux-app/releases), or [Google Play](https://github.com/termux-play-store). Open Termux and run these commands, regardless of which source you used:

```sh
pkg install -y git
mkdir -p ~/repos
git clone https://github.com/Sergi095/termux-nas.git ~/repos/termux-nas
cd ~/repos/termux-nas
bash install.sh
nas --help
```

The repository is public, so cloning does not require a GitHub login. The installer adds `nas` and `nas-mount` to Termux, installs Python dependencies, builds the patched PRoot binary, and checks that PRoot can start a Termux command. The first install can take a few minutes; later runs reuse the PRoot build. You do not need root, a separate PRoot checkout, or an Android add-on APK.

Google Play Termux uses its app-provided executable PRoot loader when present. F-Droid and GitHub builds use the loader bundled in the patched PRoot. Termux APKs from these sources have different signatures; see [Termux's installation notes](https://github.com/termux/termux-app#installation) before switching the Termux app itself between sources.

If you already have the repository, update the installed package with:

```sh
cd ~/repos/termux-nas
git fetch origin
git switch main
git pull --ff-only
bash install.sh
```

The installer skips rebuilding PRoot when its source version and patch have not changed.

If an older Termux bootstrap reports a broken `curl` while installing packages, run `apt update && apt full-upgrade` in Termux, then run `bash install.sh` again. The installer downloads PRoot with Python, so it does not upgrade `curl` just for this package.

After installing, follow [Add a NAS connection](#add-a-nas-connection). The full command reference is in [docs/cli.md](docs/cli.md).

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
cd ~/nas/Shared
ls -lah
find . -type f
cat Photos/notes.txt
cp Photos/picture.jpg ~/storage/downloads/picture.jpg
mkdir NewFolder
cp ~/local.txt NewFolder/file.txt
printf 'hello\n' > NewFolder/hello.txt
mv NewFolder/hello.txt NewFolder/renamed.txt
rm NewFolder/renamed.txt
cd ~
ls
exit
```

Use your chosen folder instead of `~/nas` if you changed it. If you added a connection with `--share Shared`, start at `~/nas`; otherwise enter the share folder as shown. Copying files in either direction, editing files, `touch`, `mkdir`, `mv` within one share, and `rm` are supported. Your other Termux and Android storage paths remain available in the session.

Changes become visible on the NAS after the command finishes and the Bash prompt returns. Large uploads can make the next prompt wait. For noninteractive commands, they sync before `nas mount` exits. If SMB rejects a change or the connection fails, `nas` prints the error and leaves the local files in the chosen folder for recovery. Review those files before running another mount there.

This is limited write-through emulation. A command may finish locally before an SMB error is reported at the prompt. Symbolic links, hard links, ownership and permission changes, and renaming across different shares are unsupported. The local folder does not mirror SMB access control checks before each write; the server applies your account's permissions when the change syncs. Changed remote files are checked before overwriting, but concurrent renames and deletes are not fully protected.

Directory listings are reused for two seconds to reduce SMB requests. Opened files are cached until you exit, so a file changed on the NAS by another device may need a new `nas mount` session before you see the change. PRoot adds overhead to filesystem operations, so this shell is slower than ordinary Termux. The writable bridge has been tested against a local SMB2 server on Linux; a live NAS connection on the Android 17 aarch64 phone still needs verification.

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
