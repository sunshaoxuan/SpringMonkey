"""Bake PM's pinned driver outside the runtime /opt/data volume."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

home=Path('/opt/pilot/driver-build-home')
home.mkdir(mode=0o700,parents=True,exist_ok=True)
env={**os.environ,'HOME':str(home),'HERMES_HOME':str(home),
     'XDG_DATA_HOME':str(home/'.local/share'),'XDG_CACHE_HOME':str(home/'.cache')}
subprocess.run(['/opt/hermes/.venv/bin/hermes','pm','install','cua-driver'],env=env,check=True)
candidates=[p for p in home.rglob('cua-driver') if p.is_file()]
if not candidates:
    raise RuntimeError('PM driver was not installed under isolated build home')
digests={hashlib.sha256(p.read_bytes()).hexdigest() for p in candidates}
if len(digests)!=1:
    raise RuntimeError('ambiguous driver builds')
target=Path('/opt/pilot/cua-driver')
shutil.copyfile(candidates[0],target)
target.chmod(0o755)
assert hashlib.sha256(target.read_bytes()).hexdigest() in digests
version=subprocess.check_output([str(target),'--version'],text=True).strip()
if '0.21.0' not in version:
    raise RuntimeError('driver version does not match fixed Hermes PM lock')
print(version)
