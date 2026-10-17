#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
VENV="$HOME/.local/share/novera/venv"

command -v python >/dev/null 2>&1 || { echo "Python belum terpasang. Jalankan: pkg install python" >&2; exit 1; }
mkdir -p "$(dirname "$VENV")" "$PREFIX/bin"
python -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install "$PROJECT_DIR"
ln -sf "$VENV/bin/novera" "$PREFIX/bin/novera"
chmod +x "$PREFIX/bin/novera"
echo "Novera terpasang. Jalankan: novera"
if [ ! -d "$HOME/storage/downloads" ]; then
  echo "Catatan: untuk Download bersama, jalankan termux-setup-storage. Alternatif: ubah downloads.directory menjadi ~/Novera-Downloads."
fi
