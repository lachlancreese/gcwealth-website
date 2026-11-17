#!/usr/bin/env python3
"""Pre-push check for the GC Wealth site. Run from the site folder:  npm test   (or python3 tests/check.py)

It starts the site locally (wrangler dev) with a stand-in email server, then for every page in sitemap.xml plus
the hidden pages, on desktop and mobile, it checks:
  - the page loads (200), with no console errors and no failed requests (images, fonts, CSS, JS)
  - one <h1>, a title under 60 characters and a description under 160
  - no sideways scrolling on mobile
  - accessibility (axe-core: contrast, labels, landmarks, etc.)
  - every internal link and asset on the page resolves
Then it checks old-address redirects and submits each form (contact, get started, newsletter, honeypot).
Screenshots go to tests/out/. Exit code 1 if anything fails.

Needs: Python 3 with playwright, and `npm install` run once (for wrangler and axe-core).
"""
import html
import http.server
import signal
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "out"
PORT = 8799
MAIL_PORT = 9911
BASE = f"http://127.0.0.1:{PORT}"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")

from playwright.sync_api import sync_playwright  # noqa: E402

failures = []

# Words and phrases Connective and ASIC flag in credit advertising. "best" is only allowed as "best interests".
FLAGGED = [
    (r"\bfree\b(?! call)", "free (use 'complimentary')"),
    (r"(?<!our )\bbest\b(?! interests)", "best (only allowed as 'best interests')"),
    (r"\bgreat\b(?! sense of humour)", "great"),
    (r"\bguaranteed\b(?! amount)", "guaranteed"),
    (r"\bindependent\b(?! (party|legal advice))", "independent"),
    (r"save you", "save you ..."),
    (r"massive savings|substantial amounts|lowest rate|expert advice|no-brainer", "claim Connective lists as misleading"),
    (r"\bTODO\b|<mark class=\"todo\"", "unconfirmed draft text"),
]
sent_mail = []


def fail(msg):
    failures.append(msg)
    print("  FAIL", msg)


class Mail(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        sent_mail.append(json.loads(body or b"{}"))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"id":"test"}')

    def log_message(self, *a):
        pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def status_of(url, follow=True):
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        r = opener.open(urllib.request.Request(url, method="GET"), timeout=20)
        return r.status, r.geturl(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location"), e.headers


def wait_for(port, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            print(f"Port {PORT} is already in use (an old local server?). Stop it and run again.")
            return 1
    mail = http.server.ThreadingHTTPServer(("127.0.0.1", MAIL_PORT), Mail)
    threading.Thread(target=mail.serve_forever, daemon=True).start()
    os.environ["WRANGLER_SEND_METRICS"] = "false"
    dev = subprocess.Popen(
        ["npx", "wrangler", "dev", "--port", str(PORT), "--ip", "127.0.0.1",
         "--var", "RESEND_API_KEY:test", "--var", f"RESEND_URL:http://127.0.0.1:{MAIL_PORT}/emails",
         "--persist-to", tempfile.mkdtemp(prefix="gcw-check-")],  # fresh state, so the form limits start at zero
        cwd=ROOT, stdout=open(OUT / "wrangler.log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not wait_for(PORT):
            print("Local server didn't start (is `npm install` done?)")
            return 1
        time.sleep(1.5)
        run_checks()
    finally:
        os.killpg(dev.pid, signal.SIGTERM)  # wrangler and the workerd process it starts
        dev.wait(timeout=20)
        mail.shutdown()
    print()
    if failures:
        print(f"{len(failures)} problem(s) found.")
        return 1
    print("All checks passed.")
    return 0


def page_list():
    sitemap = (ROOT / "public" / "sitemap.xml").read_text()
    paths = [re.sub(r"^https?://[^/]+", "", u) or "/" for u in re.findall(r"<loc>(.*?)</loc>", sitemap)]
    hidden = ["/thanks", "/privacy", "/credit-guide"]
    return paths + [p for p in hidden if p not in paths]


def run_checks():
    axe = (ROOT / "node_modules" / "axe-core" / "axe.min.js").read_text()
    seen_links = set()
    pages = page_list()
    print(f"Checking {len(pages)} pages on desktop, laptop, tablet and mobile")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for device, viewport, mobile in [("desktop", {"width": 1440, "height": 900}, False),
                                         ("laptop", {"width": 1024, "height": 768}, False),
                                         ("tablet", {"width": 768, "height": 1024}, True),
                                         ("mobile", {"width": 390, "height": 844}, True)]:
            ctx = browser.new_context(viewport=viewport, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
            for path in pages:
                pg = ctx.new_page()
                errors, bad = [], []
                pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.on("requestfailed", lambda r: bad.append(f"{r.url} ({r.failure})"))
                pg.on("response", lambda r: bad.append(f"{r.url} ({r.status})") if r.status >= 400 else None)
                res = pg.goto(BASE + path, wait_until="networkidle")
                label = f"{path} [{device}]"
                if not res or res.status != 200:
                    fail(f"{label}: status {res.status if res else 'none'}")
                for e in errors:
                    fail(f"{label}: console error: {e}")
                for b in bad:
                    fail(f"{label}: failed request {b}")
                info = pg.evaluate("""() => ({
                    h1: document.querySelectorAll('h1').length,
                    title: document.title,
                    desc: (document.querySelector('meta[name=description]')||{}).content || '',
                    overflow: document.documentElement.scrollWidth - window.innerWidth,
                    header: (document.querySelector('.site-header')||{}).offsetHeight || 0,
                    brokenImgs: [...document.images].filter(i => i.complete && i.naturalWidth === 0 && i.loading !== 'lazy').map(i => i.src),
                    links: [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')),
                    leftover: (document.body.innerHTML.match(/\\{\\{[\\w.]+\\}\\}/g) || []),
                })""")
                if info["h1"] != 1:
                    fail(f"{label}: {info['h1']} h1 elements")
                if device == "desktop":
                    if len(info["title"]) > 60:
                        fail(f"{label}: title is {len(info['title'])} characters")
                    if not 50 <= len(info["desc"]) <= 160:
                        fail(f"{label}: description is {len(info['desc'])} characters")
                if info["overflow"] > 1:
                    fail(f"{label}: scrolls sideways by {info['overflow']}px")
                if info["header"] > 96:
                    fail(f"{label}: header is {info['header']}px tall (menu wrapping?)")
                for src in info["brokenImgs"]:
                    fail(f"{label}: image didn't load {src}")
                if device == "desktop":
                    text = pg.evaluate("document.body.innerText")
                    marked = pg.evaluate("document.querySelectorAll('mark.todo').length")
                    indexed = pg.evaluate("!(document.querySelector('meta[name=robots]')||{}).content?.includes('noindex')")
                    for pattern, flag in FLAGGED:
                        if flag == "unconfirmed draft text":
                            if marked and indexed:
                                fail(f"{flag}: {path} has {marked} item(s) still to confirm")
                            continue
                        for m in re.finditer(pattern, text, re.I):
                            snippet = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
                            fail(f"wording: {flag} on {path}: ...{snippet}...")
                for t in info["leftover"]:
                    fail(f"{label}: unfilled placeholder {t}")
                for href in info["links"]:
                    if href.startswith("/") and not href.startswith("//"):
                        seen_links.add(href.split("#")[0])
                if device in ("laptop", "tablet"):
                    pg.screenshot(path=str(OUT / ((path.strip("/").replace("/", "_") or "home") + f"-{device}.png")), full_page=True)
                    pg.close()
                    continue  # accessibility rules are checked at desktop and mobile sizes
                pg.evaluate(axe + "\n;0")  # evaluate, not a script tag, so the page's security policy still applies to everything else
                result = pg.evaluate("""async () => (await axe.run(document, {resultTypes: ['violations']})).violations
                    .map(v => ({id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))""")
                for v in result:
                    fail(f"{label}: accessibility {v['impact']}: {v['help']} ({v['id']}) at {', '.join(v['nodes'])}")
                name = (path.strip("/").replace("/", "_") or "home") + f"-{device}.png"
                pg.screenshot(path=str(OUT / name), full_page=True)
                pg.close()
            ctx.close()

        print(f"Checking {len(seen_links)} internal links")
        for href in sorted(seen_links):
            code, final, _ = status_of(BASE + href)
            if code != 200:
                fail(f"link {href} returns {code}")

        print("Checking redirects from old addresses")
        CALC_MOVED = {
            "borrowing-power": "/calculators/borrowing-power", "repayment-calculator": "/calculators/repayments",
            "stamp-duty": "/calculators/stamp-duty", "budget-planner": "/calculators/borrowing-power",
            "extra-repayments": "/calculators/extra-repayments", "offset-account": "/calculators/extra-repayments",
            "split-loan": "/calculators/repayments", "refinancing-savings": "/calculators/refinance",
            "income-tax": "/calculators/borrowing-power", "compound-interest": "/calculators/deposit",
            "savings-goal": "/calculators/deposit", "fortnightly-repayment": "/calculators/repayments",
            "loan-comparison-calculator": "/calculators/refinance", "lump-sum-repayment": "/calculators/extra-repayments",
            "property-buying-cost": "/calculators/stamp-duty", "property-selling-cost": "/calculators",
            "rent-vs-buy": "/calculators/deposit", "credit-card": "/calculators",
            "how-long-to-repay-calculator": "/calculators/extra-repayments", "introductory-rate": "/calculators/repayments",
            "asset-leasing": "/business-finance/asset-finance", "reverse-mortgage": "/calculators",
            "saving": "/calculators/deposit", "income-annualisation": "/calculators/borrowing-power",
            "income-gross-up": "/calculators/borrowing-power", "how-much-to-deposit": "/calculators/deposit",
            "comparison-rate": "/calculators/repayments", "interest-only": "/calculators/repayments",
        }  # all 28 calculator pages in the old Elementor sitemap
        moves = [(f"/calculators/{k}/", v) for k, v in CALC_MOVED.items()] + [
            ("/contact-us/", "/contact"), ("/about/", "/about"), ("/refinancing/", "/home-loans/refinancing"),
            ("/construction-lending-qld/", "/home-loans/construction-loans"), ("/smsf-refinancing/", "/smsf-loans"),
            ("/why-gold-coast-wealth/", "/about"), ("/tag/smsf/", "/"), ("/privacy-policy/", "/privacy"),
            ("/complaints-handling-process/", "/compliments-and-concerns"), ("/get-started/", "/get-started"),
            ("/home-loans.html", "/home-loans"), ("/borrowing-capacity-gold-coast-wealth/", "/calculators/borrowing-power"),
            ("/calculators/", "/calculators")]
        for old, new in moves:
            code, loc, _ = status_of(BASE + old, follow=False)
            loc = re.sub(r"^https?://[^/]+", "", loc or "")
            if code != 301 or loc != new:
                fail(f"redirect {old}: got {code} to {loc!r}, expected 301 to {new}")
        code, _, headers = status_of(BASE + "/no-such-page")
        if code != 404:
            fail(f"missing page returns {code}, expected 404")
        code, _, headers = status_of(BASE + "/")
        if "Content-Security-Policy" not in headers:
            fail("security headers missing on /")
        if "noindex" not in (headers.get("X-Robots-Tag") or headers.get("x-robots-tag") or ""):
            fail("preview address (not gcwealth.com.au) isn't marked noindex")
        # Link previews on the preview address must load the share image from the preview, not the old site.
        import urllib.request as _ur
        home_html = _ur.urlopen(BASE + "/").read().decode()
        og = re.search(r'<meta property="og:image" content="([^"]+)"', home_html)
        if not og or not og.group(1).startswith(BASE + "/assets/img/og-image.jpg"):
            fail(f"preview og:image points at {og and og.group(1)}, expected this address")
        elif status_of(og.group(1))[0] != 200:
            fail("preview og:image doesn't load")

        print("Checking calculators")
        check_calculators(browser)
        print("Checking forms")
        check_forms(browser)
        print("Checking team matcher")
        check_matcher(browser)
        print("Checking broker contact panels")
        check_contact(browser)
        print("Checking header menus")
        check_menus(browser)
        print("Checking first home buyer help by state")
        check_first_home(browser)
        browser.close()


def check_calculators(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.goto(BASE + "/calculators/stamp-duty")
    # Stamp duty in every state, against worked examples published from each revenue office's 2026-27 schedules.
    inv = {"home": False, "first": False, "kind": "established", "eligible": True}
    oo = {"home": True, "first": False, "kind": "established", "eligible": True}
    fhb = {"home": True, "first": True, "kind": "established", "eligible": True}
    fhb_new = {"home": True, "first": True, "kind": "new", "eligible": True}
    duty_cases = [
        ("QLD", 750000, inv, 26775), ("QLD", 600000, inv, 20025), ("QLD", 750000, oo, 19600),
        ("QLD", 795000, fhb, 19890), ("QLD", 695000, fhb, 0), ("QLD", 1500000, fhb_new, 0),
        ("NSW", 750000, inv, 27937), ("NSW", 1000000, oo, 39187), ("NSW", 900000, fhb, 19594), ("NSW", 800000, fhb, 0),
        ("VIC", 750000, inv, 40070), ("VIC", 700000, fhb, 24713), ("VIC", 600000, fhb, 0),
        ("WA", 750000, inv, 29741), ("WA", 800000, fhb, 32300), ("WA", 600000, fhb, 0),
        ("SA", 750000, inv, 35080), ("SA", 600000, fhb, 26830), ("SA", 750000, fhb_new, 0),
        ("TAS", 750000, inv, 28935), ("TAS", 500000, fhb, 18248),
        ("ACT", 750000, inv, 22200), ("ACT", 1000000, inv, 36950), ("ACT", 750000, oo, 19208), ("ACT", 1000000, oo, 33958), ("ACT", 900000, fhb, 0),
        ("NT", 750000, inv, 37125), ("NT", 500000, fhb, 23929),
    ]
    for code, value, opts, want in duty_cases:
        got = pg.evaluate("([c, v, o]) => Math.round(window.GCW_CALC.duty(c, v, o))", [code, value, opts])
        if got != want:
            fail(f"stamp duty {code} ${value:,} {opts}: got ${got:,}, expected ${want:,}")
    m = pg.evaluate("""() => { const c = window.GCW_CALC; return {
        tax100k: Math.round(c.incomeTax(100000)),  // $20,520 tax + $2,000 Medicare levy
        pmt: Math.round(c.pmt(100000, 6, 30) * 100) / 100,  // $599.55
    }; }""")
    for k, v in {"tax100k": 22520, "pmt": 599.55}.items():
        if abs(m[k] - v) > 0.01:
            fail(f"calculator maths: {k} is {m[k]}, expected {v}")
    # Borrowing power against the big four banks' own calculators (run 17 Nov 2026 with the same inputs and each
    # bank's rate). Ours must never be higher, and should be within 8% so it isn't uselessly low.
    # (two, deps, inc1, inc2, expenses a month, rate, invest, rent a week, bank result, bank)
    bank = [
        (0, 0, 100000, 0, 3000, 6.64, 0, 0, 400100, "CBA"), (0, 0, 100000, 0, 2000, 6.64, 0, 0, 508500, "CBA"),
        (0, 0, 100000, 0, 1000, 6.64, 0, 0, 508500, "CBA"), (0, 0, 100000, 0, 2500, 6.64, 0, 0, 458900, "CBA"),
        (0, 0, 60000, 0, 0, 6.64, 0, 0, 295500, "CBA"), (0, 0, 60000, 0, 2500, 6.64, 0, 0, 193600, "CBA"),
        (0, 0, 150000, 0, 0, 6.64, 0, 0, 749700, "CBA"), (0, 0, 150000, 0, 5000, 6.64, 0, 0, 487800, "CBA"),
        (0, 0, 250000, 0, 0, 6.64, 0, 0, 1203600, "CBA"), (0, 0, 250000, 0, 8000, 6.64, 0, 0, 685500, "CBA"),
        (0, 1, 100000, 0, 0, 6.64, 0, 0, 457200, "CBA"), (0, 2, 100000, 0, 0, 6.64, 0, 0, 396900, "CBA"),
        (0, 1, 100000, 0, 4000, 6.64, 0, 0, 282600, "CBA"), (1, 0, 100000, 0, 2500, 6.64, 0, 0, 362000, "CBA"),
        (1, 0, 150000, 0, 0, 6.64, 0, 0, 602500, "CBA"), (1, 0, 250000, 100000, 0, 6.64, 0, 0, 1667800, "CBA"),
        (1, 0, 250000, 100000, 12000, 6.64, 0, 0, 974200, "CBA"), (1, 1, 120000, 80000, 1000, 6.64, 0, 0, 920400, "CBA"),
        (1, 1, 120000, 80000, 7000, 6.64, 0, 0, 688800, "CBA"), (1, 1, 120000, 80000, 8000, 6.64, 0, 0, 571300, "CBA"),
        (0, 0, 100000, 0, 3000, 6.79, 1, 0, 395000, "CBA"), (0, 0, 100000, 0, 3000, 6.79, 1, 500, 621200, "CBA"),
        (0, 0, 100000, 0, 0, 6.79, 1, 500, 684700, "CBA"), (0, 0, 100000, 0, 3000, 6.79, 1, 1000, 847400, "CBA"),
        (0, 0, 100000, 0, 3000, 6.94, 0, 0, 395889, "NAB"), (0, 0, 100000, 0, 1000, 6.94, 0, 0, 495186, "NAB"),
        (0, 0, 100000, 0, 2500, 6.94, 0, 0, 453154, "NAB"), (0, 0, 60000, 0, 1, 6.94, 0, 0, 289071, "NAB"),
        (0, 0, 150000, 0, 1, 6.94, 0, 0, 725599, "NAB"), (0, 1, 100000, 0, 1, 6.94, 0, 0, 435860, "NAB"),
        (0, 2, 100000, 0, 1, 6.94, 0, 0, 382489, "NAB"), (1, 1, 120000, 80000, 1, 6.94, 0, 0, 894739, "NAB"),
        (1, 1, 120000, 80000, 8000, 6.94, 0, 0, 562719, "NAB"), (1, 0, 100000, 1, 1, 6.94, 0, 0, 355470, "NAB"),
        (1, 0, 150000, 1, 1, 6.94, 0, 0, 585653, "NAB"), (1, 0, 250000, 100000, 1, 6.94, 0, 0, 1612283, "NAB"),
        (1, 2, 150000, 50000, 1, 6.94, 0, 0, 847037, "NAB"),
        (0, 0, 100000, 0, 3000, 7.04, 0, 0, 392566, "Westpac"), (0, 0, 100000, 0, 1, 7.04, 0, 0, 500342, "Westpac"),
        (0, 0, 100000, 0, 2500, 7.04, 0, 0, 449350, "Westpac"), (0, 0, 60000, 0, 1, 7.04, 0, 0, 293914, "Westpac"),
        (0, 0, 150000, 0, 1, 7.04, 0, 0, 731662, "Westpac"), (0, 0, 150000, 0, 5000, 7.04, 0, 0, 477269, "Westpac"),
    ]
    got = pg.evaluate("""(cases) => cases.map(([two, deps, inc1, inc2, expenses, rate, invest, rentWeek]) =>
        window.GCW_CALC.borrow({ two: !!two, deps, inc1, inc2, expenses, rate, invest: !!invest, rentWeek, years: 30 }).loan)""",
        [list(c[:8]) for c in bank])
    for c, ours in zip(bank, got):
        if ours > c[8]:
            fail(f"borrowing power is above {c[9]} for {c[:8]}: ours ${ours:,}, {c[9]} ${c[8]:,}")
        elif ours < c[8] * 0.92:
            fail(f"borrowing power is more than 8% below {c[9]} for {c[:8]}: ours ${ours:,}, {c[9]} ${c[8]:,}")
    h = pg.evaluate("[60000, 80000, 150000, 227123].map(x => Math.round(window.GCW_CALC.helpRepay(x) * 100) / 100)")
    if h != [0, 1570.8, 12476.11, 22712.3]:  # ATO 2026-27 marginal rates; $227,123 matches the ATO example
        fail(f"HELP repayments: got {h}")
    # The form: pick WA, a first home at $800,000.
    pg.select_option("#c-state", "WA")
    pg.fill("#c-price", "800000")
    pg.wait_for_timeout(200)
    if pg.locator(".result-main").inner_text().strip() != "$32,300":
        fail(f"stamp duty form: WA first home at $800,000 shows {pg.locator('.result-main').inner_text()}, expected $32,300")
    pg.goto(BASE + "/calculators/stamp-duty/act")
    if pg.locator("#c-state").input_value() != "ACT":
        fail("stamp duty: the ACT page doesn't start on the ACT")
    # No calculator may show a pre-filled interest rate (comparison rate rule).
    for path in ["/calculators/repayments", "/calculators/borrowing-power", "/calculators/extra-repayments", "/calculators/refinance"]:
        pg.goto(BASE + path)
        rates = pg.evaluate("[...document.querySelectorAll('input[name=rate], input[name=current], input[name=newrate]')].map(i => i.value)")
        if any(rates):
            fail(f"{path}: an interest rate is pre-filled ({rates})")
        if "Enter" not in pg.locator(".result-main").inner_text():
            fail(f"{path}: results should ask for a rate before showing figures")
    pg.goto(BASE + "/calculators/repayments")
    pg.fill("#c-rate", "6")
    pg.wait_for_timeout(200)
    if pg.locator(".result-main").inner_text().strip() != "$3,597":
        fail(f"repayments: $600,000 at 6% over 30 years shows {pg.locator('.result-main').inner_text()}, expected $3,597")
    pg.screenshot(path=str(OUT / "calc-repayments-filled.png"), full_page=True)
    # Interest only for 5 years at 6%, then principal and interest over the remaining 25.
    pg.locator("label", has_text="Interest only").click()
    pg.wait_for_timeout(150)
    if pg.locator(".result-main").inner_text().strip() != "$3,000" or "$3,866" not in pg.locator("[data-show=io-note]").inner_text():
        fail(f"repayments: interest only shows {pg.locator('.result-main').inner_text()} / {pg.locator('[data-show=io-note]').inner_text()}")
    # Deposit planner adds stamp duty for the state: a first home in NSW at $750,000 has none, in QLD it does.
    pg.goto(BASE + "/calculators/deposit")
    pg.select_option("#c-state", "NSW")
    pg.wait_for_timeout(150)
    if pg.locator("[data-out=duty]").inner_text().strip() != "$0":
        fail(f"deposit: NSW first home duty at $750,000 shows {pg.locator('[data-out=duty]').inner_text()}, expected $0")
    pg.select_option("#c-state", "QLD")
    pg.locator("label", has_text="No").first.click()
    pg.wait_for_timeout(150)
    want = pg.evaluate("Math.round(window.GCW_CALC.duty('QLD', 750000, {home: true, first: false, kind: 'established', eligible: true}))")
    if pg.locator("[data-out=duty]").inner_text().strip() != f"${want:,}":
        fail(f"deposit: QLD duty at $750,000 shows {pg.locator('[data-out=duty]').inner_text()}, expected ${want:,}")
    pg.goto(BASE + "/calculators/borrowing-power")
    pg.fill("#c-rate", "6")
    pg.wait_for_timeout(200)
    if not pg.locator(".result-main").inner_text().startswith("$"):
        fail("borrowing power: no estimate after entering a rate")
    href = pg.locator("[data-cta]").get_attribute("href")
    if "goal=" not in href:
        fail("borrowing power: call to action doesn't carry the result to Get started")
    base = pg.locator(".result-main").inner_text()
    pg.check("#c-help1")
    pg.wait_for_timeout(150)
    dollars = lambda t: int(t.replace("$", "").replace(",", "") or 0)
    if dollars(pg.locator(".result-main").inner_text()) >= dollars(base):
        fail("borrowing power: a HELP debt doesn't lower the estimate")
    pg.uncheck("#c-help1")
    pg.locator("label", has_text="An investment").click()
    pg.fill("#c-rent", "600")
    pg.wait_for_timeout(150)
    if not pg.locator("#c-rent").is_visible() or not pg.locator("[data-show=invest-note]").is_visible():
        fail("borrowing power: investment rent field or note not shown")
    if pg.locator("[data-cta]").get_attribute("href").find("investment") < 0:
        fail("borrowing power: investment estimate doesn't carry the goal to Get started")
    pg.locator("label", has_text="A home to live in").click()
    pg.fill("#c-exp", "500")
    pg.wait_for_timeout(150)
    if not pg.locator("[data-show=floor-note]").is_visible():
        fail("borrowing power: very low living costs don't explain the lender minimum")
    href = pg.locator("[data-cta]").get_attribute("href")
    pg.goto(BASE + href)
    if not pg.locator('input[name="goal"][value="Buy my first home"]').is_checked():
        fail("get started: goal from the calculator wasn't preselected")
    ctx.close()


def check_matcher(browser):
    """'Who should I talk to?' on /team shows the right brokers and carries the choice into Get started."""
    import json as _json
    data = _json.loads((ROOT / "data" / "team.json").read_text())
    names = {p["slug"]: p["name"] for p in data["people"]}
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto(BASE + "/team")
    if not pg.locator("[data-matcher]").is_visible():
        fail("team matcher: not shown")
    for need in data["needs"]:
        pg.locator("label.chip", has_text=need["label"]).click()
        pg.wait_for_timeout(150)
        shown = pg.locator(".match:not([hidden]) .match-card h3").all_inner_texts()
        want = [names[s] for s in need["people"]]
        if shown != want:
            fail(f"team matcher '{need['label']}': shows {shown}, expected {want}")
    # The last choice's first broker: their button pre-fills Get started with the broker and the goal.
    need = next(n for n in data["needs"] if n.get("goal"))
    pg.locator("label.chip", has_text=need["label"]).click()
    pg.locator(".match:not([hidden]) .match-card .btn").first.click()
    pg.wait_for_url("**/get-started**")
    pg.wait_for_timeout(300)
    if pg.locator('input[name="broker"]').input_value() != names[need["people"][0]]:
        fail("team matcher: Talk to button didn't pass the broker to Get started")
    if not pg.locator(f'input[name="goal"][value="{need["goal"]}"]').is_checked():
        fail("team matcher: Talk to button didn't pre-select the goal on Get started")
    ctx.close()


def check_contact(browser):
    """Each broker profile's Text, Call and Email links reach the right person with a started message
    that follows what the visitor picks. Text shows on phones only. Service pages list the right brokers."""
    import json as _json
    from urllib.parse import unquote
    data = _json.loads((ROOT / "data" / "team.json").read_text())
    brand = _json.loads((ROOT / "brand.json").read_text())
    people = [p for p in data["people"] if p.get("client_facing", True)]
    phone = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    desk = browser.new_context(viewport={"width": 1440, "height": 900})
    for p in people:
        first = p["name"].split()[0]
        own = bool(p.get("phone_tel"))
        pg = phone.new_page()
        pg.goto(BASE + f"/team/{p['slug']}")
        box = pg.locator("[data-contact]")
        if not box.is_visible():
            fail(f"{p['slug']}: contact panel not shown")
            continue
        tel = box.locator('a[href^="tel:"]').get_attribute("href")
        if tel != "tel:" + (p["phone_tel"] if own else brand["phone_tel"]):
            fail(f"{p['slug']}: Call goes to {tel}")
        mail = box.locator("[data-mail]")
        if not mail.get_attribute("href").startswith("mailto:" + (p.get("email") or brand["email"]) + "?"):
            fail(f"{p['slug']}: Email goes to the wrong address")
        sms = box.locator("[data-sms]")
        if own != (sms.count() == 1 and sms.is_visible()):
            fail(f"{p['slug']}: Text button {'missing' if own else 'shown without a mobile'} on a phone")
        need = next(n for n in data["needs"] if p["slug"] in n["people"])
        box.locator("label.chip", has_text=need["label"]).click()
        box.locator("#cb-name").fill("Sam")
        pg.wait_for_timeout(100)
        topic = need["label"][0].lower() + need["label"][1:]
        body = unquote(mail.get_attribute("href"))
        if f"Hi {first}," not in body or topic not in body or "Thanks,\nSam" not in body or need["label"] not in body:
            fail(f"{p['slug']}: email isn't started with the greeting, topic, subject and name")
        if own:
            text = unquote(sms.get_attribute("href"))
            if not text.startswith(f"sms:{p['phone_tel']}?&body=Hi {first}, it's Sam.") or topic not in text:
                fail(f"{p['slug']}: text message doesn't follow the choice: {text[:120]}")
        pg.close()
        pg = desk.new_page()
        pg.goto(BASE + f"/team/{p['slug']}")
        if pg.locator("[data-contact] [data-sms]").count() and pg.locator("[data-contact] [data-sms]").is_visible():
            fail(f"{p['slug']}: Text button shown on a desktop")
        pg.close()
    phone.close()
    desk.close()
    names = {p["slug"]: p["name"] for p in data["people"]}
    needs = {n["key"]: n for n in data["needs"]}
    for f in sorted((ROOT / "pages").rglob("*.html")):
        m = re.search(r"<!--brokers-for:([\w-]+)-->", f.read_text())
        if not m:
            continue
        built = ROOT / "public" / f.relative_to(ROOT / "pages")
        shown = [html.unescape(x) for x in re.findall(r'<h3><a href="/team/[\w-]+">([^<]+)</a></h3>', built.read_text().split('class="section-tight brokers-for"')[1].split("</section>")[0])]
        want = [names[s] for s in needs[m.group(1)]["people"]]
        if shown != want:
            fail(f"{built.relative_to(ROOT)}: lists {shown} as focusing on this, expected {want}")


def check_menus(browser):
    """Desktop dropdowns: a mouse that drifts on the way down, or cuts across the next heading, still reaches the link."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.goto(BASE + "/")
    menus = pg.locator(".has-sub")
    first, second = menus.nth(0), menus.nth(1)
    top = first.locator(":scope > a").bounding_box()
    pg.mouse.move(top["x"] + top["width"] / 2, top["y"] + top["height"] / 2)
    pg.wait_for_timeout(100)
    if not first.locator(".sub").is_visible():
        fail("header menu: doesn't open on hover")
    # Down through the gap under the heading, briefly outside the menu, then onto the last link.
    last = first.locator(".sub a").last
    box = last.bounding_box()
    pg.mouse.move(top["x"] + top["width"] + 30, top["y"] + top["height"] + 6, steps=4)
    pg.mouse.move(box["x"] + 20, box["y"] + box["height"] / 2, steps=8)
    if not last.is_visible():
        fail("header menu: closed while moving down to a link")
    # Cutting across the next heading on the way back shouldn't swap menus.
    nxt = second.locator(":scope > a").bounding_box()
    pg.mouse.move(nxt["x"] + 10, nxt["y"] + nxt["height"] / 2, steps=3)
    pg.mouse.move(box["x"] + 20, box["y"] + box["height"] / 2, steps=3)
    pg.wait_for_timeout(50)
    if not last.is_visible() or second.locator(".sub").is_visible():
        fail("header menu: cutting across the next heading swapped the menus")
    href = last.get_attribute("href")
    last.click()
    pg.wait_for_url("**" + href)
    # Leaving the menu closes it after a moment.
    pg.goto(BASE + "/")
    pg.mouse.move(top["x"] + top["width"] / 2, top["y"] + top["height"] / 2)
    pg.mouse.move(700, 600, steps=3)
    pg.wait_for_timeout(600)
    if first.locator(".sub").is_visible():
        fail("header menu: stays open after the mouse leaves")
    ctx.close()


def check_first_home(browser):
    """Every state shows a grant and duty summary, and the chips switch between them."""
    import json as _json
    duty = _json.loads((ROOT / "data" / "stamp-duty.json").read_text())
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto(BASE + "/home-loans/first-home-buyers")
    box = pg.locator("[data-fhb]")
    for code in duty["order"]:
        st = duty["states"][code]
        box.locator("label.chip", has_text=st["short"]).click()
        shown = box.locator(".fhb-state:not([hidden])")
        if shown.count() != 1 or shown.get_attribute("data-state") != code:
            fail(f"first home help: choosing {code} doesn't show {code}")
            continue
        text = shown.inner_text()
        if st["fhog"]["short"] not in text or st["fhb_short"] not in text:
            fail(f"first home help: {code} is missing its grant or duty summary")
        if shown.locator(f'a[href="/calculators/stamp-duty/{st["slug"]}"]').count() != 1:
            fail(f"first home help: {code} doesn't link to its stamp duty calculator")
    ctx.close()


def check_forms(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()

    # Get started: three steps, a bad phone number first, then a good one.
    sent_mail.clear()
    pg.goto(BASE + "/get-started")
    pg.locator("label.chip", has_text="Refinance").first.click()
    pg.wait_for_timeout(400)
    if not pg.locator("#s-when").is_visible():
        fail("get started: picking a goal didn't move to step 2")
    pg.select_option("#s-when", "In the next 3 months")
    pg.locator(".step:not([hidden]) [data-next]").click()
    pg.fill("#s-name", "Test Person")
    pg.fill("#s-phone", "12345")
    pg.fill("#s-email", "test@example.com")
    pg.click("text=Send my enquiry")
    if not pg.locator("#s-phone-error").is_visible():
        fail("get started: bad phone number wasn't flagged")
    pg.fill("#s-phone", "0412 345 678")
    pg.click("text=Send my enquiry")
    if not pg.locator("#s-consent-error").is_visible():
        fail("get started: missing consent wasn't flagged")
    pg.check("#s-consent")
    pg.click("text=Send my enquiry")
    try:
        pg.wait_for_url("**/thanks", timeout=15000)
    except Exception:
        status = pg.locator(".step:not([hidden]) .form-status").all_inner_texts()
        errors = pg.locator(".field-error").all_inner_texts()
        pg.screenshot(path=str(OUT / "form-get-started-stuck.png"), full_page=True)
        fail(f"get started: didn't reach /thanks (status {status}, errors {errors})")
        ctx.close()
        return
    pg.screenshot(path=str(OUT / "form-thanks-mobile.png"))
    if len(sent_mail) != 2:
        fail(f"get started: expected 2 emails (team + auto-reply), got {len(sent_mail)}")
    else:
        team, auto = sent_mail
        if "Refinance" not in team["html"] or "0412 345 678" not in team["html"] or team.get("reply_to") != "test@example.com":
            fail("get started: team email is missing details")
        if auto["to"] != ["test@example.com"] or "Credit Representative" not in auto["text"] or "Privacy notice" not in auto["text"]:
            fail("get started: auto-reply is wrong")
        (OUT / "email-auto-reply.html").write_text(auto["html"])
        (OUT / "email-team.html").write_text(team["html"])

    # Enquiry from a broker's profile names the broker.
    sent_mail.clear()
    pg.goto(BASE + "/get-started?broker=steven-shaw")
    pg.locator("label.chip", has_text="Refinance").first.click()
    pg.wait_for_timeout(400)
    pg.locator(".step:not([hidden]) [data-next]").click()
    pg.fill("#s-name", "Test Person")
    pg.fill("#s-phone", "0412 345 678")
    pg.fill("#s-email", "test2@example.com")
    pg.check("#s-consent")
    pg.click("text=Send my enquiry")
    pg.wait_for_url("**/thanks", timeout=15000)
    if not sent_mail or "Steven Shaw" not in sent_mail[0]["subject"]:
        fail("get started: enquiry from Steven's profile doesn't name him")

    # Contact form.
    sent_mail.clear()
    pg.goto(BASE + "/contact")
    pg.fill("#c-name", "Test Person")
    pg.fill("#c-phone", "0412 345 678")
    pg.fill("#c-email", "test@example.com")
    pg.fill("#c-message", "Testing the contact form")
    pg.click("text=Send message")
    pg.wait_for_url("**/thanks", timeout=15000)
    if len(sent_mail) != 2:
        fail(f"contact: expected 2 emails, got {len(sent_mail)}")

    # Newsletter in the footer stays on the page.
    sent_mail.clear()
    pg.goto(BASE + "/about")
    pg.fill("#nl-email", "list@example.com")
    pg.click(".signup button")
    pg.wait_for_selector(".signup .form-status.ok", timeout=15000)
    if len(sent_mail) != 2:
        fail(f"newsletter: expected 2 emails, got {len(sent_mail)}")

    # Loan health check.
    sent_mail.clear()
    pg.goto(BASE + "/loan-health-check")
    pg.fill("#h-lender", "Example Bank")
    pg.fill("#h-name", "Test Person")
    pg.fill("#h-phone", "0412 345 678")
    pg.fill("#h-email", "test@example.com")
    pg.check("#h-consent")
    pg.click("text=Request my health check")
    pg.wait_for_url("**/thanks", timeout=15000)
    if len(sent_mail) != 2 or "Example Bank" not in sent_mail[0]["html"]:
        fail("health check: emails missing or incomplete")

    # Referral: partner gets the confirmation, the client is not emailed.
    sent_mail.clear()
    pg.goto(BASE + "/partners")
    pg.fill("#r-name", "Pat Partner")
    pg.fill("#r-business", "Partner Accounting")
    pg.fill("#r-email", "partner@example.com")
    pg.fill("#r-phone", "0412 000 111")
    pg.fill("#r-client", "Casey Client")
    pg.fill("#r-client-phone", "0413 222 333")
    pg.fill("#r-client-email", "client@example.com")
    pg.check("#r-consent")
    pg.check("#r-agreement")
    pg.click("text=Send referral")
    pg.wait_for_url("**/thanks", timeout=15000)
    if len(sent_mail) != 2 or sent_mail[1]["to"] != ["partner@example.com"] or "NOT YET IN PLACE" not in sent_mail[0]["html"]:
        fail("referral: wrong emails (team should be told no agreement exists; only the partner gets a reply)")

    # First home buyer guide: stays on the page with a download link, emails the link.
    sent_mail.clear()
    pg.goto(BASE + "/first-home-buyer-guide")
    pg.fill("#g-name", "Test Person")
    pg.fill("#g-email", "guide@example.com")
    pg.click("text=Email me the guide")
    pg.wait_for_selector("#guide-form .form-status.ok a", timeout=15000)
    if len(sent_mail) != 2 or ".pdf" not in sent_mail[1]["text"]:
        fail("guide: emails missing or no link to the PDF")
    code, _, headers = status_of(BASE + "/assets/guides/gc-wealth-first-home-buyer-guide.pdf")
    if code != 200:
        fail(f"guide PDF returns {code}")
    # The PDF is rendered from data/stamp-duty.json: it must show each state's current grant and duty help.
    try:
        import pypdf
        text = " ".join(pg_.extract_text() for pg_ in pypdf.PdfReader(str(ROOT / "public/assets/guides/gc-wealth-first-home-buyer-guide.pdf")).pages)
        text = " ".join(text.split())
        duty_data = json.loads((ROOT / "data" / "stamp-duty.json").read_text())
        for code_ in duty_data["order"]:
            st = duty_data["states"][code_]
            for want in (st["name"], st["fhog"]["short"]):
                if want not in text:
                    fail(f"guide PDF is out of date: '{want}' not found. Run python3 tools/guides/render.py")
    except ImportError:
        print("  (pypdf not installed: skipped the guide PDF content check)")

    # Honeypot: pretend success, send nothing.
    sent_mail.clear()
    req = urllib.request.Request(BASE + "/api/enquiry", data=b"type=contact&name=Bot&email=bot%40example.com&phone=0412345678&website=spam",
                                 headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req) as r:
        if json.loads(r.read()).get("ok") is not True or sent_mail:
            fail("honeypot: bot submission wasn't quietly dropped")
    ctx.close()


if __name__ == "__main__":
    sys.exit(main())
