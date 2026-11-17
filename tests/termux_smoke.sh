#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$repo_dir/src"
export TERMUX_NAS_TEST_PROOT="${PREFIX:?Run this inside Termux}/libexec/termux-nas/proot"

nas --help >/dev/null
log_file="$HOME/termux-nas-smoke.log"
if ! python -m unittest discover -s "$repo_dir/tests" -v > "$log_file" 2>&1; then
    cat "$log_file"
    exit 1
fi
cat "$log_file"
printf 'PASS: Termux CLI and patched PRoot filesystem tests\n'
