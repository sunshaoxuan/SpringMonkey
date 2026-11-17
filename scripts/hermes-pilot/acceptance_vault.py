"""Check the installed Hermes vault using disposable synthetic credentials only."""
import dataclasses
import json
from pathlib import Path
import secrets
import stat
import tempfile

from agent.vault_store import VaultStore, VaultError


def main():
    with tempfile.TemporaryDirectory(prefix='hermes-vault-acceptance-') as temporary:
        base=Path(temporary)
        password=secrets.token_urlsafe(32)
        store=VaultStore(base)
        item=store.add_item('login','Synthetic acceptance',
                            {'identifier_type':'username','identifier':'synthetic-only','password':password},
                            origin='https://example.com')
        metadata=dataclasses.asdict(item)
        assert password not in json.dumps(metadata)
        encrypted=base/'vault.json.enc'
        key=base/'vault.key'
        assert encrypted.exists() and key.exists()
        assert password.encode() not in encrypted.read_bytes()
        assert stat.S_IMODE(encrypted.stat().st_mode)==0o600
        assert stat.S_IMODE(key.stat().st_mode)==0o600
        restored=VaultStore(base)
        assert restored.resolve_secret(item.id)['password']==password
        raw=encrypted.read_bytes()
        encrypted.write_bytes(raw[:len(raw)//2]+b'!'+raw[len(raw)//2+1:])
        try:
            VaultStore(base).resolve_secret(item.id)
        except VaultError:
            rejected=True
        else:
            rejected=False
        assert rejected,'tampered ciphertext accepted'
        return {'synthetic_only':True,'ciphertext_excludes_password':True,
                'metadata_excludes_password':True,'reload_decrypts':True,
                'ciphertext_and_key_mode':'0600','tamper_rejected':True,
                'default_key_colocated_with_ciphertext':True}


if __name__=='__main__':
    print(json.dumps(main()))
