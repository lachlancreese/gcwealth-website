#!/usr/bin/env python3
"""Render the first home buyer guide to PDF:  python3 tools/guides/render.py

Fills first-home-buyer-guide.html with each state's grant and stamp duty help from data/stamp-duty.json
(the same data as the website), works out the duty examples with the site's own calculator script, and
writes public/assets/guides/gc-wealth-first-home-buyer-guide.pdf. Needs Python playwright with Chromium.
"""
import html
import json
import os
import pathlib
import tempfile

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
from playwright.sync_api import sync_playwright  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SRC = HERE / "first-home-buyer-guide.html"
OUT = ROOT / "public" / "assets" / "guides" / "gc-wealth-first-home-buyer-guide.pdf"
DUTY = json.loads((ROOT / "data" / "stamp-duty.json").read_text())
KEEP = ("name", "short", "term", "round", "general", "owner", "owner_max", "owner_needs_residency", "kinds", "fhb", "grant", "slug")

esc = html.escape
state_rows, duty_rows = [], []
for code in DUTY["order"]:
    st = DUTY["states"][code]
    g = st["fhog"]
    state_rows.append(f'    <tr><td><b>{esc(st["name"])}</b></td><td><b>{esc(g["short"])}</b><br>{esc(g["text"])}</td>'
                      f'<td><b>{esc(st["fhb_short"])}</b></td></tr>')
    duty_rows.append(f'    <tr><td>{esc(st["name"])}</td><td class="n" data-duty="{code}:1"></td><td class="n" data-duty="{code}:0"></td></tr>')
payload = {"checked": DUTY["checked"], "states": {c: {k: v for k, v in st.items() if k in KEEP} for c, st in DUTY["states"].items()}}

page = (SRC.read_text()
        .replace("<!--STATE_ROWS-->", "\n".join(state_rows))
        .replace("<!--DUTY_ROWS-->", "\n".join(duty_rows))
        .replace("<!--DUTY_DATA-->", json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")))
# Written next to the template so its relative links to fonts, the logo and the script still work.
with tempfile.NamedTemporaryFile("w", suffix=".html", dir=HERE, delete=False) as f:
    f.write(page)
    filled = pathlib.Path(f.name)

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page()
        pg.goto(filled.as_uri(), wait_until="networkidle")
        pg.wait_for_selector("body[data-ready]")
        empty = pg.locator("[data-duty]:empty").count()
        if empty:
            raise SystemExit(f"{empty} duty figures didn't fill in; check calculators.js loads")
        pg.pdf(path=str(OUT), format="A4", print_background=True, prefer_css_page_size=True,
               display_header_footer=True, header_template="<span></span>",
               footer_template='<div style="width:100%;font:8px sans-serif;color:#5B6B72;padding:0 18mm;display:flex;justify-content:space-between">'
                               '<span>GC Wealth · First home buyer guide · November 2026</span><span class="pageNumber"></span></div>',
               margin={"top": "18mm", "bottom": "20mm", "left": "18mm", "right": "18mm"})
        browser.close()
finally:
    filled.unlink()
print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
