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
    var clearBtn = boxEl.querySelector("[data-clear-btn]");
    var dropdownMenu = boxEl.querySelector("[data-dropdown-menu]");
    var selectEl = boxEl.querySelector("[data-service-select]");
    var priceEl = boxEl.querySelector("[data-price-val]");
    var submitBtn = boxEl.querySelector("[data-submit-btn]");
    var allServices = opts.services || [];
    var currentFiltered = allServices.slice();
    var selectedItem = null;
    var highlightedIndex = -1;
    var isOpen = false;

    function openDropdown() {
      if (!dropdownMenu) return;
      isOpen = true;
      dropdownMenu.classList.add("is-open");
      dropdownMenu.style.display = "block";
      renderDropdownItems(currentFiltered);
      scrollHighlightedIntoView();
    }

    function closeDropdown() {
      if (!dropdownMenu) return;
      isOpen = false;
      dropdownMenu.classList.remove("is-open");
      dropdownMenu.style.display = "none";
      highlightedIndex = -1;
    }

    function scrollHighlightedIntoView() {
      if (!dropdownMenu || highlightedIndex < 0) return;
      var items = dropdownMenu.querySelectorAll(".search-dropdown-item");
      if (items[highlightedIndex]) {
        items[highlightedIndex].scrollIntoView({ block: "nearest" });
      }
    }

    function renderDropdownItems(items) {
      if (!dropdownMenu) return;
      dropdownMenu.innerHTML = "";

      if (!items || items.length === 0) {
        var emptyEl = document.createElement("div");
        emptyEl.className = "search-dropdown-empty";
        emptyEl.textContent = "No services match your search";
        dropdownMenu.appendChild(emptyEl);
        return;
      }

      var MAX_RENDER = 70;
      var toRender = items.slice(0, MAX_RENDER);

      toRender.forEach(function (s, idx) {
        var itemEl = document.createElement("div");
        itemEl.className = "search-dropdown-item";
        if (selectedItem && selectedItem.id === s.id) {
          itemEl.classList.add("is-selected");
        }
        if (idx === highlightedIndex) {
          itemEl.classList.add("is-highlighted");
        }

        var iconLetter = (s.service_name || s.name || "S").charAt(0).toUpperCase();
        var routeDesc = s.quality || (opts.type === "premium" ? "100% Non-VoIP Cellular" : "High-Delivery Pool");

        itemEl.innerHTML =
          '<div class="search-dropdown-item-left">' +
            '<span class="search-dropdown-item-icon">' + iconLetter + '</span>' +
            '<div class="search-dropdown-item-info">' +
              '<span class="search-dropdown-item-name">' + (s.name || s.service_name) + '</span>' +
              '<span class="search-dropdown-item-route">' + routeDesc + '</span>' +
            '</div>' +
          '</div>' +
          '<span class="search-dropdown-item-price">' + formatMoney(s.price_usd) + '</span>';

        itemEl.addEventListener("mousedown", function (e) {
          e.preventDefault(); // prevent input blur
          chooseService(s);
          closeDropdown();
        });

        dropdownMenu.appendChild(itemEl);
      });

      if (items.length > MAX_RENDER) {
        var footer = document.createElement("div");
        footer.className = "search-dropdown-empty";
        footer.style.padding = "8px 12px";
        footer.style.fontSize = "0.7rem";
        footer.style.borderTop = "1px solid var(--border)";
        footer.textContent = "Showing top " + MAX_RENDER + " of " + items.length + " matching routes — type to narrow down";
        dropdownMenu.appendChild(footer);
      }
    }

    function chooseService(s) {
      if (!s) return;
      selectedItem = s;
      if (selectEl) {
        var opt = selectEl.querySelector('option[value="' + s.id + '"]');
        if (!opt) {
          opt = document.createElement("option");
          opt.value = s.id;
          opt.textContent = s.name + "  —  " + formatMoney(s.price_usd);
          selectEl.prepend(opt);
        }
        selectEl.value = s.id;
      }
      if (searchInput) {
        searchInput.value = s.name || s.service_name;
        if (clearBtn) clearBtn.style.display = "inline-block";
      }
      updatePriceDisplay();
      if (submitBtn) submitBtn.disabled = false;
    }

    function renderOptions(items, preserveSelectionId) {
      if (!selectEl) return;
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

      var MAX_SELECT = 80;
      var toRender = items.slice(0, MAX_SELECT);

      if (preserveSelectionId && !toRender.some(function (x) { return x.id === preserveSelectionId; })) {
        var foundPreserved = items.find(function (x) { return x.id === preserveSelectionId; });
        if (foundPreserved) toRender.unshift(foundPreserved);
      }

      var selectedIndex = 0;
      toRender.forEach(function (s, idx) {
        var opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = s.name + "  —  " + formatMoney(s.price_usd);
        if (preserveSelectionId && s.id === preserveSelectionId) {
          selectedIndex = idx;
        }
        selectEl.appendChild(opt);
      });

      selectEl.selectedIndex = selectedIndex;
      selectedItem = toRender[selectedIndex];
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

    // Filter services on search typing & open dropdown
    if (searchInput) {
      searchInput.addEventListener("focus", function () {
        openDropdown();
      });

      searchInput.addEventListener("click", function () {
        openDropdown();
      });

      searchInput.addEventListener("input", function () {
        var q = searchInput.value.trim().toLowerCase();
        if (clearBtn) {
          clearBtn.style.display = q ? "inline-block" : "none";
        }
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
        highlightedIndex = currentFiltered.length > 0 ? 0 : -1;
        renderOptions(currentFiltered, selectedItem ? selectedItem.id : null);
        openDropdown();
      });

      // Keyboard navigation
      searchInput.addEventListener("keydown", function (e) {
        if (!isOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
          openDropdown();
          return;
        }

        if (e.key === "ArrowDown") {
          e.preventDefault();
          if (currentFiltered.length > 0) {
            highlightedIndex = (highlightedIndex + 1) % currentFiltered.length;
            renderDropdownItems(currentFiltered);
            scrollHighlightedIntoView();
          }
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          if (currentFiltered.length > 0) {
            highlightedIndex = (highlightedIndex - 1 + currentFiltered.length) % currentFiltered.length;
            renderDropdownItems(currentFiltered);
            scrollHighlightedIntoView();
          }
        } else if (e.key === "Enter") {
          e.preventDefault();
          if (highlightedIndex >= 0 && currentFiltered[highlightedIndex]) {
            chooseService(currentFiltered[highlightedIndex]);
            closeDropdown();
          } else if (currentFiltered.length > 0) {
            chooseService(currentFiltered[0]);
            closeDropdown();
          }
        } else if (e.key === "Escape") {
          closeDropdown();
        }
      });
    }

    // Clear search button
    if (clearBtn) {
      clearBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        searchInput.value = "";
        clearBtn.style.display = "none";
        currentFiltered = allServices.slice();
        renderOptions(currentFiltered, selectedItem ? selectedItem.id : null);
        searchInput.focus();
        openDropdown();
      });
    }

    // Close dropdown on click outside
    document.addEventListener("click", function (e) {
      if (!boxEl.contains(e.target)) {
        closeDropdown();
      }
    });

    // Update on select change
    selectEl.addEventListener("change", function () {
      var val = selectEl.value;
      var matched = allServices.filter(function (s) { return s.id === val; })[0];
      if (matched) {
        chooseService(matched);
      }
    });

    // Handle currency flip
    document.addEventListener("currencychange", function () {
      var currId = selectedItem ? selectedItem.id : null;
      renderOptions(currentFiltered, currId);
      if (isOpen) renderDropdownItems(currentFiltered);
    });

    // Initial render
    renderOptions(currentFiltered);
    if (selectedItem && searchInput && !searchInput.value) {
      searchInput.value = selectedItem.name || selectedItem.service_name;
      if (clearBtn) clearBtn.style.display = "inline-block";
    }

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
