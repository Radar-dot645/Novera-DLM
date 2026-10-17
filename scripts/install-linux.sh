#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$HOME/.local/share/novera/venv"
BIN_DIR="$HOME/.local/bin"
command -v python3 >/dev/null 2>&1 || { echo "Python 3.11+ diperlukan." >&2; exit 1; }
mkdir -p "$(dirname "$VENV")" "$BIN_DIR"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install "$PROJECT_DIR"
ln -sf "$VENV/bin/novera" "$BIN_DIR/novera"
chmod +x "$BIN_DIR/novera"
echo "Novera terpasang. Jalankan: $BIN_DIR/novera"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "Tambahkan ke PATH: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;; esac
