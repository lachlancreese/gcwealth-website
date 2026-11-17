// Shared email helpers: sending through Resend, a simple per-visitor limit, and the email layouts.
// Business details come from brand.json, so a rebrand only needs that file changed.
import brand from "../brand.json";

export const BRAND = brand;

export function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export const validEmail = (s) => /^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$/.test(s) && s.length <= 200;

export async function sendEmail(env, payload) {
  try {
    // RESEND_URL is only set when testing locally (tests/check.py points it at a stand-in server).
    const res = await fetch(env.RESEND_URL || "https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) console.error("Resend", res.status, await res.text().catch(() => ""));
    return res.ok;
  } catch (err) {
    console.error("Resend unreachable", err);
    return false;
  }
}

export const teamAddresses = (env) => String(env.TO_EMAIL).split(",").map((s) => s.trim()).filter(Boolean);

// Emails to the public come from "<brand name>" on the website's sending address; replies go to the team inbox.
export function customerSender(env) {
  const address = (String(env.FROM_EMAIL).match(/<([^>]+)>/) || [null, env.FROM_EMAIL])[1].trim();
  return { from: `${brand.name} <${address}>`, reply_to: teamAddresses(env)[0] };
}

// At most `max` uses per `seconds` for one key (a visitor's IP or an email address), counted at each Cloudflare
// location. Not exact, but enough to stop the forms being used to send a flood of emails.
export async function overLimit(bucket, key, max, seconds) {
  if (typeof caches === "undefined" || !caches.default) return false;
  const slot = Math.floor(Date.now() / 1000 / seconds);
  const id = new Request(`${brand.site}/__limit/${bucket}/${encodeURIComponent(key)}/${slot}`);
  const hit = await caches.default.match(id);
  const count = hit ? Number(await hit.text()) || 0 : 0;
  if (count >= max) return true;
  await caches.default.put(id, new Response(String(count + 1), { headers: { "Cache-Control": `max-age=${seconds}` } }));
  return false;
}

// Small print on every email to the public, from Connective's "Advertising requirements" (email signature section).
const FOOTER = [
  `${brand.name} is a trading name of ${brand.legal_name} (ABN ${brand.abn}). ${brand.licence.line}`,
  "Your full financial situation will need to be reviewed prior to acceptance of any offer or product.",
  "Privacy notice: We collect and use your information to assist with your credit needs, including loan applications and marketing " +
    "communications (you may opt out at any time). Your information may be shared with our credit licensee (Connective Credit Services " +
    "Pty Ltd ABN 51 143 651 496), your chosen lenders, and relevant service providers. We do not sell or rent your data. For details on " +
    `accessing or correcting your information or making a complaint, contact us or visit ${brand.site}/privacy.`,
  "We will never ask you to transfer money or make payments via email. If you receive such a request, do not respond and contact us " +
    "directly. Learn more at www.scamwatch.gov.au.",
];

// The customer email layout: a heading, short paragraphs, the team sign-off and the licence line. All text is escaped.
export function customerEmail({ heading, paragraphs, after = [] }) {
  const c = brand.colours;
  const p = (t) => `<p style="margin:0 0 16px;font:16px/1.55 Arial,Helvetica,sans-serif;color:${c.ink}">${esc(t)}</p>`;
  const html = `<!doctype html><html><body style="margin:0;background:${c.mist}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:${c.mist}"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#FFFFFF;border-radius:12px">
<tr><td style="padding:28px 32px 0"><img src="${brand.site}${brand.logo.png}" width="72" height="72" alt="${esc(brand.name)}" style="display:block;border:0"></td></tr>
<tr><td style="padding:16px 32px 0">
<h1 style="margin:0 0 20px;font:600 26px/1.25 Arial,Helvetica,sans-serif;color:${c.navy}">${esc(heading)}</h1>
${paragraphs.map(p).join("\n")}
${after.map(p).join("\n")}
<p style="margin:24px 0 24px;font:16px/1.5 Arial,Helvetica,sans-serif;color:${c.ink}">The ${esc(brand.name)} team<br><span style="color:#5B6B72;font-size:14px"><a href="tel:${brand.phone_tel}" style="color:#5B6B72">${esc(brand.phone)}</a> · <a href="${brand.site}" style="color:#5B6B72">${esc(brand.site.replace("https://", ""))}</a></span></p>
${FOOTER.map((t) => `<p style="margin:0 0 10px;font:11px/1.5 Arial,Helvetica,sans-serif;color:#5B6B72">${esc(t)}</p>`).join("\n")}
<div style="height:18px"></div>
</td></tr></table>
</td></tr></table></body></html>`;
  const text = [heading, "", ...paragraphs, ...(after.length ? ["", ...after] : []), "", `The ${brand.name} team`, `${brand.phone} · ${brand.site}`, "",
    ...FOOTER].join("\n");
  return { html, text };
}

// A two-column table of details, for the team's emails.
export function detailsTable(title, rows) {
  const html =
    `<h2 style="font-family:Arial,sans-serif;color:${brand.colours.navy}">${esc(title)}</h2><table cellpadding="6" style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px">` +
    rows.map(([k, v]) => `<tr><td style="color:#5B6B72;vertical-align:top"><b>${esc(k)}</b></td><td>${esc(v || "-").replace(/\n/g, "<br>")}</td></tr>`).join("") +
    `</table>`;
  const text = rows.map(([k, v]) => `${k}: ${v || "-"}`).join("\n");
  return { html, text };
}
