# Sourced by deploy.sh and push.sh. The server's firewall rate-limits new SSH connections, and a deploy opens several
# (rsync x4, ssh x3), so it was refused part-way. This shares one connection for the whole run, for ssh and rsync alike.
SSH_SHARE=(-o ControlMaster=auto -o "ControlPath=/tmp/cadence-ssh-%C" -o ControlPersist=120 -o ConnectionAttempts=5 -o ConnectTimeout=15)
ssh() { command ssh "${SSH_SHARE[@]}" "$@"; }
export RSYNC_RSH="ssh ${SSH_SHARE[*]}"
