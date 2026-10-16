#!/usr/bin/env bash
# Install what `make ci` needs on Debian or Ubuntu: a C compiler, ngspice and
# the Python packages. ngspice is optional; without it `make spice` skips.
set -euo pipefail
if command -v apt-get >/dev/null; then
    sudo apt-get install -y -qq gcc make ngspice || \
        (sudo apt-get update -qq && sudo apt-get install -y -qq gcc make ngspice)
fi
python3 -m pip install -r "$(dirname "$0")/../requirements.txt"
