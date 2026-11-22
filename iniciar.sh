#!/usr/bin/env bash
set -euo pipefail
proyecto_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$proyecto_dir"
exec "$proyecto_dir/.venv/bin/python" "$proyecto_dir/Codigo/Interfaz.py"
