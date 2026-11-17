// GC Wealth: menu, footer year, and the enquiry forms (contact, get started, newsletter).
// Every form works without JavaScript (it posts to /api/enquiry and lands on /thanks); this adds steps,
// friendlier error messages and sending without leaving the page.
document.documentElement.classList.add("js");

(() => {
  const btn = document.querySelector(".menu-btn");
  const links = document.getElementById("nav-links");
  if (btn && links) {
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      links.classList.toggle("open", open);
    });
  }
  document.querySelectorAll(".sub-btn").forEach((b) => {
    b.addEventListener("click", () => {
      const li = b.closest(".has-sub");
      const open = !li.classList.contains("open");
      document.querySelectorAll(".has-sub.open").forEach((o) => { if (o !== li) { o.classList.remove("open"); o.querySelector(".sub-btn").setAttribute("aria-expanded", "false"); } });
      li.classList.toggle("open", open);
      b.setAttribute("aria-expanded", String(open));
    });
  });
  // Desktop hover menus. Opening is instant; closing waits a moment, and moving across to the next
  // heading waits a beat too, so cutting a corner on the way down to a link doesn't swap or shut the menu.
  const desk = matchMedia("(hover: hover) and (min-width: 1081px)");
  const subs = [...document.querySelectorAll(".has-sub")];
  const setOpen = (li, open) => { li.classList.toggle("open", open); li.querySelector(".sub-btn").setAttribute("aria-expanded", String(open)); };
  let closeT, switchT;
  subs.forEach((li) => {
    li.addEventListener("pointerenter", (e) => {
      if (e.pointerType !== "mouse" || !desk.matches) return;
      clearTimeout(closeT); clearTimeout(switchT);
      const go = () => { subs.forEach((o) => { if (o !== li) setOpen(o, false); }); setOpen(li, true); };
      if (subs.some((o) => o !== li && o.classList.contains("open"))) switchT = setTimeout(go, 150); else go();
    });
    li.addEventListener("pointerleave", (e) => {
      if (e.pointerType !== "mouse" || !desk.matches) return;
      clearTimeout(switchT);
      closeT = setTimeout(() => subs.forEach((o) => setOpen(o, false)), 400);
    });
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".has-sub")) subs.forEach((o) => { if (o.classList.contains("open")) setOpen(o, false); });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".has-sub.open").forEach((o) => { o.classList.remove("open"); o.querySelector(".sub-btn").setAttribute("aria-expanded", "false"); });
    if (btn && btn.getAttribute("aria-expanded") === "true") { btn.click(); btn.focus(); }
  });
  document.querySelectorAll(".year").forEach((el) => { el.textContent = new Date().getFullYear(); });
})();

// Australian mobile, landline, 13/1300/1800, or an overseas number with + and country code.
// Keep in step with validPhone() in src/enquiry.js.
function validPhone(raw) {
  const n = String(raw).replace(/[\s().-]/g, "");
  return /^(?:\+?610?|0)[23478]\d{8}$/.test(n) || /^1[38]00\d{6}$/.test(n) || /^13\d{4}$/.test(n) || /^\+(?!61)[1-9]\d{7,14}$/.test(n);
}
const validEmail = (s) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(s).trim());

function setError(input, message) {
  const id = input.id + "-error";
  let msg = document.getElementById(id);
  if (!message) {
    input.removeAttribute("aria-invalid");
    if (msg) msg.remove();
    return true;
  }
  input.setAttribute("aria-invalid", "true");
  if (!msg) {
    msg = document.createElement("p");
    msg.className = "field-error";
    msg.id = id;
    input.insertAdjacentElement("afterend", msg);
    input.setAttribute("aria-describedby", id);
  }
  msg.textContent = message;
  return false;
}

function checkFields(scope) {
  let first = null;
  scope.querySelectorAll("input, textarea, select").forEach((el) => {
    if (el.closest(".hp") || el.type === "hidden" || el.type === "radio") return;
    let message = "";
    const value = el.type === "checkbox" ? el.checked : el.value.trim();
    if (el.required && !value) {
      message = el.type === "checkbox" ? "Please tick this box to continue." : "Please fill this in.";
    } else if (el.type === "email" && value && !validEmail(value)) {
      message = "Enter an email address like name@example.com.";
    } else if (el.type === "tel" && value && !validPhone(value)) {
      message = "Enter an Australian phone number, like 0412 345 678.";
    }
    if (!setError(el, message) && !first) first = el;
  });
  if (first) first.focus();
  return !first;
}

document.querySelectorAll("form[data-ajax]").forEach((form) => {
  const status = form.querySelector(".form-status");
  const steps = [...form.querySelectorAll(".step")];
  const stepper = form.parentElement.querySelector(".stepper");
  let current = 0;

  const show = (i) => {
    current = i;
    steps.forEach((s, n) => { s.hidden = n !== i; });
    if (stepper) {
      [...stepper.children].forEach((li, n) => {
        li.classList.toggle("done", n < i);
        li.classList.toggle("current", n === i);
        if (n === i) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
      });
    }
  };
  if (steps.length > 1) {
    show(0);
    form.querySelectorAll("[data-next]").forEach((b) => b.addEventListener("click", () => {
      if (!checkFields(steps[current])) return;
      show(current + 1);
      const h = steps[current].querySelector("h2");
      if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
    }));
    form.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => show(current - 1)));
    // Picking an answer on the first step moves straight on.
    steps[0].querySelectorAll('input[type="radio"]').forEach((r) => r.addEventListener("change", () => {
      if (r.name === "goal") setTimeout(() => form.querySelector("[data-next]").click(), 150);
    }));
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!checkFields(form)) return;
    const button = form.querySelector('button[type="submit"]');
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Sending…";
    if (status) { status.textContent = ""; status.className = "form-status"; }
    try {
      const res = await fetch(form.action, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" } });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) throw new Error(data.error || "Your message didn't send.");
      if (form.dataset.done) { window.location.href = form.dataset.done; return; }
      form.reset();
      if (status && form.dataset.download) {
        status.className = "form-status ok";
        status.textContent = "Done. We've emailed you the guide. ";
        const a = document.createElement("a");
        a.href = form.dataset.download;
        a.textContent = "Download it now";
        status.appendChild(a);
      } else if (status) { status.textContent = "Thanks, you're on the list."; status.className = "form-status ok"; }
    } catch (err) {
      if (status) {
        status.textContent = `${err.message} Please try again, or call ${form.dataset.phone || "us"}.`;
        status.className = "form-status error";
      }
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  });
});

// Get started can be opened from a calculator with ?goal=...&amount=... to save the visitor retyping.
(() => {
  const form = document.getElementById("start-form");
  if (!form) return;
  const q = new URLSearchParams(location.search);
  const goal = q.get("goal"), amount = q.get("amount"), broker = q.get("broker");
  // From a broker's profile: "Talk to Steven" passes ?broker=steven-shaw, which is sent with the enquiry.
  let names = {};
  try { names = JSON.parse(form.elements.broker.dataset.names || "{}"); } catch (e) {}
  if (broker && Object.prototype.hasOwnProperty.call(names, broker)) {
    form.elements.broker.value = names[broker];
    const lede = document.querySelector(".lede");
    if (lede) lede.textContent = `Three quick steps. Tell us what you're planning and ${form.elements.broker.value.split(" ")[0]} will be in touch to talk it through.`;
  }
  if (goal) {
    const radio = [...form.querySelectorAll('input[name="goal"]')].find((r) => r.value === goal);
    if (radio) radio.checked = true;
  }
  if (amount) {
    const opt = [...form.querySelectorAll("#s-amount option")].find((o) => o.textContent === amount);
    if (opt) opt.selected = true;
  }
})();

// Team page: "Who should I talk to?" shows the brokers who focus on the chosen need.
(() => {
  const box = document.querySelector("[data-matcher]");
  if (!box) return;
  box.hidden = false;
  const note = box.querySelector(".match-note");
  box.addEventListener("change", (e) => {
    if (e.target.name !== "need") return;
    let shown;
    box.querySelectorAll(".match").forEach((m) => { m.hidden = m.dataset.need !== e.target.value; if (!m.hidden) shown = m; });
    note.hidden = false;
    // On a phone the results can sit below the options; bring them into view.
    if (shown && shown.getBoundingClientRect().top > window.innerHeight - 120) {
      const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      shown.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
    }
  });
})();

// Homepage skyline: on a desktop, the layers shift at different depths as the cursor moves.
(() => {
  const hero = document.querySelector(".hero");
  const layers = hero ? [...hero.querySelectorAll(".coast .layer")] : [];
  if (!layers.length) return;
  if (!window.matchMedia("(pointer: fine)").matches || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let frame = 0, mx = 0, my = 0;
  const apply = () => {
    frame = 0;
    layers.forEach((el) => {
      const d = parseFloat(el.dataset.depth) || 0;
      // Towers only move sideways so they stay on the waterline; the sky drifts a little up and down too.
      el.style.transform = `translate(${(-mx * d * 14).toFixed(2)}px, ${d < 0.5 ? (-my * 6 * (1 - d)).toFixed(2) : 0}px)`;
    });
  };
  hero.addEventListener("pointermove", (e) => {
    const r = hero.getBoundingClientRect();
    mx = ((e.clientX - r.left) / r.width - 0.5) * 2;
    my = ((e.clientY - r.top) / r.height - 0.5) * 2;
    if (!frame) frame = requestAnimationFrame(apply);
  });
  hero.addEventListener("pointerleave", () => { mx = 0; my = 0; if (!frame) frame = requestAnimationFrame(apply); });
})();

// Broker profiles: "Get in touch" starts a text or email for the visitor, worded for what they choose.
// Nothing is sent through the site: the links open the visitor's own messages or email app.
document.querySelectorAll("[data-contact]").forEach((box) => {
  const first = box.dataset.first;
  const sms = box.querySelector("[data-sms]");
  const mail = box.querySelector("[data-mail]");
  const nameInput = box.querySelector("#cb-name");
  const update = () => {
    const name = (nameInput.value || "").replace(/[^\p{L}\p{M}' -]/gu, "").trim().slice(0, 40);
    const picked = box.querySelector('input[name="cb-topic"]:checked');
    const topic = picked ? picked.value : "my finances";
    const label = picked ? picked.dataset.label : "";
    const hi = `Hi ${first}, ` + (name ? `it's ${name}. ` : "");
    const text = `${hi}I found you on the GC Wealth website and I'd like to talk about ${topic}. When's a good time for a quick chat?`;
    const subject = "Enquiry from the GC Wealth website" + (label ? `: ${label}` : "");
    const body = `Hi ${first},\n\nI found you on the GC Wealth website and I'd like to talk about ${topic}.\n\n` +
      `A bit about what I'm after:\n\n\nThe best way and time to reach me:\n\n\nThanks,\n${name}`;
    if (sms) sms.href = `${sms.href.split("?")[0]}?&body=${encodeURIComponent(text)}`;
    if (mail) mail.href = `${mail.href.split("?")[0]}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };
  box.addEventListener("input", update);
  box.addEventListener("change", update);
});

// First home buyers: show one state's grant and duty help at a time. Without this, every state shows.
document.querySelectorAll("[data-fhb]").forEach((box) => {
  box.classList.add("is-picking");
  const show = () => {
    const code = (box.querySelector('input[name="fhb-state"]:checked') || {}).value;
    box.querySelectorAll(".fhb-state").forEach((s) => { s.hidden = s.dataset.state !== code; });
  };
  box.addEventListener("change", show);
  show();
});
