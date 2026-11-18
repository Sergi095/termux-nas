# Rootless NAS filesystem view

Inside a `nas mount` session, `~/nas` (or a configured empty folder) works with ordinary Termux programs while home, `$PREFIX`, and Android storage remain available. `cd`, `ls`, `find`, `cat`, `cp`, shell redirection, and `vi` have been exercised through the PRoot bridge. A connection without `--share` presents accessible shares as subfolders.

The default mode uses sparse placeholders for file names and sizes. The PRoot hook relays supported file descriptor reads and writes to SMB in byte ranges. A four-byte edit near the end of a sparse 500 GB SMB file was tested on an Android 17 Termux emulator with 4 KiB allocated locally. This does not reduce the data a program chooses to read or the memory it uses itself.

`nas mount --cached` preserves the earlier full-file download and command-boundary sync behavior with its 256 MiB default download limit. See the [README](../README.md#large-files-and-local-storage) for use and limitations.

This is a process-scoped view, not a kernel mount. Other Termux sessions and Android apps cannot see live NAS data at this path. Unsupported filesystem operations fail rather than silently changing only local placeholders. SMB errors, concurrent remote edits, and PRoot overhead still limit how closely the view matches a native mount.

References: [Termux PRoot source](https://github.com/termux/proot), [extension API](https://github.com/termux/proot/blob/master/src/extension/extension.h).
