"""Opt-in browser contract probe using inert fixture HTML, no account mutation."""
import os
from google_doc_delivery import recipient_role, browser_document_lock


def run_browser_contract_probe():
    from playwright.sync_api import sync_playwright
    html='''<body>
      <div style="display:none"><span>viewer@example.com</span></div>
      <ul role="menu">
        <li role="menuitem"><div data-hovercard-id="owner@example.com">owner@example.com</div><button aria-label="所有者。">所有者</button></li>
        <li role="menuitem"><div data-hovercard-id="viewer@example.com">viewer@example.com</div><button aria-label="查看者。更改权限">查看者</button></li>
      </ul></body>'''
    with browser_document_lock(), sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(os.environ.get('OPENCLAW_BROWSER_CDP','http://127.0.0.1:18800'))
        page=browser.contexts[0].new_page()
        try:
            page.set_content(html)
            assert recipient_role(page,'viewer@example.com').startswith('查看者')
            assert recipient_role(page,'owner@example.com').startswith('所有者')
            assert recipient_role(page,'absent@example.com')==''
            page.locator('ul').evaluate('(ul)=>ul.appendChild(ul.children[1].cloneNode(true))')
            assert recipient_role(page,'viewer@example.com')==''
            print('BROWSER_PERMISSION_CONTRACT_OK')
        finally:
            page.close()


def test_browser_contract():
    import pytest
    if os.environ.get('OPENCLAW_TEST_BROWSER_CONTRACT')!='1':
        pytest.skip('browser contract probe is opt-in on the persistent browser host')
    run_browser_contract_probe()


if __name__=='__main__':
    run_browser_contract_probe()
