# Running Cadence on a DigitalOcean droplet

One small always-on Linux server runs Cadence. Your phone reaches it through Tailscale; nothing but SSH is open to
the internet. Nightly encrypted backups go to your Google Drive.

What the server holds: your Garmin key (`/etc/cadence/garmin.env`) and your health data
(`/var/lib/cadence/data`). The disk is not encrypted, so anyone with access to your DigitalOcean account or the
droplet could read it. Use a strong password and two-factor sign-in on DigitalOcean.

## 1. Create the droplet (DigitalOcean website)

- Region **Bangalore (BLR1)**, image **Ubuntu 24.04 (LTS) x64**.
- Plan: Basic, regular SSD, **1 GB RAM / 1 vCPU** (the $6 tier at the time of writing). 512 MB is too tight.
- Authentication: **SSH key**. If you don't have one, run `ssh-keygen -t ed25519` on your Mac and paste the contents
  of `~/.ssh/id_ed25519.pub` into DigitalOcean.
- Name it `cadence`. Skip the paid extras. Note the droplet's IP address.

## 2. Prepare the server

```sh
ssh root@<ip> 'bash -s' < deploy/setup-server.sh
```

This sets the timezone to Asia/Kolkata (notifications fire at 06:00 and 21:00 local time), adds a swap file,
creates a `cadence` user, opens only SSH in the firewall, and switches SSH to key-only login. Change the zone with
`CADENCE_TZ=Europe/London ssh ...` if you move.

## 3. Deploy the code

```sh
deploy/push.sh root@<ip>
```

Run it again whenever you change the code. It builds the web app on your Mac, copies the backend and build, installs,
and restarts the service.

## 4. Move your data and Garmin key

On your Mac, stop the local service first so nothing writes while you copy:

```sh
scripts/cadence-service.sh uninstall
sqlite3 data/cadence.sqlite3 ".backup '/tmp/cadence.sqlite3'"
ssh root@<ip> 'systemctl stop cadence'
scp /tmp/cadence.sqlite3 root@<ip>:/var/lib/cadence/data/cadence.sqlite3
rsync -a data/archive/ root@<ip>:/var/lib/cadence/data/archive/
scp .secrets/garmin.env root@<ip>:/etc/cadence/garmin.env
ssh root@<ip> 'chown -R cadence:cadence /var/lib/cadence/data && chown root:cadence /etc/cadence/garmin.env && chmod 640 /etc/cadence/garmin.env && systemctl start cadence'
rm /tmp/cadence.sqlite3
```

Keep your Mac's `data/` folder as a safety copy until you're happy with the server.

## 5. Reach it from your phone (Tailscale)

On the droplet:

```sh
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
tailscale serve --bg 8766
```

Enable HTTPS certificates in the Tailscale admin console, and install Tailscale on your iPhone with the same account.

The full app (port 8765) only listens on the server itself. To open it from your Mac, tunnel to it, then use the
Settings page to start phone sharing and scan the pairing QR code:

```sh
ssh -L 8765:127.0.0.1:8765 root@<ip>      # leave running; Cadence is then at http://127.0.0.1:8765
```

Your Mac's own service must be stopped (step 4) because it uses the same port. Phones re-pair and re-enable
notifications once, since the address changed.

## 6. Encrypted backups to Google Drive

Notes: the Garmin key and the push-notification key are deliberately not backed up. Files are encrypted before they
leave the server using rclone's `crypt`. **Save the two passwords you choose below somewhere safe (a password
manager). Without them the backups cannot be read.**

On your Mac, install rclone (`brew install rclone`) and run `rclone authorize "drive"`, sign in, and copy the token it
prints. On the droplet:

```sh
sudo -u cadence RCLONE_CONFIG=/var/lib/cadence/rclone.conf rclone config
```

1. New remote `gdrive`, storage `drive`, scope `drive.file`, leave the rest default, answer **n** to "Use auto config",
   and paste the token from your Mac.
2. New remote `cadence-crypt`, storage `crypt`, remote `gdrive:cadence-backup`, encrypt filenames, and set both
   passwords (generate them).

Then test it and switch on the nightly timer (03:30):

```sh
sudo -u cadence RCLONE_CONFIG=/var/lib/cadence/rclone.conf CADENCE_DATA_DIR=/var/lib/cadence/data /opt/cadence/deploy/backup.sh
systemctl enable --now cadence-backup.timer
```

The newest 14 database snapshots are kept; the Garmin archive is uploaded once and only new files after that.

**Restore** onto a fresh server (after steps 2-3 and the rclone config):

```sh
RCLONE_CONFIG=/var/lib/cadence/rclone.conf rclone lsf --dirs-only cadence-crypt:db     # pick a snapshot
RCLONE_CONFIG=/var/lib/cadence/rclone.conf /opt/cadence/deploy/restore.sh 20261024-0330
```

## Everyday commands

```sh
ssh root@<ip> systemctl status cadence
ssh root@<ip> journalctl -u cadence -n 50 --no-pager     # logs can contain health data; skim for errors only
ssh root@<ip> systemctl list-timers cadence-backup.timer
```

## Not available on the server

The strength-class screenshot reader uses Apple's on-device text recognition, which only exists on a Mac. On the
server, paste the class text instead.
