#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PREFIX:-}" ]] || ! command -v pkg >/dev/null 2>&1; then
    printf 'Run this installer inside Termux.\n' >&2
    exit 1
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
patch_file="$repo_dir/experiments/proot/termux-proot-nasfs.patch"
source_commit=52d65a4dc140ca554d241a1438ddd4f6b00c9813
installed_dir="$PREFIX/libexec/termux-nas"
installed_proot="$installed_dir/proot"
stamp_file="$installed_dir/build-id"

pkg install -y git clang make libtalloc python python-cryptography python-pycryptodomex
mkdir -p "$PREFIX/tmp"

patch_hash="$(sha256sum "$patch_file" | cut -d ' ' -f 1)"
build_id="$(uname -m):$source_commit:$patch_hash"
current_id=""
if [[ -f "$stamp_file" ]]; then
    IFS= read -r current_id < "$stamp_file" || true
fi

if [[ ! -x "$installed_proot" || "$current_id" != "$build_id" ]]; then
    cache_root="${XDG_CACHE_HOME:-$HOME/.cache}/termux-nas"
    mkdir -p "$cache_root"
    build_dir="$(mktemp -d "$cache_root/build.XXXXXXXX")"
    mkdir -p "$build_dir/source"
    printf 'Downloading pinned Termux PRoot source...\n'
    python - "$source_commit" "$build_dir/source.tar.gz" <<'PY'
import shutil
import sys
import time
from urllib.request import urlopen

url = f"https://github.com/termux/proot/archive/{sys.argv[1]}.tar.gz"
for attempt in range(3):
    try:
        with urlopen(url, timeout=45) as response, open(sys.argv[2], "wb") as output:
            shutil.copyfileobj(response, output)
        break
    except Exception:
        if attempt == 2:
            raise
        time.sleep(2 ** attempt)
PY
    tar -xzf "$build_dir/source.tar.gz" -C "$build_dir/source" --strip-components=1
    (cd "$build_dir/source" && git apply "$patch_file")
    printf 'Building the patched PRoot (log: %s)...\n' "$build_dir/build.log"
    if ! make -C "$build_dir/source/src" -j2 > "$build_dir/build.log" 2>&1; then
        tail -n 80 "$build_dir/build.log" >&2
        exit 1
    fi
    mkdir -p "$installed_dir"
    install -m 0700 "$build_dir/source/src/proot" "$installed_proot"
    printf '%s\n' "$build_id" > "$stamp_file.tmp"
    mv "$stamp_file.tmp" "$stamp_file"
    rm -rf "$build_dir"
fi

crypto_version="$(python -c 'from importlib.metadata import version; print(version("cryptography"))')"
constraints_file="$(mktemp "$PREFIX/tmp/termux-nas-constraints.XXXXXXXX")"
trap 'rm -f "$constraints_file"' EXIT
printf 'cryptography==%s\n' "$crypto_version" > "$constraints_file"
python -m pip install --constraint "$constraints_file" "$repo_dir"
app_loader="$PREFIX/../applib/libproot-loader.so"
if [[ -f "$app_loader" ]]; then
    printf 'Checking patched PRoot with the app-provided loader...\n'
    PROOT_LOADER="$(realpath "$app_loader")" "$installed_proot" -r / "$PREFIX/bin/true"
else
    printf 'Checking patched PRoot with its bundled loader...\n'
    "$installed_proot" -r / "$PREFIX/bin/true"
fi
printf '\nInstalled. Add a NAS with `nas add` if needed, then run `nas mount NAME`.\n'
