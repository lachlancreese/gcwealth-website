#!/usr/bin/env python3
"""Quick screenshots while designing: python3 tests/shoot.py /path [/path ...]  (starts wrangler dev itself)."""
import os, subprocess, sys, time, socket, pathlib
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8798
dev = subprocess.Popen(["npx", "wrangler", "dev", "--port", str(PORT), "--ip", "127.0.0.1"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(120):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", PORT)) == 0: break
        time.sleep(0.5)
    time.sleep(1.5)
    out = ROOT / "tests" / "out"; out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for device, vp, mob in [("desktop", {"width": 1440, "height": 900}, False), ("mobile", {"width": 390, "height": 844}, True)]:
            ctx = b.new_context(viewport=vp, is_mobile=mob, has_touch=mob, device_scale_factor=1)
            for path in sys.argv[1:]:
                pg = ctx.new_page(); pg.goto(f"http://127.0.0.1:{PORT}{path}", wait_until="networkidle")
                name = (path.strip("/").replace("/", "_") or "home") + f"-{device}.png"
                pg.screenshot(path=str(out / name), full_page=True); pg.close()
                print(out / name)
            ctx.close()
        b.close()
finally:
    dev.terminate()
