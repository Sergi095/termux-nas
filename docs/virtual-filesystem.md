# Rootless virtual filesystem target

## Required behavior

Inside one `nas-mount` session, `~/nas` (or a configured name) must work for ordinary Termux programs. The shell must keep the user's Termux home, `$PREFIX`, and Android storage paths available. Initial acceptance commands are `cd ~/nas`, `ls ~/nas`, `find ~/nas`, `cat ~/nas/file`, and opening a NAS file in a text editor. The Bash command wrappers in the older `nas shell` preview are insufficient because `command ls`, `find`, and editors bypass them.

## Feasibility finding

Termux's PRoot uses `ptrace` to rewrite filesystem paths for child processes without root. In the Termux PRoot source, `GUEST_PATH` is delivered before a path is canonicalized (`src/path/path.c`), and extensions are built into the PRoot binary rather than loaded as independent plugins. A NAS implementation would therefore need a maintained PRoot fork or patch, built for Termux, plus an SMB service. Installing ordinary `proot` alone cannot expose SMB files.

References: [Termux PRoot source](https://github.com/termux/proot), [extension API](https://github.com/termux/proot/blob/master/src/extension/extension.h), [Termux maintainer discussion](https://github.com/termux/termux-app/issues/3282).

## Implementation status

1. **Path hydration:** the patched PRoot asks a Python service to populate cache entries so ordinary `ls`, `find`, `cat`, and `cd` work. Directory metadata is reused briefly to reduce SMB requests.
2. **Share discovery:** a connection without `--share` lists the account's accessible file shares as folders under the NAS path.
3. **Limited writes:** supported path operations change the local cache, then the bridge sends the changes to SMB after each interactive command and on shell exit. SMB errors are reported during sync; failed changes leave the local cache for recovery. Changed remote files are checked before overwriting.
4. **Remaining gaps:** SMB errors cannot always be returned by the original command, and Unix metadata operations, symlinks, cross-share renames, concurrent directory changes, and cache bounds need more work. A live writable NAS session on the Android phone still needs verification.

This is a process-scoped virtual filesystem, not a kernel mount. Programs outside the traced session and other Android apps will not see the NAS path. PRoot can slow filesystem-heavy commands and may not support every Termux program; this needs device testing before claiming normal behavior.
