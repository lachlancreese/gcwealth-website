// GET /api/cash-rate: the latest cash rate target from the Reserve Bank's own table (rba.gov.au/statistics/cash-rate),
// cached for six hours. Always answers 200: { ok: true, rate, effective, rows } or { ok: false } if the RBA page can't be read,
// in which case the site keeps showing the figures in data/rates.json.
const SOURCE = "https://www.rba.gov.au/statistics/cash-rate/";
const MONTHS = { Jan: "January", Feb: "February", Mar: "March", Apr: "April", May: "May", Jun: "June", Jul: "July",
  Aug: "August", Sep: "September", Oct: "October", Nov: "November", Dec: "December" };

export function parseRbaTable(html) {
  const text = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ");
  const rows = [];
  const re = /(\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}) ([+-]?\d+\.\d{2}) (\d+\.\d{2})/g;
  let m;
  while ((m = re.exec(text)) && rows.length < 12) rows.push([m[1], m[2], m[3]]);
  return rows;
}

export async function handleCashRate(request, ctx) {
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const key = new Request(new URL("/api/cash-rate", request.url).toString());
  if (cache) {
    const hit = await cache.match(key);
    if (hit) return hit;
  }
  let body = { ok: false };
  try {
    const res = await fetch(SOURCE, { headers: { "User-Agent": "gcwealth.com.au cash rate check", Accept: "text/html" }, cf: { cacheTtl: 3600 } });
    if (res.ok) {
      const rows = parseRbaTable(await res.text());
      if (rows.length) {
        const [d, , r] = rows[0];
        const [day, mon, year] = d.split(" ");
        body = { ok: true, rate: r, effective: `${day} ${MONTHS[mon]} ${year}`, rows, source: SOURCE };
      }
    }
  } catch (err) {
    console.error("cash rate", err);
  }
  const response = Response.json(body, { headers: { "Cache-Control": `public, max-age=${body.ok ? 21600 : 600}` } });
  if (cache && ctx) ctx.waitUntil(cache.put(key, response.clone()));
  return response;
}
