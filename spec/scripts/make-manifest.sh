#!/bin/sh
# Write MANIFEST.sha256: one SHA-256 line for each file of the tree, in a stable order.
# Usage: sh scripts/make-manifest.sh   (from the root of the tree)
set -eu
cd "$(dirname "$0")/.."
LC_ALL=C find . -type f ! -name MANIFEST.sha256 ! -name '*.pyc' ! -path './.git/*' -print \
  | LC_ALL=C sort \
  | while IFS= read -r f; do sha256sum "$f"; done > MANIFEST.sha256
wc -l < MANIFEST.sha256
