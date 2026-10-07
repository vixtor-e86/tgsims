/* ==========================================================================
   fund.js  -  Fund Your Wallet Page Interactions
   Supports 2 active payment gateways:
   1. Squad Checkout (Instant Bank Transfer, Debit Card & USSD in NGN)
   2. OXAPay Cryptocurrency ($1 minimum, BTC, USDT, ETH, etc.)
   ========================================================================== */
(function () {
  "use strict";

  var container = document.querySelector("[data-fund]");
  if (!container) return;

  var amountInput       = container.querySelector("[data-amount-input]");
  var amountSymbol      = container.querySelector("[data-amount-symbol]");
  var presetsContainer  = document.getElementById("amount-presets");
  var methodButtons     = container.querySelectorAll("[data-method]");
  var dedicatedFields   = container.querySelector("[data-dedicated-fields]");
  var cryptoFields      = container.querySelector("[data-crypto-fields]");
  var cardBankFields    = container.querySelector("[data-card-bank-fields]");
  var cryptoSelect      = container.querySelector("[data-crypto-select]");
  var submitBtn         = container.querySelector("[data-fund-submit]");
  var confirmLabel      = container.querySelector("[data-confirm-label]");
  var summaryAmount     = container.querySelector("[data-summary-amount]");
  var summaryFee        = container.querySelector("[data-summary-fee]");
  var summaryTotal      = container.querySelector("[data-summary-total]");
  var cryptoMinWarning  = document.getElementById("crypto-min-warning");
  var cryptoCurrEntered = document.getElementById("crypto-curr-entered");
  var orderSummaryBlock = document.getElementById("order-summary-block");

  // Crypto Modal elements
  var cryptoModal       = document.getElementById("crypto-payment-modal");
  var modalTitle        = document.getElementById("modal-crypto-title");
  var modalOrderId      = document.getElementById("modal-crypto-order-id");
  var modalStatusPill   = document.getElementById("crypto-status-pill");
  var modalStatusText   = document.getElementById("crypto-status-text");
  var modalQrContainer  = document.getElementById("crypto-qr-container");
  var modalAmount       = document.getElementById("crypto-modal-amount");
  var modalNetwork      = document.getElementById("crypto-modal-network");
  var btnOpenPage       = document.getElementById("btn-open-payment-page");
  var btnCheckStatus    = document.getElementById("btn-check-crypto-status");
  var closeBtns         = document.querySelectorAll("[data-close-crypto-modal]");

  // Configuration from data attributes
  var FEE_RATE         = parseFloat(container.getAttribute("data-fee-rate")) || 0.015;
  var squadActive      = container.getAttribute("data-squad-active") === "true";
  var cryptoActive     = container.getAttribute("data-crypto-active") === "true";
  var CRYPTO_MIN       = parseFloat(container.getAttribute("data-crypto-min")) || 1.0;
  var SQUAD_PUBLIC_KEY = container.getAttribute("data-squad-public-key") || "";
  var RATE             = parseFloat(container.getAttribute("data-ngn-per-usd")) || Number(window.TG_NGN_PER_USD) || 1350;

  var currentUSD       = 0;
  var currentNGN       = 0;
  var activePaymentId  = null;   // OXAPay track_id
  var activePayLink    = null;   // OXAPay hosted page URL
  var pollInterval     = null;

  function isUSD() {
    return !!(window.TgCurrency && window.TgCurrency.active === "USD");
  }

  function getActiveMethodId() {
    var active = container.querySelector("[data-method].is-active");
    return active ? active.getAttribute("data-method-id") : "card";
  }

  function syncSymbol() {
    var methodId = getActiveMethodId();
    if (amountSymbol) {
      if (methodId === "crypto" || isUSD()) {
        amountSymbol.textContent = "$";
      } else {
        amountSymbol.textContent = "₦";
      }
    }
  }

  function renderPresets() {
    if (!presetsContainer) return;

    var methodId = getActiveMethodId();
    var usdMode = isUSD() || methodId === "crypto";
    var presets = [];

    if (usdMode) {
      presets = [
        { label: "$1",  usd: 1.0 },
        { label: "$5",  usd: 5.0 },
        { label: "$10", usd: 10.0 },
        { label: "$20", usd: 20.0 },
        { label: "$50", usd: 50.0 }
      ];
    } else {
      presets = [
        { label: "₦1,000",  ngn: 1000 },
        { label: "₦5,000",  ngn: 5000 },
        { label: "₦10,000", ngn: 10000 },
        { label: "₦25,000", ngn: 25000 },
        { label: "₦50,000", ngn: 50000 }
      ];
    }

    presetsContainer.innerHTML = presets.map(function (p) {
      if (p.usd !== undefined) {
        return '<button type="button" class="preset-btn" data-preset-usd="' + p.usd + '">' + p.label + '</button>';
      } else {
        return '<button type="button" class="preset-btn" data-preset-ngn="' + p.ngn + '">' + p.label + '</button>';
      }
    }).join("");

    presetsContainer.querySelectorAll(".preset-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        presetsContainer.querySelectorAll(".preset-btn").forEach(function (b) { b.classList.remove("is-active"); });
        btn.classList.add("is-active");

        if (btn.hasAttribute("data-preset-usd")) {
          var uVal = parseFloat(btn.getAttribute("data-preset-usd")) || 0;
          currentUSD = uVal;
          currentNGN = uVal * RATE;
          if (amountInput) amountInput.value = uVal.toFixed(2);
        } else {
          var nVal = parseFloat(btn.getAttribute("data-preset-ngn")) || 0;
          currentNGN = nVal;
          currentUSD = nVal / RATE;
          if (amountInput) amountInput.value = Math.round(nVal).toString();
        }
        syncSummary();
      });
    });
  }

  function syncSummary() {
    var methodId = getActiveMethodId();
    var isCrypto = (methodId === "crypto");
    var usdMode = isUSD() || isCrypto;

    // 0% platform fee on crypto, 1.5% fee on Squad
    var effectiveFeeRate = isCrypto ? 0.0 : FEE_RATE;
    var feeUSD   = currentUSD * effectiveFeeRate;
    var totalUSD = currentUSD + feeUSD;

    var feeNGN   = currentNGN * effectiveFeeRate;
    var totalNGN = currentNGN + feeNGN;

    if (summaryAmount) {
      if (usdMode) {
        summaryAmount.textContent = "$" + currentUSD.toFixed(2) + " (≈ ₦" + Math.round(currentNGN).toLocaleString() + ")";
      } else {
        summaryAmount.textContent = "₦" + Math.round(currentNGN).toLocaleString() + " (≈ $" + currentUSD.toFixed(2) + ")";
      }
    }

    if (summaryFee) {
      if (isCrypto) {
        summaryFee.textContent = "0% (Free)";
      } else {
        summaryFee.textContent = usdMode
          ? "$" + feeUSD.toFixed(2) + " (1.5%)"
          : "₦" + Math.round(feeNGN).toLocaleString() + " (1.5%)";
      }
    }

    if (summaryTotal) {
      if (usdMode) {
        summaryTotal.textContent = "$" + totalUSD.toFixed(2) + " (≈ ₦" + Math.round(totalNGN).toLocaleString() + ")";
      } else {
        summaryTotal.textContent = "₦" + Math.round(totalNGN).toLocaleString() + " (≈ $" + totalUSD.toFixed(2) + ")";
      }
    }

    // Crypto minimum warning
    var isUnderCryptoMin = isCrypto && currentUSD > 0 && currentUSD < CRYPTO_MIN;
    if (cryptoMinWarning && cryptoCurrEntered) {
      if (isUnderCryptoMin) {
        cryptoMinWarning.style.display = "";
        cryptoCurrEntered.textContent = "$" + currentUSD.toFixed(2);
      } else {
        cryptoMinWarning.style.display = "none";
      }
    }

    // Button label & state
    if (confirmLabel) {
      if (isCrypto) {
        if (currentUSD <= 0) {
          confirmLabel.textContent = "Enter Amount to Deposit";
        } else if (isUnderCryptoMin) {
          confirmLabel.textContent = "Minimum $" + CRYPTO_MIN.toFixed(2) + " Required";
        } else {
          var optEl = cryptoSelect ? cryptoSelect.options[cryptoSelect.selectedIndex] : null;
          var coin = optEl ? (optEl.getAttribute("data-coin") || optEl.value || "Crypto") : "Crypto";
          confirmLabel.textContent = "Pay $" + currentUSD.toFixed(2) + " in " + coin;
        }
      } else {
        // Squad (Bank Transfer / Card)
        if (currentNGN < 100) {
          confirmLabel.textContent = "Enter Amount (Min ₦100)";
        } else {
          confirmLabel.textContent = "Pay ₦" + Math.round(totalNGN).toLocaleString() + " via Squad" + (usdMode ? " (≈ $" + totalUSD.toFixed(2) + ")" : "");
        }
      }
    }

    if (submitBtn) {
      var disabledCrypto = isCrypto && (currentUSD <= 0 || isUnderCryptoMin || !cryptoActive);
      var disabledSquad  = !isCrypto && (currentNGN < 100 || !squadActive);
      submitBtn.disabled = (disabledCrypto || disabledSquad);
    }
  }

  // Manual amount input handler
  if (amountInput) {
    amountInput.addEventListener("input", function () {
      var val = parseFloat(amountInput.value) || 0;
      var methodId = getActiveMethodId();
      var usdMode = isUSD() || methodId === "crypto";

      if (usdMode) {
        currentUSD = val;
        currentNGN = val * RATE;
      } else {
        currentNGN = val;
        currentUSD = val / RATE;
      }

      syncSummary();
      if (presetsContainer) {
        presetsContainer.querySelectorAll(".preset-btn").forEach(function (b) { b.classList.remove("is-active"); });
      }
    });
  }

  // Method switching
  function syncMethodFields() {
    var methodId = getActiveMethodId();
    if (dedicatedFields) dedicatedFields.style.display = (methodId === "dedicated") ? "" : "none";
    if (cryptoFields)    cryptoFields.style.display    = (methodId === "crypto")    ? "" : "none";
    if (cardBankFields)  cardBankFields.style.display  = (methodId === "card")      ? "" : "none";

    syncSymbol();
    renderPresets();

    currentUSD = 0;
    currentNGN = 0;
    if (amountInput) amountInput.value = "";
    syncSummary();
  }

  methodButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      methodButtons.forEach(function (b) { b.classList.remove("is-active"); });
      btn.classList.add("is-active");
      syncMethodFields();
    });
  });

  if (cryptoSelect) {
    cryptoSelect.addEventListener("change", function () { syncSummary(); });
  }

  // ---- COPY TO CLIPBOARD ----
  function copyText(val, btnEl, originalHtml) {
    if (!navigator.clipboard) {
      var ta = document.createElement("textarea");
      ta.value = val;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    } else {
      navigator.clipboard.writeText(val);
    }
    if (btnEl) {
      btnEl.innerHTML = "<span>Copied!</span>";
      setTimeout(function () { btnEl.innerHTML = originalHtml; }, 2000);
    }
  }

  window.copyToClipboard = function (val, btnEl) {
    var orig = btnEl ? btnEl.innerHTML : "";
    copyText(val, btnEl, orig);
    if (window.toast) window.toast("Copied to clipboard!", "success");
  };

  // ---- QR CODE GENERATION (QRServer with QuickChart fallback) ----
  function renderQRCode(url) {
    if (!modalQrContainer) return;
    var encodedUrl = encodeURIComponent(url);
    var primaryUrl = "https://api.qrserver.com/v1/create-qr-code/?size=190x190&margin=4&data=" + encodedUrl;
    var fallbackUrl = "https://quickchart.io/qr?size=190&text=" + encodedUrl;
    modalQrContainer.innerHTML = '<img src="' + primaryUrl + '" alt="Payment QR Code" style="width:190px;height:190px;display:block;margin:0 auto;border-radius:6px;" onerror="this.onerror=null;this.src=\'' + fallbackUrl + '\';" />';
  }

  // ---- CLOSE CRYPTO MODAL ----
  function closeCryptoModal() {
    if (cryptoModal) cryptoModal.classList.remove("is-open");
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
  }

  closeBtns.forEach(function (btn) { btn.addEventListener("click", closeCryptoModal); });
  if (cryptoModal) {
    cryptoModal.addEventListener("click", function (e) {
      if (e.target === cryptoModal) closeCryptoModal();
    });
  }

  // ---- CRYPTO STATUS POLLING ----
  function checkCryptoStatus(isManualClick) {
    if (!activePaymentId) return;

    if (isManualClick && btnCheckStatus) {
      btnCheckStatus.disabled = true;
      btnCheckStatus.textContent = "Checking blockchain…";
    }

    fetch("/api/payments/crypto/status/" + activePaymentId)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (isManualClick && btnCheckStatus) {
          btnCheckStatus.disabled = false;
          btnCheckStatus.textContent = "Check Status Now";
        }

        var status = (data.status || "").toLowerCase();
        if (data.is_completed || status === "paid") {
          // PAYMENT COMPLETED
          if (modalStatusPill) {
            modalStatusPill.style.background  = "rgba(16, 185, 129, 0.15)";
            modalStatusPill.style.color       = "#10b981";
            modalStatusPill.style.borderColor = "rgba(16, 185, 129, 0.35)";
          }
          if (modalStatusText) modalStatusText.textContent = "Payment Confirmed & Balance Credited!";
          if (btnCheckStatus) {
            btnCheckStatus.textContent = "Go to Wallet Overview";
            btnCheckStatus.className   = "btn btn-primary btn-block";
            btnCheckStatus.onclick     = function () { window.location.href = "/wallet"; };
          }
          if (btnOpenPage) btnOpenPage.style.display = "none";
          if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
          if (window.toast) window.toast("Deposit successfully credited to your wallet!", "success");
        } else if (status === "confirming") {
          if (modalStatusText) modalStatusText.textContent = "Detected on blockchain (confirming…)";
          if (modalStatusPill) {
            modalStatusPill.style.background  = "rgba(99, 102, 241, 0.15)";
            modalStatusPill.style.color       = "#6366f1";
            modalStatusPill.style.borderColor = "rgba(99, 102, 241, 0.35)";
          }
        } else if (status === "expired" || status === "failed" || status === "canceled" || status === "cancelled") {
          if (modalStatusText) modalStatusText.textContent = "Session expired or failed.";
          if (modalStatusPill) {
            modalStatusPill.style.background  = "rgba(239, 68, 68, 0.15)";
            modalStatusPill.style.color       = "#ef4444";
            modalStatusPill.style.borderColor = "rgba(239, 68, 68, 0.35)";
          }
          if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
        } else {
          if (modalStatusText) modalStatusText.textContent = "Waiting for transaction…";
        }
      })
      .catch(function (err) {
        console.warn("[OXAPay Polling] error:", err);
        if (isManualClick && btnCheckStatus) {
          btnCheckStatus.disabled = false;
          btnCheckStatus.textContent = "Check Status Now";
        }
      });
  }

  if (btnCheckStatus) {
    btnCheckStatus.addEventListener("click", function () { checkCryptoStatus(true); });
  }

  // ---- SUBMIT DEPOSIT HANDLER ----
  if (submitBtn) {
    submitBtn.addEventListener("click", function () {
      var methodId = getActiveMethodId();

      // =========================================================================
      // METHOD: CRYPTOCURRENCY (OXAPay)
      // =========================================================================
      if (methodId === "crypto") {
        if (currentUSD <= 0) {
          if (window.toast) window.toast("Please enter an amount to deposit.", "error");
          return;
        }
        if (currentUSD < CRYPTO_MIN) {
          if (window.toast) window.toast("Minimum crypto deposit is $" + CRYPTO_MIN.toFixed(2) + " USD.", "error");
          return;
        }

        var optEl            = cryptoSelect ? cryptoSelect.options[cryptoSelect.selectedIndex] : null;
        var selectedCurrency = optEl ? optEl.value : "USDT";
        var selectedNetwork  = optEl ? (optEl.getAttribute("data-network") || "TRON") : "TRON";

        submitBtn.disabled = true;
        var prevLabel = confirmLabel ? confirmLabel.textContent : "Confirm";
        if (confirmLabel) confirmLabel.textContent = "Generating Secure Payment Session…";

        fetch("/api/payments/crypto/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            amount:   currentUSD,
            currency: selectedCurrency,
            network:  selectedNetwork
          })
        })
          .then(function (res) { return res.json(); })
          .then(function (data) {
            submitBtn.disabled = false;
            if (confirmLabel) confirmLabel.textContent = prevLabel;

            if (!data.success) {
              if (window.toast) window.toast(data.message || "Failed to initialize crypto deposit.", "error", 6000);
              return;
            }

            activePaymentId = data.track_id;
            activePayLink   = data.pay_link;

            if (modalTitle)   modalTitle.textContent   = "Pay $" + data.amount_usd + " in " + data.currency;
            if (modalOrderId) modalOrderId.textContent = data.order_id || ("OP-" + data.track_id);
            if (modalAmount)  modalAmount.textContent  = "$" + parseFloat(data.amount_usd).toFixed(2);
            if (modalNetwork) modalNetwork.textContent = data.currency + " / " + (data.network || selectedNetwork);

            if (btnOpenPage) {
              btnOpenPage.href = data.pay_link || "#";
              btnOpenPage.style.display = "";
            }

            if (data.pay_link) {
              renderQRCode(data.pay_link);
            }

            if (modalStatusPill) {
              modalStatusPill.style.background  = "rgba(245, 158, 11, 0.15)";
              modalStatusPill.style.color       = "#f59e0b";
              modalStatusPill.style.borderColor = "rgba(245, 158, 11, 0.3)";
            }
            if (modalStatusText) modalStatusText.textContent = "Waiting for transaction…";

            if (btnCheckStatus) {
              btnCheckStatus.textContent = "Check Status Now";
              btnCheckStatus.className   = "btn btn-secondary btn-block";
              btnCheckStatus.onclick     = function () { checkCryptoStatus(true); };
            }

            if (cryptoModal) cryptoModal.classList.add("is-open");

            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(function () { checkCryptoStatus(false); }, 10000);
          })
          .catch(function () {
            submitBtn.disabled = false;
            if (confirmLabel) confirmLabel.textContent = prevLabel;
            if (window.toast) window.toast("Network error. Please try again.", "error");
          });
        return;
      }

      // =========================================================================
      // METHOD: SQUAD CHECKOUT (Bank Transfer / Card / USSD)
      // =========================================================================
      if (methodId === "card") {
        if (currentNGN < 100) {
          if (window.toast) window.toast("Please enter an amount of at least ₦100.", "error");
          return;
        }

        if (!squadActive || !SQUAD_PUBLIC_KEY) {
          if (window.toast) window.toast("Squad payment gateway is currently unavailable.", "error");
          return;
        }

        var totalNGN = currentNGN * (1 + FEE_RATE);

        submitBtn.disabled = true;
        var prevSquadLabel = confirmLabel ? confirmLabel.textContent : "Confirm";
        if (confirmLabel) confirmLabel.textContent = "Opening Secure Checkout…";

        fetch("/api/payments/squad/card/initiate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ amount_ngn: currentNGN })
        })
          .then(function (res) { return res.json(); })
          .then(function (data) {
            submitBtn.disabled = false;
            if (confirmLabel) confirmLabel.textContent = prevSquadLabel;

            if (!data.success) {
              if (window.toast) window.toast(data.message || "Failed to start payment session.", "error");
              return;
            }

            var userEmail = (window.TgUser && window.TgUser.email) || "";

            // Check if Squad inline SDK is loaded
            if (typeof window.squad !== "undefined") {
              try {
                var squadInstance = new window.squad({
                  onClose: function () {
                    if (window.toast) window.toast("Checkout window closed.", "info", 4000);
                  },
                  onSuccess: function (resp) {
                    if (window.toast) window.toast("Payment successful! Your wallet is being credited...", "success", 6000);
                    setTimeout(function () { window.location.href = "/wallet"; }, 2000);
                  },
                  onpayment: function (resp) {
                    if (resp && (resp.transaction_status === "success" || resp.status === "success")) {
                      if (window.toast) window.toast("Payment successful! Your wallet is being credited...", "success", 6000);
                      setTimeout(function () { window.location.href = "/wallet"; }, 2000);
                    }
                  },
                  key: SQUAD_PUBLIC_KEY,
                  email: userEmail,
                  amount: Math.round(totalNGN * 100), // in kobo
                  currency_code: "NGN",
                  transaction_ref: data.reference,
                  payment_channels: ["card", "bank", "ussd", "transfer"]
                });
                squadInstance.setup();
                squadInstance.open();
                return;
              } catch (sdkErr) {
                console.error("[Squad SDK error]:", sdkErr);
              }
            }

            // Fallback if SDK modal didn't open
            if (data.checkout_url) {
              window.location.href = data.checkout_url;
            } else {
              if (window.toast) window.toast("Payment session created (Ref: " + data.reference + ").", "info");
            }
          })
          .catch(function (err) {
            submitBtn.disabled = false;
            if (confirmLabel) confirmLabel.textContent = prevSquadLabel;
            if (window.toast) window.toast("Network error. Please try again.", "error");
          });
      }
    });
  }

  // Re-render on currency switch
  document.addEventListener("currencychange", function () {
    syncSymbol();
    renderPresets();
    syncSummary();
  });

  // Initial setup
  syncMethodFields();
})();
