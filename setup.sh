#!/usr/bin/env bash
# Keymic setup script for Linux.
# Installiert System-Deps und startet interaktives Setup.

set -euo pipefail

if [[ $EUID -eq 0 ]]; then
    echo "Bitte nicht als root ausführen." >&2
    exit 1
fi

# Detect distro
if command -v pacman &>/dev/null; then
    DISTRO="arch"
elif command -v apt &>/dev/null; then
    DISTRO="debian"
else
    echo "Nicht unterstützte Distribution. Installiere ydotool, xdotool, wl-clipboard manuell." >&2
    DISTRO="unknown"
fi

echo "==> Distribution erkannt: $DISTRO"

# Install system deps
case "$DISTRO" in
    arch)
        echo "==> Installiere via pacman..."
        sudo pacman -S --needed --noconfirm \
            pipewire pipewire-pulse pw-cli \
            ydotool \
            xdotool \
            wl-clipboard \
            xclip \
            python python-pip
        ;;
    debian)
        echo "==> Installiere via apt..."
        sudo apt update
        sudo apt install -y \
            pipewire pipewire-pulse \
            ydotool \
            xdotool \
            wl-clipboard \
            xclip \
            python3 python3-pip python3-venv
        ;;
    *)
        echo "==> Überspringe Paketinstallation."
        ;;
esac

# User-Groups (input für evdev, audio für mic)
echo "==> Setze User-Groups (input, audio)..."
sudo usermod -aG input,audio "$USER" || true
echo "Hinweis: Neu-Anmeldung erforderlich, damit Group-Änderung wirkt."

# Python deps
echo "==> Installiere Python-Deps..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install --user -e "$SCRIPT_DIR"

# Start ydotoold if Wayland
if command -v ydotoold &>/dev/null; then
    if ! pgrep -x ydotoold >/dev/null; then
        echo "==> Starte ydotoold..."
        ydotoold &
        sleep 1
    fi
fi

# Start interactive setup
echo "==> Starte Setup..."
python3 -m keymic setup

echo ""
echo "==> Fertig. Daemon starten mit: python -m keymic run"
