import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from guard import check_disk, check_manifest, release_install_source, wait_wifi
from persist_failure import persist
from prepare import frp_config
import tomllib


class SafetyContracts(unittest.TestCase):
    def test_wifi_waits_for_address_and_route(self):
        values = ['40 (connecting)\n', '[]', '[{"addr_info":[]}]',
                  '100 (connected)\n', '[{"dev":"wlan-test"}]', '[{"addr_info":[{"scope":"global"}]}]']
        with patch('guard.subprocess.check_output', side_effect=values), patch('guard.time.sleep') as pause:
            wait_wifi('wlan-test')
            pause.assert_called_once_with(2)

    def test_wifi_timeout_blocks_install(self):
        with patch('guard.subprocess.check_output', side_effect=['40\n', '[]', '[]']), patch('guard.time.monotonic', side_effect=[0, 2]):
            with self.assertRaisesRegex(TimeoutError, 'wifi_connection_address_route_timeout'):
                wait_wifi('wlan-test', timeout=1)

    def test_failure_log_cannot_mount_after_ack(self):
        with patch('persist_failure.Path.exists', return_value=True), patch('persist_failure.subprocess.run') as mount:
            with self.assertRaisesRegex(ValueError, 'after_ack'):
                persist('unused', 'preflight', 1)
            mount.assert_not_called()

    def test_failure_log_rejects_wrong_disk_before_mount(self):
        expected = {'path':'/dev/vda','bytes':123,'serial':'expected','gpt_id':'expected'}
        wrong = dict(expected, serial='different')
        with patch('persist_failure.Path.exists', return_value=False), patch('persist_failure.check_manifest', return_value={'mode':'fixture','disk':expected}), patch('persist_failure.disk_identity', return_value=wrong), patch('persist_failure.subprocess.run') as mount:
            with self.assertRaisesRegex(ValueError, 'disk_identity_mismatch_serial'):
                persist('unused', 'preflight', 1)
            mount.assert_not_called()

    def test_disk_backed_media_rejected_before_release(self):
        with patch('guard.subprocess.check_output', return_value='iso9660\n') as probe:
            with self.assertRaisesRegex(ValueError, 'installation_media_not_in_ram'):
                release_install_source('/dev/vda')
            self.assertEqual(probe.call_count, 1)

    def test_exact_disk_required(self):
        expected = {'path': '/dev/sda', 'bytes': 360777252864, 'serial': 'disk-a', 'gpt_id': 'original-gpt'}
        check_disk(expected, expected.copy())
        for field in expected:
            wrong = expected.copy(); wrong[field] = 'wrong'
            with self.subTest(field=field), self.assertRaises(ValueError):
                check_disk(expected, wrong)

    def test_payload_tamper_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'frpc').write_bytes(b'expected-binary')
            manifest = {'files': {'frpc': hashlib.sha256(b'expected-binary').hexdigest()}}
            (root / 'manifest.json').write_text(json.dumps(manifest)); check_manifest(root)
            (root / 'frpc').write_bytes(b'tampered')
            with self.assertRaises(ValueError): check_manifest(root)
            manifest['files'] = {'../escape': 'unused'}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): check_manifest(root)

    def test_frp_only_one_local_ssh_proxy(self):
        good = {'serverAddr': 'example.invalid', 'serverPort': 7000, 'auth': {'method': 'token', 'token': 'fixture'},
                'proxies': [{'name': 'ssh', 'type': 'tcp', 'localPort': 22, 'localIP': '127.0.0.1', 'remotePort': 8822}]}
        self.assertEqual(tomllib.loads(frp_config(good).decode())['proxies'][0]['localPort'], 22)
        bads = []
        value = copy.deepcopy(good); value['proxies'].append(dict(value['proxies'][0])); bads.append(value)
        value = copy.deepcopy(good); value['proxies'][0]['localPort'] = 18789; bads.append(value)
        value = copy.deepcopy(good); value['proxies'][0]['localIP'] = '10.0.0.2'; bads.append(value)
        value = copy.deepcopy(good); value['webServer'] = {'port': 7400}; bads.append(value)
        for value in bads:
            with self.assertRaises(ValueError): frp_config(value)


if __name__ == '__main__':
    unittest.main()
