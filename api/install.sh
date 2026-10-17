#!/usr/bin/env bash
# Install garden-api as a systemd service on a Gardyn's Pi (Zero / 2 / 3 / 4).
#
# Run as the user the service should run as, from a clone of gomo:
#   git clone https://git.pkrm.dev/gomo ~/gomo && ~/gomo/api/install.sh
#
# Safe to re-run: every step checks before changing anything.
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
    echo "Run this as the service user, not root; it uses sudo where needed." >&2
    exit 1
fi

api_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
user="$(id -un)"
overlay='dtoverlay=pwm,pin=18,func=2'

# Bookworm and later: /boot/firmware/config.txt. Bullseye: /boot/config.txt.
if [[ -f /boot/firmware/config.txt ]]; then
    boot_config=/boot/firmware/config.txt
else
    boot_config=/boot/config.txt
fi

echo "==> Hardware PWM on GPIO18 (light)"
if ! grep -qxF "$overlay" "$boot_config"; then
    echo "$overlay" | sudo tee -a "$boot_config" >/dev/null
fi
if [[ ! -e /sys/class/pwm/pwmchip0 ]]; then
    sudo dtoverlay pwm pin=18 func=2   # load now so no reboot is needed
fi

echo "==> I2C (power sensor)"
sudo raspi-config nonint do_i2c 0

echo "==> Packages"
sudo apt-get install -y fswebcam
if command -v uv >/dev/null; then
    uv="$(command -v uv)"
else
    curl -LsSf https://astral.sh/uv/install.sh | sh
    uv="$HOME/.local/bin/uv"
fi

echo "==> Device access for $user"
sudo usermod -aG gpio,i2c,video "$user"

echo "==> Service"
# Never overwrite an env file that may have been edited.
if [[ ! -f /etc/garden-api.env ]]; then
    sudo install -m 644 "$api_dir/deploy/garden-api.env" /etc/garden-api.env
fi
sudo tee /etc/systemd/system/garden-api.service >/dev/null <<EOF
[Unit]
Description=Garden API (lean)
After=network.target

[Service]
User=$user
WorkingDirectory=$api_dir
# --frozen: install exactly what uv.lock pins, never re-resolve at startup.
ExecStart=$uv run --frozen garden-api
# Runs after every stop *and* crash: the pump pin must never be left high.
ExecStopPost=$uv run --frozen garden-api --pump-off
EnvironmentFile=-/etc/garden-api.env
Restart=always
RestartSec=1

# Device access: gpio (/dev/gpiomem, /sys/class/pwm), i2c (/dev/i2c-1), video (cameras).
SupplementaryGroups=gpio i2c video

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable garden-api
sudo systemctl restart garden-api

echo
echo "Installed. Check it with:"
echo "  curl http://localhost:5000/light/brightness"
echo "  journalctl -u garden-api    # lists any hardware that didn't initialize"
