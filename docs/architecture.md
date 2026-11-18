# Architecture

## Process-scoped filesystem view

`nas mount` starts the Python SMB bridge and a Bash process under patched Termux PRoot. PRoot intercepts filesystem calls from that Bash process and its children. Paths outside the chosen NAS folder continue to use the normal Termux and Android filesystem. The NAS folder is visible only in this traced session; no kernel mount is created.

```text
Termux command → patched PRoot → Unix socket → Python bridge → SMB server
                       ↓                ↓
                 path translation   sparse local names and sizes
```

The default range mode fetches directory entries and file sizes from SMB. It creates sparse placeholders in a private temporary directory and binds it over the selected NAS path only inside PRoot. The ordinary path remains empty outside PRoot. Supported reads and writes go to the server in byte ranges; file data passes through memory and is not stored in the placeholders. The bridge synchronizes directory changes and removes its private placeholders when the session exits successfully.

`nas mount --cached` selects the older mode. It downloads opened files to the backing folder and uploads changes after each interactive command or on exit. This mode has a download limit because a large NAS file could fill phone storage.

## Components

- `src/termux_nas/cli.py` parses commands and chooses the I/O mode.
- `src/termux_nas/mounted.py` starts the PRoot shell and bridge service.
- `src/termux_nas/hydrate.py` manages directory entries, sparse placeholders, byte-range requests, and cached-mode sync.
- `src/termux_nas/smb.py` translates bridge operations to SMB.
- `experiments/proot/termux-proot-nasfs.patch` adds the PRoot filesystem hook.

## Limits

Range mode supports normal read, pread, write, pwrite, seek, truncate, file creation, and common directory operations. Operations without a safe remote equivalent, such as mmap, vector I/O, append mode, links, and permission changes, fail. Concurrent edits from another device are not fully coordinated. Programs that read an entire large file still transfer that file over the network. PRoot and SMB add latency to filesystem calls.
