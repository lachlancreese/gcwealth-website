// Shows the latest RBA cash rate. The page is built with the figure in data/rates.json; this asks the Worker
// (/api/cash-rate, which reads the RBA's own table) whether there's a newer decision and updates the page if so.
(async () => {
  // Hide the "next decision" date once it has passed (until data/rates.json is updated).
  document.querySelectorAll("[data-next-decision]").forEach((el) => {
    const due = new Date(el.dataset.nextDecision + "T23:59:59+10:00");
    if (Date.now() > due.getTime()) el.hidden = true;
  });
  try {
    const res = await fetch("/api/cash-rate", { headers: { Accept: "application/json" } });
    const data = await res.json();
    if (!data.ok || !data.rate) return;
    document.querySelectorAll("[data-cash-rate]").forEach((el) => {
      const small = el.querySelector("small");
      el.textContent = data.rate;
      if (small) el.appendChild(small);
    });
    document.querySelectorAll("[data-cash-effective]").forEach((el) => { el.textContent = data.effective; });
    const tbody = document.querySelector("[data-cash-rate-table] tbody");
    if (tbody && Array.isArray(data.rows) && data.rows.length) {
      tbody.replaceChildren(...data.rows.slice(0, 8).map(([d, c, r]) => {
        const tr = document.createElement("tr");
        [d, c, r + "%"].forEach((t) => { const td = document.createElement("td"); td.textContent = t; tr.appendChild(td); });
        return tr;
      }));
    }
  } catch {
    // Keep the published figures if the check fails.
  }
})();
