# gcwealth.com.au

Website for GC Wealth (Gold Coast Wealth Pty Ltd), hosted on Cloudflare Workers: static pages plus a small Worker for the forms.
Cloudflare runs no build step: the finished pages in `public/` are committed.

## Files

| Path | What it is |
|---|---|
| `brand.json` | **Every business detail in one place:** name, legal name, ABN, licence line, phone, email, address, hours, lender count, review rating, colours and logo files. Change it here and rebuild. |
| `pages/` | The text of each page. Edit these, not the HTML in `public/`. Sub-pages sit in folders (`pages/home-loans/refinancing.html` → `/home-loans/refinancing`). |
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

### Rebranding

Change `name`, `legal_name`, `colours` and the `logo` file paths in `brand.json`, replace the logo files in `public/assets/img/`, rebuild and push.
Then search `pages/` for the old name in any headings you've written by hand.

### Compliance

- The licence line, legal name and ABN appear in the footer of every page and every email, from `brand.json`.
- Service pages set `disclaimer: yes` to add the general-information note.
- Only publish facts that are confirmed. No "lowest rate", "guaranteed approval" or similar claims (ASIC RG 234).
- Government scheme details on the first home buyers page were checked against official sources in November 2026. Recheck after each state and federal budget.
- `/privacy`, `/credit-guide` and `/complaints` are drafts (not indexed) until the final text is added in phase 2.

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
| Privacy, credit guide, complaints (drafts) | `pages/privacy.html` etc. | `/privacy`, `/credit-guide`, `/complaints` |
| Thanks, not found | `pages/thanks.html`, `pages/404.html` | `/thanks` |
