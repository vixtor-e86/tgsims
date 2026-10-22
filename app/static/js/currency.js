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

  /**
   * Reconciles round-trip conversion distortion from USD storage to exact Naira amounts.
   * - Clean dollar amounts ($1.00, $2.00, $0.50, $2.50) are exact USD settings or fees.
   *   For example, Reactivation Fee $2.00 @ rate 1340 is EXACTLY 2,680 NGN (never 2675).
   * - 4-decimal amounts (e.g. 2.2388 for 3,000 NGN, 3.7313 for 5,000 NGN) round to their exact integer.
   * - Legacy 2-decimal amounts (e.g. 2.24, 2.25, 1.85) snap to clean multiples of 25.
   */
  function reconcileNgn(usd, rawVal, rate) {
    if (rate === undefined) {
      rate = rawVal;
      rawVal = usd;
      usd = null;
    }
    if (isNaN(rawVal)) return 0;
    var rateNum = Number(rate) || 1600;

    if (usd != null && !isNaN(Number(usd))) {
      var usdNum = Number(usd);
      // 1. Clean dollar amounts (e.g. $1.00, $2.00, $0.50, $2.50) are exact USD settings or fees.
      // E.g. Reactivation Fee $2.00 @ rate 1340 is EXACTLY 2,680 NGN (never snapped to 2675).
      if (Math.abs(usdNum * 2 - Math.round(usdNum * 2)) < 1e-4) {
        return Math.round(rawVal);
      }
      // 2. Sub-cent precision (4 decimals, e.g. 2.2388 for 3000 NGN, 3.7313 for 5000 NGN)
      var usd2 = Math.round(usdNum * 100) / 100;
      var usd4 = Math.round(usdNum * 10000) / 10000;
      if (Math.abs(usd2 - usd4) > 1e-5) {
        return Math.round(rawVal);
      }
    }

    // 3. Legacy 2-decimal USD rounding error (+-0.005 * rate):
    var nearest25 = Math.round(rawVal / 25.0) * 25.0;
    var maxErr = rateNum * 0.0051;
    if (Math.abs(rawVal - nearest25) <= maxErr) {
      return nearest25;
    }
    return Math.round(rawVal);
  }

  function format(usd, opts) {
    opts = opts || {};
    var cfg = CONFIG[active] || CONFIG.NGN;
    var value;
    if (active === "NGN") {
      if (opts.ngn != null && !isNaN(Number(opts.ngn)) && Number(opts.ngn) > 0) {
        value = Number(opts.ngn);
      } else {
        var raw = Number(usd) * cfg.rate;
        value = reconcileNgn(usd, raw, cfg.rate);
      }
    } else {
      value = Number(usd) * cfg.rate;
    }
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
      var ngn = el.getAttribute("data-ngn");
      var formatted = format(usd, { decimals: decimals, sign: sign, ngn: ngn });
      el.textContent = formatted;

      var chip = el.closest(".wallet-chip");
      if (chip) {
        chip.setAttribute("title", "Wallet balance: " + formatted);
      }
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
    reconcileNgn: reconcileNgn,
    get active() { return active; },
    get rate() { return CONFIG[active].rate; },
    get symbol() { return CONFIG[active].symbol; },
  };
})();
