# Architecture and target behavior

## User goal

On an unrooted Android phone, run `nas shell` and keep the full local Termux environment while accessing an SMB share at a configurable path under `~`. Local files and `~/storage/shared` should remain accessible from the same shell.

## Current implementation

`nas shell` requests the SMB password and connects using `smbprotocol`. It starts interactive Bash with the user's `~/.bashrc` and a few additional shell functions. A temporary symlink at the configured path points to a private shadow directory so Bash can physically enter it. The shell functions route `cd`, `ls`, `cat`, and simple `cp` operations on that path to an SMB backend through a private Unix socket. Local paths go to Bash and ordinary Termux commands. The symlink and socket are removed at exit.

The shadow directory does not contain the full NAS. It only holds directory placeholders needed for Bash to change directories. Direct filesystem access by unrelated programs is not provided by the current bridge.

## Longer-term investigation: arbitrary CLI programs

For unmodified programs to see NAS file contents, a rootless bridge would have to intercept filesystem calls such as `chdir`, `getcwd`, `stat`, `openat`, `getdents64`, `read`, `write`, and `rename`, then translate them to SMB operations. A PRoot-style traced process is a possible research direction. PRoot currently maps paths to local files; it does not implement an SMB backend. This approach would only affect processes launched under the bridge, may be slower, and may not support every program.

Success criteria for a later bridge: `cd`, `ls`, `cat`, `find`, and a text editor work on the NAS path without command-specific Bash functions; local Termux and Android storage paths remain available; file writes handle network interruption safely.
