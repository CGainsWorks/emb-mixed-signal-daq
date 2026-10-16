#!/usr/bin/env bash
# One command from a clean checkout: install, regenerate, test, cross-check.
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/setup.sh
make ci PY=python3
