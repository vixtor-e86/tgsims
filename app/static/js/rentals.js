/* ==========================================================================
   rentals.js  -  Dedicated Long-Term Number Rentals (3-List / 3-Step Layout)
   List 1: Service selection (10 core services, Universal Number highlighted)
   List 2: Rental Duration (7 tiers: 1, 3, 7, 14, 30, 90, 365 days)
   List 3: Dedicated Line Specs Breakdown & Review Checkout
   Includes: Mobile Stepper navigation, Mailbox Viewer, and Line Renewal Modal
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

  function escapeAndLinkify(text) {
    if (!text) return "";
    var div = document.createElement("div");
    div.textContent = text;
    var escaped = div.innerHTML;
    return escaped.replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer" style="color:var(--brand); text-decoration:underline; word-break:break-all;">$1</a>'
    );
  }

  var DURATION_TIERS = [
    { days: 1, label: "1 Day", sub: "Fast Day Pass • Instant OTPs", badge: "1 Day" },
    { days: 3, label: "3 Days", sub: "Popular Short-Term • Real Cellular", badge: "3 Days" },
    { days: 7, label: "7 Days (1 Wk)", sub: "Standard Project • Unlimited Codes", badge: "1 Week" },
    { days: 14, label: "14 Days (2 Wks)", sub: "Extended Project • Private Line", badge: "2 Weeks" },
    { days: 30, label: "30 Days (1 Mo)", sub: "Monthly Line • Full Account Hold", badge: "1 Month" },
    { days: 90, label: "90 Days (3 Mos)", sub: "Quarterly Retention • Continuous OTPs", badge: "3 Months" },
    { days: 365, label: "365 Days (1 Yr)", sub: "Annual Permanent Line • Best Value", badge: "1 Year" }
  ];

  function initRentals() {
    var root = document.querySelector("[data-rental]");
    if (!root) return;

    var endpoint = root.getAttribute("data-endpoint") || "/api/rent-number";

    var catalog = [];
    try {
      var raw = JSON.parse(root.getAttribute("data-catalog") || "[]");
      if (Array.isArray(raw)) catalog = raw;
    } catch (e) {
      catalog = [];
    }
    if (!catalog.length) return;

    // Elements
    var serviceListEl = root.querySelector("[data-service-list]");
    var durationListEl = root.querySelector("[data-duration-list]");
    var serviceSearch = root.querySelector("[data-service-search]");
    var serviceCount = root.querySelector("[data-service-count]");
    var durationCount = root.querySelector("[data-duration-count]");

    // Review Card Elements
    var reviewService = root.querySelector("[data-review-service]");
    var reviewDuration = root.querySelector("[data-review-duration]");
    var reviewPrice = root.querySelector("[data-review-price]");
    var submitBtn = root.querySelector("[data-rental-submit]");

    // Mobile Stepper Tabs & Pills
    var tabService = root.querySelector('[data-mobile-tab="service"]');
    var tabDuration = root.querySelector('[data-mobile-tab="duration"]');
    var tabCheckout = root.querySelector('[data-mobile-tab="checkout"]');

    var stepSelService = root.querySelector("[data-step-selected-service]");
    var stepSelDuration = root.querySelector("[data-step-selected-duration]");
    var stepSelPay = root.querySelector("[data-step-selected-pay]");

    var pillService = root.querySelector('[data-step-pill="service"]');
    var pillDuration = root.querySelector('[data-step-pill="duration"]');
    var pillCheckout = root.querySelector('[data-step-pill="checkout"]');

    // Mobile Back Buttons
    var backServiceBtn = root.querySelector('[data-mobile-back="service"]');
    var backDurationBtn = root.querySelector('[data-mobile-back="duration"]');

    // Active state
    var state = {
      selectedService: catalog[0], // Universal by default
      selectedDuration: 3,         // 3 days by default
      currentMobileStep: "service"
    };

    function setMobileStep(step) {
      state.currentMobileStep = step;
      root.setAttribute("data-mobile-active", step);

      var tabs = [tabService, tabDuration, tabCheckout];
      tabs.forEach(function (t) { if (t) t.classList.remove("is-active", "is-complete"); });

      if (step === "service") {
        if (tabService) tabService.classList.add("is-active");
      } else if (step === "duration") {
        if (tabService) tabService.classList.add("is-complete");
        if (tabDuration) tabDuration.classList.add("is-active");
      } else if (step === "checkout") {
        if (tabService) tabService.classList.add("is-complete");
        if (tabDuration) tabDuration.classList.add("is-complete");
        if (tabCheckout) tabCheckout.classList.add("is-active");
      }

      // Scroll container into view smoothly on mobile if needed
      if (window.innerWidth <= 768) {
        var offsetTop = root.getBoundingClientRect().top + window.pageYOffset - 80;
        if (window.pageYOffset > offsetTop) {
          window.scrollTo({ top: offsetTop, behavior: "smooth" });
        }
      }
    }

    if (tabService) tabService.addEventListener("click", function () { setMobileStep("service"); });
    if (tabDuration) tabDuration.addEventListener("click", function () { setMobileStep("duration"); });
    if (tabCheckout) tabCheckout.addEventListener("click", function () { setMobileStep("checkout"); });
    if (backServiceBtn) backServiceBtn.addEventListener("click", function () { setMobileStep("service"); });
    if (backDurationBtn) backDurationBtn.addEventListener("click", function () { setMobileStep("duration"); });

    function getPriceInfo(svc, days) {
      if (!svc || !svc.pricing) return { retail_usd: 0, formatted: "₦0.00" };
      var tier = svc.pricing[String(days)];
      if (!tier) return { retail_usd: 0, formatted: "₦0.00" };
      return {
        retail_usd: tier.retail_usd,
        formatted: formatMoney(tier.retail_usd)
      };
    }

    function renderServices(filterQuery) {
      if (!serviceListEl) return;
      var q = (filterQuery || "").toLowerCase().trim();
      serviceListEl.innerHTML = "";

      var filtered = catalog.filter(function (s) {
        if (!q) return true;
        return (
          (s.name || "").toLowerCase().indexOf(q) !== -1 ||
          (s.code || "").toLowerCase().indexOf(q) !== -1 ||
          (s.description || "").toLowerCase().indexOf(q) !== -1
        );
      });

      if (serviceCount) serviceCount.textContent = filtered.length;

      if (!filtered.length) {
        serviceListEl.innerHTML = '<div class="buy-empty-msg">No rental services match your search.</div>';
        return;
      }

      filtered.forEach(function (svc) {
        var row = document.createElement("button");
        row.type = "button";
        row.className = "buy-list-row" + (state.selectedService.code === svc.code ? " is-active" : "");

        var initialLetter = (svc.name || "S").charAt(0).toUpperCase();
        var iconHtml = svc.code === "allservices"
          ? '<svg class="tg-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24"/><path d="m14.83 9.17 4.24-4.24"/><path d="m14.83 14.83 4.24 4.24"/><path d="m9.17 14.83-4.24 4.24"/></svg>'
          : '<svg class="tg-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>';

        var badgeHtml = "";
        if (svc.badge) {
          badgeHtml = '<span class="buy-list-badge-core" style="background:rgba(37,99,235,0.12); color:var(--brand);">' + svc.badge + "</span>";
        }

        // Show starting price (1-day price)
        var p1 = getPriceInfo(svc, 1);

        row.innerHTML =
          '<div class="buy-list-row-left">' +
            '<div style="width:32px; height:32px; border-radius:var(--r-md); background:rgba(37,99,235,0.08); color:var(--brand); display:grid; place-items:center; flex-shrink:0;">' +
              iconHtml +
            "</div>" +
            '<div class="buy-list-text">' +
              '<div style="display:flex; align-items:center; gap:6px;">' +
                '<span class="buy-list-primary">' + svc.name + "</span>" +
                badgeHtml +
              "</div>" +
              '<span class="buy-list-secondary">' + (svc.description || "100% Dedicated Non-VoIP Cellular Line") + "</span>" +
            "</div>" +
          "</div>" +
          '<div class="buy-list-meta">' +
            '<span class="buy-list-price" style="font-size:0.78rem; color:var(--text-muted); font-weight:600;">From ' + p1.formatted + "</span>" +
          "</div>";

        row.addEventListener("click", function () {
          state.selectedService = svc;
          renderServices(serviceSearch ? serviceSearch.value : "");
          renderDurations();
          updateCheckout();
          setMobileStep("duration");
        });

        serviceListEl.appendChild(row);
      });
    }

    function renderDurations() {
      if (!durationListEl) return;
      durationListEl.innerHTML = "";

      if (durationCount) durationCount.textContent = DURATION_TIERS.length + " Tiers";

      DURATION_TIERS.forEach(function (tier) {
        var pInfo = getPriceInfo(state.selectedService, tier.days);
        var isSelected = state.selectedDuration === tier.days;

        var card = document.createElement("div");
        card.className = "buy-op-card" + (isSelected ? " is-active" : "");

        card.innerHTML =
          '<div class="buy-op-info">' +
            '<div class="buy-op-name">' +
              "<span>" + tier.label + "</span>" +
              '<span class="badge badge-brand badge-xs" style="font-size:0.68rem; padding:1px 6px;">' + tier.badge + "</span>" +
            "</div>" +
            '<span class="buy-op-stock">' + tier.sub + "</span>" +
          "</div>" +
          '<div style="text-align:right;">' +
            '<div class="buy-op-price">' + pInfo.formatted + "</div>" +
            '<span style="font-size:0.7rem; color:var(--text-muted); font-weight:normal;">$' + pInfo.retail_usd.toFixed(2) + "</span>" +
          "</div>";

        card.addEventListener("click", function () {
          state.selectedDuration = tier.days;
          renderDurations();
          updateCheckout();
          setMobileStep("checkout");
        });

        durationListEl.appendChild(card);
      });
    }

    function updateCheckout() {
      var svc = state.selectedService;
      var days = state.selectedDuration;
      var pInfo = getPriceInfo(svc, days);

      if (reviewService) reviewService.textContent = svc.name;
      var durationTierObj = DURATION_TIERS.find(function (t) { return t.days === days; });
      var durationLabel = durationTierObj ? durationTierObj.label : days + " Days";

      if (reviewDuration) reviewDuration.textContent = durationLabel;

      if (reviewPrice) {
        reviewPrice.setAttribute("data-usd", pInfo.retail_usd.toFixed(2));
        reviewPrice.textContent = pInfo.formatted;
      }

      if (stepSelService) stepSelService.textContent = svc.name;
      if (stepSelDuration) stepSelDuration.textContent = durationLabel;
      if (stepSelPay) stepSelPay.textContent = pInfo.formatted;

      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML =
          '<svg class="tg-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg> Rent Dedicated Line (' + pInfo.formatted + ")";
      }
    }

    if (serviceSearch) {
      serviceSearch.addEventListener("input", function () {
        renderServices(serviceSearch.value);
      });
    }

    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        var svc = state.selectedService;
        var days = state.selectedDuration;
        var pInfo = getPriceInfo(svc, days);

        submitBtn.disabled = true;
        submitBtn.innerHTML =
          '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="margin-right:8px;"></span> Reserving Private Carrier Line...';

        fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            service_code: svc.code,
            duration_days: days
          })
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.success) {
              if (window.toast) window.toast(data.message || "Dedicated number rented successfully!", "success");
              setTimeout(function () {
                window.location.reload();
              }, 1000);
            } else {
              if (window.toast) window.toast(data.message || "Failed to allocate number.", "error");
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

    // Currency update listener
    document.addEventListener("currencychange", function () {
      renderServices(serviceSearch ? serviceSearch.value : "");
      renderDurations();
      updateCheckout();
    });

    // Initial render
    renderServices("");
    renderDurations();
    updateCheckout();
  }

  // =========================================================================
  // RENTAL SMS MAILBOX VIEWER MODAL
  // =========================================================================
  var activeRentalMailboxId = null;
  var rentalSmsModal = document.getElementById("rentalSmsModal");
  var rentalSmsFeed = document.getElementById("rentalSmsFeed");
  var smsModalSubtitle = document.getElementById("smsModalSubtitle");
  var btnRefreshRentalSms = document.getElementById("btnRefreshRentalSms");

  function openRentalMailboxModal(rentalId, phone, serviceName) {
    activeRentalMailboxId = rentalId;
    if (smsModalSubtitle) {
      smsModalSubtitle.textContent = (serviceName || "Dedicated Line") + " • " + (phone || "US Private Line");
    }
    if (rentalSmsFeed) {
      rentalSmsFeed.innerHTML =
        '<div style="text-align:center; padding:var(--sp-6); color:var(--text-dim); font-size:var(--fs-sm);">' +
          '<div style="margin-bottom:8px;"><span class="spinner-border spinner-border-sm"></span></div>' +
          "Checking incoming messages from carrier line..." +
        "</div>";
    }
    if (rentalSmsModal) {
      rentalSmsModal.classList.add("is-open");
      document.body.style.overflow = "hidden";
    }
    fetchRentalSms(rentalId);
  }

  function fetchRentalSms(rentalId) {
    if (!rentalId || !rentalSmsFeed) return;
    if (btnRefreshRentalSms) {
      btnRefreshRentalSms.disabled = true;
      btnRefreshRentalSms.textContent = "Checking...";
    }

    fetch("/api/check-rental-sms/" + encodeURIComponent(rentalId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (btnRefreshRentalSms) {
          btnRefreshRentalSms.disabled = false;
          btnRefreshRentalSms.innerHTML =
            '<svg class="tg-ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg> Refresh';
        }

        if (data.success && data.messages && data.messages.length > 0) {
          var html = "";
          data.messages.forEach(function (m) {
            html += '<div style="background:var(--surface-2); border:1px solid var(--border); border-radius:var(--r-md); padding:var(--sp-3) var(--sp-4); text-align:left; margin-bottom:8px;">';
            html += '  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">';
            html += '    <span class="badge badge-brand badge-xs" style="font-size:0.75rem; font-weight:700;">' + (m.sender || "Verification") + "</span>";
            html += '    <span class="td-dim" style="font-size:0.72rem; font-family:monospace;">' + (m.received_at ? m.received_at.split(".")[0].replace("T", " ") : "Just now") + "</span>";
            html += "  </div>";
            if (m.sms_code) {
              html += '  <div style="display:flex; align-items:center; gap:8px; margin:8px 0;">';
              html += '    <span class="code-chip" style="font-size:1.2rem; font-weight:800; letter-spacing:0.04em;">' + m.sms_code + "</span>";
              html += '    <button class="copy-btn" data-copy="' + m.sms_code + '" type="button" aria-label="Copy verification code" title="Copy OTP code"><svg class="tg-ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>';
              html += "  </div>";
            }
            html += '  <p style="font-size:var(--fs-xs); color:var(--text); margin:0; line-height:1.5; white-space:pre-wrap;">' + escapeAndLinkify(m.full_text || "") + "</p>";
            html += "</div>";
          });
          rentalSmsFeed.innerHTML = html;
        } else {
          rentalSmsFeed.innerHTML =
            '<div style="text-align:center; padding:var(--sp-8) var(--sp-4); color:var(--text-dim); font-size:var(--fs-sm);">' +
              '<div style="font-weight:600; color:var(--text); margin-bottom:4px;">No verification SMS received yet</div>' +
              '<span style="font-size:0.75rem; color:var(--text-muted);">Trigger your verification code on your app or website and click Refresh.</span>' +
            "</div>";
        }
      })
      .catch(function () {
        if (btnRefreshRentalSms) {
          btnRefreshRentalSms.disabled = false;
          btnRefreshRentalSms.innerHTML = "Refresh";
        }
        rentalSmsFeed.innerHTML =
          '<div style="text-align:center; padding:var(--sp-6); color:var(--text-danger); font-size:var(--fs-sm);">' +
            "Could not connect to SMS feed. Click Refresh to retry." +
          "</div>";
      });
  }

  if (btnRefreshRentalSms) {
    btnRefreshRentalSms.addEventListener("click", function () {
      if (activeRentalMailboxId) fetchRentalSms(activeRentalMailboxId);
    });
  }

  document.querySelectorAll("[data-modal-sms-close]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (rentalSmsModal) {
        rentalSmsModal.classList.remove("is-open");
        document.body.style.overflow = "";
      }
    });
  });

  // =========================================================================
  // RENTAL LINE RENEWAL MODAL
  // =========================================================================
  var rentalRenewalModal = document.getElementById("rentalRenewalModal");
  var renewalTargetId = null;
  var renewalTargetPhone = null;
  var renewalTargetService = null;
  var renewalSelectedDuration = 3;

  var renewalModalTitle = document.getElementById("renewalModalTitle");
  var renewalModalSubtitle = document.getElementById("renewalModalSubtitle");
  var renewalPriceDisplay = document.getElementById("renewalPriceDisplay");
  var btnConfirmRenewal = document.getElementById("btnConfirmRenewal");
  var renewalDurationGrid = document.getElementById("renewalDurationGrid");

  function openRenewalModal(rentalId, phone, serviceName, serviceCode, currentDuration) {
    renewalTargetId = rentalId;
    renewalTargetPhone = phone;
    renewalTargetService = serviceCode || "allservices";
    renewalSelectedDuration = parseInt(currentDuration, 10) || 3;

    if (renewalModalSubtitle) {
      renewalModalSubtitle.textContent = (serviceName || "Dedicated Line") + " • " + (phone || "");
    }

    renderRenewalDurationOptions();
    updateRenewalPrice();

    if (rentalRenewalModal) {
      rentalRenewalModal.classList.add("is-open");
      document.body.style.overflow = "hidden";
    }
  }

  function closeRenewalModal() {
    if (rentalRenewalModal) {
      rentalRenewalModal.classList.remove("is-open");
      document.body.style.overflow = "";
    }
  }

  function getCatalogItem(code) {
    var rawCatalog = window.TG_RENTAL_CATALOG || [];
    var matched = rawCatalog.find(function (s) {
      return (s.code || "").toLowerCase() === (code || "").toLowerCase();
    });
    return matched || rawCatalog[0] || null;
  }

  function renderRenewalDurationOptions() {
    if (!renewalDurationGrid) return;
    renewalDurationGrid.innerHTML = "";

    DURATION_TIERS.forEach(function (tier) {
      var btn = document.createElement("button");
      btn.type = "button";
      var isAct = renewalSelectedDuration === tier.days;
      btn.className = "btn btn-sm " + (isAct ? "btn-primary" : "btn-secondary");
      btn.style.cssText = "display:flex; flex-direction:column; align-items:center; justify-content:center; padding:8px 6px; min-height:48px; border-radius:var(--r-md);";

      btn.innerHTML =
        '<span style="font-weight:700; font-size:0.82rem;">' + tier.label + "</span>" +
        '<span style="font-size:0.65rem; opacity:0.85;">' + tier.badge + "</span>";

      btn.addEventListener("click", function () {
        renewalSelectedDuration = tier.days;
        renderRenewalDurationOptions();
        updateRenewalPrice();
      });

      renewalDurationGrid.appendChild(btn);
    });
  }

  function updateRenewalPrice() {
    var svc = getCatalogItem(renewalTargetService);
    var usd = 3.00;
    if (svc && svc.pricing && svc.pricing[String(renewalSelectedDuration)]) {
      usd = svc.pricing[String(renewalSelectedDuration)].retail_usd;
    }

    if (renewalPriceDisplay) {
      renewalPriceDisplay.setAttribute("data-usd", usd.toFixed(2));
      renewalPriceDisplay.textContent = formatMoney(usd) + " ($" + usd.toFixed(2) + ")";
    }

    if (btnConfirmRenewal) {
      btnConfirmRenewal.disabled = false;
      btnConfirmRenewal.textContent = "Confirm & Renew (" + formatMoney(usd) + ")";
    }
  }

  if (btnConfirmRenewal) {
    btnConfirmRenewal.addEventListener("click", function () {
      if (!renewalTargetId) return;

      btnConfirmRenewal.disabled = true;
      btnConfirmRenewal.innerHTML =
        '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="margin-right:6px;"></span> Extending Line...';

      fetch("/api/rent-number/renew", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rental_id: renewalTargetId,
          duration_days: renewalSelectedDuration
        })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.success) {
            closeRenewalModal();
            if (window.toast) window.toast(data.message || "Number renewed successfully!", "success");
            setTimeout(function () {
              window.location.reload();
            }, 800);
          } else {
            if (window.toast) window.toast(data.message || "Failed to renew line.", "error");
            btnConfirmRenewal.disabled = false;
            updateRenewalPrice();
          }
        })
        .catch(function () {
          if (window.toast) window.toast("Failed to connect to server. Please try again.", "error");
          btnConfirmRenewal.disabled = false;
          updateRenewalPrice();
        });
    });
  }

  document.querySelectorAll("[data-modal-renewal-close]").forEach(function (btn) {
    btn.addEventListener("click", closeRenewalModal);
  });

  // Global click delegate for Mailbox and Renew buttons across pages
  document.addEventListener("click", function (e) {
    var mailboxBtn = e.target.closest('[data-action="view-rental-mailbox"], [data-action="view-rental-sms"]');
    if (mailboxBtn) {
      var rId = mailboxBtn.dataset.id;
      var rPhone = mailboxBtn.dataset.phone;
      var rSvc = mailboxBtn.dataset.service;
      openRentalMailboxModal(rId, rPhone, rSvc);
      return;
    }

    var renewBtn = e.target.closest('[data-action="renew-rental-btn"]');
    if (renewBtn) {
      var renId = renewBtn.dataset.id;
      var renPhone = renewBtn.dataset.phone;
      var renSvc = renewBtn.dataset.service;
      var renCode = renewBtn.dataset.serviceCode || "allservices";
      var renDays = renewBtn.dataset.duration || 3;
      openRenewalModal(renId, renPhone, renSvc, renCode, renDays);
      return;
    }
  });

  // Export functions to window
  window.TgRentals = {
    init: initRentals,
    openMailbox: openRentalMailboxModal,
    openRenewal: openRenewalModal
  };

  document.addEventListener("DOMContentLoaded", initRentals);
})();
