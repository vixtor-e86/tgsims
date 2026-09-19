/* ==========================================================================
   fund.js  -  Fund Your Wallet Page Interactions & Enterprise Crypto Gateway
   - Preset amount pills (set USD canonical, render active currency)
   - Manual amount entry (user types active currency, convert to USD)
   - Payment method cards (Card, Crypto, Bank Transfer)
   - Dynamic 0% fee for Crypto, 1.5% fee for Card
   - NOWPayments Crypto Modal with dynamic QR code & 1-click clipboard copy
   - Real-time blockchain status polling with idempotency & instant balance credit
   ========================================================================== */
(function () {
  "use strict";

  var container = document.querySelector("[data-fund]");
  if (!container) return;

  var amountInput = container.querySelector("[data-amount-input]");
  var amountSymbol = container.querySelector("[data-amount-symbol]");
  var presetButtons = container.querySelectorAll("[data-preset]");
  var methodButtons = container.querySelectorAll("[data-method]");
  var cardFields = container.querySelector("[data-card-fields]");
  var cryptoFields = container.querySelector("[data-crypto-fields]");
  var bankFields = container.querySelector("[data-bank-fields]");
  var cryptoSelect = container.querySelector("[data-crypto-select]");
  var submitBtn = container.querySelector("[data-fund-submit]");
  var confirmLabel = container.querySelector("[data-confirm-label]");
  var summaryAmount = container.querySelector("[data-summary-amount]");
  var summaryFee = container.querySelector("[data-summary-fee]");
  var summaryTotal = container.querySelector("[data-summary-total]");
  var defaultPresets = container.querySelector("[data-default-presets]");
  var cryptoPresets = container.querySelector("[data-crypto-presets]");
  var cryptoMinWarning = document.getElementById("crypto-min-warning");
  var cryptoCurrEntered = document.getElementById("crypto-curr-entered");

  // Modal elements
  var cryptoModal = document.getElementById("crypto-payment-modal");
  var modalTitle = document.getElementById("modal-crypto-title");
  var modalOrderId = document.getElementById("modal-crypto-order-id");
  var modalStatusPill = document.getElementById("crypto-status-pill");
  var modalStatusText = document.getElementById("crypto-status-text");
  var modalQrCode = document.getElementById("crypto-qr-code");
  var modalAmount = document.getElementById("crypto-modal-amount");
  var modalAddress = document.getElementById("crypto-modal-address");
  var modalNetwork = document.getElementById("crypto-modal-network");
  var noticeSymbol = document.getElementById("crypto-notice-symbol");
  var noticeNetwork = document.getElementById("crypto-notice-network");
  var btnCopyAmount = document.getElementById("btn-copy-amount");
  var btnCopyAddress = document.getElementById("btn-copy-address");
  var btnCheckStatus = document.getElementById("btn-check-crypto-status");
  var closeBtns = document.querySelectorAll("[data-close-crypto-modal]");

  var FEE_RATE = parseFloat(container.getAttribute("data-fee-rate")) || 0.015;
  var currentUSD = 0; // Canonical amount in USD
  var activePaymentId = null;
  var pollInterval = null;
  var currentPayAmountRaw = "";
  var currentAddressRaw = "";

  function cur() { return window.TgCurrency || { rate: 1600, symbol: "₦", format: function(v){ return "₦" + v.toFixed(2); }, render: function(){} }; }

  function getActiveMethodId() {
    var active = container.querySelector("[data-method].is-active");
    return active ? active.getAttribute("data-method-id") : "card";
  }

  // Reflect active currency symbol next to amount input
  function syncSymbol() {
    if (amountSymbol) amountSymbol.textContent = cur().symbol;
  }

  // Show active-currency equivalent of currentUSD in input
  function syncInput() {
    if (!amountInput) return;
    var displayValue = currentUSD * cur().rate;
    amountInput.value = displayValue > 0 ? displayValue.toFixed(2) : "";
  }

  // Recompute deposit / fee / total and confirm-button label
  function syncSummary() {
    var methodId = getActiveMethodId();
    // 0% fee on crypto and direct bank; 1.5% on card
    var effectiveFeeRate = (methodId === "crypto" || methodId === "bank") ? 0.0 : FEE_RATE;
    var feeUSD = currentUSD * effectiveFeeRate;
    var totalUSD = currentUSD + feeUSD;

    if (summaryAmount) summaryAmount.setAttribute("data-usd", currentUSD.toFixed(4));
    if (summaryFee) summaryFee.setAttribute("data-usd", feeUSD.toFixed(4));
    if (summaryTotal) summaryTotal.setAttribute("data-usd", totalUSD.toFixed(4));
    cur().render(container);

    var isCrypto = (methodId === "crypto");
    var isUnderCryptoMin = isCrypto && currentUSD > 0 && currentUSD < 19.999;

    if (cryptoMinWarning && cryptoCurrEntered) {
      if (isUnderCryptoMin) {
        cryptoMinWarning.style.display = "";
        var valFormatted = "$" + currentUSD.toFixed(2);
        if (cur().symbol !== "$") {
          valFormatted += " (≈ " + cur().format(currentUSD * cur().rate, { decimals: 0 }) + ")";
        }
        cryptoCurrEntered.textContent = valFormatted;
      } else {
        cryptoMinWarning.style.display = "none";
      }
    }

    if (confirmLabel) {
      if (currentUSD <= 0) {
        confirmLabel.textContent = "Confirm Deposit";
      } else if (isUnderCryptoMin) {
        confirmLabel.textContent = "Minimum $20.00 Required for Crypto";
      } else if (isCrypto) {
        confirmLabel.textContent = "Generate " + getSelectedCryptoName() + " Deposit Address";
      } else if (methodId === "bank") {
        confirmLabel.textContent = "View Bank Transfer Details (" + cur().format(totalUSD, { decimals: 2 }) + ")";
      } else {
        confirmLabel.textContent = "Confirm Deposit of " + cur().format(totalUSD, { decimals: 2 });
      }
    }
    if (submitBtn) {
      submitBtn.disabled = (currentUSD <= 0 || isUnderCryptoMin);
    }
  }

  function getSelectedCryptoName() {
    if (!cryptoSelect) return "Crypto";
    var opt = cryptoSelect.options[cryptoSelect.selectedIndex];
    return opt ? (opt.getAttribute("data-symbol") || "Crypto") : "Crypto";
  }

  function clearPresetActive() {
    presetButtons.forEach(function (b) { b.classList.remove("is-active"); });
  }

  // Preset pills: set canonical USD
  presetButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      currentUSD = parseFloat(btn.getAttribute("data-usd")) || 0;
      syncInput();
      syncSummary();
      clearPresetActive();
      btn.classList.add("is-active");
    });
  });

  // Manual entry: user types in active currency -> convert to USD
  if (amountInput) {
    amountInput.addEventListener("input", function () {
      var displayValue = parseFloat(amountInput.value) || 0;
      currentUSD = displayValue / cur().rate;
      syncSummary();
      clearPresetActive();
    });
  }

  // Method switching: toggle Card, Crypto, and Bank sections
  function syncMethodFields() {
    var methodId = getActiveMethodId();
    if (cardFields) cardFields.style.display = (methodId === "card") ? "" : "none";
    if (cryptoFields) cryptoFields.style.display = (methodId === "crypto") ? "" : "none";
    if (bankFields) bankFields.style.display = (methodId === "bank") ? "" : "none";

    // Toggle presets between fiat/card and dedicated crypto amounts
    if (defaultPresets) defaultPresets.style.display = (methodId === "crypto") ? "none" : "";
    if (cryptoPresets) cryptoPresets.style.display = (methodId === "crypto") ? "" : "none";

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
    cryptoSelect.addEventListener("change", function () {
      syncSummary();
    });
  }

  // Copy to clipboard helper
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

  if (btnCopyAmount) {
    var origAmountHtml = btnCopyAmount.innerHTML;
    btnCopyAmount.addEventListener("click", function () {
      copyText(currentPayAmountRaw, btnCopyAmount, origAmountHtml);
      if (window.toast) window.toast("Exact crypto amount copied to clipboard.", "info");
    });
  }

  if (btnCopyAddress) {
    var origAddrHtml = btnCopyAddress.innerHTML;
    btnCopyAddress.addEventListener("click", function () {
      copyText(currentAddressRaw, btnCopyAddress, origAddrHtml);
      if (window.toast) window.toast("Deposit address copied to clipboard.", "info");
    });
  }

  // Close modal controls
  function closeCryptoModal() {
    if (cryptoModal) cryptoModal.classList.remove("is-open");
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  closeBtns.forEach(function (btn) {
    btn.addEventListener("click", closeCryptoModal);
  });

  if (cryptoModal) {
    cryptoModal.addEventListener("click", function (e) {
      if (e.target === cryptoModal) closeCryptoModal();
    });
  }

  // Real-time status polling & check status
  function checkPaymentStatus(isManualClick) {
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
        if (data.is_completed || status === "finished" || status === "confirmed" || status === "sending") {
          // PAYMENT COMPLETED
          if (modalStatusPill) {
            modalStatusPill.style.background = "rgba(16, 185, 129, 0.15)";
            modalStatusPill.style.color = "#10b981";
            modalStatusPill.style.borderColor = "rgba(16, 185, 129, 0.35)";
          }
          if (modalStatusText) {
            modalStatusText.textContent = "Payment Confirmed & Balance Credited!";
          }
          if (btnCheckStatus) {
            btnCheckStatus.textContent = "Go to Wallet Overview";
            btnCheckStatus.className = "btn btn-primary btn-block";
            btnCheckStatus.onclick = function () {
              window.location.href = "/wallet";
            };
          }
          if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
          }
          if (window.toast) {
            window.toast("Deposit successfully credited to your wallet balance!", "success");
          }
        } else if (status === "confirming") {
          if (modalStatusText) modalStatusText.textContent = "Detected on blockchain (confirming…)";
          if (modalStatusPill) {
            modalStatusPill.style.background = "rgba(99, 102, 241, 0.15)";
            modalStatusPill.style.color = "#6366f1";
            modalStatusPill.style.borderColor = "rgba(99, 102, 241, 0.35)";
          }
        } else if (status === "failed" || status === "expired") {
          if (modalStatusText) modalStatusText.textContent = "Session expired or failed.";
          if (modalStatusPill) {
            modalStatusPill.style.background = "rgba(239, 68, 68, 0.15)";
            modalStatusPill.style.color = "#ef4444";
            modalStatusPill.style.borderColor = "rgba(239, 68, 68, 0.35)";
          }
          if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
          }
        } else {
          if (modalStatusText) modalStatusText.textContent = "Waiting for transaction…";
        }
      })
      .catch(function (err) {
        console.warn("[NOWPayments Polling] error:", err);
        if (isManualClick && btnCheckStatus) {
          btnCheckStatus.disabled = false;
          btnCheckStatus.textContent = "Check Status Now";
        }
      });
  }

  if (btnCheckStatus) {
    btnCheckStatus.addEventListener("click", function () {
      checkPaymentStatus(true);
    });
  }

  // Handle Submit Button Click
  if (submitBtn) {
    submitBtn.addEventListener("click", function () {
      if (currentUSD <= 0) {
        if (window.toast) window.toast("Please enter an amount to fund.", "error");
        return;
      }

      var methodId = getActiveMethodId();

      // CASE 1: BANK TRANSFER
      if (methodId === "bank") {
        if (bankFields) bankFields.scrollIntoView({ behavior: "smooth" });
        if (window.toast) window.toast("Please review the direct bank transfer details below.", "info");
        return;
      }

      // CASE 2: CARD PAYMENT
      if (methodId === "card") {
        var cardNum = (document.getElementById("card-number") || {}).value || "";
        if (!cardNum.replace(/\s+/g, "")) {
          if (window.toast) window.toast("Please enter your card number to proceed.", "error");
          return;
        }
        var totalUSD = currentUSD * (1 + FEE_RATE);
        if (window.toast) window.toast("Initiating card charge of " + cur().format(totalUSD, { decimals: 2 }) + "…", "info", 4000);
        return;
      }

      // CASE 3: CRYPTOCURRENCY VIA NOWPAYMENTS
      if (methodId === "crypto") {
        if (currentUSD < 19.999) {
          if (window.toast) {
            window.toast("The minimum deposit for Cryptocurrency is $20.00 USD (≈ ₦" + Math.round(20 * cur().rate).toLocaleString() + ").", "error");
          }
          return;
        }

        var selectedCoin = cryptoSelect ? cryptoSelect.value : "usdttrc20";
        var selectedOpt = cryptoSelect ? cryptoSelect.options[cryptoSelect.selectedIndex] : null;
        var selectedSymbol = selectedOpt ? selectedOpt.getAttribute("data-symbol") : "USDT";
        var selectedNetwork = selectedOpt ? selectedOpt.getAttribute("data-network") : "Tron (TRC20)";

        submitBtn.disabled = true;
        var prevLabel = confirmLabel ? confirmLabel.textContent : "Confirm Deposit";
        if (confirmLabel) confirmLabel.textContent = "Generating Secure Deposit Address…";

        fetch("/api/payments/crypto/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            amount: currentUSD,
            currency: selectedCoin
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

            // Populate Modal
            activePaymentId = data.payment_id;
            currentPayAmountRaw = data.pay_amount.toString();
            currentAddressRaw = data.pay_address;

            if (modalTitle) modalTitle.textContent = "Deposit " + data.pay_currency + " (" + (data.network || selectedNetwork) + ")";
            if (modalOrderId) modalOrderId.textContent = data.order_id || ("NP-" + data.payment_id);
            if (modalQrCode) modalQrCode.src = data.qr_code_url;
            if (modalAmount) modalAmount.textContent = data.pay_amount + " " + data.pay_currency;
            if (modalAddress) modalAddress.textContent = data.pay_address;
            if (modalNetwork) modalNetwork.textContent = data.network || selectedNetwork;
            if (noticeSymbol) noticeSymbol.textContent = data.pay_currency;
            if (noticeNetwork) noticeNetwork.textContent = data.network || selectedNetwork;

            // Reset Status Badge
            if (modalStatusPill) {
              modalStatusPill.style.background = "rgba(245, 158, 11, 0.15)";
              modalStatusPill.style.color = "#f59e0b";
              modalStatusPill.style.borderColor = "rgba(245, 158, 11, 0.3)";
            }
            if (modalStatusText) modalStatusText.textContent = "Waiting for transaction…";

            if (btnCheckStatus) {
              btnCheckStatus.textContent = "Check Status Now";
              btnCheckStatus.className = "btn btn-secondary btn-block";
              btnCheckStatus.onclick = function () { checkPaymentStatus(true); };
            }

            // Open Modal
            if (cryptoModal) cryptoModal.classList.add("is-open");

            // Start automated polling every 6 seconds
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(function () {
              checkPaymentStatus(false);
            }, 6000);
          })
          .catch(function (err) {
            submitBtn.disabled = false;
            if (confirmLabel) confirmLabel.textContent = prevLabel;
            if (window.toast) window.toast("Network error generating crypto address. Please try again.", "error");
          });
      }
    });
  }

  // Re-render on currency switch
  document.addEventListener("currencychange", function () {
    syncSymbol();
    syncInput();
    syncSummary();
  });

  // Initial setup
  syncSymbol();
  syncMethodFields();
  syncSummary();
})();
