#!/usr/bin/env bash
set -euo pipefail
# Run inside the Linux/Ubuntu WSL shell, not PowerShell.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 belum tersedia. Di Ubuntu/WSL: sudo apt update && sudo apt install -y python3 python3-venv python3-pip git" >&2
  exit 1
fi
bash "$PROJECT_DIR/scripts/install-linux.sh"
