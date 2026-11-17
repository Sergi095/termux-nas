# PRoot NAS hook

The normal [installer](../../README.md#install-in-termux) downloads, patches, and builds PRoot automatically. These instructions are for developing the C hook.

The patch adds a `GUEST_PATH` extension to Termux PRoot. It asks the Python bridge to populate local cache entries before commands access a NAS path. Supported writes change that cache and sync to SMB after the shell command finishes. Unsupported metadata operations are rejected with `EROFS`.

The patch targets Termux PRoot commit `52d65a4dc140ca554d241a1438ddd4f6b00c9813` (GPL-2.0-or-later). To build manually on a Linux host:

```sh
git clone https://github.com/termux/proot.git /tmp/nasfs-proot
cd /tmp/nasfs-proot
git checkout 52d65a4dc140ca554d241a1438ddd4f6b00c9813
git apply /path/to/termux-nas/experiments/proot/termux-proot-nasfs.patch
make -C src
python /path/to/termux-nas/experiments/proot/run_host_demo.py src/proot
```

The host needs a C compiler, `make`, and `libtalloc-dev`. The fixture demo checks reads and the metadata write guard. The writable SMB integration test can run with `TERMUX_NAS_TEST_PROOT=/tmp/nasfs-proot/src/proot python -m unittest discover -s tests -v` from the project root.

The original read-only patch passed a fixture test on an unrooted Android 17 aarch64 phone with Google Play Termux `googleplay.2026.10.09`. That Termux build needs its executable PRoot loader at `$PREFIX/../applib/libproot-loader.so`; the package detects it automatically. The current writable patch has been tested against a local SMB2 server on Linux and still needs a live phone test.

`upgrade-readonly.patch` is kept only for the earlier experiment. Use `bash install.sh` for the current patch.
