# Running Cadence on a DigitalOcean droplet

One small always-on Linux server runs Cadence. Your phone reaches it through Tailscale, only SSH is open to the
internet, and nightly encrypted backups go to your Google Drive.

The server holds your Garmin key (`/etc/cadence/garmin.env`) and your health data (`/var/lib/cadence/data`). The disk
is not encrypted, so anyone with access to your DigitalOcean account or the droplet could read it. Turn on two-factor
sign-in for DigitalOcean and keep your SSH key private.

## Everyday use

```sh
scripts/deploy.sh          # runs the tests, builds the web app, deploys, waits until the server is healthy
scripts/deploy.sh --fast   # same, skipping the tests
```

The server address is read from `.deploy-host` in the repo root (git-ignored), for example `root@203.0.113.10`. You can
also pass it as an argument or set `CADENCE_DEPLOY_HOST`. It deploys your working tree, not the last commit, and says
so when there are uncommitted changes.

What it does: backend tests, web typecheck and tests, `npm run build` on your Mac (the server needs no Node), copies the
backend, web build and `deploy/` to `/opt/cadence`, installs the Python packages, restarts the `cadence` service, and
waits for `/api/health`. Database migrations run automatically when the service starts. Your data is never touched by a
deploy.

Useful commands:

```sh
ssh root@<ip> systemctl status cadence
ssh root@<ip> journalctl -u cadence -n 50 --no-pager    # logs can contain health data; skim for errors only
ssh root@<ip> systemctl list-timers cadence-backup.timer
ssh -L 8765:127.0.0.1:8765 root@<ip>                     # then open http://127.0.0.1:8765 on your Mac
```

## One-time setup

### 1. Create the droplet (DigitalOcean website)

- Region **Bangalore (BLR1)**, image **Ubuntu 24.04 (LTS) x64**.
- Plan: **Basic, Regular CPU, 1 GB RAM, 25 GB disk, $6/month** (`s-1vcpu-1gb`). Newer plan types listed first on the
  page can cost about three times as much for the same RAM. 512 MB is too small.
- Authentication: **SSH key**. Create one with `ssh-keygen -t ed25519`, then `pbcopy < ~/.ssh/id_ed25519.pub` and paste
  it into "Add SSH Key". Never share the file without `.pub`.
- Name it `cadence`, leave the paid extras off, and note the droplet's public IPv4 address.

Put the address in `.deploy-host`:

```sh
echo 'root@<ip>' > .deploy-host
```

### 2. Prepare the server

```sh
ssh root@<ip> 'bash -s' < deploy/setup-server.sh
```

This sets the timezone to Asia/Kolkata (notifications fire at 06:00 and 21:00 local time; use
`CADENCE_TZ=<zone>` to change it), adds a 1 GB swap file, creates a `cadence` user, allows only SSH through the
firewall (rate-limited), and switches SSH to key-only login (only if a key is installed). It is safe to run again.

### 3. First deploy

```sh
scripts/deploy.sh --fast
```

### 4. Move your data and Garmin key

Stop the Mac's own service first so the database is flushed and nothing writes during the copy:

```sh
scripts/cadence-service.sh uninstall
ssh root@<ip> 'systemctl stop cadence && rm -f /var/lib/cadence/data/cadence.sqlite3*'
rsync -a data/cadence.sqlite3 root@<ip>:/var/lib/cadence/data/cadence.sqlite3
rsync -a data/archive/ root@<ip>:/var/lib/cadence/data/archive/
scp .secrets/garmin.env root@<ip>:/etc/cadence/garmin.env
ssh root@<ip> 'chown -R cadence:cadence /var/lib/cadence/data && chown root:cadence /etc/cadence/garmin.env && chmod 640 /etc/cadence/garmin.env && systemctl restart cadence'
```

Keep the Mac's `data/` folder as a safety copy. Only one place should run Cadence at a time; to go back to the Mac, run
`scripts/cadence-service.sh install`. The push-notification key is not copied; the server makes its own, and phones
re-enable notifications once.

Check it: `ssh root@<ip> 'curl -s http://127.0.0.1:8765/api/health'`, then run a sync from the app (or
`curl -X POST -H 'X-Cadence-Request: 1' -H 'Content-Type: application/json' -d '{"mode":"quick"}' http://127.0.0.1:8765/api/garmin/sync`
on the server).

### 5. Phone access with Tailscale

On the droplet (Tailscale's own package repository):

```sh
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg -o /usr/share/keyrings/tailscale-archive-keyring.gpg
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list -o /etc/apt/sources.list.d/tailscale.list
apt-get update && apt-get install -y tailscale
tailscale up --hostname=cadence       # open the printed link and sign in
tailscale serve --bg 8766             # HTTPS address for the phone share server
```

Install Tailscale on your iPhone with the same account, and enable HTTPS certificates in the Tailscale admin console
if it asks. The address looks like `https://cadence.<tailnet>.ts.net`. The first request can take about 30 seconds
while the certificate is issued.

To pair the phone, tunnel to the full app, open Settings, and scan the QR code on the phone-sharing card:

```sh
ssh -L 8765:127.0.0.1:8765 root@<ip>        # leave running; the Mac's own service must be stopped
# open http://127.0.0.1:8765/settings
```

Then add the page to the Home Screen and turn notifications on again.

### 6. Encrypted backups to Google Drive

Files are encrypted on the server (rclone `crypt`, including file names) before upload. The Garmin key and the
push-notification key are deliberately not backed up. The nightly job stores the newest 14 database snapshots, and
uploads each archived Garmin response once.

Create two random passwords on the server and keep them in a password manager. **Without them the backups cannot be
read, and nobody can recover them.**

```sh
ssh root@<ip> 'umask 077; printf "password1=%s\npassword2=%s\n" "$(openssl rand -base64 24)" "$(openssl rand -base64 24)" > /root/cadence-backup-passwords.txt; cat /root/cadence-backup-passwords.txt'
```

Save both lines, then delete the file from the server: `ssh root@<ip> shred -u /root/cadence-backup-passwords.txt`.
(The passwords are also stored, lightly obscured, inside the rclone config on the server.)

Sign in to Google from the server through a temporary tunnel (the server has no browser). Keep this tunnel open:

```sh
ssh -L 53682:127.0.0.1:53682 root@<ip>
```

In a second terminal, start the sign-in on the server and open the printed `http://127.0.0.1:53682/auth?...` link in
your Mac browser, choosing the Google account for the backups. The scope `drive.file` gives access only to files this
backup creates.

```sh
ssh root@<ip> 'install -m 600 -o cadence -g cadence /dev/null /var/lib/cadence/auth.log; sudo -u cadence rclone authorize drive --drive-scope drive.file > /var/lib/cadence/auth.log 2>&1 &'
ssh root@<ip> "grep -o 'http://127.0.0.1:53682/auth?state=[A-Za-z0-9_-]*' /var/lib/cadence/auth.log"
```

After you approve, build the rclone config from the token that was saved (nothing is printed), then remove it:

```sh
ssh root@<ip> 'bash -s' <<'EOF'
set -e
export RCLONE_CONFIG=/var/lib/cadence/rclone.conf
tok=$(grep -o '{"access_token".*}' /var/lib/cadence/auth.log | head -1)
p1=$(grep ^password1= /root/cadence-backup-passwords.txt | cut -d= -f2-)
p2=$(grep ^password2= /root/cadence-backup-passwords.txt | cut -d= -f2-)
rm -f "$RCLONE_CONFIG"
rclone config create gdrive drive scope drive.file token "$tok" </dev/null >/dev/null 2>&1 || true
rclone config create cadence-crypt crypt remote gdrive:cadence-backup filename_encryption standard password "$p1" password2 "$p2" </dev/null >/dev/null
chown cadence:cadence "$RCLONE_CONFIG"; chmod 600 "$RCLONE_CONFIG"
shred -u /var/lib/cadence/auth.log
EOF
```

(Run this before deleting the passwords file. The first `rclone config create` may stall on a Shared Drive question;
the token is already saved at that point, so stop it with Ctrl+C and continue.)

Test, then turn on the nightly timer (03:30):

```sh
ssh root@<ip> 'sudo -u cadence env RCLONE_CONFIG=/var/lib/cadence/rclone.conf CADENCE_DATA_DIR=/var/lib/cadence/data /opt/cadence/deploy/backup.sh'
ssh root@<ip> 'systemctl enable --now cadence-backup.timer'
```

The first run is slow because it uploads every archived response one by one (hundreds of small files); later runs take
about two minutes. After every run (and every failure) the script writes `backup-status.json` into the data folder, and
**Settings -> Backups** in the app shows when the last backup succeeded, turning amber if more than 36 hours have passed
or the last run failed. A machine that has never run a backup shows a neutral "no backup has run" note.

## Restoring from a backup

On a fresh server (steps 1-3, then the Google sign-in and rclone config from step 6):

```sh
ssh root@<ip> 'RCLONE_CONFIG=/var/lib/cadence/rclone.conf rclone lsf --dirs-only cadence-crypt:db'    # pick a snapshot
ssh root@<ip> 'RCLONE_CONFIG=/var/lib/cadence/rclone.conf /opt/cadence/deploy/restore.sh 20261024-0330'
```

The restore keeps the previous database next to the new one as `cadence.sqlite3.before-restore`. You then need to
copy `/etc/cadence/garmin.env` back (step 4).

## Troubleshooting

- **SSH says "Connection refused" or times out:** the firewall rate-limits SSH to about six new connections per 30
  seconds per address, and every retry restarts that window, so do not retry in a loop. Wait a minute, or connect over
  Tailscale instead (`ssh root@<tailscale-ip>`, from `tailscale status`), which counts separately. A deploy followed by
  more commands can trigger it.
- **`scripts/deploy.sh` says the server did not become healthy:** `ssh root@<ip> journalctl -u cadence -n 50 --no-pager`.
  The 1 vCPU server needs about 15 seconds to start.
- **Phone shows "not paired":** re-scan the QR code from the tunnelled Settings page.
- **Notifications have the wrong time:** check `ssh root@<ip> timedatectl`; it should show Asia/Kolkata (or your zone).
- **Memory:** the service uses about 460 MB of the 1 GB plus a 1 GB swap file. `ssh root@<ip> free -m` to check.

## Not available on the server

The strength-class screenshot reader uses Apple's on-device text recognition, which only exists on a Mac. On the server,
paste the class text instead.
