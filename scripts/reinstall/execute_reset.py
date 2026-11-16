"""Windows controller for an explicitly authorized, prepared physical reset.

Run after activate_host.py has prepared the boot entry and all isolated checks
have passed. Production secrets remain in memory or DPAPI files.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import time
import zipfile

import paramiko


def command(c, text, timeout=45):
    _, out, err = c.exec_command(text, timeout=timeout)
    data = out.read().decode(); code = out.channel.recv_exit_status()
    if code:
        raise RuntimeError('remote_command_failed')
    return data.strip()


def validate_resume(record, commit):
    if record.get('source_commit') != commit or record.get('phase') not in {
            'PHYSICAL_ONE_SHOT_BOOT_SCHEDULED', 'PHYSICAL_BOOT_COMMAND_ACK_INTERRUPTED',
            'PHYSICAL_WAITING_LIVE', 'PHYSICAL_CHECKING_LIVE', 'PHYSICAL_RESUMING_LIVE_WAIT'}:
        raise ValueError('live_resume_not_bound_to_pending_boot')


def main():
    import win32crypt
    ap = argparse.ArgumentParser()
    ap.add_argument('--recovery', required=True, type=Path)
    ap.add_argument('--password-file', required=True, type=Path)
    ap.add_argument('--host', required=True)
    ap.add_argument('--port', type=int, default=8822)
    ap.add_argument('--commit', required=True)
    ap.add_argument('--evidence', required=True, type=Path)
    ap.add_argument('--resume-live', action='store_true')
    args = ap.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.commit):
        raise ValueError('exact_source_commit_required')
    def decrypt(name):
        return win32crypt.CryptUnprotectData((args.recovery / name).read_bytes(), None, None, None, 1)[1]
    raw = decrypt('CONNECTIVITY_RECOVERY.dpapi')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        private = paramiko.Ed25519Key.from_private_key(io.StringIO(z.read('private/admin.key').decode()))
        host_key = paramiko.Ed25519Key(data=base64.b64decode(z.read('payload/ssh_host_ed25519_key.pub').split()[1]))
        manifest = json.loads(z.read('payload/manifest.json'))
    if manifest['mode'] != 'production' or manifest['release'] != '26.10':
        raise ValueError('production_release_mismatch')
    discord = decrypt('DISCORD_CONNECTIONS.dpapi')
    if hashlib.sha256(discord).hexdigest() != json.loads((args.recovery / 'DISCORD_CONNECTIONS_MANIFEST.json').read_text())['sha256']:
        raise ValueError('discord_backup_mismatch')
    state = decrypt('TAILSCALE_STATE_AUTHENTICATED.dpapi')
    if hashlib.sha256(state).hexdigest() != json.loads((args.recovery / 'TAILSCALE_STATE_AUTHENTICATED_MANIFEST.json').read_text())['archive_sha256']:
        raise ValueError('tailscale_backup_mismatch')
    result = {'source_commit': args.commit, 'off_host_discord_backup': 'PASS', 'off_host_tailscale_backup': 'PASS'}
    def save(phase):
        result['phase'] = phase
        args.evidence.write_text(json.dumps(result, indent=2))
        print(phase, flush=True)
    if args.resume_live:
        previous = json.loads(args.evidence.read_text())
        validate_resume(previous, args.commit)
        result.update(previous)
    else:
        old = paramiko.SSHClient()
        old.load_system_host_keys(str(Path.home() / '.ssh/known_hosts'))
        old.set_missing_host_key_policy(paramiko.RejectPolicy())
        password = args.password_file.read_text(encoding='utf-8-sig').strip().splitlines()[0]
        old.connect(args.host, port=args.port, username='root', password=password, timeout=12,
                    auth_timeout=12, look_for_keys=False, allow_agent=False)
        if command(old, 'hostname') != 'ubuntu-2625':
            raise ValueError('wrong_original_host')
        prep = json.loads(command(old, 'cat /srv/springmonkey-reset-prep-20261116/PRODUCTION_BOOT_PREPARATION.json'))
        if prep.get('state') != 'BOOT_PREPARED_NOT_SCHEDULED':
            raise ValueError('boot_not_prepared')
        if command(old, 'git -C /srv/springmonkey-reset-prep-20261116/source rev-parse HEAD') != args.commit:
            raise ValueError('host_source_commit_mismatch')
        staged = json.loads(command(old, 'cat /srv/springmonkey-reset-prep-20261116/production-next/payload/manifest.json'))
        for name, digest in manifest['files'].items():
            if staged['files'].get(name) != digest:
                raise ValueError('staged_config_mismatch')
    result['controller_commit'] = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[2]), 'rev-parse', 'HEAD'], text=True).strip()
    def tailscale_probe(live=False):
        probe = 'test -s /run/reset-media-released && echo PASS' if live else 'test -s /run/reset-connectivity-ready && echo PASS'
        try:
            p = subprocess.run(['tailscale', 'ssh', 'root@ubuntu-2625', probe], capture_output=True, timeout=25)
        except subprocess.TimeoutExpired:
            return False
        return p.returncode == 0 and p.stdout.strip() == b'PASS'
    if args.resume_live:
        save('PHYSICAL_RESUMING_LIVE_WAIT')
    else:
        save('PHYSICAL_ONE_SHOT_BOOT_SCHEDULED')
        try:
            command(old, 'grub-reboot springmonkey-reset && sync && systemd-run --unit=spring-reset-reboot --on-active=5s /usr/bin/systemctl reboot')
        except (EOFError, paramiko.SSHException, OSError):
            # A reboot can close the transport before its command status arrives.
            # Continue observation; all live identity/network gates still apply.
            save('PHYSICAL_BOOT_COMMAND_ACK_INTERRUPTED')
        finally:
            old.close()
        time.sleep(10)
    save('PHYSICAL_WAITING_LIVE')
    def connect(user, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            c = paramiko.SSHClient()
            c.get_host_keys().add('[' + args.host + ']:' + str(args.port), 'ssh-ed25519', host_key)
            c.set_missing_host_key_policy(paramiko.RejectPolicy())
            try:
                c.connect(args.host, port=args.port, username=user, pkey=private, timeout=5,
                          auth_timeout=5, look_for_keys=False, allow_agent=False)
                return c
            except (paramiko.SSHException, OSError):
                c.close(); time.sleep(4)
        raise TimeoutError('prepared_host_key_ssh_timeout_' + user)
    c = connect('root', 600)
    save('PHYSICAL_CHECKING_LIVE')
    staged = json.loads(command(c, 'cat /cdrom/spring-reset/payload/manifest.json'))
    for name, digest in manifest['files'].items():
        if staged['files'].get(name) != digest:
            raise ValueError('live_config_mismatch')
    live = json.loads(command(c, "python3 -c 'import json,pathlib,subprocess; print(json.dumps({\"media\":subprocess.check_output([\"findmnt\",\"-n\",\"-o\",\"FSTYPE\",\"/cdrom\"],text=True).strip(),\"released\":pathlib.Path(\"/run/reset-media-released\").read_text().strip(),\"target_untouched\":not pathlib.Path(\"/target/etc/os-release\").exists()}))'"))
    if live != {'media': 'tmpfs', 'released': 'RAM_MEDIA_TARGET_DISK_EXCLUSIVE_PASS', 'target_untouched': True}:
        raise ValueError('live_disk_and_media_checks_failed')
    deadline = time.monotonic() + 150
    while not tailscale_probe(live=True):
        if time.monotonic() > deadline:
            c.close(); raise TimeoutError('live_original_tailscale_not_restored')
        time.sleep(4)
    result['physical_live_frp_ssh'] = 'PASS'
    result['physical_live_original_tailscale_ssh'] = 'PASS'
    result['physical_live_ram_media_exclusive_disk'] = 'PASS'
    save('PHYSICAL_LIVE_VERIFIED_ALLOWING_INSTALL')
    command(c, 'touch /run/reset-live-ssh-confirmed'); c.close()
    c = connect('springadmin', 1800)
    def verify(client):
        version = command(client, '. /etc/os-release; echo "$VERSION_ID"')
        if version != '26.10':
            raise ValueError('installed_release_mismatch')
        deadline = time.monotonic() + 180
        while True:
            services = command(client, 'systemctl is-active NetworkManager ssh reset-connectivity-ready frpc tailscaled || true').splitlines()
            if services == ['active'] * 5:
                break
            if time.monotonic() > deadline:
                raise ValueError('recovery_service_not_active')
            time.sleep(3)
        if command(client, '/usr/local/bin/frpc --version') != '0.72.0':
            raise ValueError('unexpected_frpc_version')
        if 'Status: active' not in command(client, 'sudo -n ufw status'):
            raise ValueError('firewall_not_active')
        deadline = time.monotonic() + 150
        while not tailscale_probe():
            if time.monotonic() > deadline:
                raise ValueError('new_system_tailscale_ssh_failed')
            time.sleep(4)
        command(client, 'test ! -e /var/lib/openclaw && test ! -e /usr/local/bin/openclaw && test ! -e /var/lib/docker && sudo -n true')
        return {'release': version, 'services': services,
                'boot_id': command(client, 'cat /proc/sys/kernel/random/boot_id'),
                'kernel': command(client, 'uname -r'), 'tailscale_ssh': 'PASS', 'old_app_paths_absent': 'PASS'}
    result['first_boot'] = verify(c); save('PHYSICAL_FIRST_BOOT_VERIFIED')
    # Preserve Discord as migration input, with no application activation.
    command(c, 'install -d -m 700 /home/springadmin/.reset-preserved')
    with c.open_sftp() as s:
        with s.open('/home/springadmin/.reset-preserved/discord.json', 'wb') as f:
            f.write(discord)
        s.chmod('/home/springadmin/.reset-preserved/discord.json', 0o600)
    command(c, 'sudo -n install -d -m 700 /srv/springmonkey-preserved/discord && sudo -n install -m 600 /home/springadmin/.reset-preserved/discord.json /srv/springmonkey-preserved/discord/DISCORD_CONNECTIONS.json && rm /home/springadmin/.reset-preserved/discord.json && rmdir /home/springadmin/.reset-preserved')
    expected = hashlib.sha256(discord).hexdigest()
    if command(c, 'sudo -n sha256sum /srv/springmonkey-preserved/discord/DISCORD_CONNECTIONS.json').split()[0] != expected:
        raise ValueError('discord_restored_copy_mismatch')
    result['discord_preserved_on_new_host'] = 'PASS'
    _, out, err = c.exec_command('sudo -n reboot'); c.close(); time.sleep(15)
    c = connect('springadmin', 300); result['second_boot'] = verify(c); c.close()
    if result['first_boot']['boot_id'] == result['second_boot']['boot_id']:
        raise ValueError('native_reboot_not_observed')
    result['result'] = 'PASS'; save('PHYSICAL_RESET_REBOOT_ACCESS_PASS')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('reset_controller_FAIL_' + type(e).__name__, flush=True)
        raise SystemExit(1)
