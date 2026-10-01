#!/usr/bin/env python3
"""Deterministic private Google Docs import, export checks and Viewer verification."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DOC_RE = re.compile(r"^https://docs\.google\.com/document/d/([A-Za-z0-9_-]+)(?:/|$)")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def document_id(url: str) -> str:
    match = DOC_RE.match(url)
    if not match:
        raise ValueError("invalid Google Docs URL")
    return match.group(1)


def docx_signature(data: bytes) -> dict:
    if len(data) > 25_000_000:
        raise ValueError("document exceeds size limit")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 60_000_000:
            raise ValueError("expanded document exceeds size limit")
        root = ET.fromstring(archive.read("word/document.xml"))
        # Text nodes exclude formatting metadata and survive Google import/export.
        text = "".join(node.text or "" for node in root.iter(f"{W}t"))
        normalized = re.sub(r"\s+", "", text)
        images = [archive.read(n) for n in archive.namelist() if n.startswith("word/media/") and not n.endswith("/")]
    return {"text": normalized, "images": len(images),
            "distinct_images": len({hashlib.sha256(b).hexdigest() for b in images})}


def verify_export(expected: bytes, actual: bytes, *, min_images: int = 3) -> dict:
    source, exported = docx_signature(expected), docx_signature(actual)
    if not source["text"] or source["text"] != exported["text"]:
        raise ValueError("Google Docs exported body does not match the prepared draft")
    if source["distinct_images"] < min_images or exported["distinct_images"] < min_images:
        raise ValueError("Google Docs requires three distinct embedded images")
    if exported["images"] < source["images"]:
        raise ValueError("Google Docs export lost embedded images")
    return {"body_verified": True, "embedded_images": exported["images"],
            "distinct_images": exported["distinct_images"]}


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def open_share(page):
    page.locator("#docs-titlebar-share-client-button").click(timeout=45000)
    frame = page.frame_locator('iframe[src*="/drivesharing/driveshare"]')
    frame.get_by_text("有访问权限的人", exact=True).wait_for(timeout=45000)
    return frame


def recipient_role(frame, recipient: str) -> str:
    # Hidden address chips also contain the email; only saved permission rows count.
    return frame.locator("body").evaluate("""(body, email) => {
      const rows=Array.from(body.querySelectorAll('li[role="menuitem"]')).filter(row =>
        row.getClientRects().length && Array.from(row.querySelectorAll('[data-hovercard-id]')).some(e =>
          e.getAttribute('data-hovercard-id').toLowerCase() === email.toLowerCase()));
      if(rows.length!==1) return '';
      const roles=Array.from(rows[0].querySelectorAll('button')).filter(b=>
        /^(查看者|评论者|编辑者|所有者)/.test(b.getAttribute('aria-label')||b.textContent));
      return roles.length===1 ? (roles[0].getAttribute('aria-label')||roles[0].textContent) : '';
    }""", recipient)


def restricted(frame) -> bool:
    return frame.get_by_text("受限", exact=True).count() == 1


def verify_viewer(page, url: str, recipient: str) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    frame = open_share(page)
    role = recipient_role(frame, recipient)
    if not role.startswith("查看者") or not restricted(frame):
        raise ValueError("saved permission is not the configured Viewer with restricted general access")
    frame.get_by_role("button", name="完成", exact=True).click()
    return {"viewer_verified": True, "general_access": "restricted",
            "recipient_fingerprint": hashlib.sha256(recipient.lower().encode()).hexdigest()}


def grant_viewer(page, url: str, recipient: str) -> dict:
    document_id(url)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        raise ValueError("configured recipient is missing or invalid")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    frame = open_share(page)
    if not restricted(frame):
        raise ValueError("general access is not restricted; automatic delivery stopped")
    role = recipient_role(frame, recipient)
    if role and not role.startswith("查看者"):
        raise ValueError("configured recipient has another role; automatic role changes stopped")
    if not role:
        field = frame.locator('input[role="combobox"]')
        field.fill(recipient)
        # Enter commits an exact address, avoiding suggested identities.
        field.press("Enter")
        send = frame.get_by_role("button", name="发送", exact=True)
        send.wait_for(timeout=30000)
        editor = frame.locator('button:visible').filter(has_text=re.compile(r"^编辑者$"))
        if editor.count():
            editor.click()
            frame.get_by_text("查看者", exact=True).filter(visible=True).click()
        frame.locator('button:visible').filter(has_text=re.compile(r"^查看者$")).wait_for(timeout=15000)
        send.click()
        page.wait_for_timeout(1500)
    else:
        frame.get_by_role("button", name="完成", exact=True).click()
    # Reload the saved document, independent of the optimistic dialog state.
    return verify_viewer(page, url, recipient)


def import_docx(page, source: Path) -> str:
    page.goto("https://docs.google.com/document/u/0/", wait_until="domcontentloaded", timeout=60000)
    page.get_by_role("button", name="打开文件选择器", exact=True).click(timeout=45000)
    picker = page.frame_locator('iframe[src*="/picker/"]')
    picker.get_by_text("上传", exact=True).click(timeout=45000)
    picker.locator('input[type="file"]').set_input_files(str(source))
    page.wait_for_url(re.compile(r"https://docs\.google\.com/document/d/"), timeout=120000)
    page.locator("#docs-titlebar-share-client-button").wait_for(timeout=60000)
    return f"https://docs.google.com/document/d/{document_id(page.url)}/edit"


def export_docx(page, url: str) -> bytes:
    result = page.request.get(f"https://docs.google.com/document/d/{document_id(url)}/export?format=docx", timeout=60000)
    if not result.ok:
        raise ValueError(f"document export failed with HTTP {result.status}")
    return result.body()


def deliver_document(source: Path, recipient: str, receipt_path: Path, *, cdp_url: str = "http://127.0.0.1:18800") -> dict:
    from playwright.sync_api import sync_playwright
    data = source.read_bytes()
    signature = docx_signature(data)
    if signature["distinct_images"] < 3 or not signature["text"]:
        raise ValueError("prepared document lacks body or three distinct images")
    digest = hashlib.sha256(data).hexdigest()
    prior = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    if prior and prior.get("draft_sha256") != digest:
        raise ValueError("existing receipt belongs to a different draft; use another run directory")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url, timeout=30000)
        page = browser.contexts[0].new_page()
        try:
            url = prior.get("url") or import_docx(page, source)
            # Save creation before later gates so a retry reuses the same document.
            receipt = {"url": url, "draft_sha256": digest, "status": "created"}
            atomic_json(receipt_path, receipt)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            for attempt in range(3):
                try:
                    verified = verify_export(data, export_docx(page, url))
                    break
                except (ValueError, zipfile.BadZipFile):
                    if attempt == 2:
                        raise
                    page.wait_for_timeout(5000)
            permissions = grant_viewer(page, url, recipient)
            receipt.update(verified, **permissions, status="verified", verified_at=int(time.time()))
            atomic_json(receipt_path, receipt)
            return receipt
        finally:
            if not page.is_closed():
                page.close()


def authorize_document(url: str, recipient: str, *, cdp_url: str = "http://127.0.0.1:18800") -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url, timeout=30000)
        page = browser.contexts[0].new_page()
        try:
            result = grant_viewer(page, url, recipient)
            state = Path("/var/lib/openclaw/.openclaw/workspace/state/artifacts/access")
            atomic_json(state / f"{document_id(url)}.json", {"url": url, **result, "verified_at": int(time.time())})
            return result
        finally:
            if not page.is_closed():
                page.close()
