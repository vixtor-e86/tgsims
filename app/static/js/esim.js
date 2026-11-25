/* ==========================================================================
   esim.js  -  Travel & Global Data eSIM Marketplace (Admin Preview UI)
   Column 1: Destination / Region selection (Search + Region Filter Tabs)
   Column 2: Data Package / Validity Plan selection
   Column 3: Technical Specs & Review Checkout
   Includes: QR Code & Manual SM-DP+ Installation Modal
   ========================================================================== */
(function () {
  "use strict";

  function formatMoney(usd) {
    if (window.TgCurrency && window.TgCurrency.format) {
      return window.TgCurrency.format(usd);
    }
    var rate = Number(window.TG_NGN_PER_USD) || 1600;
    var raw = Number(usd) * rate;
    var nearest25 = Math.round(raw / 25.0) * 25.0;
    var maxErr = rate * 0.0051;
    var val = Math.abs(raw - nearest25) <= maxErr ? nearest25 : raw;
    return "₦" + val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function initEsimStore() {
    var root = document.querySelector("[data-esim-store]");
    if (!root) return;

    var endpoint = root.getAttribute("data-endpoint") || "/api/purchase-esim";
    var catalog = [];
    try {
      var raw = JSON.parse(root.getAttribute("data-catalog") || "[]");
      if (Array.isArray(raw)) catalog = raw;
    } catch (e) {
      catalog = [];
    }
    if (!catalog.length) return;

    var destListEl = root.querySelector("[data-dest-list]");
    var planListEl = root.querySelector("[data-plan-list]");
    var destSearch = root.querySelector("[data-dest-search]");
    var destCount = root.querySelector("[data-dest-count]");
    var planCount = root.querySelector("[data-plan-count]");
    var regionTabs = root.querySelectorAll("[data-region-filter]");

    var detailFlag = root.querySelector("[data-detail-flag]");
    var detailName = root.querySelector("[data-detail-dest-name]");
    var detailBadge = root.querySelector("[data-detail-dest-badge]");
    var detailDesc = root.querySelector("[data-detail-dest-desc]");
    var specNetworks = root.querySelector("[data-spec-networks]");
    var specSpeed = root.querySelector("[data-spec-speed]");
    var specHotspot = root.querySelector("[data-spec-hotspot]");

    var reviewDest = root.querySelector("[data-review-dest]");
    var reviewPlan = root.querySelector("[data-review-plan]");
    var reviewValidity = root.querySelector("[data-review-validity]");
    var reviewPrice = root.querySelector("[data-review-price]");
    var submitBtn = root.querySelector("[data-esim-submit]");

    var state = {
      regionFilter: "all",
      selectedDest: catalog[0],
      selectedPlan: catalog[0].plans && catalog[0].plans.length ? catalog[0].plans[1] || catalog[0].plans[0] : null
    };

    function renderDestinations() {
      if (!destListEl) return;
      destListEl.innerHTML = "";

      var q = (destSearch ? destSearch.value : "").trim().toLowerCase();
      var shown = catalog.filter(function (d) {
        if (state.regionFilter !== "all" && d.region !== state.regionFilter) {
          return false;
        }
        if (!q) return true;
        return (
          (d.name || "").toLowerCase().indexOf(q) !== -1 ||
          (d.code || "").toLowerCase().indexOf(q) !== -1 ||
          (d.networks || "").toLowerCase().indexOf(q) !== -1
        );
      });

      if (destCount) destCount.textContent = shown.length;

      if (!shown.length) {
        destListEl.innerHTML = '<div class="buy-empty-msg">No destinations match your search.</div>';
        return;
      }

      shown.forEach(function (d) {
        var row = document.createElement("button");
        row.type = "button";
        var isActive = state.selectedDest && state.selectedDest.code === d.code;
        row.className = "buy-list-row" + (isActive ? " is-active" : "");

        var startPrice = formatMoney(d.starting_usd || 2.5);

        row.innerHTML =
          '<div class="buy-list-row-left">' +
            '<span class="buy-list-flag">' + (d.flag || "🌐") + "</span>" +
            '<div class="buy-list-text">' +
              '<span class="buy-list-primary">' + d.name + "</span>" +
              '<span class="buy-list-secondary">' + (d.plans ? d.plans.length : 0) + " Data Plans • 4G/5G</span>" +
            "</div>" +
          "</div>" +
          '<div class="buy-list-meta">' +
            '<span style="font-size:0.75rem; font-weight:600; color:var(--text-muted);">From ' + startPrice + "</span>" +
          "</div>";

        row.addEventListener("click", function () {
          state.selectedDest = d;
          state.selectedPlan = d.plans && d.plans.length ? d.plans[1] || d.plans[0] : null;
          renderDestinations();
          renderPlans();
          updateCheckout();
          if (window.innerWidth <= 768) {
            var pCol = root.querySelector('[data-column="plan"]');
            if (pCol) pCol.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        });

        destListEl.appendChild(row);
      });
    }

    function renderPlans() {
      if (!planListEl || !state.selectedDest) return;
      planListEl.innerHTML = "";

      var plans = state.selectedDest.plans || [];
      if (planCount) planCount.textContent = plans.length + " Plans";

      if (!plans.length) {
        planListEl.innerHTML = '<div class="buy-empty-msg">No plans available for this destination.</div>';
        return;
      }

      plans.forEach(function (p) {
        var isSelected = state.selectedPlan && state.selectedPlan.id === p.id;
        var card = document.createElement("div");
        card.className = "buy-op-card" + (isSelected ? " is-active" : "");

        var formatted = formatMoney(p.retail_usd);
        var badgeHtml = p.badge
          ? '<span class="badge badge-brand badge-xs" style="font-size:0.66rem; padding:1px 6px;">' + p.badge + "</span>"
          : "";

        card.innerHTML =
          '<div class="buy-op-info">' +
            '<div class="buy-op-name" style="display:flex; align-items:center; gap:6px;">' +
              "<span>" + (isSelected ? "✓ " : "") + p.label + "</span>" +
              badgeHtml +
            "</div>" +
            '<span class="buy-op-stock">' + state.selectedDest.networks + "</span>" +
          "</div>" +
          '<div style="text-align:right;">' +
            '<div class="buy-op-price" data-usd="' + p.retail_usd + '">' + formatted + "</div>" +
            '<span style="font-size:0.7rem; color:var(--text-muted); font-weight:normal;">$' + Number(p.retail_usd).toFixed(2) + "</span>" +
          "</div>";

        card.addEventListener("click", function () {
          state.selectedPlan = p;
          renderPlans();
          updateCheckout();
          if (window.innerWidth <= 768) {
            var cCol = root.querySelector('[data-column="checkout"]');
            if (cCol) cCol.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        });

        planListEl.appendChild(card);
      });
    }

    function updateCheckout() {
      var d = state.selectedDest;
      var p = state.selectedPlan;
      if (!d || !p) return;

      if (detailFlag) detailFlag.textContent = d.flag || "🌐";
      if (detailName) detailName.textContent = d.name;
      if (detailBadge) detailBadge.textContent = d.badge || "4G/5G";
      if (detailDesc) detailDesc.textContent = d.description || "";
      if (specNetworks) specNetworks.textContent = d.networks || "Tier-1 5G/LTE Partner";
      if (specSpeed) specSpeed.textContent = d.speed || "4G LTE / 5G";
      if (specHotspot) specHotspot.textContent = d.hotspot || "Allowed";

      if (reviewDest) reviewDest.textContent = (d.flag || "") + " " + d.name;
      if (reviewPlan) reviewPlan.textContent = p.data_gb + " High-Speed Data";
      if (reviewValidity) reviewValidity.textContent = p.days + " Days";

      var formattedPrice = formatMoney(p.retail_usd);
      if (reviewPrice) {
        reviewPrice.setAttribute("data-usd", Number(p.retail_usd).toFixed(2));
        reviewPrice.textContent = formattedPrice;
      }

      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML =
          '<svg class="tg-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg> Generate Preview eSIM (' +
          formattedPrice +
          ")";
      }
    }

    if (destSearch) {
      destSearch.addEventListener("input", function () {
        renderDestinations();
      });
    }

    regionTabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        state.regionFilter = tab.getAttribute("data-region-filter") || "all";
        regionTabs.forEach(function (t) {
          t.className = t === tab ? "badge badge-brand" : "badge badge-neutral";
        });
        renderDestinations();
      });
    });

    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        if (!state.selectedDest || !state.selectedPlan) return;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span> <span>Provisioning eSIM Profile...</span>';

        fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            country_code: state.selectedDest.code,
            plan_id: state.selectedPlan.id
          })
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data && data.success) {
              if (window.toast) window.toast(data.message || "Preview eSIM generated!", "success");
              setTimeout(function () {
                window.location.reload();
              }, 800);
            } else {
              if (window.toast) window.toast((data && data.message) || "Failed to provision eSIM.", "error");
              submitBtn.disabled = false;
              updateCheckout();
            }
          })
          .catch(function () {
            if (window.toast) window.toast("Network error. Please try again.", "error");
            submitBtn.disabled = false;
            updateCheckout();
          });
      });
    }

    document.addEventListener("currencychange", function () {
      renderDestinations();
      renderPlans();
      updateCheckout();
    });

    renderDestinations();
    renderPlans();
    updateCheckout();
  }

  // =========================================================================
  // eSIM QR CODE & SETUP MODAL
  // =========================================================================
  function initEsimModal() {
    var modal = document.getElementById("esimQrModal");
    if (!modal) return;

    var qrImg = document.getElementById("esimQrImage");
    var subEl = document.getElementById("esimQrModalSub");
    var smdpEl = document.getElementById("esimSmdpVal");
    var actEl = document.getElementById("esimActCodeVal");
    var lpaEl = document.getElementById("esimLpaVal");
    var iccidEl = document.getElementById("esimIccidFooter");

    var btnCopySmdp = document.getElementById("btnCopySmdp");
    var btnCopyAct = document.getElementById("btnCopyActCode");
    var btnCopyLpa = document.getElementById("btnCopyLpa");

    function openQrModal(esim) {
      if (!esim) return;
      if (subEl) subEl.textContent = (esim.country_name || "Travel eSIM") + " • " + (esim.plan_label || "");
      if (smdpEl) smdpEl.textContent = esim.smdp_address || "smdp.io.tgsims.network";
      if (actEl) actEl.textContent = esim.activation_code || "";
      if (lpaEl) lpaEl.textContent = esim.lpa_string || "";
      if (iccidEl) iccidEl.textContent = esim.iccid || "";

      if (btnCopySmdp) btnCopySmdp.setAttribute("data-copy", esim.smdp_address || "");
      if (btnCopyAct) btnCopyAct.setAttribute("data-copy", esim.activation_code || "");
      if (btnCopyLpa) btnCopyLpa.setAttribute("data-copy", esim.lpa_string || "");

      if (qrImg) {
        var qrData = encodeURIComponent(esim.lpa_string || "LPA:1$smdp.io.tgsims.network$PREVIEW");
        qrImg.src = "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=" + qrData;
      }

      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
    }

    function closeQrModal() {
      modal.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");
    }

    document.addEventListener("click", function (e) {
      var openBtn = e.target.closest('[data-action="open-esim-qr"]');
      if (openBtn) {
        try {
          var esimObj = JSON.parse(openBtn.getAttribute("data-esim") || "{}");
          openQrModal(esimObj);
        } catch (err) {
          console.error(err);
        }
        return;
      }
      if (e.target.closest("[data-esim-modal-close]") || e.target === modal) {
        closeQrModal();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initEsimStore();
      initEsimModal();
    });
  } else {
    initEsimStore();
    initEsimModal();
  }
})();
