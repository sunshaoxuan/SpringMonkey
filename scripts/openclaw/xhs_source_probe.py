#!/var/lib/openclaw/venvs/xhs/bin/python
"""Allowlisted executable: bounded public product/image evidence, no private sites."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urlparse

from google_doc_delivery import browser_document_lock
from xhs_delivery_pipeline import validate_public_url, fetch_image, WORKSPACE

SOURCE_DOMAINS = ('costco.co.jp','kewpie.co.jp','lindt.jp','kuzefuku.com',
                  'kuzefuku.jp','sanktgallenbrewery.com','hatenablog.com','hatenablog.jp',
                  'ameblo.jp','livedoor.blog','livedoor.jp','rakuten.co.jp','suzunoya.com',
                  'starbucks.co.jp','danone.co.jp','costcolover.blog','coslover.com',
                  'ultimate-setsuko.com','costco-johokan.com','marronroy-recipes.com',
                  'costco-japan.com','sweets365.jp','costco-blog.com')
IMAGE_DOMAINS = SOURCE_DOMAINS + ('st-hatena.com','f.st-hatena.com','ameba.jp','rakuten.ne.jp')
PROBE_ROOT = WORKSPACE / 'state/xhs-delivery/_probe'


def validate_source(url: str, *, image: bool = False) -> str:
    validate_public_url(url)
    host = urlparse(url).hostname.lower()
    domains = IMAGE_DOMAINS if image else SOURCE_DOMAINS
    if not any(host == domain or host.endswith('.'+domain) for domain in domains):
        raise ValueError('source host is outside the public recommendation-source allowlist')
    if re.search(r'/(?:my-account|myaccount|login|logout|cart|checkout|account|admin|dashboard|settings|mypage)(?:/|$)',urlparse(url).path,re.I):
        raise ValueError('private/account source path is blocked')
    return url


def fetch_page(url: str, *, search: bool = False) -> dict:
    from playwright.sync_api import sync_playwright
    if not search:
        validate_source(url)
    with browser_document_lock(), sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://127.0.0.1:18800')
        page = browser.contexts[0].new_page()
        try:
            page.goto(url,wait_until='domcontentloaded',timeout=45000)
            page.wait_for_timeout(2000)
            if not search:
                validate_source(page.url)
            data = page.locator('body').evaluate("""body=>({
              title:document.title.slice(0,300),
              text:body.innerText.replace(/\\s+/g,' ').slice(0,3200),
              images:Array.from(body.querySelectorAll('img')).map(e=>({url:e.currentSrc||e.src,alt:e.alt,w:e.naturalWidth,h:e.naturalHeight})).filter(e=>e.w>=200&&e.h>=200).slice(0,24),
              links:Array.from(body.querySelectorAll('a[href]')).filter(e=>e.innerText.trim()).map(e=>({url:e.href,title:e.innerText.trim().slice(0,80)})).slice(0,40)
            })""")
            # Source navigation is public; Google account/navigation chrome is omitted.
            if search:
                data.pop('text',None)
                data.pop('images',None)
            links=[]
            for link in data.get('links',[]):
                try: validate_source(link['url'])
                except ValueError: continue
                links.append(link)
            data['links']=links[:15]
            data['text']=re.sub(r'[\w.+-]+@[\w.-]+','[private]',data.get('text',''))
            # A hard byte budget, independent of an agent's snapshot arguments.
            while len(json.dumps(data,ensure_ascii=False))>7000 and data.get('images'):
                data['images'].pop()
            while len(json.dumps(data,ensure_ascii=False))>7000 and data['links']:
                data['links'].pop()
            return data
        finally:
            if not page.is_closed():page.close()


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['search','fetch','image'])
    parser.add_argument('value')
    parser.add_argument('--name',default='image')
    args=parser.parse_args()
    try:
        if args.action=='search':
            if len(args.value)>200:raise ValueError('query exceeds length limit')
            result=fetch_page('https://www.google.com/search?'+urlencode({'q':args.value}),search=True)
        elif args.action=='fetch':
            result=fetch_page(args.value)
        else:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',args.name):raise ValueError('invalid image name')
            validate_source(args.value,image=True)
            PROBE_ROOT.mkdir(parents=True,exist_ok=True)
            path=PROBE_ROOT/f'{args.name}.jpg'
            digest=fetch_image(args.value,path)
            from PIL import Image
            with Image.open(path) as im:
                im.thumbnail((1000,1000));im.save(path,quality=90)
            result={'image_path':str(path),'source_sha256':digest,'instruction':'Use read on this image to check packaging, composition and watermark.'}
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__,'completed':False}))
        return 1


if __name__=='__main__':raise SystemExit(main())
