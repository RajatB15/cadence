#!/usr/bin/env bash
# Run on the droplet as root: serves the phone share port over HTTPS at https://<hostname>, no VPN on the phone.
#   deploy/enable-public.sh cadence.<ip-with-dashes>.sslip.io     (sslip.io is a free name that points at that IP)
# Caddy gets and renews a Let's Encrypt certificate on its own. Only 80 (certificate check) and 443 are opened; the
# share server itself stays bound to loopback. Phones still need a one-time QR pairing; unpaired requests get nothing.
set -euo pipefail
HOSTNAME_="${1:?usage: enable-public.sh <hostname>}"
[[ "$HOSTNAME_" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "Bad hostname" >&2; exit 2; }

if ! command -v caddy >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi

cat > /etc/caddy/Caddyfile <<CADDY
$HOSTNAME_ {
	encode zstd gzip
	reverse_proxy 127.0.0.1:8766
	header {
		Strict-Transport-Security "max-age=31536000"
		-Server
	}
}
CADDY
systemctl enable --now caddy
systemctl reload caddy

ufw allow 80/tcp
ufw allow 443/tcp

# The app builds its pairing QR from this address and keeps the share port off the network.
sed -i '/^CADENCE_PUBLIC_URL=/d;/^CADENCE_SHARE_HOST=/d' /etc/cadence/cadence.env
printf 'CADENCE_PUBLIC_URL=https://%s\nCADENCE_SHARE_HOST=127.0.0.1\n' "$HOSTNAME_" >> /etc/cadence/cadence.env
systemctl restart cadence
echo "Done. Open https://$HOSTNAME_ (the first request can take a few seconds while the certificate is issued)."
