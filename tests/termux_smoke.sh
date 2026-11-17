#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$repo_dir/src"
export TERMUX_NAS_TEST_PROOT="${PREFIX:?Run this inside Termux}/libexec/termux-nas/proot"

nas --help >/dev/null
python -m unittest discover -s "$repo_dir/tests" -v
printf 'PASS: Termux CLI and patched PRoot filesystem tests\n'
