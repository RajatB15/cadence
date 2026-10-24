#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 24.04 server (DigitalOcean droplet). Run as root:
#   ssh root@<ip> 'bash -s' < deploy/setup-server.sh
# Idempotent: safe to run again.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync sqlite3 rclone tesseract-ocr ufw fail2ban unattended-upgrades

# Cadence schedules its notifications (06:00 brief, 21:00 bedtime nudge) and splits days in local time.
timedatectl set-timezone "${CADENCE_TZ:-Asia/Kolkata}"

# A 1 GB server gets a small swap file so a memory spike degrades instead of killing the service.
if ! swapon --show | grep -q .; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

id cadence >/dev/null 2>&1 || adduser --system --group --home /var/lib/cadence --shell /usr/sbin/nologin cadence
install -d -o cadence -g cadence -m 750 /opt/cadence /opt/cadence/app /opt/cadence/app/backend /opt/cadence/app/web /var/lib/cadence /var/lib/cadence/data
install -d -o root -g cadence -m 750 /etc/cadence

# Only SSH is reachable from the internet. Phones reach Cadence through Tailscale, which connects outwards.
ufw default deny incoming
ufw default allow outgoing
ufw limit OpenSSH
ufw --force enable

# Key-only SSH, but never lock yourself out: only if a key is already installed for root.
if [[ -s /root/.ssh/authorized_keys ]]; then
  cat > /etc/ssh/sshd_config.d/99-cadence.conf <<'SSH'
PasswordAuthentication no
PermitRootLogin prohibit-password
SSH
  systemctl reload ssh
else
  echo "WARNING: no SSH key found for root; leaving password login on. Add a key, then re-run." >&2
fi

echo "Server ready. Next: deploy/push.sh from your Mac, then install Tailscale (see docs/deploy-digitalocean.md)."
