/* ==========================================================================
   us_canada.js  -  Buy US Number (Basic & Reliable Dedicated Lines)
   Handles dual Quick Buy boxes:
     1. Basic Package (5sim multi-route options with different price tags)
     2. Reliable Package (TextVerified 100% Non-VoIP dedicated cellular line)
   Features real-time search filtering, dynamic route pricing, currency flip,
   and instant checkout allocation.
   ========================================================================== */
(function () {
  "use strict";

  function formatMoney(usd) {
    if (window.TgCurrency && window.TgCurrency.format) {
      return window.TgCurrency.format(usd);
    }
    var rate = Number(window.TG_NGN_PER_USD) || 1600;
    return "₦" + (Number(usd) * rate).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function initUSBoxes() {
    var root = document.querySelector("[data-usca-boxes]");
    if (!root) return;

    var endpoint = root.getAttribute("data-endpoint") || "/api/purchase-us-canada";
    var config = {};
    try {
      config = JSON.parse(root.getAttribute("data-config") || "{}");
    } catch (e) {
      config = {};
    }

    var basicServices = config.basic_services || [];
    var premiumServices = config.premium_services || [];

    // Setup Box 1: Basic
    var basicBox = root.querySelector('[data-box="basic"]');
    setupBox(basicBox, {
      type: "basic",
      packageId: "basic_pool",
      services: basicServices,
      endpoint: endpoint,
    });

    // Setup Box 2: Premium / Reliable
    var premBox = root.querySelector('[data-box="premium"]');
    setupBox(premBox, {
      type: "premium",
      packageId: "reliable_non_voip",
      services: premiumServices,
      endpoint: endpoint,
    });

    // Update package explanation cards on currency change
    updateStaticPackageRanges();
    document.addEventListener("currencychange", function () {
      updateStaticPackageRanges();
    });
  }

  function updateStaticPackageRanges() {
    var isUSD = window.TgCurrency && window.TgCurrency.active === "USD";
    document.querySelectorAll(".pkg-card-static [data-range-ngn]").forEach(function (el) {
      var ngn = el.getAttribute("data-range-ngn");
      var usd = el.getAttribute("data-range-usd");
      el.textContent = isUSD ? usd : ngn;
    });
  }

  function setupBox(boxEl, opts) {
    if (!boxEl) return;

    var searchInput = boxEl.querySelector("[data-search-input]");
    var selectEl = boxEl.querySelector("[data-service-select]");
    var priceEl = boxEl.querySelector("[data-price-val]");
    var submitBtn = boxEl.querySelector("[data-submit-btn]");
    var allServices = opts.services || [];
    var currentFiltered = allServices.slice();
    var selectedItem = null;

    function renderOptions(items, preserveSelectionId) {
      selectEl.innerHTML = "";

      if (!items || items.length === 0) {
        var noneOpt = document.createElement("option");
        noneOpt.disabled = true;
        noneOpt.selected = true;
        noneOpt.textContent = "No services match your search";
        selectEl.appendChild(noneOpt);
        selectedItem = null;
        if (priceEl) {
          priceEl.setAttribute("data-usd", "0");
          priceEl.textContent = formatMoney(0);
        }
        if (submitBtn) submitBtn.disabled = true;
        return;
      }

      var selectedIndex = 0;
      items.forEach(function (s, idx) {
        var opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = s.name + "  —  " + formatMoney(s.price_usd);
        if (preserveSelectionId && s.id === preserveSelectionId) {
          selectedIndex = idx;
        }
        selectEl.appendChild(opt);
      });

      selectEl.selectedIndex = selectedIndex;
      selectedItem = items[selectedIndex];
      updatePriceDisplay();
      if (submitBtn) submitBtn.disabled = false;
    }

    function updatePriceDisplay() {
      if (!selectedItem || !priceEl) return;
      var usd = String(selectedItem.price_usd);
      priceEl.setAttribute("data-usd", usd);
      if (window.TgCurrency && window.TgCurrency.render) {
        window.TgCurrency.render(priceEl.parentNode);
      } else {
        priceEl.textContent = formatMoney(usd);
      }
    }

    // Filter services on search typing
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        var q = searchInput.value.trim().toLowerCase();
        if (!q) {
          currentFiltered = allServices.slice();
        } else {
          currentFiltered = allServices.filter(function (s) {
            var n = (s.name || "").toLowerCase();
            var sn = (s.service_name || "").toLowerCase();
            var ql = (s.quality || "").toLowerCase();
            return n.indexOf(q) > -1 || sn.indexOf(q) > -1 || ql.indexOf(q) > -1;
          });
        }
        renderOptions(currentFiltered);
      });

      // Quick focus helper
      searchInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          selectEl.focus();
        }
      });
    }

    // Update on select change
    selectEl.addEventListener("change", function () {
      var val = selectEl.value;
      var matched = currentFiltered.filter(function (s) { return s.id === val; })[0];
      if (matched) {
        selectedItem = matched;
        updatePriceDisplay();
      }
    });

    // Handle currency flip
    document.addEventListener("currencychange", function () {
      var currId = selectedItem ? selectedItem.id : null;
      renderOptions(currentFiltered, currId);
    });

    // Initial render
    renderOptions(currentFiltered);

    // Submit purchase
    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        if (!selectedItem || submitBtn.disabled) {
          if (window.toast) window.toast("Please choose a service first.", "error");
          return;
        }

        var origHtml = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.classList.add("is-loading");
        submitBtn.setAttribute("aria-busy", "true");
        submitBtn.innerHTML = '<span class="spinner"></span> <span>Ordering Number...</span>';

        var payload = {
          country_code: "US",
          package_id: opts.packageId,
          service_name: selectedItem.service_name || selectedItem.name,
          service_code: selectedItem.service_code,
          provider_id: selectedItem.operator || "auto",
          price: selectedItem.price_usd,
        };

        fetch(opts.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
          .then(function (res) {
            if (res.status === 401) {
              window.location.href = "/auth/login";
              throw new Error("Please sign in to complete your order.");
            }
            return res.json().then(function (data) { return { ok: res.ok, data: data }; });
          })
          .then(function (r) {
            if (!r.ok) throw new Error(r.data.message || "Could not allocate number.");
            submitBtn.innerHTML = '<span class="spinner"></span> <span>Number Allocated! Redirecting...</span>';
            if (window.toast) window.toast(r.data.message || "Number ordered successfully!", "success");
            setTimeout(function () {
              window.location.href = r.data.redirect_url || "/sims/my-sims";
            }, 600);
          })
          .catch(function (err) {
            if (window.toast) window.toast(err.message || "Something went wrong. Try again.", "error");
            submitBtn.disabled = false;
            submitBtn.classList.remove("is-loading");
            submitBtn.removeAttribute("aria-busy");
            submitBtn.innerHTML = origHtml;
          });
      });
    }
  }

  function init() {
    initUSBoxes();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
