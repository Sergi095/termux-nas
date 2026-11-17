# PRoot syscall-hook experiment

This branch contains a **read-only proof of concept** for the mount-simulation goal. The patch adds a `GUEST_PATH` extension to Termux PRoot. Before PRoot resolves a path below the configured NAS folder, it asks a local service to populate a private directory. Unmodified `find`, `ls`, `cat`, and Bash `cd` then see those files through ordinary filesystem calls. The hook rejects common path-based writes with `EROFS`. The demo service reads from a local fixture directory; `nas-mount` uses the same service with the SMB backend.

The patch targets Termux PRoot commit `52d65a4dc140ca554d241a1438ddd4f6b00c9813` (GPL-2.0-or-later). Build and test on a Linux host:

```sh
git clone https://github.com/termux/proot.git /tmp/nasfs-proot
cd /tmp/nasfs-proot
git checkout 52d65a4dc140ca554d241a1438ddd4f6b00c9813
git apply /path/to/termux-nas/experiments/proot/termux-proot-nasfs.patch
make -C src
python /path/to/termux-nas/experiments/proot/run_host_demo.py src/proot
```

The host needs a C compiler, `make`, and `libtalloc-dev`.

## Android emulator check

On 2026-11-17, the original patch built and the demo passed in the official Termux v0.118.3 x86_64 APK on a separate Android SDK 37 AOSP ATD emulator. The demo was first run through `adb run-as`, then launched from Termux's own terminal. The terminal run reported UID `u0_a106` and SELinux context `u:r:untrusted_app_27:s0:c106,c256,c512,c768`; it exited with status 0. The emulator was not rooted for the test. The test also read a regular local Termux file after `cd` into the virtual NAS folder, so both trees were visible to the same Bash process.

In that Termux installation, the build used `pkg install clang make libtalloc python` and `make -C src` on a source tree prepared with the patch above. The fixture demo ran with `python experiments/proot/run_host_demo.py src/proot`. It used Termux's `find`, `ls`, `cat`, and `bash` executables.

## Android phone check

On 2026-11-17, the original patch also built and the demo passed on an unrooted Samsung SM-S928B running Android 17, aarch64, with Google Play Termux `googleplay.2026.10.09`. The initial run failed with `execve(...): Permission denied` because PRoot extracted its loader under Termux's writable temporary directory. Android denied execution from there. Google Play Termux ships an executable PRoot loader in its APK, exposed as `$PREFIX/../applib/libproot-loader.so`. Setting `PROOT_LOADER` to that path made the demo pass. The demo now detects this loader automatically when available. This behavior follows the [Google Play Termux PRoot package recipe](https://github.com/termux-play-store/termux-packages/blob/master/packages/proot/build.sh).

The current read-only guard and `nas-mount` command passed host integration tests against a temporary SMB2 server. They still need a phone test with a live NAS. The experiment eagerly copies file contents when opened, has no cache bounds or refresh policy, and does not synchronize writes. Path-based write operations are blocked; this is still experimental and should first be tried on a non-critical share.

## Try the fixture demo in Termux

Use the `proot-spike` branch of this repository. These commands build the patched PRoot locally in Termux and run the same demo on your phone:

```sh
pkg install -y git clang make libtalloc python
cd ~/repos/termux-nas
git fetch origin
git switch --track origin/proot-spike
mkdir -p ~/repos
git clone https://github.com/termux/proot.git ~/repos/proot-nasfs
cd ~/repos/proot-nasfs
git checkout 52d65a4dc140ca554d241a1438ddd4f6b00c9813
git apply ~/repos/termux-nas/experiments/proot/termux-proot-nasfs.patch
make -C src
cd ~/repos/termux-nas
python experiments/proot/run_host_demo.py ~/repos/proot-nasfs/src/proot
```

The expected last line is `PASS: find, ls, cat and bash cd see NAS and local files; writes are blocked`. This only tests a temporary local fixture, not an SMB connection. If you already have a local `proot-spike` branch, run `git switch proot-spike` and `git pull --ff-only` instead of the `git switch --track` command above.

If you built the earlier patch in `~/repos/proot-nasfs`, update that existing source tree instead of applying the full patch again:

```sh
cd ~/repos/termux-nas
git pull --ff-only
cd ~/repos/proot-nasfs
git apply ~/repos/termux-nas/experiments/proot/upgrade-readonly.patch
make -C src
```
