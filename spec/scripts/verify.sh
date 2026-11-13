#!/bin/sh
# Run each check of the tree. Exit 0 only when each check passes.
# Usage: sh scripts/verify.sh   (from the root of the tree)
set -u
cd "$(dirname "$0")/.."
rc=0
step() {
  name=$1; shift
  if "$@"; then echo "PASS $name"; else echo "FAIL $name"; rc=1; fi
}
step "form of the documents" python3 -I scripts/lint-docs.py .
step "ids"                   python3 -I scripts/check-ids.py .
step "section pointers"      python3 -I scripts/check-refs.py .
if [ -f schemas/validate.py ]; then
  step "schemas and examples" python3 -I schemas/validate.py
fi
if [ -f MANIFEST.sha256 ]; then
  step "manifest" sha256sum --quiet -c MANIFEST.sha256
fi
exit $rc
