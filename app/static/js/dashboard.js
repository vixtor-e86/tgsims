/* ==========================================================================
   dashboard.js  -  Dashboard Quick Buy
   Reads the catalog + purchase endpoint off [data-quick-buy]:
     data-catalog  JSON: [{country_code, country_name, flag, services:[...]}]
     data-endpoint POST url for api.purchase_sim
   Country -> Service selects, live price (data-usd + TgCurrency), purchase.
   ========================================================================== */
(function () {
  "use strict";

  function initQuickBuy() {
    var root = document.querySelector("[data-quick-buy]");
    if (!root) return;

    var countrySel = root.querySelector("[data-qb-country]");
    var serviceSel = root.querySelector("[data-qb-service]");
    var priceEl = root.querySelector("[data-qb-price]");
    var submit = root.querySelector("[data-qb-submit]");
    if (!countrySel || !serviceSel || !priceEl || !submit) return;

    var endpoint = root.getAttribute("data-endpoint") || "/api/purchase-sim";
    var catalog = [];
    try {
      catalog = JSON.parse(root.getAttribute("data-catalog") || "[]");
    } catch (e) {
      catalog = [];
    }
    if (!catalog.length) return;

    var selected = { country: null, service: null };

    /* ---- Render country select ---- */
    catalog.forEach(function (c) {
      var opt = document.createElement("option");
      opt.value = c.country_code;
      opt.textContent = (c.flag || "") + "  " + c.country_name;
      opt.dataset.countryName = c.country_name;
      countrySel.appendChild(opt);
    });

    function currentCountry() {
      var code = countrySel.value;
      var country = catalog.filter(function (c) { return c.country_code === code; })[0];
      return country || null;
    }

    function renderServices() {
      serviceSel.innerHTML = "";
      var country = currentCountry();
      selected.service = null;
      if (!country) {
        priceEl.setAttribute("data-usd", "0");
        refreshPrice();
        submit.disabled = true;
        return;
      }
      country.services.forEach(function (s) {
        var opt = document.createElement("option");
        opt.value = s.name;
        opt.textContent = s.name + "  (N" + s.available.toLocaleString() + " available)";
        serviceSel.appendChild(opt);
      });
      selectFirstService();
    }

    function selectFirstService() {
      if (serviceSel.options.length) {
        serviceSel.selectedIndex = 0;
        selected.service = serviceSel.value;
        updatePrice();
        submit.disabled = false;
      } else {
        submit.disabled = true;
      }
    }

    function currentService() {
      var country = currentCountry();
      if (!country) return null;
      return country.services.filter(function (s) { return s.name === serviceSel.value; })[0] || null;
    }

    function updatePrice() {
      var s = currentService();
      var usd = s ? String(s.price) : "0";
      priceEl.setAttribute("data-usd", usd);
      refreshPrice();
    }

    function refreshPrice() {
      if (window.TgCurrency && window.TgCurrency.render) {
        window.TgCurrency.render(priceEl.parentNode);
      } else {
        priceEl.textContent = "$" + (Number(priceEl.getAttribute("data-usd")) || 0).toFixed(2);
      }
    }

    /* ---- Live currency flip: re-render the active price ---- */
    document.addEventListener("currencychange", function () { refreshPrice(); });

    /* ---- Purchase ---- */
    submit.addEventListener("click", function () {
      if (submit.disabled) return;
      var country = currentCountry();
      var service = currentService();
      if (!country || !service) {
        if (window.toast) window.toast("Pick a country and service first.", "error");
        return;
      }
      submit.disabled = true;
      submit.classList.add("is-loading");
      submit.setAttribute("aria-busy", "true");

      var payload = {
        country_code: country.country_code,
        country_name: country.country_name,
        service_name: service.name,
        price: service.price,
      };

      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          return res.json().then(function (data) { return { ok: res.ok, data: data }; });
        })
        .then(function (r) {
          if (!r.ok) throw new Error(r.data.message || "Could not complete purchase.");
          if (window.toast) window.toast(r.data.message || "SIM purchased!", "success");
        })
        .catch(function (err) {
          if (window.toast) window.toast(err.message || "Something went wrong. Try again.", "error");
        })
        .then(function () {
          submit.disabled = false;
          submit.classList.remove("is-loading");
          submit.removeAttribute("aria-busy");
        });
    });

    countrySel.addEventListener("change", renderServices);
    serviceSel.addEventListener("change", function () {
      selected.service = serviceSel.value;
      updatePrice();
    });

    renderServices();
  }

  function init() {
    initQuickBuy();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
