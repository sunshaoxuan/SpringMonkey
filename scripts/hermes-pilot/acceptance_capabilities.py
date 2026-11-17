"""Bounded synthetic-file acceptance inside the extended CLI image; no model keys."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import os
import subprocess
import sys

ROOT = Path('/workspace/capabilities-acceptance')
ROOT.mkdir(exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(ROOT / 'matplotlib-cache')
os.environ['MPLBACKEND'] = 'Agg'
os.environ['HOME'] = '/workspace'
results = {}


def run(args, timeout=90):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('failed ' + args[0] + ': ' + p.stderr[-1200:])
    return p.stdout


def main():
    import numpy as np
    import pandas as pd
    from scipy import stats
    import matplotlib.pyplot as plt
    import plotly.express as px
    import seaborn
    import debugpy
    import nbformat
    from openpyxl import Workbook, load_workbook
    from docx import Document
    from pptx import Presentation
    from pypdf import PdfReader
    from PIL import Image, ImageDraw, ImageFont
    import pytesseract
    from playwright.sync_api import sync_playwright

    packages = ['numpy', 'pandas', 'scipy', 'matplotlib', 'seaborn', 'plotly',
                'pygount', 'debugpy', 'playwright', 'pytesseract', 'pytest', 'hypothesis', 'nbformat']
    results['versions'] = {n: metadata.version(n) for n in packages}
    df = pd.DataFrame({'month': ['Jan', 'Feb', 'Mar'], 'value': [10, 15, 20]})
    df.to_csv(ROOT / 'sample.csv', index=False)
    assert df['value'].sum() == 45 and np.mean(df['value']) == 15
    assert abs(stats.linregress([1, 2, 3], df['value']).slope - 5) < 0.001
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(df['month'], df['value']); ax.set_title('Synthetic monthly totals'); ax.set_ylabel('Value')
    fig.tight_layout(); fig.savefig(ROOT / 'chart.png', dpi=150); plt.close(fig)
    px.bar(df, x='month', y='value', title='Synthetic fixture').write_html(ROOT / 'interactive-chart.html')
    (ROOT / 'statistics.json').write_text(json.dumps({'sum': 45, 'mean': 15, 'slope': 5}))
    results['analysis'] = 'PASS: CSV, exact totals, regression, PNG and interactive HTML'

    wb = Workbook(); ws = wb.active
    ws.append(['Month', 'Value'])
    for row in df.itertuples(index=False, name=None): ws.append(row)
    ws.append(['Total', '=SUM(B2:B4)']); wb.save(ROOT / 'sample.xlsx')
    doc = Document(); doc.add_heading('Capability acceptance', 0)
    doc.add_paragraph('Synthetic fixture. HERMES DOCUMENT 7419. 日本語・中文の文書処理。')
    doc.add_paragraph('Total: 45. Mean: 15.'); doc.save(ROOT / 'sample.docx')
    slides = Presentation()
    for title in ['Synthetic acceptance', 'Total 45 / Mean 15']:
        slide = slides.slides.add_slide(slides.slide_layouts[1]); slide.shapes.title.text = title
    slides.save(ROOT / 'sample.pptx')
    pdf = ROOT / 'pdf'; pdf.mkdir(exist_ok=True)
    recalc = ROOT / 'recalculated'; recalc.mkdir(exist_ok=True)
    profile = '-env:UserInstallation=' + (ROOT / 'lo-profile').as_uri()
    for name in ['sample.docx', 'sample.pptx']:
        folder = pdf / name.split('.')[-1]; folder.mkdir(exist_ok=True)
        run(['libreoffice', profile, '--headless', '--convert-to', 'pdf', '--outdir', str(folder), str(ROOT / name)])
    run(['libreoffice', profile, '--headless', '--convert-to', 'xlsx', '--outdir', str(recalc), str(ROOT / 'sample.xlsx')])
    assert load_workbook(recalc / 'sample.xlsx', data_only=True).active['B5'].value == 45
    text = ''.join(p.extract_text() for p in PdfReader(pdf / 'docx/sample.pdf').pages)
    assert '7419' in text and len(PdfReader(pdf / 'pptx/sample.pdf').pages) == 2
    run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '1200', '-png', str(pdf / 'docx/sample.pdf'), str(ROOT / 'document-render')])
    results['office'] = 'PASS: DOCX/PPTX to PDF, PDF text/readback, XLSX formula recalculation and PNG rendering'

    image = Image.new('RGB', (1200, 180), 'white'); draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 64)
    draw.text((25, 40), 'HERMES OCR 7419', font=font, fill='black')
    image.save(ROOT / 'ocr-fixture.png')
    ocr = pytesseract.image_to_string(image, lang='eng', config='--psm 7')
    assert '7419' in ocr and 'HERMES' in ocr
    langs = pytesseract.get_languages(); assert {'eng', 'jpn', 'chi_sim'}.issubset(langs)
    (ROOT / 'ocr.txt').write_text(ocr)
    results['ocr'] = {'english_marker': 'PASS', 'installed_languages': langs,
                      'japanese_chinese_accuracy': 'not measured; language data installed'}

    fixture = ROOT / 'code'; fixture.mkdir(exist_ok=True)
    (fixture / 'calc.py').write_text('def total(values):\n    return sum(values)\n')
    (fixture / 'test_calc.py').write_text('from calc import total\ndef test_total():\n    assert total([10,15,20]) == 45\ndef test_empty():\n    assert total([]) == 0\n')
    tests = run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', str(fixture)])
    count = run(['/opt/skills-python/bin/pygount', '--format=summary', '--folders-to-skip=.git,node_modules,.venv,__pycache__', str(fixture)])
    assert '2 passed' in tests and 'Python' in count
    (ROOT / 'code-checks.txt').write_text(tests + '\n' + count)
    results['development'] = 'PASS: 2 synthetic tests and actual pygount statistics'

    feed_path = Path('/opt/data/skills/hermes/rss-feeds/scripts/feed.py')
    spec = importlib.util.spec_from_file_location('accepted_feed', feed_path)
    feed = importlib.util.module_from_spec(spec); spec.loader.exec_module(feed)
    small = b'<rss version="2.0"><channel><title>Fixture</title><item><title>Entry</title><link>https://example.com/item</link></item></channel></rss>'
    assert len(feed.parse_feed(small, 'application/rss+xml')['entries']) == 1
    original = feed.urllib.request.urlopen
    class LargeResponse:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, n): return b'x' * n
    feed.urllib.request.urlopen = lambda *a, **kw: LargeResponse()
    rejected = False
    try: feed.fetch('https://example.com/feed')
    except ValueError: rejected = True
    finally: feed.urllib.request.urlopen = original
    assert rejected
    actual = json.loads(run([sys.executable, str(feed_path), 'read', 'https://pypi.org/rss/project/pandas/releases.xml', '--limit', '1', '--json']))
    assert len(actual['entries']) == 1 and 'pypi.org' in actual['entries'][0]['link']
    # Preserve metadata only, without article bodies.
    (ROOT / 'feed.json').write_text(json.dumps({'title': actual['title'], 'entry': {k: actual['entries'][0][k] for k in ['title', 'link', 'published']}}))
    results['rss'] = 'PASS: real PyPI release feed, synthetic parse and 4MiB rejection'

    console = []; failed = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'], headless=True, args=['--no-sandbox'])
        try:
            page = browser.new_page(viewport={'width': 1024, 'height': 768})
            page.on('pageerror', lambda e: console.append(str(e)))
            page.on('requestfailed', lambda req: failed.append(req.url))
            page.set_content('<!doctype html><title>Synthetic QA fixture</title><h1>Browser capability fixture</h1><button onclick="document.querySelector(\'output\').textContent=\'PASS 7419\'">Run check</button><output>Ready</output>')
            page.get_by_role('button', name='Run check').click()
            assert page.locator('output').inner_text() == 'PASS 7419'
            page.screenshot(path=str(ROOT / 'web-qa.png'))
        finally: browser.close()
    assert not console and not failed
    results['web_qa'] = {'click': 'PASS', 'page_errors': console, 'failed_requests': failed, 'scope': 'synthetic local fixture'}
    (ROOT / 'diagram.dot').write_text('digraph { Input -> Analysis -> Report; }')
    run(['dot', '-Tsvg', str(ROOT / 'diagram.dot'), '-o', str(ROOT / 'diagram.svg')])
    (ROOT / 'note.md').write_text('# Synthetic note\n\nTotal: 45.\n')
    run(['pandoc', str(ROOT / 'note.md'), '-o', str(ROOT / 'note.html')])
    assert run(['jq', '.sum', str(ROOT / 'statistics.json')]).strip() == '45'
    results['tools'] = {'pandoc_graphviz_jq': 'PASS', 'github_cli': run(['gh', '--version']).splitlines()[0], 'private_github': 'not connected'}
    artifact_names = ['sample.csv', 'statistics.json', 'chart.png', 'interactive-chart.html', 'sample.docx', 'sample.xlsx', 'sample.pptx', 'document-render.png', 'ocr.txt', 'feed.json', 'web-qa.png', 'diagram.svg', 'note.html']
    results['artifacts'] = {n: {'bytes': (ROOT / n).stat().st_size, 'sha256': hashlib.sha256((ROOT / n).read_bytes()).hexdigest()} for n in artifact_names}
    results['status'] = 'PASS'
    (ROOT / 'ACCEPTANCE.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results))


if __name__ == '__main__':
    main()
