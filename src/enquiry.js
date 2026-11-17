// POST /api/enquiry: the contact form, the Get started form and the newsletter sign-up.
// Emails each one to the team through Resend, then sends the person an automatic reply.
//
// Cloudflare > Workers & Pages > gcwealth-website > Settings > Variables and secrets:
//   RESEND_API_KEY  your Resend API key (add as a Secret)
//   TO_EMAIL        where enquiries go, comma-separated (set in wrangler.jsonc)
//   FROM_EMAIL      a sender on your verified Resend domain (set in wrangler.jsonc)

import { BRAND, customerEmail, customerSender, detailsTable, overLimit, sendEmail, teamAddresses, validEmail } from "./mail.js";

// Australian mobile, landline, 13/1300/1800, or an overseas number written with + and country code.
// Keep in step with validPhone() in public/assets/js/site.js.
export function validPhone(raw) {
  const n = String(raw).replace(/[\s().-]/g, "");
  return /^(?:\+?610?|0)[23478]\d{8}$/.test(n) || /^1[38]00\d{6}$/.test(n) || /^13\d{4}$/.test(n) ||
    /^\+(?!61)[1-9]\d{7,14}$/.test(n);
}

const TYPES = ["contact", "get-started", "newsletter"];

export async function handleEnquiry(request, env) {
  const wantsJson = (request.headers.get("Accept") || "").includes("application/json");
  const reply = (ok, status, error) =>
    wantsJson
      ? Response.json(ok ? { ok: true } : { ok: false, error }, { status })
      : ok
        ? Response.redirect(new URL("/thanks", request.url).toString(), 303)
        : new Response(`${error || "Something went wrong."} Please go back and try again, or call ${BRAND.phone}.`, {
            status, headers: { "Content-Type": "text/plain; charset=utf-8" },
          });

  let form;
  try {
    form = await request.formData();
  } catch {
    return reply(false, 400, "The form couldn't be read.");
  }

  // Honeypot: bots fill hidden fields. Pretend it worked.
  if (String(form.get("website") || "").trim()) return reply(true, 200);

  const field = (key, max = 500) => String(form.get(key) || "").trim().slice(0, max);
  const type = TYPES.includes(field("type", 20)) ? field("type", 20) : "contact";
  const d = {
    goal: field("goal", 80),
    timeframe: field("timeframe", 60),
    amount: field("amount", 60),
    situation: field("situation", 80),
    name: field("name", 120),
    email: field("email", 200),
    phone: field("phone", 40),
    postcode: field("postcode", 10),
    contact_by: field("contact_by", 30),
    best_time: field("best_time", 60),
    message: field("message", 4000),
    consent: field("consent", 10),
    page: field("page", 200),
  };

  if (!validEmail(d.email)) return reply(false, 422, "Enter a valid email address.");
  if (type !== "newsletter") {
    if (!d.name) return reply(false, 422, "Please add your name.");
    if (!validPhone(d.phone)) return reply(false, 422, "Enter a valid phone number.");
  }
  if (type === "get-started" && d.consent !== "yes") {
    return reply(false, 422, "Please confirm we can contact you about your enquiry.");
  }

  if (!env.RESEND_API_KEY || !env.TO_EMAIL || !env.FROM_EMAIL) return reply(false, 500, "Email isn't set up yet.");
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  if (await overLimit("enquiry-ip", ip, 8, 3600)) return reply(false, 429, "Too many messages from here just now.");
  if (await overLimit("enquiry-email", d.email.toLowerCase(), 4, 3600)) return reply(false, 429, "Too many messages from this email address just now.");

  let team;
  if (type === "newsletter") {
    team = {
      subject: `Newsletter sign-up: ${d.email}`,
      ...detailsTable("Newsletter sign-up (add to the mailing list)", [["Email", d.email], ["Signed up on", d.page]]),
    };
  } else if (type === "get-started") {
    team = {
      subject: `New enquiry: ${d.name}${d.goal ? ", " + d.goal.toLowerCase() : ""}${d.timeframe ? " (" + d.timeframe.toLowerCase() + ")" : ""}`,
      ...detailsTable("Get started enquiry", [
        ["Looking to", d.goal], ["Timeframe", d.timeframe], ["Rough loan amount", d.amount], ["Situation", d.situation],
        ["Name", d.name], ["Email", d.email], ["Phone", d.phone], ["Postcode", d.postcode],
        ["Prefers", d.contact_by], ["Best time", d.best_time], ["Message", d.message], ["Agreed to be contacted", "Yes"],
      ]),
    };
  } else {
    team = {
      subject: `Website message: ${d.name}`,
      ...detailsTable("Contact form message", [["Name", d.name], ["Email", d.email], ["Phone", d.phone], ["Message", d.message], ["Sent from", d.page]]),
    };
  }

  const sent = await sendEmail(env, { from: env.FROM_EMAIL, to: teamAddresses(env), reply_to: d.email, ...team });
  if (!sent) return reply(false, 502, "Your message didn't send.");

  // The automatic reply, so they know it arrived and what happens next. If it fails, the enquiry still went through.
  try {
    await sendEmail(env, autoReply(env, type, d));
  } catch (err) {
    console.error("auto-reply", err);
  }
  return reply(true, 200);
}

export function autoReply(env, type, d) {
  const first = (d.name || "").split(/\s+/)[0];
  let mail;
  if (type === "newsletter") {
    mail = customerEmail({
      heading: "You're on the list",
      paragraphs: [`Thanks for signing up. We'll email you occasional rate updates and finance tips from ${BRAND.name}.`,
        "If you didn't sign up, or change your mind, reply to this email and we'll take you off the list."],
    });
  } else {
    mail = customerEmail({
      heading: `Thanks${first ? ", " + first : ""}. We've got your enquiry.`,
      paragraphs: [
        `A broker will be in touch shortly${{ "Phone call": " by phone", "Email": " by email", "Text message": " by text" }[d.contact_by] || ""}.`,
        "To make the first conversation quicker, it helps to have a rough idea of your income, your regular expenses, any debts, and the property or purchase you have in mind. There's no need to send documents yet.",
      ],
      after: [`If anything changes, reply to this email or call us on ${BRAND.phone}.`],
    });
  }
  return {
    ...customerSender(env),
    to: [d.email],
    subject: type === "newsletter" ? `You're on the ${BRAND.name} list` : `We've got your enquiry`,
    html: mail.html,
    text: mail.text,
  };
}
