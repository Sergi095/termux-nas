# termux-nas

`termux-nas` is a rootless Termux package for browsing an SMB NAS with ordinary commands. Run `nas mount` to open a Bash session where the NAS appears as a folder alongside your normal Termux files, commands, and Android storage. Remote byte-range I/O is the default: the bridge does not download entire NAS files into the mount folder.

The folder is a simulated filesystem view provided by PRoot. It exists only for commands started inside the `nas mount` session. Exiting the session disconnects it; an already-running ordinary Termux shell cannot see the live NAS folder. The older download and sync mode remains available with `nas mount --cached`.

## How the simulated mount works

`nas mount` starts a Python bridge and a Bash shell under patched PRoot. PRoot watches filesystem calls made by that shell and its child programs. It binds a private temporary backing directory over `~/nas` inside the session. The bridge puts directory entries and sparse file placeholders in that private directory so commands can navigate the NAS without storing NAS file contents there. The ordinary `~/nas` path stays empty outside PRoot:

```text
  `cd`, `ls`, `find` ──▶ PRoot ──▶ Python bridge ──SMB──▶ NAS names and sizes
                                   │
                                   └──▶ sparse placeholders in private temp folder
                                        │  (names and sizes, no NAS file contents)
                                        └──▶ visible as ~/nas only inside PRoot

  `cat`, `read`    ──▶ PRoot ──▶ Python bridge ──SMB──▶ NAS file bytes
                         ◀──────── requested bytes in memory ◀────────┘
                         └──▶ terminal or command output

  `write`, `pwrite` ──▶ PRoot ──▶ Python bridge ──SMB──▶ NAS file bytes
                         (changed byte ranges go to the server)
```

For example, `cd ~/nas/Shared` works because the bridge creates the corresponding local directory before Android handles `chdir()`. `ls` sees names fetched from the NAS. A read fetches the bytes the command requests into memory; it does not fill the sparse placeholder with those bytes. `cat` still transfers an entire file over the network because it reads the entire file. `cat file > ~/local-copy` saves a copy because the output path is on the phone.

Supported file writes go to SMB as the program makes them. Directory changes are synchronized with the server. A newly created NAS file remains on the server, while its private placeholder disappears on exit. If a sync fails in range mode, the bridge reports the error and discards its temporary backing directory; it does not keep a local recovery copy. Programs may still create their own temporary files outside the NAS folder, and files you save elsewhere on the phone remain there. Other Termux paths are available in the same shell because PRoot runs with the existing Android filesystem as its root. No kernel mount or root access is involved, so a shell outside this PRoot session does not get the live NAS view.

## Install in Termux

Install Termux from [F-Droid](https://f-droid.org/packages/com.termux/), [GitHub Releases](https://github.com/termux/termux-app/releases), or [Google Play](https://play.google.com/store/apps/details?id=com.termux). Open Termux and run:

```sh
pkg install -y git
mkdir -p ~/repos
git clone https://github.com/Sergi095/termux-nas.git ~/repos/termux-nas
cd ~/repos/termux-nas
bash install.sh
nas --help
```

The repository is public; a GitHub account is not needed to clone it. The installer adds `nas` and `nas-mount` to Termux, installs Python dependencies, builds the patched PRoot binary, and checks that PRoot can start a Termux command. The first install can take a few minutes; later runs reuse the PRoot build. You do not need root, a separate PRoot checkout, or an Android add-on APK.

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

To check the CLI and patched PRoot locally without a NAS, run `bash ~/repos/termux-nas/tests/termux_smoke.sh`. A real NAS connection is still needed to check SMB login and your account's share permissions.

### Verified builds

| Termux source | Environment | Checked |
| --- | --- | --- |
| Google Play `googleplay.2026.10.09` | Android 17, aarch64 phone | Installer, PRoot loader, live SMB share listing, and `cd ~/nas` confirmed by a user. |
| F-Droid `0.118.3` | Android 17, x86_64 emulator | Installer, bundled PRoot loader, local fixture reads and writes. |
| GitHub `0.118.3` | Android 17, x86_64 emulator | Installer, bundled PRoot loader, shell writes, normal `vi` edits, and experimental range I/O against fixtures and a real SMB2 test share. |

These checks cover the named versions and architectures. The live Google Play test confirmed browsing; write operations have been checked against a local SMB2 server and emulator fixtures.

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

### Redirected SMB shares

Some SMB paths use a DFS referral: the server named in the connection points the client to another server that holds the share. The bridge sends the same account credentials with each SMB operation so the referred server can authenticate the request. This happens automatically. Use the server's full hostname and the username format required by the SMB account, such as `user@example.org`:

```sh
nas add files --host files.example.org --share Shared --user user@example.org
nas mount files
```

Replace `Shared` with the actual SMB share name. Specifying `--share` skips server-wide share discovery, which some servers disable. If authentication fails, check the complete error, the account's required username format, and whether the network or server requires additional authentication setup. Do not send your password in an issue or log.

A DFS namespace may list links whose targets your account cannot open. Listing the namespace folder should still show the available names; entering a restricted link reports access denied for that link. The bridge does not require access to every advertised target to browse an accessible one.

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

`nas mount` checks that its local folder can be accessed before opening the shell. If it reports a folder error, choose an empty folder under your Termux home and retry with `--at` or `nas set-mount`. The NAS server decides whether your account can write to a share.

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
vi NewFolder/file.txt
printf 'hello\n' > NewFolder/hello.txt
mv NewFolder/hello.txt NewFolder/renamed.txt
rm NewFolder/renamed.txt
cd ~
ls
exit
```

Use your chosen folder instead of `~/nas` if you changed it. If you added a connection with `--share Shared`, start at `~/nas`; otherwise enter the share folder as shown. Copying files in either direction, editing files, `mkdir`, `mv` within one share, and `rm` are supported. Your other Termux and Android storage paths remain available in the session.

In the default range mode, supported file writes are sent to SMB as they happen. Directory changes such as rename and delete are synchronized as commands make them. If SMB rejects an operation, the command reports an error. Check the NAS after a failed operation or interrupted session before retrying; some earlier writes may already have reached it.

This is limited filesystem emulation. Symbolic links, hard links, ownership and permission changes, and renaming across different shares are unsupported. Programs requiring `mmap`, vector I/O, `sendfile`, `splice`, or `fallocate` on a NAS file will fail rather than read placeholder bytes. The server applies your account's SMB permissions. Append (`>>`) checks the current remote size before each write; concurrent appenders are not protected from overwriting each other.

Directory listings are reused for two seconds to reduce SMB requests. File names and sizes can be stale within a session if another device changes the NAS; start a new mount session to refresh them. PRoot and SMB add latency to file operations, so this shell is slower than ordinary Termux.

### Large files and local storage

The default `nas mount home` uses remote byte-range I/O. To read or change part of a huge file without downloading it into the mount folder:

```sh
nas mount home
cd ~/nas/Shared             # Or cd ~/nas if you selected one share
python - <<'PY'
import os
with open("huge.bin", "r+b", buffering=0) as file:
    offset = 500 * 1024**3 - 4
    print(os.pread(file.fileno(), 4, offset))
    os.pwrite(file.fileno(), b"edit", offset)
PY
```

The range mode keeps a **sparse placeholder** with the file's name and size in a private temporary directory. PRoot binds that directory to `~/nas` only for the mounted session. The placeholder holds no copy of the file's contents. PRoot routes each supported file read or write through the bridge to SMB:

```text
  Program in `nas mount`                  Local phone          NAS server
  ──────────────────────────────────────────────────────────────────────
  stat("huge.bin")                      sparse name + size  ◀─ metadata
  pread(fd, 4, 500 GB - 4)             no data stored      ◀─ 4 bytes
  pwrite(fd, "edit", 500 GB - 4)        no data stored      ─▶ 4 bytes
```

The same session still shows your normal Termux home and Android storage. A 500 GB file was tested on Android 17 with four-byte reads and writes near its end; the private local placeholder occupied 4 KiB. The actual transfer depends on what the program does: reading or copying the entire file still transfers 500 GB, and a program that loads it all into memory may run out of memory. `vi` can edit ordinary files in this mode, but it is not a practical random-access editor for a 500 GB file. Editors may also make their own swap or backup copies on the phone; the bridge cannot prevent that.

Range mode handles ordinary `read`, `pread`, `write`, `pwrite`, append, seek, truncate, file creation, and common directory changes. It deliberately rejects operations without remote equivalents rather than reading placeholder zeros or changing only local metadata. It is still experimental; keep backups of important files on the NAS or another device. The `--range-io` flag remains accepted but is no longer needed.

### Older cached mode

Run `nas mount home --cached` to use the previous download and sync behavior. In that mode, opening an existing NAS file downloads its **entire contents** into the local backing folder. The bridge limits downloads to **256 MiB total per session** and refuses a download that would leave less than **512 MiB free**. You can raise the session limit with `TERMUX_NAS_MAX_DOWNLOAD_MB=512 nas mount home --cached` if your device has room.

Cached mode uploads edited files after each interactive command or when the session exits. An interrupted upload can leave the remote file incomplete because the uploader truncates it before copying the new contents. This mode does not support editing a 500 GB file without storing it locally. Its download limit does not cap files or editor temporary files created locally by programs.

## Remove the package

```sh
python -m pip uninstall termux-nas
rm -r "$PREFIX/libexec/termux-nas"
```

The saved connections remain in `~/.config/termux-nas/connections.json` unless you remove that file. The repository checkout can be deleted separately.

## Development

The Python package uses the [smbprotocol `smbclient` API](https://github.com/jborean93/smbprotocol). The PRoot hook talks to a private Unix socket service for NAS metadata and byte-range I/O. Manual PRoot build details are in [experiments/proot/README.md](experiments/proot/README.md).

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```
