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
  const goal = q.get("goal"), amount = q.get("amount");
  if (goal) {
    const radio = [...form.querySelectorAll('input[name="goal"]')].find((r) => r.value === goal);
    if (radio) radio.checked = true;
  }
  if (amount) {
    const opt = [...form.querySelectorAll("#s-amount option")].find((o) => o.textContent === amount);
    if (opt) opt.selected = true;
  }
})();
