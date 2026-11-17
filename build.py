#!/usr/bin/env python3
"""Build the GC Wealth site: wraps each pages/**/*.html in the shared layout and writes public/.

Business details (name, phone, licence line, colours, logo) live in brand.json. Menus live in NAV below.
Run:  python3 build.py   (Python 3, no packages needed)

Each page file starts with a settings block:
    <!--
    title: Page title | GC Wealth       (under ~60 characters)
    description: One sentence for Google. (under ~155 characters)
    path: /home-loans/refinancing
    crumb: Refinancing                  (short name for breadcrumbs and menus)
    nav: home-loans                     (menu item to highlight; blank for none)
    schema: service                     (optional: adds Service structured data)
    disclaimer: yes                     (optional: general-information note at the end)
    bar: yes                            (mobile call / get started bar; "no" to hide)
    index: yes                          (list in sitemap; "no" keeps it out of search)
    -->
In page text, {{phone}}, {{email}}, {{name}}, {{lenders}} and other brand.json keys are filled in.
Shared sections: <!--include:cta--> inserts pages/partials/cta.html.
"""
import datetime
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import subprocess

ROOT = pathlib.Path(__file__).parent
PAGES = ROOT / "pages"
OUT = ROOT / "public"
B = json.loads((ROOT / "brand.json").read_text())
RATES = json.loads((ROOT / "data" / "rates.json").read_text())
TEAM_DATA = json.loads((ROOT / "data" / "team.json").read_text())
TEAM = {p["slug"]: p for p in TEAM_DATA["people"]}
BROKERS = {k: p for k, p in TEAM.items() if p.get("client_facing", True)}  # shown with contact details and Talk to buttons
BEHIND = [p for p in TEAM.values() if not p.get("client_facing", True)]   # behind the scenes: no contact details
NEEDS = TEAM_DATA.get("needs", [])
for _need in NEEDS:
    for _slug in _need["people"]:
        assert _slug in BROKERS, f"team.json need '{_need['key']}' names '{_slug}', who isn't a client-facing broker"
REVIEWS = json.loads((ROOT / "data" / "reviews.json").read_text())
DUTY = json.loads((ROOT / "data" / "stamp-duty.json").read_text())  # stamp duty for every state: tables, state pages and calculator
SITE = B["site"]
ORG_ID = SITE + "/#organization"

# Main menu: (key, label, href, children). Children appear in the dropdown and the footer.
NAV = [
    ("home-loans", "Home loans", "/home-loans", [
        ("First home buyers", "/home-loans/first-home-buyers"),
        ("Refinancing", "/home-loans/refinancing"),
        ("Investment loans", "/home-loans/investment-loans"),
        ("Construction loans", "/home-loans/construction-loans"),
        ("Self-employed loans", "/home-loans/self-employed"),
        ("Guarantor loans", "/home-loans/guarantor-loans"),
        ("Bridging loans", "/home-loans/bridging-loans"),
        ("Pre-approval", "/home-loans/pre-approval"),
    ]),
    ("business", "Business finance", "/business-finance", [
        ("Commercial property loans", "/business-finance/commercial-property"),
        ("Business loans", "/business-finance/business-loans"),
        ("Asset and equipment finance", "/business-finance/asset-finance"),
        ("SMSF commercial property", "/smsf-loans"),
    ]),
    ("calculators", "Calculators", "/calculators", [
        ("Borrowing power", "/calculators/borrowing-power"),
        ("Repayments", "/calculators/repayments"),
        ("Extra repayments and offset", "/calculators/extra-repayments"),
        ("Refinance", "/calculators/refinance"),
        ("Stamp duty (all states)", "/calculators/stamp-duty"),
        ("Deposit planner", "/calculators/deposit"),
        ("RBA cash rate and lending rules", "/rba-cash-rate"),
    ]),
    ("about", "About", "/about", [
        ("Our team", "/team"),
        ("Referral partners", "/partners"),
        ("Loan health check", "/loan-health-check"),
        ("First home buyer guide", "/first-home-buyer-guide"),
    ]),
    ("contact", "Contact", "/contact", []),
]

ICON = {
    "phone": '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/></svg>',
    "chev": '<svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
    "star": '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/></svg>',
}


def asset(path):
    """Add a content hash so browsers fetch a fresh copy whenever the file changes."""
    digest = hashlib.sha256((OUT / path.lstrip("/")).read_bytes()).hexdigest()[:10]
    return f"{path}?v={digest}"


IMG_REF = re.compile(r"/assets/(?:img|guides)/[\w.-]+\.(?:webp|png|jpe?g|svg|pdf)(?![\w?])")


def version_images(text):
    """Images keep a week-long browser cache, so tag each one with its hash: a replaced photo shows straight away."""
    return IMG_REF.sub(lambda m: asset(m.group(0)) if (OUT / m.group(0).lstrip("/")).exists() else m.group(0), text)


def ld(data):
    return '\n<script type="application/ld+json">\n' + json.dumps(data, ensure_ascii=False, indent=1) + "\n</script>"


def strip_tags(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def _dollars(n):
    return f"${n:,.0f}"


def _rate(rate, unit):
    return f"{rate:g}%" if unit == "pct" else f"${rate:.2f} per $100"


def duty_rows(brackets, unit):
    """Plain-English rows for a rate schedule, e.g. ('$103,001 to $387,000', '$1,662 plus $3.50 per $100 over $103,000')."""
    rows, prev = [], 0
    for b in brackets:
        band = (f"Up to {_dollars(b['to'])}" if prev == 0 else
                f"{_dollars(prev + 1)} to {_dollars(b['to'])}" if b["to"] else f"Over {_dollars(prev)}")
        if b.get("formula") == "nt":
            text = "(0.06571441 × V²) + 15V, where V is the value in thousands of dollars"
        elif "flat" in b:
            text = f"{b['flat']:g}% of the total value"
        elif b["rate"] == 0:
            text = _dollars(b["base"]) if b["base"] else "Nil"
        else:
            per = _rate(b["rate"], unit)
            text = (per + (f" (minimum {_dollars(b['min'])})" if b.get("min") else "")) if not b["base"] and not b["over"] else \
                   f"{_dollars(b['base'])} plus {per} over {_dollars(b['over'])}" if b["base"] else f"{per} over {_dollars(b['over'])}"
        rows.append((band, text))
        prev = b["to"] or prev
    return rows


def duty_table(code):
    st = DUTY["states"][code]
    out = []
    tables = [("General rates" if st.get("owner") else "Rates", st["general"], st.get("general_note", ""))]
    if st.get("owner"):
        tables.append((st["owner_title"], st["owner"], ""))
    for title, brackets, note in tables:
        rows = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>" for a, b in duty_rows(brackets, st["unit"]))
        out.append(f"""<div class="table-wrap"><table class="rate-table duty-table">
        <caption>{html.escape(title)}{(' <span>' + html.escape(note) + '</span>') if note else ''}</caption>
        <thead><tr><th scope="col">Dutiable value</th><th scope="col">Duty</th></tr></thead>
        <tbody>{rows}</tbody></table></div>""")
    if st["round"] == "part":
        out.append('<p class="hint">Each rate applies per $100, or part of $100.</p>')
    return "\n".join(out)


def duty_states(current=None):
    items = []
    for code in DUTY["order"]:
        st = DUTY["states"][code]
        if code == current:
            continue
        items.append(f'<li><a href="/calculators/stamp-duty/{st["slug"]}"><b>{html.escape(st["name"])}</b>'
                     f'<span>First home buyers: {html.escape(st["fhb_short"])}</span></a></li>')
    return '<ul class="duty-states">' + "".join(items) + "</ul>"


def duty_calc(default):
    """The stamp duty calculator form and results. Rates come from data/stamp-duty.json, embedded for the script."""
    options = "".join(f'<option value="{c}"{" selected" if c == default else ""}>{html.escape(DUTY["states"][c]["name"])}</option>'
                      for c in DUTY["order"])
    keep = ("name", "short", "term", "round", "general", "owner", "owner_max", "owner_needs_residency", "kinds", "fhb", "grant", "slug")
    data = {"checked": DUTY["checked"], "states": {c: {k: v for k, v in st.items() if k in keep} for c, st in DUTY["states"].items()}}
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return f"""<form class="calc-form" data-calc="stamp-duty" data-results="results" novalidate>
      <div class="field full">
        <label for="c-state">State or territory</label>
        <select class="input" id="c-state" name="state">{options}</select>
      </div>
      <div class="field full">
        <label for="c-price">Purchase price</label>
        <div class="input-wrap"><span class="unit pre">$</span><input class="input" id="c-price" name="price" inputmode="decimal" value="750,000"></div>
      </div>
      <fieldset class="full">
        <legend>What's it for?</legend>
        <div class="seg">
          <label><input type="radio" name="purpose" value="home" checked><span>A home I'll live in</span></label>
          <label><input type="radio" name="purpose" value="investment"><span>An investment</span></label>
        </div>
      </fieldset>
      <fieldset class="full" data-home-only>
        <legend data-first-label>Is it your first home?</legend>
        <div class="seg">
          <label><input type="radio" name="first" value="yes" checked><span>Yes</span></label>
          <label><input type="radio" name="first" value="no"><span>No</span></label>
        </div>
      </fieldset>
      <fieldset class="full" data-kind-only>
        <legend>What are you buying?</legend>
        <div class="seg">
          <label><input type="radio" name="kind" value="established" checked><span>An established home</span></label>
          <label><input type="radio" name="kind" value="new"><span>A new home</span></label>
          <label data-kind="land"><input type="radio" name="kind" value="land"><span>Land to build on</span></label>
        </div>
      </fieldset>
      <label class="consent full" for="c-res" data-home-only>
        <input id="c-res" name="resident" type="checkbox" checked>
        <span>I'm an Australian citizen or permanent resident</span>
      </label>
      <details class="full more-costs">
        <summary>Add your other upfront costs <span class="muted">(optional)</span></summary>
        <div class="more-costs-grid">
          <div class="field">
            <label for="c-legal">Conveyancing or legal</label>
            <div class="input-wrap"><span class="unit pre">$</span><input class="input" id="c-legal" name="legal" inputmode="decimal" value="0"></div>
          </div>
          <div class="field">
            <label for="c-insp">Building and pest</label>
            <div class="input-wrap"><span class="unit pre">$</span><input class="input" id="c-insp" name="inspections" inputmode="decimal" value="0"></div>
          </div>
          <div class="field">
            <label for="c-lender">Lender fees</label>
            <div class="input-wrap"><span class="unit pre">$</span><input class="input" id="c-lender" name="lender" inputmode="decimal" value="0"></div>
          </div>
          <div class="field">
            <label for="c-other">Registration and other</label>
            <div class="input-wrap"><span class="unit pre">$</span><input class="input" id="c-other" name="other" inputmode="decimal" value="0"></div>
          </div>
        </div>
      </details>
    </form>
    <aside class="results" id="results" aria-labelledby="results-title">
      <h2 id="results-title">Your upfront costs</h2>
      <div class="result-main" data-out="main" aria-live="polite"></div>
      <div class="result-sub" data-out="sub" data-detail></div>
      <ul class="result-list" data-detail>
        <li>Calculated using <b data-out="basis" style="max-width:60%"></b></li>
        <li>Duty at standard rates, for comparison <b data-out="general"></b></li>
        <li>Your other costs <b data-out="others"></b></li>
        <li>Total upfront <b data-out="total"></b></li>
      </ul>
      <p class="result-note" data-out="note" data-detail hidden></p>
      <p class="result-note" data-show="grant" hidden><span data-out="grant"></span> <a href="/home-loans/first-home-buyers" style="color:#fff">How it works</a>.</p>
      <a class="btn btn-light" data-cta href="/get-started">Talk to a broker about this</a>
    </aside>
    <script type="application/json" id="duty-data">{payload}</script>"""


def fill(text):
    """Replace {{key}} and {{key.sub}} with values from brand.json."""
    ctx = dict(B, rates=dict(RATES, next_decision_short=nice_date(RATES["next_decision_date"])))

    def get(m):
        val = ctx
        for part in m.group(1).split("."):
            val = val[part]
        return html.escape(str(val), quote=False)
    text = text.replace("<!--lenders-->", "".join(f"<li>{html.escape(n)}</li>" for n in B["lender_examples"]))
    text = re.sub(r"<!--reviews:([\w-]+)-->", lambda m: reviews_html(m.group(1)), text)
    text = text.replace("<!--cash-rate-table-->", cash_rate_table())
    text = text.replace("<!--team-cards-->", team_cards())
    text = text.replace("<!--team-behind-->", behind_cards())
    text = re.sub(r"<!--contact:([\w-]+)-->", lambda m: contact_panel(m.group(1)), text)
    text = re.sub(r"<!--brokers-for:([\w-]+)-->", lambda m: brokers_for(m.group(1)), text)
    text = text.replace("<!--team-matcher-->", team_matcher())
    text = text.replace("<!--broker-names-->", html.escape(json.dumps({k: v["name"] for k, v in BROKERS.items()}, ensure_ascii=False)))
    text = re.sub(r"<!--duty-calc:(\w+)-->", lambda m: duty_calc(m.group(1)), text)
    text = re.sub(r"<!--duty-table:(\w+)-->", lambda m: duty_table(m.group(1)), text)
    text = re.sub(r"<!--duty-states(?::(\w+))?-->", lambda m: duty_states(m.group(1)), text)
    text = text.replace("<!--featured-->", "".join(f"<li>{html.escape(n)}</li>" for n in B["featured_in"]))
    return re.sub(r"\{\{([\w.]+)\}\}", get, text)


def reviews_html(which):
    """Review cards: 'home' uses the homepage list; a person's slug uses the reviews that name them."""
    keys = REVIEWS["home"] if which == "home" else TEAM[which]["reviews"]
    cards = []
    for k in keys:
        r = REVIEWS["reviews"][k]
        stars = '<span class="stars" role="img" aria-label="5 out of 5 stars">' + ICON["star"] * 5 + "</span>"
        more = f' <a href="{B["reviews"]["url"]}" rel="noopener">Read the full review</a>' if r["excerpt"] else ""
        cards.append(f"""      <figure class="review">
        {stars}
        <blockquote><p>{html.escape(r["text"])}{more}</p></blockquote>
        <figcaption><b>{html.escape(r["author"])}</b> <span>{html.escape(r["topic"])}, Google review</span></figcaption>
      </figure>""")
    return '<div class="reviews">\n' + "\n".join(cards) + "\n    </div>"


def cash_rate_table():
    rows = "".join(f"<tr><td>{d}</td><td>{c}</td><td>{r}%</td></tr>" for d, c, r in RATES["history"])
    return ('<table class="rate-table" data-cash-rate-table><caption class="visually-hidden">Recent RBA cash rate decisions</caption>'
            '<thead><tr><th scope="col">Effective date</th><th scope="col">Change (% points)</th><th scope="col">Cash rate target</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>")


def behind_cards():
    """People who keep the business running but don't take client enquiries: no profile page, phone or email."""
    cards = []
    for p in BEHIND:
        link = (f'\n        <a class="text-link" href="{html.escape(p["linkedin"])}" rel="noopener">{html.escape(p["name"].split()[0])} on LinkedIn</a>'
                if p.get("linkedin") else "")
        cards.append(f"""      <li class="behind-card">
        <img src="/assets/img/{p['photo']}-4x5-480.webp" alt="{html.escape(p['name'])}" width="480" height="600" loading="lazy">
        <div>
          <span class="person-name">{html.escape(p['name'])}</span>
          <span class="person-role">{html.escape(p['role'])}</span>
          <p>{html.escape(p.get('summary', ''))}</p>{link}
        </div>
      </li>""")
    return '<ul class="behind">\n' + "\n".join(cards) + "\n    </ul>"


def team_cards():
    cards = []
    for p in BROKERS.values():
        cards.append(f"""      <li><a class="person-card" href="/team/{p['slug']}">
        <img src="/assets/img/{p['photo']}-4x5-480.webp" alt="{html.escape(p['name'])}" width="480" height="600" loading="lazy">
        <span class="person-name">{html.escape(p['name'])}</span>
        <span class="person-role">{html.escape(p['role'])}</span>
      </a></li>""")
    return '<ul class="people">\n' + "\n".join(cards) + "\n    </ul>"


def team_matcher():
    """'Who should I talk to?': pick what you're working on, see the brokers who focus on it.
    Hidden until the script runs; without it, visitors still have the broker cards below."""
    esc = html.escape
    chips = "\n".join(
        f'        <label class="chip"><input type="radio" name="need" value="{esc(n["key"])}"><span>{esc(n["label"])}</span></label>'
        for n in NEEDS)
    groups = []
    for n in NEEDS:
        cards = []
        for slug in n["people"]:
            p = TEAM[slug]
            first = esc(p["name"].split()[0])
            q = f"broker={slug}" + (f"&amp;goal={urllib.parse.quote(n['goal'])}" if n.get("goal") else "")
            cards.append(f"""          <li class="match-card">
            <img src="/assets/img/{p['photo']}-4x5-480.webp" alt="" width="96" height="120" loading="lazy">
            <div>
              <h3><a href="/team/{slug}">{esc(p['name'])}</a></h3>
              <p class="person-role">{esc(p['role'])}</p>
              <p>{esc(p.get('summary', ''))}</p>
              <div class="btn-row"><a class="btn btn-small" href="/get-started?{q}">Talk to {first}</a><a class="text-link" href="/team/{slug}">View profile</a></div>
            </div>
          </li>""")
        groups.append(f"""      <div class="match" data-need="{esc(n['key'])}" hidden>
        <h3 class="visually-hidden">Brokers for {esc(n['label'].lower())}</h3>
        <ul class="match-list">
{chr(10).join(cards)}
        </ul>
      </div>""")
    return f"""<section class="matcher" data-matcher hidden aria-labelledby="matcher-heading">
      <h2 id="matcher-heading">Who should I talk to?</h2>
      <p>Choose what you're working on and we'll point you to the brokers who focus on it.</p>
      <fieldset class="chips">
        <legend class="visually-hidden">What are you working on?</legend>
{chips}
      </fieldset>
      <div class="match-results" aria-live="polite">
{chr(10).join(groups)}
      </div>
      <p class="match-note" hidden>Every GC Wealth broker can help with most loans. Not sure? <a href="/get-started">Get started</a> and we'll match you with the right person.</p>
    </section>"""


def _phrase(label):
    """'Buying my first home' -> 'buying my first home', for 'I'd like to talk about ...'."""
    return label[0].lower() + label[1:]


def contact_message(first, topic="my finances", name=""):
    """The prefilled text and email a visitor sends a broker. site.js builds the same wording as they choose."""
    hi = f"Hi {first}, " + (f"it's {name}. " if name else "")
    sms = f"{hi}I found you on the GC Wealth website and I'd like to talk about {topic}. When's a good time for a quick chat?"
    subject = "Enquiry from the GC Wealth website"
    body = (f"Hi {first},\n\nI found you on the GC Wealth website and I'd like to talk about {topic}.\n\n"
            f"A bit about what I'm after:\n\n\nThe best way and time to reach me:\n\n\nThanks,\n{name}")
    return sms, subject, body


def contact_panel(slug):
    """Text, call or email a broker, with the message started for them. Opens in the visitor's own app:
    nothing is sent through the site. Brokers without their own mobile and email use the office."""
    p = BROKERS[slug]
    esc = html.escape
    first = p["name"].split()[0]
    own = bool(p.get("phone_tel") and p.get("email"))
    tel = p["phone_tel"] if own else B["phone_tel"]
    email = p["email"] if own else B["email"]
    sms, subject, body = contact_message(first)
    q = urllib.parse.quote
    topics = [n for n in NEEDS if slug in n["people"]]
    chips = "\n".join(
        f'          <label class="chip"><input type="radio" name="cb-topic" value="{esc(_phrase(n["label"]))}" data-label="{esc(n["label"])}"><span>{esc(n["label"])}</span></label>'
        for n in topics) + '\n          <label class="chip"><input type="radio" name="cb-topic" value="my finances" data-label=""><span>Something else</span></label>'
    text_btn = (f'<a class="btn" data-sms href="sms:{tel}?&amp;body={esc(q(sms))}">Text {esc(first)}</a>' if own else "")
    call_label = f"Call {esc(first)}" if own else f"Call {esc(B['phone'])}"
    email_label = f"Email {esc(first)}" if own else "Email our office"
    return f"""<section class="contact-broker" data-contact data-first="{esc(first)}" aria-labelledby="cb-title">
        <h2 id="cb-title">Get in touch with {esc(first)}</h2>
        <p>Choose what it's about and we'll start the message for you. It opens in your own messages or email app, so nothing is sent until you press send.</p>
        <div class="field">
          <label for="cb-name">Your first name <span class="muted">(optional)</span></label>
          <input class="input" id="cb-name" name="cb-name" autocomplete="given-name" maxlength="40">
        </div>
        <fieldset class="chips">
          <legend>What's it about?</legend>
{chips}
        </fieldset>
        <div class="btn-row contact-actions">
          {text_btn}
          <a class="btn{' btn-ghost' if own else ''}" href="tel:{tel}">{call_label}</a>
          <a class="btn btn-ghost" data-mail href="mailto:{email}?subject={esc(q(subject))}&amp;body={esc(q(body))}">{email_label}</a>
        </div>
        <p class="hint">Prefer a form? <a href="/get-started?broker={slug}">Send an enquiry</a> and {esc(first)} will get back to you.</p>
      </section>"""


def brokers_for(key):
    """'Talk to a broker who focuses on this' for a service page, from the same data as the team matcher."""
    need = next((n for n in NEEDS if n["key"] == key), None)
    if not need:
        return ""
    esc = html.escape
    cards = []
    for slug in need["people"]:
        p = BROKERS[slug]
        first = esc(p["name"].split()[0])
        goal = f"&amp;goal={urllib.parse.quote(need['goal'])}" if need.get("goal") else ""
        cards.append(f"""        <li class="match-card">
          <img src="/assets/img/{p['photo']}-4x5-480.webp" alt="" width="96" height="120" loading="lazy">
          <div>
            <h3><a href="/team/{slug}">{esc(p['name'])}</a></h3>
            <p class="person-role">{esc(p['role'])}</p>
            <p>{esc(p.get('summary', ''))}</p>
            <div class="btn-row"><a class="btn btn-small" href="/get-started?broker={slug}{goal}">Talk to {first}</a><a class="text-link" href="/team/{slug}">View profile</a></div>
          </div>
        </li>""")
    return f"""<section class="section-tight brokers-for" aria-labelledby="bf-title">
  <div class="wrap">
    <h2 id="bf-title">Talk to a broker who focuses on this</h2>
    <p>Every GC Wealth broker can help with most loans. These are the people who focus on {esc(_phrase(need['label']))}.</p>
    <ul class="match-list">
{chr(10).join(cards)}
    </ul>
  </div>
</section>"""


def nice_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def byline(meta, updated):
    """'Reviewed by' only appears once that person has actually reviewed the page (meta 'reviewed_by')."""
    parts = []
    who = TEAM.get(meta.get("reviewed_by", ""))
    if who:
        parts.append(f'<span class="byline-who"><img src="/assets/img/{who["photo"]}-4x5-480.webp" alt="" width="40" height="50">'
                     f'Reviewed by <a href="/team/{who["slug"]}">{html.escape(who["name"])}</a>, {html.escape(who["role"])}</span>')
    parts.append(f"<span>Last updated {nice_date(updated)}</span>")
    return '<p class="byline">' + "".join(parts) + "</p>"


def address_ld():
    a = B["address"]
    return {"@type": "PostalAddress", "streetAddress": a["street"], "addressLocality": a["locality"],
            "addressRegion": a["region"], "postalCode": a["postcode"], "addressCountry": a["country"]}


def crumbs_for(path, pages):
    """[(label, href)] from Home down to this page, using each parent's crumb name."""
    trail = [("Home", "/")]
    parts = path.strip("/").split("/")
    for i in range(1, len(parts) + 1):
        href = "/" + "/".join(parts[:i])
        meta = pages.get(href)
        trail.append(((meta or {}).get("crumb") or parts[i - 1].replace("-", " ").capitalize(), href))
    return trail


def structured_data(meta, body, pages):
    path = meta["path"]
    blocks = []
    if path == "/":
        blocks.append({
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": ["FinancialService", "LocalBusiness"],
                    "@id": ORG_ID,
                    "name": B["name"],
                    "legalName": B["legal_name"],
                    "url": SITE + "/",
                    "logo": SITE + B["logo"]["png"],
                    "image": SITE + "/assets/img/og-image.jpg",
                    "description": meta["description"],
                    "telephone": B["phone_tel"],
                    "email": B["email"],
                    "taxID": B["abn"],
                    "foundingDate": B["founded"],
                    "founder": [{"@type": "Person", "name": f["name"], "jobTitle": f["role"], **({"sameAs": [f["linkedin"]]} if f.get("linkedin") else {})}
                                for f in TEAM.values() if f.get("founder")],
                    "address": address_ld(),
                    "openingHours": B["hours_schema"],
                    "areaServed": {"@type": "Country", "name": "Australia"},
                    "sameAs": list(B["social"].values()),
                },
                {
                    "@type": "WebSite",
                    "@id": SITE + "/#website",
                    "url": SITE + "/",
                    "name": B["name"],
                    "inLanguage": "en-AU",
                    "publisher": {"@id": ORG_ID},
                },
            ],
        })
    elif meta.get("index", "yes") != "no":
        trail = crumbs_for(path, pages)
        blocks.append({
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": label, "item": SITE + href}
                                for i, (label, href) in enumerate(trail)],
        })
    if meta.get("schema") == "service":
        blocks.append({
            "@context": "https://schema.org",
            "@type": "Service",
            "name": meta.get("crumb") or meta["title"].split("|")[0].strip(),
            "description": meta["description"],
            "url": SITE + path,
            "provider": {"@type": "FinancialService", "@id": ORG_ID, "name": B["name"]},
            "areaServed": {"@type": "Country", "name": "Australia"},
        })
    if meta.get("schema") == "calculator":
        blocks.append({
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": meta.get("h1") or meta["title"].split("|")[0].strip(),
            "description": meta["description"],
            "url": SITE + path,
            "applicationCategory": "FinanceApplication",
            "operatingSystem": "Any",
            "isAccessibleForFree": True,
            "provider": {"@type": "FinancialService", "@id": ORG_ID, "name": B["name"]},
        })
    if meta.get("person") in TEAM:
        p = TEAM[meta["person"]]
        blocks.append({
            "@context": "https://schema.org",
            "@type": "Person",
            "name": p["name"],
            "jobTitle": p["role"],
            "image": SITE + f"/assets/img/{p['photo']}-4x5-800.webp",
            "url": SITE + path,
            "worksFor": {"@type": "FinancialService", "@id": ORG_ID, "name": B["name"]},
            "hasCredential": [{"@type": "EducationalOccupationalCredential", "name": c} for c in p["credentials"]],
            **({"sameAs": links} if (links := [p[k] for k in ("linkedin", "instagram") if p.get(k)]) else {}),
        })
    if 'class="faq-list"' in body:
        qa = re.findall(r"<summary>(.*?)</summary>\s*<div>(.*?)</div>", body.split('class="faq-list"', 1)[1], re.S)
        blocks.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": strip_tags(q),
                            "acceptedAnswer": {"@type": "Answer", "text": strip_tags(a)}} for q, a in qa],
        })
    return "".join(ld(b) for b in blocks)


def lastmod(src):
    """Date the page source last changed: today if it has uncommitted edits, else its last commit."""
    today = datetime.date.today().isoformat()
    try:
        dirty = subprocess.run(["git", "status", "--porcelain", str(src)], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if dirty:
            return today
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(src)], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return out or today
    except OSError:
        return today


def brand_css():
    c = B["colours"]
    return ":root{" + "".join(f"--{k}:{v};" for k, v in c.items()) + "}"


def head(meta, extra_head):
    title = html.escape(meta["title"])
    desc = html.escape(meta["description"])
    url = SITE + meta["path"]
    noindex = meta.get("index", "yes") == "no"
    robots = '\n<meta name="robots" content="noindex">' if noindex else '\n<meta name="robots" content="max-image-preview:large">'
    canonical = "" if noindex else f'\n<link rel="canonical" href="{url}">'
    beacon = ""
    if B.get("analytics_token"):
        beacon = ('\n<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
                  f'data-cf-beacon=\'{{"token": "{B["analytics_token"]}"}}\'></script>')
    return f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{desc}">{canonical}{robots}
<meta name="theme-color" content="{B['colours']['navy']}">
<link rel="icon" href="{B['logo']['colour']}" type="image/svg+xml">
<link rel="icon" href="/assets/img/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{html.escape(B['name'])}">
<meta property="og:locale" content="en_AU">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/assets/img/og-image.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="preload" href="/assets/fonts/figtree-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/figtree-latin-600-normal.woff2" as="font" type="font/woff2" crossorigin>
<style>{brand_css()}</style>
<link rel="stylesheet" href="{asset('/assets/css/site.css')}">{extra_head}{beacon}
</head>"""


def logo(kind="colour", height=52):
    w = round(B["logo"]["width"] * height / B["logo"]["height"])
    return f'<img src="{B["logo"][kind]}" alt="{html.escape(B["name"])}" width="{w}" height="{height}">'


def header(active, path):
    items = []
    for key, label, href, children in NAV:
        cur = ' aria-current="page"' if href == path else (' aria-current="true"' if key == active else "")
        if children:
            sub = "\n".join(f'            <li><a href="{h}"{" aria-current=\"page\"" if h == path else ""}>{l}</a></li>'
                            for l, h in children)
            items.append(f"""<li class="has-sub">
          <a href="{href}"{cur}>{label}</a>
          <button class="sub-btn" type="button" aria-expanded="false" aria-label="Show {label.lower()} pages">{ICON['chev']}</button>
          <ul class="sub">
            <li><a href="{href}">{"About us" if key == "about" else "All " + label.lower()}</a></li>
{sub}
          </ul>
        </li>""")
        else:
            items.append(f'<li><a href="{href}"{cur}>{label}</a></li>')
    nav_items = "\n        ".join(items)
    return f"""<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header" id="top">
  <div class="wrap">
    <a class="brand" href="/" aria-label="{html.escape(B['name'])} home">{logo('colour', 52)}</a>
    <nav class="nav" aria-label="Main">
      <ul class="nav-links" id="nav-links">
        {nav_items}
        <li class="nav-menu-extra"><a class="btn" href="/get-started">Get started</a></li>
        <li class="nav-menu-extra"><a href="tel:{B['phone_tel']}">{ICON['phone']} {B['phone']}</a></li>
      </ul>
      <a class="nav-phone" href="tel:{B['phone_tel']}">{ICON['phone']}<span>{B['phone']}</span></a>
      <a class="btn nav-cta" href="/get-started">Get started</a>
      <button class="menu-btn" type="button" aria-expanded="false" aria-controls="nav-links">
        <span class="menu-icon" aria-hidden="true"></span><span class="menu-label">Menu</span>
      </button>
    </nav>
  </div>
</header>
"""


def breadcrumbs(path, pages):
    trail = crumbs_for(path, pages)
    parts = []
    for i, (label, href) in enumerate(trail):
        if i == len(trail) - 1:
            parts.append(f'<li aria-current="page">{html.escape(label)}</li>')
        else:
            parts.append(f'<li><a href="{href}">{html.escape(label)}</a></li>')
    return f'<nav class="crumbs wrap" aria-label="Breadcrumb"><ol>{"".join(parts)}</ol></nav>\n'


def footer(show_bar):
    def col(title, links):
        lis = "\n".join(f'            <li><a href="{h}">{l}</a></li>' for l, h in links)
        return f"""        <div>
          <h2>{title}</h2>
          <ul>
{lis}
          </ul>
        </div>"""
    home = next(n for n in NAV if n[0] == "home-loans")
    biz = next(n for n in NAV if n[0] == "business")
    a = B["address"]
    social = " ".join(f'<a href="{u}" rel="noopener">{n.capitalize() if n != "linkedin" else "LinkedIn"}</a>'
                      for n, u in B["social"].items())
    bar = f"""
<div class="action-bar" role="region" aria-label="Quick actions">
  <a class="action-call" href="tel:{B['phone_tel']}">{ICON['phone']}Call</a>
  <a class="btn" href="/get-started">Get started</a>
</div>""" if show_bar else ""
    return f"""
<footer class="site-footer">
  <div class="wrap">
    <div class="footer-top">
      <div class="footer-brand">
        {logo('white', 64)}
        <p>Boutique mortgage and finance broking from {a['locality']} on the Gold Coast, for clients across Australia.</p>
        <form class="signup" action="/api/enquiry" method="post" data-ajax>
          <input type="hidden" name="type" value="newsletter">
          <label for="nl-email">Rate updates and finance tips by email</label>
          <div class="signup-row">
            <input class="input" id="nl-email" name="email" type="email" autocomplete="email" placeholder="Your email" required>
            <button class="btn btn-light" type="submit">Sign up</button>
          </div>
          <div class="hp" aria-hidden="true"><label>Leave blank <input name="website" tabindex="-1" autocomplete="off"></label></div>
          <p class="form-status" role="status" aria-live="polite"></p>
        </form>
      </div>
      <nav class="footer-cols" aria-label="Footer">
{col(home[1], home[3])}
{col(biz[1], biz[3])}
{col("Calculators", next(n for n in NAV if n[0] == "calculators")[3])}
{col("Company", [("About us", "/about"), ("Our team", "/team"), ("Referral partners", "/partners"), ("Loan health check", "/loan-health-check"), ("First home buyer guide", "/first-home-buyer-guide"), ("Contact", "/contact"), ("Get started", "/get-started")])}
        <div>
          <h2>Contact</h2>
          <ul>
            <li><a href="tel:{B['phone_tel']}">{B['phone']}</a></li>
            <li><a href="mailto:{B['email']}">{B['email']}</a></li>
            <li><a href="{a['maps']}" rel="noopener">{a['street']}, {a['locality']} {a['region']} {a['postcode']}</a></li>
            <li>{B['hours_text']}</li>
          </ul>
        </div>
      </nav>
    </div>
    <div class="footer-legal">
      <p><strong>{html.escape(B['name'])}</strong> is a trading name of {html.escape(B['legal_name'])} (ABN {B['abn']}). {B['licence']['line']}</p>
      <p>{DISCLAIMER_TEXT}</p>
      <p class="footer-links"><a href="/privacy">Privacy policy</a> <a href="/credit-guide">Credit guide</a> <a href="/compliments-and-concerns">Compliments and concerns</a> {social}</p>
      <p>© <span class="year">2026</span> {html.escape(B['legal_name'])}. Offices in {a['locality']} {a['region']} and {B['second_office']}.</p>
    </div>
  </div>
</footer>{bar}

<script src="{asset('/assets/js/site.js')}" defer></script>
</body>
</html>
"""


DISCLAIMER_TEXT = ("This page provides general information only and has been prepared without taking into account your objectives, "
                   "financial situation or needs. We recommend that you consider whether it is appropriate for your circumstances and your "
                   "full financial situation will need to be reviewed prior to acceptance of any offer or product. It does not constitute "
                   "legal, tax or financial advice and you should always seek professional advice in relation to your individual "
                   "circumstances. Subject to lenders' terms and conditions, fees and charges and eligibility criteria apply.")

DISCLAIMER = """
<aside class="note wrap-narrow" aria-label="General information">
  <p><strong>General information only.</strong> This page explains how this type of finance generally works. It doesn't consider your objectives, financial situation or needs, and it isn't tax, legal or financial product advice. Lending criteria, fees and government schemes change; any loan is subject to the lender's assessment and approval.</p>
</aside>"""


def parse(text):
    m = re.match(r"\s*<!--(.*?)-->\s*", text, re.S)
    meta = {}
    for line in m.group(1).strip().splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    body = text[m.end():]
    body = re.sub(r"<!--include:([\w-]+)-->", lambda im: (PAGES / "partials" / f"{im.group(1)}.html").read_text().strip(), body)
    extra = ""
    hm = re.search(r"<!--head-->(.*?)<!--/head-->", body, re.S)
    if hm:
        extra = "\n" + hm.group(1).strip()
        body = body[:hm.start()] + body[hm.end():]
    return meta, fill(body.strip()), extra


def build():
    sources = sorted(p for p in PAGES.rglob("*.html") if "partials" not in p.parts and "_templates" not in p.parts)
    parsed = [(src, *parse(src.read_text())) for src in sources]
    # Stamp duty: one page per state or territory, from pages/_templates/stamp-duty-state.html and data/stamp-duty.json.
    template = PAGES / "_templates" / "stamp-duty-state.html"
    for code in DUTY["order"]:
        st = DUTY["states"][code]
        surcharge = (f"<li>{html.escape(st['surcharge'])}.</li>" if st.get("surcharge") else "")
        page = template.read_text()
        for key, value in {"code": code, "name": html.escape(st["name"]), "short": st["short"], "slug": st["slug"],
                           "term": st["term"], "office": html.escape(st["office"]), "source": st["source"],
                           "fhb_text": html.escape(st["fhb_text"]), "surcharge": surcharge,
                           "surcharge_none": (f"<p>{html.escape(st['surcharge_none'])}</p>" if st.get("surcharge_none") else ""),
                           "checked": DUTY["checked"]}.items():
            page = page.replace("[[" + key + "]]", value)
        parsed.append((template, *parse(page)))
    pages = {meta["path"]: meta for _, meta, _, _ in parsed}
    urls = []
    for src, meta, body, extra_head in parsed:
        path = meta["path"]
        extra_head = structured_data(meta, body, pages) + extra_head
        crumbs = breadcrumbs(path, pages) if path != "/" and meta.get("crumbs", "yes") != "no" else ""
        note = DISCLAIMER if meta.get("disclaimer") == "yes" else ""
        if meta.get("disclaimer") == "yes" or meta.get("reviewed_by"):
            body = body.replace("<!--byline-->", byline(meta, lastmod(src)))
        out = (head(meta, extra_head) + "\n" + header(meta.get("nav", ""), path) + '\n<main id="main">\n'
               + crumbs + body + note + "\n</main>\n" + footer(meta.get("bar", "yes") != "no"))
        out = re.sub(r'(src|href)="(/assets/(?:js|css)/[\w.-]+\.(?:js|css))"', lambda m: f'{m.group(1)}="{asset(m.group(2))}"', out)
        name = "index.html" if path == "/" else path.strip("/") + ".html"
        dest = OUT / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(version_images(out))
        if meta.get("index", "yes") != "no":
            urls.append((path, lastmod(src)))
        print("built", name)
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{SITE}{u}</loc><lastmod>{d}</lastmod></url>" for u, d in sorted(urls, key=lambda x: (x[0] != "/", x[0]))]
    sitemap.append("</urlset>")
    (OUT / "sitemap.xml").write_text("\n".join(sitemap) + "\n")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: {SITE}/sitemap.xml\n")


if __name__ == "__main__":
    build()
