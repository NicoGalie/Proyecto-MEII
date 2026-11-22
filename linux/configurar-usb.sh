#!/usr/bin/env bash
set -euo pipefail
proyecto_dir="$(cd -- "$(dirname -- "$0")/.." && pwd)"
if [[ "$#" -eq 0 ]]; then
    set -- 5656:0832 6656:0834
fi
if [[ "$EUID" -ne 0 ]]; then
    exec pkexec /usr/bin/python3 "$proyecto_dir/linux/configurar_usb.py" "$@"
fi
exec /usr/bin/python3 "$proyecto_dir/linux/configurar_usb.py" "$@"
