// GC Wealth calculators. Each calculator is a <form data-calc="name"> with a results panel [data-results].
// Interest rates are never pre-filled: an advertised rate needs a comparison rate (Connective / National Credit Code),
// so the visitor always enters their own. Figures to update each year are in RULES below.
(() => {
  const RULES = {
    // Australian resident tax rates 2026-27 (ATO): [threshold, base tax, marginal rate]
    tax: [[190000, 51370, 0.45], [135000, 31020, 0.37], [45000, 4020, 0.30], [18200, 0, 0.15], [0, 0, 0]],
    medicare: 0.02,
    lito: { max: 700, t1: 37500, r1: 0.05, t2: 45000, r2: 0.015 },
    // HELP (HECS) compulsory repayments 2026-27 (ATO, marginal since 2025-26)
    help: { t1: 69528, t2: 129717, base2: 9028, t3: 186050, r1: 0.15, r2: 0.17, flat: 0.10 },
    buffer: 3,              // APRA serviceability buffer, percentage points
    minAssess: 9.6,         // lowest rate the big four assessed at in Nov 2026 (CBA 6.64% + 3); stops a low rate overstating the result
    cardRate: 0.04,         // monthly commitment per $1 of credit card limit (ANZ's calculator works out at about 3.97%)
    homeLoanLoad: 1.4,      // existing home loan repayments are re-tested at a higher rate (ANZ's calculator: about 1.42x)
    otherLoanLoad: 1.1,     // other loan repayments (ANZ's calculator: about 1.12x)
    margin: 60,             // a month: CBA counts about $50 a month less income than the ATO rates give
    rentShare: 0.8,         // share of rental or other income counted
    // Living costs: lenders use the higher of yours and a benchmark for the household (HEM). These are the highest
    // minimums we measured across CBA, NAB, ANZ and Westpac's calculators in Nov 2026, by gross household income.
    floor: {
      single: [[0, 1400], [60000, 1680], [100000, 2140], [150000, 2870], [250000, 3720], [400000, 4600]],
      couple: [[0, 2400], [100000, 3360], [150000, 4100], [350000, 6270], [500000, 7000]],
      firstChild: 620, eachChild: 480,
    },
    dti: 6,                 // APRA high debt-to-income threshold
    fhog: { amount: 30000, cap: 750000 },
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const num = (el) => {
    if (!el) return 0;
    const v = parseFloat(String(el.value).replace(/[^0-9.\-]/g, ""));
    return Number.isFinite(v) ? v : NaN;
  };
  const val = (form, name) => {
    const el = form.elements[name];
    if (!el) return "";
    return el instanceof RadioNodeList ? el.value : el.value;
  };
  const money = (n) => (n < 0 ? "-" : "") + "$" + Math.round(Math.abs(n)).toLocaleString("en-AU");
  const pct = (n) => n.toFixed(2).replace(/\.?0+$/, "") + "%";
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const duration = (months) => {
    const y = Math.floor(months / 12), m = Math.round(months % 12);
    return [y ? plural(y, "year") : "", m ? plural(m, "month") : ""].filter(Boolean).join(" ") || "0 months";
  };

  // Repayment for principal P at annual rate r% over n years with k payments a year.
  function pmt(P, r, years, k = 12) {
    const i = r / 100 / k, n = Math.round(years * k);
    if (n <= 0) return 0;
    return i === 0 ? P / n : (P * i) / (1 - Math.pow(1 + i, -n));
  }
  // Loan amount a payment supports.
  function pv(payment, r, years, k = 12) {
    const i = r / 100 / k, n = Math.round(years * k);
    return i === 0 ? payment * n : (payment * (1 - Math.pow(1 + i, -n))) / i;
  }
  function incomeTax(income) {
    if (income <= 0) return 0;
    const [t, base, rate] = RULES.tax.find(([th]) => income > th);
    let tax = base + (income - t) * rate;
    const L = RULES.lito;
    let lito = income <= L.t1 ? L.max : income <= L.t2 ? L.max - (income - L.t1) * L.r1 : Math.max(0, L.max - (L.t2 - L.t1) * L.r1 - (income - L.t2) * L.r2);
    tax = Math.max(0, tax - lito);
    return tax + income * RULES.medicare;
  }

  function helpRepay(income) {
    const H = RULES.help;
    if (income <= H.t1) return 0;
    if (income <= H.t2) return (income - H.t1) * H.r1;
    if (income <= H.t3) return H.base2 + (income - H.t2) * H.r2;
    return income * H.flat;
  }
  function interp(points, x) {
    if (x <= points[0][0]) return points[0][1];
    for (let i = 1; i < points.length; i++) {
      const [x1, y1] = points[i];
      if (x <= x1) { const [x0, y0] = points[i - 1]; return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0); }
    }
    return points[points.length - 1][1];
  }
  // The least a lender will assume a household spends each month.
  function livingFloor(two, deps, grossIncome) {
    const F = RULES.floor;
    return interp(two ? F.couple : F.single, grossIncome) + (deps > 0 ? F.firstChild + (deps - 1) * F.eachChild : 0);
  }
  // Borrowing power the way the big four's calculators work: income after tax and HELP, less the higher of
  // stated and benchmark living costs, less commitments, tested at the rate plus the buffer.
  function borrow(o) {
    const two = !!o.two, deps = o.deps || 0;
    const inc1 = o.inc1 || 0, inc2 = two ? o.inc2 || 0 : 0, other = o.other || 0;
    const rentYear = o.invest ? (o.rentWeek || 0) * 52 : 0;
    const taxable1 = inc1 + other * RULES.rentShare;
    const net1 = taxable1 - incomeTax(taxable1) - (o.help1 ? helpRepay(taxable1) : 0);
    const net2 = inc2 ? inc2 - incomeTax(inc2) - (o.help2 ? helpRepay(inc2) : 0) : 0;
    const rentCounted = (rentYear * RULES.rentShare) / 12;  // interest deductions usually cover the tax on it
    const net = (net1 + net2) / 12 + rentCounted - RULES.margin;
    const gross = inc1 + inc2 + other + rentYear;
    const floor = livingFloor(two, deps, gross);
    const living = Math.max(o.expenses || 0, floor);
    const commitments = (o.homeLoans || 0) * RULES.homeLoanLoad + (o.otherLoans || 0) * RULES.otherLoanLoad + (o.cards || 0) * RULES.cardRate;
    const surplus = net - living - commitments;
    const assess = Math.max(o.rate + RULES.buffer, RULES.minAssess);
    const loan = surplus > 0 ? Math.floor(pv(surplus, assess, o.years || 30) / 1000) * 1000 : 0;
    return { loan, assess, net, living, floor, usedFloor: floor > (o.expenses || 0), rentCounted, surplus, gross };
  }

  // Stamp duty for every state and territory. Rate schedules come from data/stamp-duty.json, which the build
  // embeds in the page; first home buyer rules are below. Both are checked against published examples in tests/check.py.
  const DUTY = (() => {
    const el = document.getElementById("duty-data");
    try { return el ? JSON.parse(el.textContent) : null; } catch (e) { return null; }
  })();
  function schedule(brackets, v, round) {
    for (const b of brackets) {
      if (b.to !== null && v > b.to) continue;
      if (b.formula === "nt") { const k = v / 1000; return 0.06571441 * k * k + 15 * k; }  // NT, up to $525,000
      if (b.flat != null) return (v * b.flat) / 100;
      const excess = Math.max(0, v - b.over);
      const units = round === "part" ? Math.ceil(excess / 100) : excess / 100;  // "per $100 or part of $100"
      return Math.max(b.min || 0, b.base + units * b.rate);
    }
    return 0;
  }
  // Queensland first home concession on an established home: full to $700,000, then reducing in steps to nil at $800,000.
  function firstHomeDeduction(v) {
    if (v < 710000) return 17350;
    if (v >= 800000) return 0;
    return 17350 - Math.floor((v - 700000) / 10000) * 1735;
  }
  function dutyFor(code, v, o) {
    const S = DUTY.states[code];
    const general = schedule(S.general, v, S.round);
    const r = (duty, basis) => ({ duty, basis, general });
    if (!o.home) return r(general, "Standard rates (investment)");
    const ownerOk = !!S.owner && (S.owner_max == null || v <= S.owner_max) && (!S.owner_needs_residency || o.eligible);
    const owner = ownerOk ? schedule(S.owner, v, S.round) : general;
    const ownerBasis = !ownerOk ? "Standard rates" : code === "VIC" ? "Principal place of residence rates" : code === "QLD" ? "Home concession rates" : "Owner-occupier rates";
    if (code === "QLD" && o.kind === "land" && !(o.first && o.eligible)) return r(general, "Standard rates (the home concession doesn't apply to vacant land unless it's for your first home)");
    if (!o.first) return r(owner, ownerBasis);
    if (!o.eligible) return r(owner, "Standard rates (first home concessions need Australian citizenship or permanent residency)");
    const per100 = (x) => (S.round === "part" ? Math.ceil(Math.max(0, x) / 100) : Math.max(0, x) / 100);
    switch (S.fhb) {
      case "nsw":  // First Home Buyers Assistance Scheme: nil to $800,000, rising in a straight line to full duty at $1,000,000
        if (v <= 800000) return r(0, "First Home Buyers Assistance Scheme: no duty up to $800,000");
        if (v < 1000000) return r((per100(v - 800000) * schedule(S.general, 1000000, S.round)) / 2000, "First Home Buyers Assistance Scheme concession");
        break;
      case "vic":  // nil to $600,000, then the saving reduces in a straight line to nil at $750,000
        if (v <= 600000) return r(0, "First home buyer exemption: no duty up to $600,000");
        if (v <= 750000) return r(owner - (owner * (750000 - v)) / 150000, "First home buyer concession");
        break;
      case "qld":
        if (o.kind === "new") return r(0, "First home (new home) concession: duty reduced to nil");
        if (o.kind === "land") return r(0, "First home vacant land concession: duty reduced to nil");
        return r(Math.max(0, owner - firstHomeDeduction(v)), "First home concession (established home)");
      case "wa":   // first home owner rate from 7 May 2026: nil to $600,000, then $16.15 per $100 above $600,000 to $800,000
        if (v <= 600000) return r(0, "First home owner rate: no duty up to $600,000");
        if (v <= 800000) return r(Math.min(general, per100(v - 600000) * 16.15), "First home owner rate of duty");
        break;
      case "sa":   // relief for new homes only, no price cap
        if (o.kind === "new") return r(0, "First home buyer relief on a new home: no duty");
        return r(owner, "Standard rates (first home relief is for new homes only)");
      case "act":  // Home Buyer Concession Scheme from 1 July 2026: no duty, no income test or price cap
        return r(0, "Home Buyer Concession Scheme: no duty");
      default:
        return r(owner, `Standard rates (no first home buyer duty concession in ${S.name})`);
    }
    return r(owner, ownerBasis + " (above the first home buyer limit)");
  }

  function setOut(panel, key, text) {
    const el = panel.querySelector(`[data-out="${key}"]`);
    if (el) el.textContent = text;
  }
  function show(panel, key, on) {
    panel.querySelectorAll(`[data-show="${key}"]`).forEach((el) => { el.hidden = !on; });
  }
  function empty(panel, message) {
    panel.setAttribute("data-empty", "");
    setOut(panel, "main", message);
    panel.querySelectorAll("[data-detail]").forEach((el) => { el.hidden = true; });
  }
  function ready(panel) {
    panel.removeAttribute("data-empty");
    panel.querySelectorAll("[data-detail]").forEach((el) => { el.hidden = false; });
  }
  function cta(panel, goal, amount) {
    const a = panel.querySelector("[data-cta]");
    if (!a) return;
    const q = new URLSearchParams();
    if (goal) q.set("goal", goal);
    if (amount) q.set("amount", amount);
    a.href = "/get-started" + (q.toString() ? "?" + q : "");
  }
  const band = (n) => n < 500000 ? "Under $500,000" : n < 750000 ? "$500,000 to $750,000" : n < 1000000 ? "$750,000 to $1 million" : n < 2000000 ? "$1 million to $2 million" : "Over $2 million";
  const needRate = "Enter an interest rate to see your results";

  const CALCS = {
    repayments(form, panel) {
      const P = num(form.elements.amount), r = num(form.elements.rate), years = num(form.elements.years);
      const freq = val(form, "frequency"), type = val(form, "type");
      const io = type === "io";
      form.querySelectorAll("[data-io]").forEach((el) => { el.hidden = !io; });
      if (!(r > 0)) return empty(panel, needRate);
      if (!(P > 0) || !(years > 0)) return empty(panel, "Enter a loan amount and term");
      ready(panel);
      const k = { monthly: 12, fortnightly: 26, weekly: 52 }[freq] || 12;
      const label = { 12: "per month", 26: "per fortnight", 52: "per week" }[k];
      // Interest only for a set period, then principal and interest over what's left of the term.
      const ioYears = io ? Math.min(Math.max(num(form.elements.ioyears) || 0, 0), years - 1) : 0;
      const rest = years - ioYears;
      const pay = (rate) => (io && ioYears > 0 ? (P * rate) / 100 / k : pmt(P, rate, years, k));
      const repayment = pay(r);
      const after = io && ioYears > 0 ? pmt(P, r, rest, k) : repayment;
      const total = io && ioYears > 0 ? repayment * k * ioYears + after * k * rest : repayment * k * years;
      const interest = total - P;
      setOut(panel, "main", money(repayment));
      setOut(panel, "sub", `${label}, ${io && ioYears > 0 ? `interest only for ${plural(ioYears, "year")}` : "principal and interest"}`);
      setOut(panel, "interest", money(interest));
      setOut(panel, "total", money(total));
      setOut(panel, "rise1", "+" + money(pay(r + 0.25) - repayment) + " " + label.replace("per ", "a "));
      setOut(panel, "rise2", "+" + money(pay(r + 1) - repayment) + " " + label.replace("per ", "a "));
      const share = Math.min(100, Math.max(0, (P / total) * 100));
      panel.querySelector(".bar .a").style.width = share + "%";
      panel.querySelector(".bar .b").style.width = 100 - share + "%";
      show(panel, "io-note", io && ioYears > 0);
      setOut(panel, "io-years", plural(ioYears, "year"));
      setOut(panel, "io-after", money(after) + " " + label);
      setOut(panel, "io-rest", plural(rest, "year"));
      cta(panel, "Buy my next home", band(P));
    },

    "borrowing-power"(form, panel) {
      const two = val(form, "applicants") === "2", invest = val(form, "purpose") === "invest";
      form.querySelectorAll("[data-second]").forEach((el) => { el.hidden = !two; });
      form.querySelectorAll("[data-invest]").forEach((el) => { el.hidden = !invest; });
      const r = num(form.elements.rate), expenses = num(form.elements.expenses);
      const o = {
        two, invest, deps: parseInt(val(form, "deps"), 10) || 0,
        inc1: num(form.elements.income1) || 0, inc2: num(form.elements.income2) || 0, other: num(form.elements.other) || 0,
        help1: form.elements.help1.checked, help2: form.elements.help2.checked,
        rentWeek: num(form.elements.rent) || 0, expenses: expenses || 0,
        homeLoans: num(form.elements.homeloans) || 0, otherLoans: num(form.elements.commitments) || 0, cards: num(form.elements.cards) || 0,
        rate: r, years: num(form.elements.years) || 30,
      };
      if (!(r > 0)) return empty(panel, needRate);
      if (!(o.inc1 + (two ? o.inc2 : 0) > 0) || Number.isNaN(expenses)) return empty(panel, "Enter your income and monthly living expenses");
      ready(panel);
      const res = borrow(o);
      setOut(panel, "main", res.loan > 0 ? money(res.loan) : "$0");
      setOut(panel, "sub", res.loan > 0 ? (invest ? "estimated borrowing power for an investment" : "estimated borrowing power") : "Your expenses and commitments use up your income at the assessment rate");
      setOut(panel, "assess", pct(res.assess));
      setOut(panel, "repay", money(pmt(res.loan, r, o.years)) + " a month");
      setOut(panel, "net", money(res.net) + " a month");
      setOut(panel, "living", money(res.living) + " a month");
      setOut(panel, "rent", money(res.rentCounted) + " a month");
      show(panel, "rent-row", invest);
      setOut(panel, "surplus", money(res.surplus) + " a month");
      show(panel, "floor-note", res.usedFloor);
      setOut(panel, "floor", money(res.floor));
      show(panel, "invest-note", invest);
      const dti = res.gross > 0 ? (res.loan + o.cards) / res.gross : 0;
      show(panel, "dti-note", dti >= RULES.dti);
      setOut(panel, "dti", dti.toFixed(1));
      cta(panel, invest ? "Buy an investment property" : "Buy my first home", res.loan > 0 ? band(res.loan) : "");
    },

    "extra-repayments"(form, panel) {
      const P = num(form.elements.balance), r = num(form.elements.rate), years = num(form.elements.years);
      const extra = num(form.elements.extra) || 0, lump = num(form.elements.lump) || 0, offset = num(form.elements.offset) || 0;
      if (!(r > 0)) return empty(panel, needRate);
      if (!(P > 0) || !(years > 0)) return empty(panel, "Enter your loan balance and remaining term");
      ready(panel);
      const i = r / 100 / 12, base = pmt(P, r, years);
      const run = (withExtras) => {
        let bal = P - (withExtras ? lump : 0), months = 0, interest = 0;
        while (bal > 0.005 && months < 1200) {
          const charged = Math.max(0, bal - (withExtras ? offset : 0)) * i;
          interest += charged;
          bal = bal + charged - base - (withExtras ? extra : 0);
          months++;
        }
        return { months, interest };
      };
      const a = run(false), b = run(true);
      const saved = Math.max(0, a.interest - b.interest), sooner = Math.max(0, a.months - b.months);
      setOut(panel, "main", money(saved));
      setOut(panel, "sub", "less interest over the life of the loan");
      setOut(panel, "sooner", duration(sooner));
      setOut(panel, "payoff", duration(b.months));
      setOut(panel, "repay", money(base) + " a month");
      setOut(panel, "base-interest", money(a.interest));
      setOut(panel, "new-interest", money(b.interest));
      cta(panel, "Refinance", band(P));
    },

    refinance(form, panel) {
      const P = num(form.elements.balance), r1 = num(form.elements.current), r2 = num(form.elements.newrate);
      const years = num(form.elements.years), costs = num(form.elements.costs) || 0;
      if (!(r1 > 0) || !(r2 > 0)) return empty(panel, "Enter your current rate and the new rate to compare");
      if (!(P > 0) || !(years > 0)) return empty(panel, "Enter your loan balance and remaining term");
      ready(panel);
      const now = pmt(P, r1, years), next = pmt(P, r2, years), diff = now - next;
      const lifetime = diff * 12 * years - costs;
      setOut(panel, "main", diff > 0 ? money(diff) : "$0");
      setOut(panel, "sub", diff > 0 ? "lower repayments a month" : "Switching wouldn't lower your repayments at these rates");
      setOut(panel, "now", money(now) + " a month");
      setOut(panel, "next", money(next) + " a month");
      setOut(panel, "breakeven", diff > 0 ? (costs > 0 ? duration(Math.ceil(costs / diff)) : "Straight away") : "Not reached");
      setOut(panel, "lifetime", money(lifetime));
      cta(panel, "Refinance", band(P));
    },

    "stamp-duty"(form, panel) {
      if (!DUTY) return empty(panel, "The calculator couldn't load. Please refresh the page.");
      const code = val(form, "state") || "QLD", S = DUTY.states[code];
      const v = num(form.elements.price);
      const home = val(form, "purpose") === "home";
      const first = home && val(form, "first") === "yes";
      const kinds = S.kinds || [];
      const landLabel = form.querySelector('[data-kind="land"]');
      if (landLabel) landLabel.hidden = !kinds.includes("land");
      if (!kinds.includes(val(form, "kind"))) form.elements.kind[0].checked = true;
      const kind = val(form, "kind");
      const eligible = form.elements.resident.checked;
      form.querySelectorAll("[data-home-only]").forEach((el) => { el.hidden = !home; });
      form.querySelectorAll("[data-kind-only]").forEach((el) => { el.hidden = !(first && kinds.length); });
      const label = form.querySelector("[data-first-label]");
      if (label) label.textContent = code === "ACT" ? "First home, or no property owned in the last five years?" : "Is it your first home?";
      if (!(v > 0)) return empty(panel, "Enter the purchase price");
      ready(panel);
      const res = dutyFor(code, v, { home, first, kind, eligible });
      const others = ["legal", "inspections", "lender", "other"].reduce((t, n) => t + (num(form.elements[n]) || 0), 0);
      setOut(panel, "main", money(res.duty));
      setOut(panel, "sub", `estimated ${S.name} ${S.term}`);
      setOut(panel, "basis", res.basis);
      setOut(panel, "general", money(res.general));
      setOut(panel, "others", money(others));
      setOut(panel, "total", money(res.duty + others));
      const note = panel.querySelector('[data-out="note"]');
      const page = `/calculators/stamp-duty/${S.slug}`;
      if (note) {
        note.hidden = location.pathname === page;
        note.innerHTML = `<a href="${page}" style="color:#fff">${S.short} rates and concessions in full</a>`;
      }
      const grant = first && eligible && kind === "new" && !!S.grant && v < RULES.fhog.cap;
      setOut(panel, "grant", S.grant || "");
      show(panel, "grant", grant);
      cta(panel, first ? "Buy my first home" : home ? "Buy my next home" : "Buy an investment property", band(v * 0.8));
    },

    deposit(form, panel) {
      const price = num(form.elements.price), share = parseFloat(val(form, "share")) || 20;
      const saved = num(form.elements.saved) || 0, monthly = num(form.elements.monthly) || 0, costs = num(form.elements.costs) || 0;
      if (!(price > 0)) return empty(panel, "Enter the property price you're aiming for");
      ready(panel);
      // Stamp duty on an established home to live in, with first home concessions where they apply.
      const code = form.elements.state ? form.elements.state.value : "";
      const first = val(form, "first") !== "no";
      const duty = DUTY && DUTY.states[code] ? dutyFor(code, price, { home: true, first, kind: "established", eligible: true }).duty : 0;
      const deposit = (price * share) / 100, target = deposit + duty + costs, gap = Math.max(0, target - saved);
      setOut(panel, "main", gap === 0 ? "You're there" : monthly > 0 ? duration(Math.ceil(gap / monthly)) : "Add a monthly amount");
      setOut(panel, "sub", gap === 0 ? "your savings cover this deposit and costs" : "to reach your deposit and costs");
      setOut(panel, "deposit", money(deposit));
      setOut(panel, "duty", money(duty));
      setOut(panel, "costs", money(costs));
      setOut(panel, "target", money(target));
      setOut(panel, "gap", money(gap));
      setOut(panel, "loan", money(price - deposit));
      const link = panel.querySelector('[data-out-href="duty-link"]');
      if (link && DUTY && DUTY.states[code]) link.href = `/calculators/stamp-duty/${DUTY.states[code].slug}`;
      show(panel, "lmi-note", share < 20);
      cta(panel, first ? "Buy my first home" : "Buy my next home", band(price - deposit));
    },
  };

  document.querySelectorAll("form[data-calc]").forEach((form) => {
    const fn = CALCS[form.dataset.calc];
    const panel = document.getElementById(form.dataset.results);
    if (!fn || !panel) return;
    const update = () => fn(form, panel);
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    form.addEventListener("submit", (e) => { e.preventDefault(); update(); panel.scrollIntoView({ behavior: "smooth", block: "start" }); });
    update();
  });

  // Exposed for tests (tests/check.py checks the duty and tax maths against published examples).
  window.GCW_CALC = { duty: (code, v, o) => dutyFor(code, v, o).duty, schedule, firstHomeDeduction, incomeTax, pmt, helpRepay, livingFloor, borrow };
})();
