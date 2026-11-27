#!/usr/bin/env bash
# Fetch Terminal-Bench 2 at the pinned commit and pull the task images used by the audit.
# Usage: bench/tbench/fetch_tb2.sh [DEST]   (default bench/tbench/data/terminal-bench-2, gitignored)
# Licence: Apache-2.0 (bench/LICENSES.md). Nothing fetched here is committed.
set -euo pipefail
REV=2fd12b88aafdd04a52c298e3940bcb189f9766d6
DEST=${1:-"$(dirname "$0")/data/terminal-bench-2"}
if [ ! -d "$DEST/.git" ]; then
  git clone --quiet https://github.com/harbor-framework/terminal-bench-2.git "$DEST"
fi
git -C "$DEST" fetch --quiet origin "$REV"
git -C "$DEST" checkout --quiet "$REV"
echo "terminal-bench-2 at $(git -C "$DEST" rev-parse HEAD) in $DEST"
