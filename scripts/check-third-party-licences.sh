#!/usr/bin/env bash
set -euo pipefail
exec python3 scripts/generate-third-party-licences.py --check
