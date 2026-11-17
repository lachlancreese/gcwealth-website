#!/usr/bin/env python3
"""Render the first home buyer guide to PDF:  python3 tools/guides/render.py
Writes public/assets/guides/gc-wealth-qld-first-home-buyer-guide.pdf. Needs Python playwright with Chromium."""
import os
import pathlib

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
from playwright.sync_api import sync_playwright  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SRC = HERE / "qld-first-home-buyer-guide.html"
OUT = ROOT / "public" / "assets" / "guides" / "gc-wealth-qld-first-home-buyer-guide.pdf"

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page()
    page.goto(SRC.as_uri(), wait_until="networkidle")
    page.pdf(path=str(OUT), format="A4", print_background=True, prefer_css_page_size=True,
             display_header_footer=True, header_template="<span></span>",
             footer_template='<div style="width:100%;font:8px sans-serif;color:#5B6B72;padding:0 18mm;display:flex;justify-content:space-between">'
                             '<span>GC Wealth · Queensland first home buyer guide · November 2026</span><span class="pageNumber"></span></div>',
             margin={"top": "18mm", "bottom": "20mm", "left": "18mm", "right": "18mm"})
    browser.close()
print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
