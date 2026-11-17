# Rootless virtual filesystem target

## Required behavior

Inside one `nas-mount` session, `~/nas` (or a configured name) must work for ordinary Termux programs. The shell must keep the user's Termux home, `$PREFIX`, and Android storage paths available. Initial acceptance commands are `cd ~/nas`, `ls ~/nas`, `find ~/nas`, `cat ~/nas/file`, and opening a NAS file in a text editor. The Bash command wrappers in the older `nas shell` preview are insufficient because `command ls`, `find`, and editors bypass them.

## Feasibility finding

Termux's PRoot uses `ptrace` to rewrite filesystem paths for child processes without root. In the Termux PRoot source, `GUEST_PATH` is delivered before a path is canonicalized (`src/path/path.c`), and extensions are built into the PRoot binary rather than loaded as independent plugins. A NAS implementation would therefore need a maintained PRoot fork or patch, built for Termux, plus an SMB service. Installing ordinary `proot` alone cannot expose SMB files.

References: [Termux PRoot source](https://github.com/termux/proot), [extension API](https://github.com/termux/proot/blob/master/src/extension/extension.h), [Termux maintainer discussion](https://github.com/termux/termux-app/issues/3282).

## Implementation sequence

1. **Read-only proof of concept (implemented on `proot-spike`):** attach a PRoot extension that detects paths below the configured NAS folder and asks the SMB service to materialize directory entries and file data in a private cache before the traced syscall continues. Test `command ls`, `find`, and `cat` without Bash overrides.
2. **Metadata and caching:** handle directory refresh, file size and timestamps, symlinks or unsupported SMB features, and stale entries after network changes. Keep cache use bounded.
3. **Writes:** track file descriptors and operations such as `openat`, `write`, `close`, `rename`, `unlink`, and `mkdir`; upload changes safely and report network failures. A partial local cache must never silently appear as a successful remote write.
4. **Termux integration (partially implemented):** launch the user's shell and child programs under the patched PRoot while retaining access to Termux paths. The fixture demo passed on Android 17 aarch64; `nas-mount` with a live NAS still needs phone validation.

This is a process-scoped virtual filesystem, not a kernel mount. Programs outside the traced session and other Android apps will not see the NAS path. PRoot can slow filesystem-heavy commands and may not support every Termux program; this needs device testing before claiming normal behavior.
