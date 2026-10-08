/* ==========================================================================
   buy.js  -  Buy a Virtual Number (3-List Layout)
   List 1: Country list (Searchable)
   List 2: Services list (10 core services prioritized with Core badge)
   List 3: Operators & Checkout list (Multi-operator breakdown for core services,
           standard route for others, order summary & purchase button)
   ========================================================================== */
(function () {
  "use strict";

  var CORE_SLUGS = [
    "whatsapp", "wa", "telegram", "tg", "google", "gmail", "youtube",
    "instagram", "ig", "threads", "twitter", "tw", "x", "facebook", "fb",
    "openai", "chatgpt", "tiktok", "discord", "apple", "icloud"
  ];

  function isCoreService(code, name) {
    var c = (code || "").toLowerCase();
    var n = (name || "").toLowerCase();
    for (var i = 0; i < CORE_SLUGS.length; i++) {
      var s = CORE_SLUGS[i];
      if (c === s || c.indexOf(s) > -1 || n.indexOf(s) > -1) return true;
    }
    return false;
  }

  function formatMoney(usd) {
    if (window.TgCurrency && window.TgCurrency.format) {
      return window.TgCurrency.format(usd);
    }
    var rate = Number(window.TG_NGN_PER_USD) || 1600;
    return "₦" + (Number(usd) * rate).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function init() {
    var root = document.querySelector("[data-buy]");
    if (!root) return;

    var endpoint = root.getAttribute("data-endpoint") || "/api/purchase-sim";
    var operatorsEndpoint = root.getAttribute("data-operators-endpoint") || "/api/catalog/operators";

    var catalog = [];
    try {
      catalog = JSON.parse(root.getAttribute("data-catalog") || "[]");
    } catch (e) {
      catalog = [];
    }
    if (!catalog.length) return;

    var countryListEl = root.querySelector("[data-country-list]");
    var serviceListEl = root.querySelector("[data-service-list]");
    var operatorListEl = root.querySelector("[data-operator-list]");
    var countrySearch = root.querySelector("[data-country-search]");
    var serviceSearch = root.querySelector("[data-service-search]");
    var countryCount = root.querySelector("[data-country-count]");
    var serviceCount = root.querySelector("[data-service-count]");
    var opCount = root.querySelector("[data-op-count]");

    var reviewCountry = root.querySelector("[data-review-country]");
    var reviewService = root.querySelector("[data-review-service]");
    var reviewCarrier = root.querySelector("[data-review-carrier]");
    var reviewPrice = root.querySelector("[data-review-price]");
    var submit = root.querySelector("[data-buy-submit]");

    var state = {
      country: null,
      service: null,
      operator: null,
      operators: [],
      isLoadingOps: false
    };

    var operatorCache = {};

    function priceRender() {
      if (window.TgCurrency && window.TgCurrency.render) {
        window.TgCurrency.render(root);
      }
    }

    /* ---- 1. Render Countries ---- */
    function renderCountries(filter) {
      if (!countryListEl) return;
      countryListEl.innerHTML = "";
      var q = (filter || "").trim().toLowerCase();

      var shown = catalog.filter(function (c) {
        return !q ||
          c.country_name.toLowerCase().indexOf(q) > -1 ||
          c.country_code.toLowerCase().indexOf(q) > -1;
      });

      if (countryCount) countryCount.textContent = shown.length;

      if (!shown.length) {
        countryListEl.innerHTML = '<div class="buy-empty-msg">No countries found</div>';
        return;
      }

      shown.forEach(function (c) {
        var row = document.createElement("button");
        row.type = "button";
        row.className = "buy-list-row";
        if (state.country && state.country.country_code === c.country_code) {
          row.classList.add("is-active");
        }

        var flagHtml = c.flag || "🌐";
        row.innerHTML =
          '<div class="buy-list-row-left">' +
            '<span class="buy-list-flag">' + flagHtml + '</span>' +
            '<div class="buy-list-text">' +
              '<span class="buy-list-primary">' + c.country_name + '</span>' +
              '<span class="buy-list-secondary">' + (c.dial || "") + '</span>' +
            '</div>' +
          '</div>' +
          '<div class="buy-list-meta">' +
            '<span class="badge badge-neutral" style="font-size:0.7rem;">' + (c.services ? c.services.length : 0) + '</span>' +
          '</div>';

        row.addEventListener("click", function () {
          selectCountry(c.country_code);
        });

        countryListEl.appendChild(row);
      });
    }

    /* ---- 2. Render Services ---- */
    function renderServices(filter) {
      if (!serviceListEl) return;
      serviceListEl.innerHTML = "";

      if (!state.country) {
        serviceListEl.innerHTML = '<div class="buy-empty-msg">Select a country first</div>';
        if (serviceCount) serviceCount.textContent = "0";
        return;
      }

      var q = (filter || "").trim().toLowerCase();
      var rawServices = (state.country.services || []).slice();

      // Prioritize 10 core services
      rawServices.sort(function (a, b) {
        var aCore = isCoreService(a.code, a.name);
        var bCore = isCoreService(b.code, b.name);
        if (aCore && !bCore) return -1;
        if (!aCore && bCore) return 1;
        return a.name.localeCompare(b.name);
      });

      var shown = rawServices.filter(function (s) {
        return !q || s.name.toLowerCase().indexOf(q) > -1 || (s.code && s.code.toLowerCase().indexOf(q) > -1);
      });

      if (serviceCount) serviceCount.textContent = shown.length;

      if (!shown.length) {
        serviceListEl.innerHTML = '<div class="buy-empty-msg">No services match your search</div>';
        return;
      }

      shown.forEach(function (s) {
        var row = document.createElement("button");
        row.type = "button";
        row.className = "buy-list-row";
        if (state.service && (state.service.code === s.code || state.service.name === s.name)) {
          row.classList.add("is-active");
        }

        var isCore = isCoreService(s.code, s.name);
        var coreBadge = isCore ? '<span class="buy-list-badge-core">Core</span>' : '';
        var letter = (s.name || "S").charAt(0).toUpperCase();

        row.innerHTML =
          '<div class="buy-list-row-left">' +
            '<span class="badge badge-brand" style="width:24px;height:24px;display:grid;place-items:center;padding:0;font-size:0.75rem;font-weight:700;">' + letter + '</span>' +
            '<div class="buy-list-text">' +
              '<span class="buy-list-primary">' + s.name + '</span>' +
              '<span class="buy-list-secondary">' + (isCore ? 'Multi-Operator Routes' : 'Standard Carrier') + '</span>' +
            '</div>' +
          '</div>' +
          '<div class="buy-list-meta">' +
            coreBadge +
            '<span class="buy-list-price" data-usd="' + s.price + '">' + formatMoney(s.price) + '</span>' +
          '</div>';

        row.addEventListener("click", function () {
          selectService(s);
        });

        serviceListEl.appendChild(row);
      });

      priceRender();
    }

    /* ---- 3. Render Operators (Column 3) ---- */
    function renderOperators() {
      if (!operatorListEl) return;
      operatorListEl.innerHTML = "";

      if (!state.country || !state.service) {
        operatorListEl.innerHTML = '<div class="buy-empty-msg">Select a service to view carrier routes &amp; checkout</div>';
        if (opCount) opCount.textContent = "Inactive";
        return;
      }

      if (state.isLoadingOps) {
        operatorListEl.innerHTML =
          '<div class="buy-empty-msg" style="display:flex;align-items:center;justify-content:center;gap:8px;">' +
            '<span class="spinner"></span> <span>Checking live carrier routes...</span>' +
          '</div>';
        if (opCount) opCount.textContent = "Loading...";
        return;
      }

      var ops = state.operators || [];
      if (opCount) opCount.textContent = ops.length + " Route" + (ops.length === 1 ? "" : "s");

      if (!ops.length) {
        // Fallback default route
        var defOp = {
          operator_name: "Standard Carrier Route",
          operator_code: "standard",
          operator_id: null,
          price_usd: state.service.price,
          available: state.service.available || 500
        };
        ops = [defOp];
        state.operators = ops;
        if (!state.operator) state.operator = defOp;
      }

      ops.forEach(function (op) {
        var card = document.createElement("div");
        card.className = "buy-op-card";
        var isSelected = state.operator && (
          (op.operator_id && state.operator.operator_id === op.operator_id) ||
          (op.operator_name === state.operator.operator_name)
        );
        if (isSelected) card.classList.add("is-active");

        var stockText = op.available ? "Stock: " + op.available.toLocaleString() + " lines" : "High Availability";

        card.innerHTML =
          '<div class="buy-op-info">' +
            '<span class="buy-op-name">' +
              (isSelected ? '✓ ' : '') + op.operator_name +
            '</span>' +
            '<span class="buy-op-stock">' + stockText + '</span>' +
          '</div>' +
          '<div class="buy-op-price" data-usd="' + op.price_usd + '">' +
            formatMoney(op.price_usd) +
          '</div>';

        card.addEventListener("click", function () {
          selectOperator(op);
        });

        operatorListEl.appendChild(card);
      });

      priceRender();
    }

    /* ---- Update Review Box ---- */
    function updateReview() {
      if (state.country) {
        reviewCountry.textContent = state.country.country_name + " (" + (state.country.dial || state.country.country_code) + ")";
      } else {
        reviewCountry.textContent = "-";
      }

      if (state.service) {
        reviewService.textContent = state.service.name;
      } else {
        reviewService.textContent = "-";
      }

      if (state.operator) {
        reviewCarrier.textContent = state.operator.operator_name;
        var p = state.operator.price_usd || state.service.price;
        reviewPrice.setAttribute("data-usd", String(p));
        reviewPrice.textContent = formatMoney(p);
      } else if (state.service) {
        reviewCarrier.textContent = "Standard Route";
        reviewPrice.setAttribute("data-usd", String(state.service.price));
        reviewPrice.textContent = formatMoney(state.service.price);
      } else {
        reviewCarrier.textContent = "-";
        reviewPrice.setAttribute("data-usd", "0");
        reviewPrice.textContent = formatMoney(0);
      }

      submit.disabled = !(state.country && state.service && state.operator);
      priceRender();
    }

    function selectCountry(code) {
      var c = catalog.filter(function (x) { return x.country_code === code; })[0];
      if (!c) return;
      state.country = c;
      state.service = (c.services && c.services.length) ? c.services[0] : null;
      state.operator = null;
      state.operators = [];

      renderCountries(countrySearch ? countrySearch.value : "");
      renderServices(serviceSearch ? serviceSearch.value : "");
      if (state.service) {
        fetchOperatorsForService(state.country, state.service);
      } else {
        renderOperators();
        updateReview();
      }
    }

    function selectService(s) {
      if (!state.country || !s) return;
      state.service = s;
      state.operator = null;
      state.operators = [];

      // Highlight active service
      if (serviceListEl) {
        serviceListEl.querySelectorAll(".buy-list-row").forEach(function (el) {
          el.classList.toggle("is-active", el.querySelector(".buy-list-primary") && el.querySelector(".buy-list-primary").textContent === s.name);
        });
      }

      fetchOperatorsForService(state.country, s);
    }

    function selectOperator(op) {
      state.operator = op;
      renderOperators();
      updateReview();
    }

    function fetchOperatorsForService(country, service) {
      var isCore = isCoreService(service.code, service.name);
      var cacheKey = country.country_code + ":" + (service.code || service.name);

      if (operatorCache[cacheKey]) {
        applyOperators(operatorCache[cacheKey], service);
        return;
      }

      if (!isCore) {
        // Non-core service: use standard route immediately without extra API query
        var singleOp = [{
          operator_name: "Standard Carrier Route",
          operator_code: "standard",
          operator_id: null,
          price_usd: service.price,
          available: service.available || 500
        }];
        operatorCache[cacheKey] = singleOp;
        applyOperators(singleOp, service);
        return;
      }

      // Query operators API for core services
      state.isLoadingOps = true;
      renderOperators();
      updateReview();

      var url = operatorsEndpoint + "?country_code=" + encodeURIComponent(country.country_code) +
                "&service_code=" + encodeURIComponent(service.code || service.name) +
                "&service_name=" + encodeURIComponent(service.name);

      fetch(url)
        .then(function (res) { return res.json(); })
        .then(function (data) {
          state.isLoadingOps = false;
          var ops = (data && data.operators && data.operators.length) ? data.operators : [];
          if (!ops.length) {
            ops = [{
              operator_name: "Standard Carrier Route",
              operator_code: "standard",
              operator_id: null,
              price_usd: service.price,
              available: service.available || 500
            }];
          }
          operatorCache[cacheKey] = ops;
          applyOperators(ops, service);
        })
        .catch(function () {
          state.isLoadingOps = false;
          var fallback = [{
            operator_name: "Standard Carrier Route",
            operator_code: "standard",
            operator_id: null,
            price_usd: service.price,
            available: service.available || 500
          }];
          applyOperators(fallback, service);
        });
    }

    function applyOperators(ops, service) {
      state.operators = ops;
      // Pre-select cheapest operator (first item in sorted list)
      state.operator = ops[0] || null;
      renderOperators();
      updateReview();
    }

    /* ---- Event Listeners ---- */
    if (countrySearch) {
      countrySearch.addEventListener("input", function () {
        renderCountries(countrySearch.value);
      });
    }

    if (serviceSearch) {
      serviceSearch.addEventListener("input", function () {
        renderServices(serviceSearch.value);
      });
    }

    // Submit purchase
    submit.addEventListener("click", function () {
      if (submit.disabled || !state.country || !state.service || !state.operator) return;

      var origHtml = submit.innerHTML;
      submit.disabled = true;
      submit.classList.add("is-loading");
      submit.setAttribute("aria-busy", "true");
      submit.innerHTML = '<span class="spinner"></span> <span>Ordering Number...</span>';

      var payload = {
        country_code: state.country.country_code,
        country_name: state.country.country_name,
        service_name: state.service.name,
        service_code: state.service.code || "",
        operator: state.operator.operator_code || state.operator.operator_name || "any",
        operator_id: state.operator.operator_id || null,
        price: state.operator.price_usd || state.service.price
      };

      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
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
          submit.innerHTML = '<span class="spinner"></span> <span>Number Allocated! Redirecting...</span>';
          if (window.toast) window.toast(r.data.message || "Number purchased successfully!", "success");
          setTimeout(function () { window.location.href = "/sims/my-sims"; }, 700);
        })
        .catch(function (err) {
          if (window.toast) window.toast(err.message || "Something went wrong. Try again.", "error");
          submit.disabled = false;
          submit.classList.remove("is-loading");
          submit.removeAttribute("aria-busy");
          submit.innerHTML = origHtml;
        });
    });

    // Currency toggle listener
    document.addEventListener("currencychange", function () {
      renderServices(serviceSearch ? serviceSearch.value : "");
      renderOperators();
      updateReview();
    });

    /* ---- Initial paint: preselect first country & service ---- */
    if (catalog.length > 0) {
      selectCountry(catalog[0].country_code);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
