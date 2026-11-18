# `nas` command reference

Install the package first with the commands in the [README](../README.md#install-in-termux). All commands below run inside Termux. `nas --help` and `nas COMMAND --help` show the built-in help.

## Quick start

```sh
nas add mynas --host 192.168.1.10 --user myuser
nas mount mynas
cd ~/nas
ls
exit
```

The password is requested when connecting and is not saved. With no `--share`, `~/nas` contains a folder for each accessible file share. If the server does not allow share discovery, add the connection with `--share SHARE` instead.

## Commands

| Command | Purpose |
| --- | --- |
| `nas add NAME --host HOST --user USER [--share SHARE] [--port PORT] [--mount-name FOLDER]` | Save or replace a connection. The default SMB port is `445`; the default folder is `~/nas`. |
| `nas list` | Show saved connections, share selection, and folder paths. |
| `nas mount [NAME] [--at FOLDER] [--proot PATH] [--range-io]` | Open a Bash session with the live NAS folder. This is the main command. |
| `nas-mount [NAME] [--at FOLDER] [--proot PATH] [--range-io]` | Alias for `nas mount`. |
| `nas set-mount NAME FOLDER` | Save a different folder name under `~` or a full path for future mount sessions. |
| `nas remove NAME` | Forget a saved connection. Remote files are untouched. |
| `nas shell [NAME]` | Open the older Bash preview with command wrappers. Use `nas mount` for ordinary programs such as `find` and editors. |

`NAME` is the local connection name, for example `mynas`; `HOST` is a NAS hostname or IP address; `USER` is the SMB account name. `--share SHARE` exposes one share directly at the selected folder. Without it, the selected folder contains accessible shares as subfolders. If there is exactly one saved connection, `nas mount` may omit `NAME`.

## Mount folder examples

```sh
nas set-mount mynas media       # Use ~/media on future sessions
nas set-mount mynas ~/archive   # Use this full path on future sessions
mkdir ~/temporary-nas
nas mount mynas --at ~/temporary-nas  # Override for one session
```

The folder must be empty and cannot be a symbolic link. `nas mount` creates a missing folder if its parent exists. A folder created by `nas mount` is removed when the session ends successfully; a folder you created remains. An SMB sync failure leaves unsynced local files in the folder for recovery.

With all-shares mode, create files inside `FOLDER/SHARE`, not at the server's share-listing root `FOLDER`. The mount command checks local write access to each discovered share folder before starting Bash.

## What `mount` does

Inside the `nas mount` Bash session, normal commands such as `cd`, `ls`, `find`, `cat`, `cp`, and editors see the NAS folder alongside Termux home, `$PREFIX`, and Android storage. Common writes sync to SMB after each interactive command and when the session exits. Exiting closes this process-scoped view. A separate, already-running Termux shell does not see a live NAS folder.

The server applies your SMB account permissions during sync. File edits with normal `vi`, shell redirection, copy, `mkdir`, rename within a share, and delete are supported. Symbolic links, ownership or permission changes, and rename across shares are unsupported. See [Use the NAS folder](../README.md#use-the-nas-folder) for examples and limitations.

`--proot PATH` selects a custom patched PRoot binary for development. Normal installs need no `--proot` option.

`TERMUX_NAS_MAX_DOWNLOAD_MB` sets the maximum total number of MiB downloaded into the local backing folder during one mount session. The default is `256`; the bridge also keeps at least 512 MiB free before each download. This limit does not apply to new files or temporary files created by programs in the session.

`--range-io` enables experimental remote byte-range I/O. It keeps sparse local placeholders and sends supported reads and writes directly to SMB, so changing a few bytes of a huge file does not download the whole file. It does not make applications themselves use less memory or transfer less data if they read the entire file. See [Experimental remote range I/O](../README.md#experimental-remote-range-io) for an example and unsupported operations. The download limit above applies to the default mode, not to `--range-io`.
