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
    (r"\bgreat\b", "great"),
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
    print(f"Checking {len(pages)} pages on desktop and mobile")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for device, viewport, mobile in [("desktop", {"width": 1440, "height": 900}, False),
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
        for old, new in [("/contact-us/", "/contact"), ("/about/", "/about"), ("/refinancing/", "/home-loans/refinancing"),
                         ("/construction-lending-qld/", "/home-loans/construction-loans"), ("/smsf-refinancing/", "/smsf-loans"),
                         ("/why-gold-coast-wealth/", "/about"), ("/tag/smsf/", "/"), ("/privacy-policy/", "/privacy"), ("/complaints-handling-process/", "/compliments-and-concerns"),
                         ("/get-started/", "/get-started"), ("/home-loans.html", "/home-loans"),
                         ("/calculators/repayment-calculator/", "/calculators/repayments"), ("/calculators/offset-account/", "/calculators/extra-repayments"),
                         ("/calculators/refinancing-savings/", "/calculators/refinance"), ("/calculators/property-buying-cost/", "/calculators/stamp-duty"),
                         ("/calculators/savings-goal/", "/calculators/deposit"), ("/borrowing-capacity-gold-coast-wealth/", "/calculators/borrowing-power")]:
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

        print("Checking calculators")
        check_calculators(browser)
        print("Checking forms")
        check_forms(browser)
        browser.close()


def check_calculators(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.goto(BASE + "/calculators/stamp-duty")
    m = pg.evaluate("""() => { const c = window.GCW_CALC; return {
        qroExample: c.dutyHome(795000) - c.firstHomeDeduction(795000),   // QRO worked example: $19,890
        firstUnder: Math.max(0, c.dutyHome(695000) - c.firstHomeDeduction(695000)),  // QRO example: $0
        general600: c.dutyGeneral(600000),       // $20,025
        home750: c.dutyHome(750000),             // $19,600
        general750: c.dutyGeneral(750000),       // $26,775
        tax100k: Math.round(c.incomeTax(100000)),  // $20,520 tax + $2,000 Medicare levy
        pmt: Math.round(c.pmt(100000, 6, 30) * 100) / 100,  // $599.55
    }; }""")
    expected = {"qroExample": 19890, "firstUnder": 0, "general600": 20025, "home750": 19600, "general750": 26775, "tax100k": 22520, "pmt": 599.55}
    for k, v in expected.items():
        if abs(m[k] - v) > 0.01:
            fail(f"calculator maths: {k} is {m[k]}, expected {v}")
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
    pg.goto(BASE + "/calculators/borrowing-power")
    pg.fill("#c-rate", "6")
    pg.wait_for_timeout(200)
    if not pg.locator(".result-main").inner_text().startswith("$"):
        fail("borrowing power: no estimate after entering a rate")
    href = pg.locator("[data-cta]").get_attribute("href")
    if "goal=" not in href:
        fail("borrowing power: call to action doesn't carry the result to Get started")
    pg.goto(BASE + href)
    if not pg.locator('input[name="goal"][value="Buy my first home"]').is_checked():
        fail("get started: goal from the calculator wasn't preselected")
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
    code, _, headers = status_of(BASE + "/assets/guides/gc-wealth-qld-first-home-buyer-guide.pdf")
    if code != 200:
        fail(f"guide PDF returns {code}")

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
