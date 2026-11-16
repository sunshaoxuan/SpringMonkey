import hashlib
import json
from pathlib import Path
import sys

mode=sys.argv[1]
if mode not in {'before','after'}:raise SystemExit('unknown verification phase')
manifest=json.loads(Path('/opt/pilot/manifest.json').read_text())
for row in manifest['files']:
    data=(Path('/opt/hermes')/row['path']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=row[mode+'_sha256']:
        raise SystemExit('image source mismatch: '+row['path'])
print('Pinned image source '+mode+': PASS')
if mode=='after':
    import importlib.metadata
    for line in Path('/opt/pilot/requirements-lock.txt').read_text().splitlines():
        name,version=line.split()[0].split('==')
        if importlib.metadata.version(name)!=version:raise SystemExit('dependency version mismatch: '+name)
    import pypdf,pdfplumber,reportlab,docx,openpyxl,pptx,ddgs
    print('Reviewed document/search dependencies: PASS')
