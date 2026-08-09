/* ==========================================================================
   currency.js  -  NGN / USD display switcher
   Canonical amounts live in the DOM as data-usd="12.34" (always USD).
   This module formats them into the active currency and re-renders instantly
   when the user flips the switch. Choice is persisted.
   ========================================================================== */
(function () {
  "use strict";

  var STORAGE_KEY = "tgsims-currency";
  var RATE = Number(window.TG_NGN_PER_USD) || 1600; // USD -> NGN

  var CONFIG = {
    NGN: { symbol: "₦", rate: RATE, locale: "en-NG" },
    USD: { symbol: "$", rate: 1, locale: "en-US" },
  };

  function stored() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }

  var active = stored() || "NGN";

  function format(usd, opts) {
    opts = opts || {};
    var cfg = CONFIG[active] || CONFIG.NGN;
    var value = Number(usd) * cfg.rate;
    var decimals = opts.decimals != null ? opts.decimals : 2;
    var abs = Math.abs(value);

    var num = new Intl.NumberFormat(cfg.locale, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(abs);

    var sign = "";
    if (value < 0) sign = "-";
    else if (opts.sign === "+") sign = "+";

    return sign + cfg.symbol + num;
  }

  function render(scope) {
    (scope || document).querySelectorAll("[data-usd]").forEach(function (el) {
      var usd = el.getAttribute("data-usd");
      if (usd === null || usd === "") return;
      var decimals = el.hasAttribute("data-decimals")
        ? Number(el.getAttribute("data-decimals")) : 2;
      var sign = el.getAttribute("data-sign") || null;
      el.textContent = format(usd, { decimals: decimals, sign: sign });
    });
    // Reflect active currency on switch controls.
    document.querySelectorAll("[data-currency-set]").forEach(function (btn) {
      var on = btn.getAttribute("data-currency-set") === active;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function set(code, persist) {
    if (!CONFIG[code]) return;
    active = code;
    if (persist !== false) {
      try { localStorage.setItem(STORAGE_KEY, code); } catch (e) {}
    }
    render();
    document.dispatchEvent(new CustomEvent("currencychange", { detail: { currency: code } }));
  }

  function init() {
    render();
    document.querySelectorAll("[data-currency-set]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        set(btn.getAttribute("data-currency-set"), true);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Public API for pages that inject amounts dynamically (e.g. Buy Number, Fund).
  window.TgCurrency = {
    format: format,
    render: render,
    set: set,
    get active() { return active; },
    get rate() { return CONFIG[active].rate; },
    get symbol() { return CONFIG[active].symbol; },
  };
})();
