/* ==========================================================================
   buy.js  -  Buy a Virtual Number
   Tile-based country + service selector with a live Review & Purchase card.
   Reads [data-buy] -> data-catalog (JSON) + data-endpoint (api.purchase_sim).
   ========================================================================== */
(function () {
  "use strict";

  var DIAL = { US: "+1", GB: "+44", CA: "+1", DE: "+49", NG: "+234",
               GH: "+233", ZA: "+27", IN: "+91" };

  /* Inline glyphs (mirror partials/icons.html) for well-known services. */
  var G = {
    chat: '<path d="M21 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z"/>',
    send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/>',
    mail: '<rect x="2.5" y="4.5" width="19" height="15" rx="2.5"/><path d="m3 6 9 7 9-7"/>',
    camera: '<path d="M4 8a2 2 0 0 1 2-2h1.5l1-1.5h5L16 6h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.5" r="3.2"/>',
    sparkles: '<path d="M12 3l1.8 4.7L18.5 9l-4.7 1.8L12 15l-1.8-4.2L5.5 9l4.7-1.3L12 3z"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/>',
    bank: '<path d="M3 10 12 4l9 6"/><path d="M4 10h16v9H4z"/><path d="M8 10v9M12 10v9M16 10v9M3 21h18"/>',
    check: '<path d="M20 6 9 17l-5-5"/>'
  };

  function svg(inner) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + inner + "</svg>";
  }

  function svcVisual(name) {
    var n = name.toLowerCase();
    if (n.indexOf("whatsapp") > -1) return { cls: "svc-whatsapp", svg: G.chat };
    if (n.indexOf("telegram") > -1) return { cls: "svc-telegram", svg: G.send };
    if (n.indexOf("google") > -1 || n.indexOf("gmail") > -1) return { cls: "svc-google", svg: G.mail };
    if (n.indexOf("instagram") > -1) return { cls: "svc-instagram", svg: G.camera };
    if (n.indexOf("openai") > -1 || n.indexOf("chatgpt") > -1) return { cls: "svc-openai", svg: G.sparkles };
    if (n.indexOf("tinder") > -1) return { cls: "svc-tinder", svg: G.sparkles };
    if (n.indexOf("esim") > -1) return { cls: "svc-esim", svg: G.globe };
    if (n.indexOf("bank") > -1) return { cls: "svc-generic", svg: G.bank };
    if (n.indexOf("facebook") > -1) return { cls: "svc-facebook", letter: "f" };
    if (n.indexOf("tiktok") > -1) return { cls: "svc-tiktok", letter: "T" };
    return { cls: "svc-generic", letter: name.charAt(0).toUpperCase() };
  }

  function flagBadge(code) {
    return '<span class="flag-badge">' +
      code.split("").map(function (ch) { return "<i>" + ch + "</i>"; }).join("") +
      "</span>";
  }
  function init() {
    var root = document.querySelector("[data-buy]");
    if (!root) return;

    var endpoint = root.getAttribute("data-endpoint") || "/api/purchase-sim";
    var catalog = [];
    try { catalog = JSON.parse(root.getAttribute("data-catalog") || "[]"); }
    catch (e) { catalog = []; }
    if (!catalog.length) return;

    var countryGrid = root.querySelector("[data-country-grid]");
    var serviceGrid = root.querySelector("[data-service-grid]");
    var countrySearch = root.querySelector("[data-country-search]");
    var serviceSearch = root.querySelector("[data-service-search]");
    var reviewCountry = root.querySelector("[data-review-country]");
    var reviewService = root.querySelector("[data-review-service]");
    var reviewPrice = root.querySelector("[data-review-price]");
    var submit = root.querySelector("[data-buy-submit]");

    var state = { country: null, service: null };

    function priceRender() {
      if (window.TgCurrency && window.TgCurrency.render) window.TgCurrency.render(root);
    }

    /* ---- Country tiles ---- */
    function renderCountries(filter) {
      countryGrid.innerHTML = "";
      var q = (filter || "").trim().toLowerCase();
      var shown = catalog.filter(function (c) {
        return !q || c.country_name.toLowerCase().indexOf(q) > -1 ||
               c.country_code.toLowerCase().indexOf(q) > -1;
      });
      if (!shown.length) {
        countryGrid.innerHTML = '<div class="tile-empty">No countries match your search.</div>';
        return;
      }
      shown.forEach(function (c) {
        var t = document.createElement("button");
        t.type = "button";
        t.className = "opt-tile";
        t.dataset.code = c.country_code;
        if (state.country && state.country.country_code === c.country_code) t.classList.add("is-selected");
        t.innerHTML =
          '<span class="opt-tile-check">' + svg(G.check) + "</span>" +
          flagBadge(c.country_code) +
          '<span class="opt-tile-name">' + c.country_name + "</span>" +
          '<span class="opt-tile-sub">' + (DIAL[c.country_code] || "") + "</span>";
        countryGrid.appendChild(t);
      });
    }

    /* ---- Service tiles (depend on selected country) ---- */
    function renderServices(filter) {
      serviceGrid.innerHTML = "";
      if (!state.country) {
        serviceGrid.innerHTML = '<div class="tile-empty">Select a country to see available services.</div>';
        return;
      }
      var q = (filter || "").trim().toLowerCase();
      var shown = state.country.services.filter(function (s) {
        return !q || s.name.toLowerCase().indexOf(q) > -1;
      });
      if (!shown.length) {
        serviceGrid.innerHTML = '<div class="tile-empty">No services match your search.</div>';
        return;
      }
      shown.forEach(function (s) {
        var vis = svcVisual(s.name);
        var glyph = vis.svg
          ? svg(vis.svg)
          : '<span style="font-weight:800;font-size:1.15rem;line-height:1;">' + vis.letter + "</span>";
        var t = document.createElement("button");
        t.type = "button";
        t.className = "opt-tile";
        t.dataset.name = s.name;
        if (state.service && state.service.name === s.name) t.classList.add("is-selected");
        t.innerHTML =
          '<span class="opt-tile-check">' + svg(G.check) + "</span>" +
          '<span class="svc-ico ' + vis.cls + '">' + glyph + "</span>" +
          '<span class="opt-tile-name">' + s.name + "</span>" +
          '<span class="opt-tile-sub" data-usd="' + s.price + '">' + s.price + "</span>";
        serviceGrid.appendChild(t);
      });
      priceRender();
    }

    /* ---- Review card ---- */
    function updateReview() {
      if (state.country) {
        reviewCountry.classList.remove("is-empty");
        reviewCountry.innerHTML = flagBadge(state.country.country_code) +
          "<span>" + state.country.country_name + "</span>";
      } else {
        reviewCountry.classList.add("is-empty");
        reviewCountry.textContent = "-";
      }
      if (state.service) {
        reviewService.classList.remove("is-empty");
        reviewService.textContent = state.service.name;
        reviewPrice.setAttribute("data-usd", String(state.service.price));
      } else {
        reviewService.classList.add("is-empty");
        reviewService.textContent = "-";
        reviewPrice.setAttribute("data-usd", "0");
      }
      submit.disabled = !(state.country && state.service);
      priceRender();
    }

    function selectCountry(code) {
      var c = catalog.filter(function (x) { return x.country_code === code; })[0];
      if (!c) return;
      state.country = c;
      state.service = c.services[0] || null;
      if (serviceSearch) serviceSearch.value = "";
      renderCountries(countrySearch ? countrySearch.value : "");
      renderServices("");
      updateReview();
    }

    function selectService(name) {
      if (!state.country) return;
      var s = state.country.services.filter(function (x) { return x.name === name; })[0];
      if (!s) return;
      state.service = s;
      root.querySelectorAll("[data-service-grid] .opt-tile").forEach(function (el) {
        el.classList.toggle("is-selected", el.dataset.name === name);
      });
      updateReview();
    }

    /* ---- Events ---- */
    countryGrid.addEventListener("click", function (e) {
      var tile = e.target.closest(".opt-tile");
      if (tile && tile.dataset.code) selectCountry(tile.dataset.code);
    });
    serviceGrid.addEventListener("click", function (e) {
      var tile = e.target.closest(".opt-tile");
      if (tile && tile.dataset.name) selectService(tile.dataset.name);
    });
    if (countrySearch) countrySearch.addEventListener("input", function () { renderCountries(countrySearch.value); });
    if (serviceSearch) serviceSearch.addEventListener("input", function () { renderServices(serviceSearch.value); });

    submit.addEventListener("click", function () {
      if (submit.disabled || !state.country || !state.service) return;
      submit.disabled = true;
      submit.classList.add("is-loading");
      submit.setAttribute("aria-busy", "true");

      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          country_code: state.country.country_code,
          country_name: state.country.country_name,
          service_name: state.service.name,
          price: state.service.price
        })
      })
        .then(function (res) {
          if (res.status === 401) {
            window.location.href = "/auth/login";
            throw new Error("Please sign in to continue.");
          }
          return res.json().then(function (data) { return { ok: res.ok, data: data }; });
        })
        .then(function (r) {
          if (!r.ok) throw new Error(r.data.message || "Could not complete purchase.");
          if (window.toast) window.toast(r.data.message || "Number purchased!", "success");
          setTimeout(function () { window.location.href = "/sims/my-sims"; }, 900);
        })
        .catch(function (err) {
          if (window.toast) window.toast(err.message || "Something went wrong. Try again.", "error");
          submit.disabled = false;
          submit.classList.remove("is-loading");
          submit.removeAttribute("aria-busy");
        });
    });

    /* ---- Initial paint: preselect first country + service ---- */
    state.country = catalog[0];
    state.service = catalog[0].services[0] || null;
    renderCountries("");
    renderServices("");
    updateReview();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
