// gcwealth.com.au on Cloudflare Workers.
// Pages and /api/* run through here first (see run_worker_first in wrangler.jsonc); /assets/* is served directly.
import { handleEnquiry } from "./enquiry.js";
import { handleCashRate } from "./cash-rate.js";
import brand from "../brand.json";

const HOST = new URL(brand.site).hostname;

// Old Elementor addresses, sent permanently to their new pages so links and search rankings carry over.
// Calculator and guide addresses are added when those pages are built (phases 3 and 4).
const MOVED = {
  "/home": "/",
  "/global-styles": "/",
  "/services": "/home-loans",
  "/knowledge": "/",
  "/contact-us": "/contact",
  "/privacy-policy": "/privacy",
  "/complaints-handling-process": "/compliments-and-concerns",
  "/complaints": "/compliments-and-concerns",
  "/why-gold-coast-wealth": "/about",
  "/construction-lending-qld": "/home-loans/construction-loans",
  "/bridging-loans": "/home-loans/bridging-loans",
  "/refinancing": "/home-loans/refinancing",
  "/pre-approval": "/home-loans/pre-approval",
  "/smsf-refinancing": "/smsf-loans",
  "/home-loan-process": "/home-loans",
  "/borrowing-capacity-gold-coast-wealth": "/calculators/borrowing-power",
  "/calculators/borrowing-power": "/calculators/borrowing-power",
  "/calculators/repayment-calculator": "/calculators/repayments",
  "/calculators/fortnightly-repayment": "/calculators/repayments",
  "/calculators/interest-only": "/calculators/repayments",
  "/calculators/split-loan": "/calculators/repayments",
  "/calculators/introductory-rate": "/calculators/repayments",
  "/calculators/comparison-rate": "/calculators/repayments",
  "/calculators/budget-planner": "/calculators/borrowing-power",
  "/calculators/income-tax": "/calculators/borrowing-power",
  "/calculators/income-annualisation": "/calculators/borrowing-power",
  "/calculators/income-gross-up": "/calculators/borrowing-power",
  "/calculators/extra-repayments": "/calculators/extra-repayments",
  "/calculators/offset-account": "/calculators/extra-repayments",
  "/calculators/lump-sum-repayment": "/calculators/extra-repayments",
  "/calculators/how-long-to-repay-calculator": "/calculators/extra-repayments",
  "/calculators/refinancing-savings": "/calculators/refinance",
  "/calculators/loan-comparison-calculator": "/calculators/refinance",
  "/calculators/stamp-duty": "/calculators/stamp-duty",
  "/calculators/property-buying-cost": "/calculators/stamp-duty",
  "/calculators/property-selling-cost": "/calculators",
  "/calculators/savings-goal": "/calculators/deposit",
  "/calculators/saving": "/calculators/deposit",
  "/calculators/compound-interest": "/calculators/deposit",
  "/calculators/how-much-to-deposit": "/calculators/deposit",
  "/calculators/rent-vs-buy": "/calculators/deposit",
  "/calculators/credit-card": "/calculators",
  "/calculators/reverse-mortgage": "/calculators",
  "/calculators/asset-leasing": "/business-finance/asset-finance",
  "/first-home-buyers": "/home-loans/first-home-buyers",
  "/investment-property": "/home-loans/investment-loans",
  "/construction-loans": "/home-loans/construction-loans",
  "/commercial-property": "/business-finance/commercial-property",
  "/business-loans": "/business-finance/business-loans",
  "/asset-finance": "/business-finance/asset-finance",
};
// Old archive pages (/tag/..., /category/..., /author/...) all go to the homepage for now.
const MOVED_PREFIX = [["/tag/", "/"], ["/category/", "/"], ["/author/", "/"]];

function redirect(url, status = 301) {
  return new Response(null, { status, headers: { Location: url, "Cache-Control": "public, max-age=3600" } });
}

export default {
  async fetch(request, env, ctx) {
    const res = await handle(request, env, ctx);
    if (new URL(request.url).hostname === HOST) return res;
    // Preview addresses (e.g. *.workers.dev before the domain moves) stay out of search results.
    const out = new Response(res.body, res);
    out.headers.set("X-Robots-Tag", "noindex, nofollow");
    return out;
  },
};

async function handle(request, env, ctx) {
    const url = new URL(request.url);

    // One address for everything: https://gcwealth.com.au (www and plain http redirect here).
    if (url.hostname === "www." + HOST || (url.hostname === HOST && url.protocol === "http:")) {
      url.hostname = HOST;
      url.protocol = "https:";
      url.port = "";
      return redirect(url.toString());
    }

    if (url.pathname === "/api/enquiry") {
      if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers: { Allow: "POST" } });
      return handleEnquiry(request, env);
    }

    if (url.pathname === "/api/cash-rate") return handleCashRate(request, ctx);

    if (request.method === "GET" || request.method === "HEAD") {
      // Tidy addresses: no trailing slash, no ".html", no "/index".
      let path = url.pathname;
      if (path.length > 1 && path.endsWith("/")) path = path.replace(/\/+$/, "");
      if (path.endsWith(".html")) path = path.slice(0, -5);
      if (path === "/index") path = "/";
      const lower = path.toLowerCase();
      const moved = MOVED[lower] || (MOVED_PREFIX.find(([p]) => lower.startsWith(p)) || [])[1];
      if (moved) path = moved;
      if (path !== url.pathname) {
        url.pathname = path;
        url.search = moved ? "" : url.search;
        return redirect(url.toString());
      }
    }

    return env.ASSETS.fetch(request);
}
