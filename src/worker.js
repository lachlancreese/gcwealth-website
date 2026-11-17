// gcwealth.com.au on Cloudflare Workers.
// Pages and /api/* run through here first (see run_worker_first in wrangler.jsonc); /assets/* is served directly.
import { handleEnquiry } from "./enquiry.js";
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
  "/borrowing-capacity-gold-coast-wealth": "/home-loans/pre-approval",
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
  async fetch(request, env) {
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
  },
};
