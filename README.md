# gcwealth.com.au

Website for GC Wealth (Gold Coast Wealth Pty Ltd), hosted on Cloudflare Workers: static pages plus a small Worker for the forms.
Cloudflare runs no build step: the finished pages in `public/` are committed.

## Files

| Path | What it is |
|---|---|
| `brand.json` | **Every business detail in one place:** name, legal name, ABN, licence line, phone, email, address, hours, lender count, review rating, colours and logo files. Change it here and rebuild. |
| `pages/` | The text of each page. Edit these, not the HTML in `public/`. Sub-pages sit in folders (`pages/home-loans/refinancing.html` → `/home-loans/refinancing`). |
| `data/rates.json` | RBA cash rate, recent decisions, next meeting, APRA settings. **Update after each RBA decision and APRA update.** The cash rate page also reads the RBA's table live (`/api/cash-rate`, `src/cash-rate.js`) and shows a newer rate if there is one |
| `data/stamp-duty.json` | Stamp duty rates and first home buyer concessions for every state and territory. Builds the calculator, the rate tables and the eight state pages (`pages/_templates/stamp-duty-state.html`). **Check every July (NSW re-indexes thresholds each 1 July) and after state budgets**, then update the worked examples in `tests/check.py` |
| `data/team.json` | People shown on the site (profile pages at `/team/<slug>`). Add a person here and a page in `pages/team/`. Make their photo with `python3 tools/headshot.py photo.jpg firstname-lastname` so it matches the others (same framing, same grey backdrop) |
| `data/reviews.json` | Google reviews shown on the site, word for word. Never edit the wording |
| `public/assets/js/calculators.js` | All six calculators. Tax rates, APRA buffer and Queensland duty rates are at the top (`RULES`) and in the duty functions; update each financial year |
| `tools/guides/` | The first home buyer guide (every state). Edit the HTML, then `python3 tools/guides/render.py` to rebuild the PDF. Grants, duty help and the $650,000 duty examples come from `data/stamp-duty.json` and the calculator script, so re-run it whenever those change |
| `pages/partials/` | Shared sections: `cta.html` (closing "Talk it through" band), `talk.html` (side box on service pages) |
| `build.py` | Wraps each page in the header, menu, breadcrumbs and footer; adds structured data; writes `public/`, `sitemap.xml` and `robots.txt`. The menu (`NAV`) is at the top. |
| `public/` | Everything the site serves: built pages, CSS, JS, fonts, images, `_headers` |
| `src/worker.js` | Redirects www, http, `.html`, trailing slashes and old Elementor addresses (`MOVED`); sends `/api/enquiry` to the form handler; serves everything else |
| `src/enquiry.js` | Emails each form (contact, get started, newsletter) through Resend, then sends the person an automatic reply |
| `src/mail.js` | Email sending, layouts and the per-visitor limit |
| `tests/check.py` | The pre-push check (see below) |
| `wrangler.jsonc` | Cloudflare config. The Worker name must match the one in the Cloudflare dashboard. Enquiry recipient and sender addresses are here. |

## Editing

1. Edit the page in `pages/`, or the details in `brand.json`.
2. Run `python3 build.py` (Python 3, no packages needed).
3. Run the checks: `npm test`.
4. Commit both `pages/` and `public/`, then push. Every push to `main` goes live.

In page text, `{{phone}}`, `{{email}}`, `{{name}}`, `{{lenders}}`, `{{reviews.rating}}` and other `brand.json` keys are filled in automatically.
To add a page, copy one in `pages/`, change the settings block at the top (title, description, path, crumb), and add it to `NAV` in `build.py` if it belongs in the menu.

### Bylines

Service and calculator pages show "Last updated" automatically. To show "Reviewed by", add `reviewed_by: brooke-juracic` (a slug from
`data/team.json`) to a page's settings block, but only once that person has actually read and approved the page.

### Rebranding

Change `name`, `legal_name`, `colours` and the `logo` file paths in `brand.json`, replace the logo files in `public/assets/img/`, rebuild and push.
Then search `pages/` for the old name in any headings you've written by hand.

### Compliance

- The licence line, legal name and ABN appear in the footer of every page and every email, from `brand.json`.
- Service pages set `disclaimer: yes` to add the general-information note.
- Only publish facts that are confirmed. No "lowest rate", "guaranteed approval" or similar claims (ASIC RG 234).
- Government scheme details on the first home buyers page were checked against official sources in November 2026. Recheck after each state and federal budget.
- `/privacy` (Connective template, items to confirm highlighted) and `/credit-guide` are drafts, kept out of search until confirmed.
  `/compliments-and-concerns` follows Connective's template and is live.
- `CLAIMS.md` lists every factual claim on the site and its evidence (RG 234 expects records). Update it when claims change.
- `npm test` fails on wording Connective and ASIC flag (free, best other than "best interests", guaranteed, save you thousands …)
  and on any highlighted draft text left on a page that search engines can see.
- Emails to the public carry the licence line, Connective's short privacy notice and the scam warning (`src/mail.js`).

### Before launch

1. **Connective approval:** send the preview link to compliance@connective.com.au. Connective requires approval before any
   advertising is published, websites included.
2. **Credit Representative number:** Connective's guide says a site advertising under the company should show the *corporate*
   Credit Representative number. The footer currently shows 491220; confirm the right number with Connective.
3. **Privacy policy:** fill the highlighted items (where information is held, security measures, Privacy Officer, access charges,
   automated decisions; the last is required from 10 December 2026), then set `index: yes`.
4. **Credit guide:** add the current Credit Guide (PDF or page).
5. **Lender names:** keep only lenders GCW brokers are accredited with.

## Checks before every push

```
npm install        # once
npm test           # builds, then runs tests/check.py
```

`tests/check.py` starts the site locally with a stand-in email server and, for every page on desktop and mobile, checks it loads with no
errors or missing files, has one heading and sensible title and description lengths, doesn't scroll sideways on mobile, and passes an
accessibility scan (axe-core). It then checks every internal link, the old-address redirects, and submits each form. Screenshots go to
`tests/out/`. `python3 tests/shoot.py /path` takes quick screenshots while designing.

## Deploy (first time)

1. **Cloudflare account:** sign up with admin@gcwealth.com.au (separate from ONIV) and turn on two-factor sign-in.
2. Workers & Pages → Create → Import a repository → `lachlancreese/gcwealth-website`. Worker name `gcwealth-website`.
   Build command: none. Deploy command: `npx wrangler deploy`.
   Cloudflare then shows a preview address (`gcwealth-website.<account>.workers.dev`). The whole site works there before the
   domain moves, and every address other than gcwealth.com.au sends `X-Robots-Tag: noindex` so Google ignores it.
3. **Email (Resend):** add the domain `gcwealth.com.au` in Resend and add the DNS records it gives you (at Squarespace Domains until the
   DNS move). Create an API key and add it in Cloudflare → `gcwealth-website` → Settings → Variables and secrets as `RESEND_API_KEY`
   (type Secret). Redeploy and send a test enquiry.
4. **Analytics:** Cloudflare → Web Analytics → add site, copy the token into `analytics_token` in `brand.json`, rebuild and push.

## Domain cutover (last)

`gcwealth.com.au` is registered with Squarespace Domains. In Cloudflare use "Add a domain" (DNS only, not transfer), check every email
record was imported (MX, SPF, DKIM, DMARC, autodiscover), then change the nameservers at Squarespace to Cloudflare's. Add
`gcwealth.com.au` and `www.gcwealth.com.au` as custom domains on the Worker. Before switching, make sure every old address in the
Elementor sitemap has a home in `MOVED` (`src/worker.js`).

## Pages

| Page | File | Address |
|---|---|---|
| Home | `pages/index.html` | `/` |
| About | `pages/about.html` | `/about` |
| Contact | `pages/contact.html` | `/contact` |
| Get started (stepped form) | `pages/get-started.html` | `/get-started` |
| Home loans hub | `pages/home-loans.html` | `/home-loans` |
| First home buyers, refinancing, investment, construction, self-employed, guarantor, bridging, pre-approval | `pages/home-loans/*.html` | `/home-loans/...` |
| SMSF loans | `pages/smsf-loans.html` | `/smsf-loans` |
| Business finance hub | `pages/business-finance.html` | `/business-finance` |
| Commercial property, business loans, asset finance | `pages/business-finance/*.html` | `/business-finance/...` |
| Privacy, credit guide (drafts) | `pages/privacy.html`, `pages/credit-guide.html` | `/privacy`, `/credit-guide` |
| Our team and profiles | `pages/team.html`, `pages/team/*.html` | `/team`, `/team/brooke-juracic`, `/team/steven-shaw`, `/team/kirisome-auvaa`, `/team/kim-edwards`, `/team/matthew-klein` |
| Referral partners (referral form) | `pages/partners.html` | `/partners` |
| Loan health check (offer and form) | `pages/loan-health-check.html` | `/loan-health-check` |
| First home buyer guide (PDF by email) | `pages/first-home-buyer-guide.html` | `/first-home-buyer-guide` |
| Calculators hub and six calculators | `pages/calculators.html`, `pages/calculators/*.html` | `/calculators/...` |
| RBA cash rate and lending rules | `pages/rba-cash-rate.html` | `/rba-cash-rate` |
| Compliments and concerns | `pages/compliments-and-concerns.html` | `/compliments-and-concerns` |
| Thanks, not found | `pages/thanks.html`, `pages/404.html` | `/thanks` |
