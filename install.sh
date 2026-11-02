#!/usr/bin/env bash
# Installs the wireless-wheel daemon: udev rule, firewall ports, udev reload.
# Run once, then launch the daemon manually.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULE_SRC="$SCRIPT_DIR/99-virtual-wheel.rules"
RULE_DST="/etc/udev/rules.d/99-virtual-wheel.rules"

if [[ $EUID -eq 0 ]]; then
    echo "Don't run as root. The script will sudo when needed."
    exit 1
fi

echo "==> Installing udev rule"
sudo install -m 0644 "$RULE_SRC" "$RULE_DST"
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "==> Opening UDP ports 5555 and 5556 in firewalld"
if command -v firewall-cmd >/dev/null 2>&1; then
    sudo firewall-cmd --add-port=5555/udp --permanent >/dev/null
    sudo firewall-cmd --add-port=5556/udp --permanent >/dev/null
    sudo firewall-cmd --reload >/dev/null
    echo "    ports opened:"
    sudo firewall-cmd --list-ports | tr ' ' '\n' | grep -E '^555[56]/udp$' || true
else
    echo "    firewalld not found — open 5555/udp and 5556/udp manually"
fi

echo "==> Checking user group"
if id -nG "$USER" | grep -qw input; then
    echo "    user $USER is in group 'input' — ok"
else
    echo "    user $USER is NOT in group 'input'."
    echo "    run:  sudo usermod -aG input $USER  &&  log out / log back in"
fi

echo
echo "Done. Launch the daemon:"
echo "    python3 $SCRIPT_DIR/wireless_wheel_daemon.py --verbose"
