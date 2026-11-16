#!/bin/sh
set -eu
phase=installer-environment
rollback=0
on_exit() {
    rc=$?
    if test "$rc" -ne 0; then
        echo "bootstrap_FAIL_${phase}_${rc}" >&2
        if test "$rollback" = 1 && ! test -f /run/reset-live-ssh-confirmed; then
            sync
            reboot
        fi
    fi
}
trap on_exit EXIT
# Executed only inside the live installer. Never invoke on the running host.
payload=/cdrom/spring-reset/payload
test -r /cdrom/casper/install-sources.yaml
test "$(findmnt -n -o FSTYPE /)" = overlay
phase=armed-payload
test -f "$payload/ARMED.json"
python3 -c 'import sys; sys.path.insert(0,sys.argv[1]); from guard import check_manifest; check_manifest(__import__("pathlib").Path(sys.argv[1]))' "$payload"
if python3 -c 'import json,sys; sys.exit(json.load(open(sys.argv[1]))["mode"] != "production")' "$payload/manifest.json"; then rollback=1; fi
export DEBIAN_FRONTEND=noninteractive
phase=offline-dependencies
mkdir -p /var/cache/apt/archives
cp "$payload"/debs/*.deb /var/cache/apt/archives/
apt-get -y --no-download install /var/cache/apt/archives/*.deb >/run/reset-offline-install.log 2>&1
apt-get clean
phase=network-configuration
rm -f /etc/netplan/*.yaml
install -m 600 "$payload/network.yaml" /etc/netplan/90-reset-connectivity.yaml
systemctl start NetworkManager
netplan generate
netplan apply >/run/reset-netplan.log 2>&1
phase=preflight
python3 "$payload/guard.py" "$payload"
if test -f "$payload/tailscaled"; then
    install -d -m 700 /var/lib/tailscale
    install -d -m 755 /run/tailscale
    tar -xzf "$payload/tailscale-state.tar.gz" -C / --wildcards 'var/lib/tailscale/*'
    chmod 700 /var/lib/tailscale
    hostname ubuntu-2625
    "$payload/tailscaled" --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock --port=41641 >/run/reset-tailscaled.log 2>&1 &
fi
# Prove live remote login is possible before allowing the installer to touch disks.
phase=installer-ssh
install -d -m 700 /root/.ssh
install -m 600 "$payload/admin.pub" /root/.ssh/authorized_keys
mkdir -p /run/sshd
printf 'PermitRootLogin prohibit-password\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nUsePAM yes\nPubkeyAuthentication yes\nAuthorizedKeysFile /root/.ssh/authorized_keys\n' >/run/reset-sshd.conf
/usr/sbin/sshd -t -f /run/reset-sshd.conf
install -m 600 "$payload/ssh_host_ed25519_key" /run/reset_host_ed25519_key
/usr/sbin/sshd -f /run/reset-sshd.conf -p 2222 -h /run/reset_host_ed25519_key
phase=installer-frp
python3 - "$payload" <<'PY'
import json,pathlib,subprocess,sys,time
p=pathlib.Path(sys.argv[1])
# Use a local copy of the configured SSH proxy, redirecting to installer sshd.
# The original port must be free because the old system has already stopped.
s=(p/'frpc.toml').read_text().replace('localPort = 22\n','localPort = 2222\n')
path=pathlib.Path('/run/reset-frpc.toml');path.write_text(s);path.chmod(0o600)
log=open('/run/reset-frpc.log','w')
process=subprocess.Popen([str(p/'frpc'),'-c',str(path)],stdout=log,stderr=log)
deadline=time.monotonic()+300
while time.monotonic()<deadline:
    # An authenticated controller must acknowledge the live installer through SSH.
    if pathlib.Path('/run/reset-live-ssh-confirmed').is_file():
        pathlib.Path('/run/reset-live-frpc.pid').write_text(str(process.pid));break
    if process.poll() is not None: raise SystemExit('live_frp_exited')
    time.sleep(2)
else:
    process.terminate();raise SystemExit('live_remote_confirmation_missing')
PY
