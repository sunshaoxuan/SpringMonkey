#!/usr/bin/env python3
"""Apply the Git-pinned XHS runner without replacing unrelated direct cron jobs."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

from xhs_delivery_pipeline import configured_recipient, MODEL, JOB, WORKSPACE

REPO = Path(__file__).resolve().parents[2]
PYTHON = Path('/var/lib/openclaw/venvs/xhs/bin/python')
CRON = Path('/etc/cron.d/openclaw-direct-discord')
DIRECT_LINE = (
    f'0 10 */3 * * root /usr/local/lib/openclaw/direct_cron_to_discord.py '
    f'--name {JOB} --channel-id 1497009159940608020 --timeout 2400 '
    f'--command env HOME=/var/lib/openclaw {PYTHON} {REPO}/scripts/openclaw/xhs_delivery_pipeline.py'
)


def cli(*args: str) -> str:
    result = subprocess.run(['openclaw','--no-color',*args], env=dict(os.environ, HOME='/var/lib/openclaw'),
                            text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'OpenClaw command failed: {args[0]}')
    return result.stdout


def dispatcher_source() -> str:
    path = REPO / 'scripts' / 'remote_install_direct_discord_cron.py'
    spec = importlib.util.spec_from_file_location('direct_installer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.REMOTE.split('cat >"${HELPER}" <<\'PY\'\n', 1)[1].split('\nPY\nchmod 755', 1)[0]
    compile(source, str(path), 'exec')
    return source


def browser_guard_source() -> str:
    path = REPO / 'scripts/remote_install_browser_guardrails.py'
    spec = importlib.util.spec_from_file_location('browser_guard_installer',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.REMOTE.split("cat >/usr/local/lib/openclaw/browser_guard.py <<'PY'\n",1)[1].split('\nPY\n',1)[0]
    compile(source,str(path),'exec')
    return source


def install_browser_guard_source() -> None:
    source = browser_guard_source()
    target = Path('/usr/local/lib/openclaw/browser_guard.py')
    target.write_text(source+'\n',encoding='utf-8')
    target.chmod(0o755)


def main() -> None:
    configured_recipient()
    install_browser_guard_source()
    timezone = subprocess.check_output(['timedatectl','show','-p','Timezone','--value'], text=True).strip()
    if timezone != 'Asia/Tokyo':
        raise ValueError('direct schedule requires the verified Japan host timezone')
    if not CRON.is_file():
        raise ValueError('existing direct dispatcher schedule is missing')
    if importlib.util.find_spec('ensurepip') is None:
        import sys
        package=f'python{sys.version_info.major}.{sys.version_info.minor}-venv'
        subprocess.run(['apt-get','install','-y','--no-install-recommends',package],check=True)
    # Re-run bootstrap to repair a partially created virtual environment as well.
    subprocess.run(['python3','-m','venv','--system-site-packages',str(PYTHON.parents[1])],check=True)
    subprocess.run([str(PYTHON),'-m','pip','install','-r',str(Path(__file__).with_name('requirements-xhs.txt'))],check=True)
    config_path = Path('/var/lib/openclaw/.openclaw/openclaw.json')
    config = json.loads(config_path.read_text())
    agents = config.get('agents',{}).get('list',[])
    if not any(a.get('id') == 'xhs-writer' for a in agents):
        cli('agents','add','xhs-writer','--workspace',str(WORKSPACE / 'state' / 'xhs-delivery'),
            '--model',MODEL,'--non-interactive','--json')
    config = json.loads(config_path.read_text())
    agents = config['agents']['list']
    index = next(i for i,a in enumerate(agents) if a['id'] == 'xhs-writer')
    cli('config','set',f'agents.list.{index}.tools',json.dumps({'allow':['web_search','web_fetch','write']}),'--strict-json')
    cli('config','validate')
    subprocess.run(['systemctl','restart','openclaw.service'],check=True)
    subprocess.run(['systemctl','is-active','--quiet','openclaw.service'],check=True)
    helper = Path('/usr/local/lib/openclaw/direct_cron_to_discord.py')
    helper.write_text(dispatcher_source()+'\n', encoding='utf-8')
    helper.chmod(0o755)
    payload = json.loads(cli('cron','list','--all','--json'))
    job = next(j for j in payload['jobs'] if j.get('name') == JOB)
    cli('cron','disable',job['id'])
    lines = [line for line in CRON.read_text().splitlines() if f'--name {JOB} ' not in line]
    CRON.write_text('\n'.join(lines+[DIRECT_LINE])+'\n')
    CRON.chmod(0o644)
    print(json.dumps({'installed':True,'native_cron_enabled':False,'direct_entries':1,
                      'writer_tools':['web_search','web_fetch','write'],'recipient_configured':True}))


if __name__ == '__main__':
    main()
