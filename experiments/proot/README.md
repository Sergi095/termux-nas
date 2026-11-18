# PRoot NAS hook

The normal [installer](../../README.md#install-in-termux) downloads, patches, and builds PRoot automatically. These instructions are for developing the C hook.

The patch adds a `GUEST_PATH` extension to Termux PRoot. In the default mode it asks the Python bridge to populate local cache entries before commands access a NAS path. Supported writes change that cache and sync to SMB after the shell command finishes. Unsupported metadata operations are rejected. In experimental `--range-io` mode it also intercepts file descriptor reads, writes, and truncation, and sends those operations to SMB in byte ranges. Sparse local files supply names and sizes only; unsupported I/O calls fail explicitly.

The patch targets Termux PRoot commit `52d65a4dc140ca554d241a1438ddd4f6b00c9813` (GPL-2.0-or-later). The upstream copyright and license text is in [COPYING](COPYING). To build manually on a Linux host:

```sh
git clone https://github.com/termux/proot.git /tmp/nasfs-proot
cd /tmp/nasfs-proot
git checkout 52d65a4dc140ca554d241a1438ddd4f6b00c9813
git apply /path/to/termux-nas/experiments/proot/termux-proot-nasfs.patch
make -C src
python /path/to/termux-nas/experiments/proot/run_host_demo.py src/proot
```

The host needs a C compiler, `make`, and `libtalloc-dev`. The fixture demo checks reads and the metadata write guard. The writable SMB integration test can run with `TERMUX_NAS_TEST_PROOT=/tmp/nasfs-proot/src/proot python -m unittest discover -s tests -v` from the project root.

Google Play Termux `googleplay.2026.10.09` needs its executable PRoot loader at `$PREFIX/../applib/libproot-loader.so`; the package detects it automatically. A user confirmed a live NAS listing from the patched PRoot shell on Android 17 aarch64. The writable patch has also passed local SMB2 tests on Linux and fixture tests in F-Droid and GitHub Termux emulators.

`upgrade-readonly.patch` is kept only for the earlier experiment. Use `bash install.sh` for the current patch.
