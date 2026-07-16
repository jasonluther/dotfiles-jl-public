#!/usr/bin/env bash
# Install unattended-upgrades configured for full nightly updates.
#
# Upgrades from *every* configured apt origin (origin=*), not just the
# security pockets the packaged default allows — so distro -updates and
# third-party repos (NodeSource, 1Password, Tailscale, ...) are all covered
# without maintaining an origin list. Hosts reboot automatically at 04:00
# when an update requires it, even with users logged in.
#
# Config lives in a 52- drop-in so the packaged 50unattended-upgrades stays
# pristine and package upgrades never hit a dpkg conffile prompt.

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

sudo apt-get install -y --no-install-recommends unattended-upgrades

conf=/etc/apt/apt.conf.d/52unattended-upgrades-local
sudo tee "$conf" >/dev/null <<'EOF'
// Managed by jasonluther/dotfiles-jl-public scripts/linux. Edit upstream, not here.
// Upgrade from every configured origin, not just security. Merged with the
// packaged 50unattended-upgrades security origins (this is a superset).
Unattended-Upgrade::Origins-Pattern {
    "origin=*";
};
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
EOF
sudo chmod 0644 "$conf"

# Ubuntu ships this via ubuntu-release-upgrader; minimal Debian hosts don't.
sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
sudo chmod 0644 /etc/apt/apt.conf.d/20auto-upgrades

# `/run/systemd/system` is the canonical "systemd is PID 1" check (sd_booted).
# Without it (Docker containers, chroots) `systemctl --now` can't reach the
# bus and aborts the apply; the config drop-ins above are still written, so
# the units activate normally on a real boot.
if [ -d /run/systemd/system ]; then
  sudo systemctl enable --now apt-daily.timer apt-daily-upgrade.timer
  sudo systemctl enable unattended-upgrades.service
else
  echo "unattended-upgrades: systemd not running (container/chroot?) — skipping unit enable" >&2
fi
