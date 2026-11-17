# Architecture and target behavior

## User goal

On an unrooted Android phone, enter `~/nas` and use normal terminal navigation to browse an SMB share. File explorers implement their own network clients; they do not expose SMB shares as filesystem paths to Termux. Termux's `~/storage` entries are links to Android-provided local paths.

## Implemented first slice

`nas add` saves non-secret connection details. `nas shell` requests the password, establishes one SMB session, and holds a virtual current directory. Commands in this shell translate `~/nas/...` to SMB share-relative paths. No kernel mount or Android APK is involved.

## Next investigation: arbitrary CLI programs

For `cd ~/nas` and arbitrary programs to work in a launched shell, a rootless bridge would need to intercept filesystem operations such as `chdir`, `getcwd`, `stat`, `openat`, `getdents64`, `read`, `write`, and `rename`, then translate them to SMB operations. A PRoot-style traced process is a possible research direction. It would only affect processes started under that bridge, may be slower, and may not support every program. A shell-only wrapper cannot provide full POSIX filesystem behavior.

The bridge should be prototyped only after confirming what Android versions and CPU architectures the device uses. Success criteria: `cd ~/nas`, `ls`, `cat`, and `find` work under the launcher without root, and file writes are safe when the network drops.
