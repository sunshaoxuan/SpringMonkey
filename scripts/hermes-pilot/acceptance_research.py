"""Real, bounded research-tool checks on public primary sources."""
from pathlib import Path
import argparse,json,subprocess,time

OUT=Path('/workspace/research-acceptance');OUT.mkdir(exist_ok=True)

def search():
    from tools.web_tools import web_search_tool
    result=web_search_tool('site.playwright.dev docs browser contexts isolation',limit=3)
    data=json.loads(result) if isinstance(result,str) else result
    (OUT/'web-search.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(data))

def browser():
    from tools.browser_use_cli import browser_exec
    code='''# Reading the official Playwright isolation guide
new_tab("https://playwright.dev/docs/browser-contexts")
wait_for_load()
print(js("JSON.stringify({url:location.href,title:document.title,text:document.querySelector('main').innerText.slice(0,12000),links:[...document.querySelectorAll('main a[href]')].slice(0,20).map(a=>({title:a.textContent,url:a.href}))})"))
print(capture_screenshot())
'''
    result=browser_exec(code,session='research-check',timeout_s=120,task_id='research-acceptance')
    if isinstance(result,str):
        try:result=json.loads(result)
        except json.JSONDecodeError:result={'raw':result}
    # Native screenshot blocks may contain base64; preserve image separately via path.
    def compact(value):
        if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if k not in ['data','image_url','image']}
        if isinstance(value,list):return [compact(x) for x in value]
        if isinstance(value,str) and value.startswith('data:image/'):return '[image bytes retained by screenshot path]'
        return value
    data=compact(result)
    (OUT/'browser.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(data))

def arxiv():
    script='/opt/data/skills/research/arxiv/scripts/search_arxiv.py'
    p=subprocess.run(['/opt/hermes/.venv/bin/python',script,'ReAct','--max','3'],capture_output=True,text=True,timeout=25)
    (OUT/'arxiv-search.txt').write_text(p.stdout)
    report={'exit':p.returncode,'output':p.stdout,'error':p.stderr[-1000:]}
    print(json.dumps(report))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['search','browser','arxiv'])
    globals()[parser.parse_args().action]()
