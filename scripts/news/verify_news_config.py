#!/usr/bin/env python3
import json
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "news" / "broadcast.json"
JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def fail(msg: str):
    raise SystemExit(msg)

def main():
    cfg = load_json(CONFIG_PATH)
    jobs_doc = load_json(JOBS_PATH)
    jobs = {job['name']: job for job in jobs_doc.get('jobs', [])}
    for spec in cfg['jobs']:
        job = jobs.get(spec['name'])
        if not job:
            fail(f"missing job: {spec['name']}")
        msg = job.get('payload', {}).get('message', '')
        required = [
            '标题只允许写成：',
            '时间窗口只允许作为标题下的一行普通文本显示，绝对不能编号',
            '只允许以下四个一级标题使用数字编号',
            '整篇中带数字编号的行只能是 1 到 4',
            '不允许出现 5.、6.、7.，也不允许出现嵌套数字编号',
            '每条新闻既然已经单独附链接，文末不要再重复列一次所有来源概览'
        ]
        for token in required:
            if token not in msg:
                fail(f"missing required token in {spec['name']}: {token}")
    print('VERIFY_OK')
    for spec in cfg['jobs']:
        print(spec['name'])

if __name__ == '__main__':
    main()
