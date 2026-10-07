/* ==========================================================================
   fund.js  -  Fund Your Wallet Page Interactions
   Supports 3 payment methods:
   1. Dedicated Virtual Account (Squad — auto-credits on bank transfer)
   2. Cryptocurrency (OXAPay — $1 minimum, hosted payment page)
   3. Card / Bank Transfer (Squad inline + dynamic account)
   ========================================================================== */
(function () {
  "use strict";

  var container = document.querySelector("[data-fund]");
  if (!container) return;

  var amountInput    = container.querySelector("[data-amount-input]");
  var amountSymbol   = container.querySelector("[data-amount-symbol]");
  var presetButtons  = container.querySelectorAll("[data-preset]");
  var methodButtons  = container.querySelectorAll("[data-method]");
  var dedicatedFields = container.querySelector("[data-dedicated-fields]");
  var cryptoFields   = container.querySelector("[data-crypto-fields]");
  var cardBankFields = container.querySelector("[data-card-bank-fields]");
  var cryptoSelect   = container.querySelector("[data-crypto-select]");
  var submitBtn      = container.querySelector("[data-fund-submit]");
  var confirmLabel   = container.querySelector("[data-confirm-label]");
  var summaryAmount  = container.querySelector("[data-summary-amount]");
  var summaryFee     = container.querySelector("[data-summary-fee]");
  var summaryTotal   = container.querySelector("[data-summary-total]");
  var defaultPresets = container.querySelector("[data-default-presets]");
  var cryptoPresets  = container.querySelector("[data-crypto-presets]");
  var cryptoMinWarning = document.getElementById("crypto-min-warning");
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

  // Squad / config from data attributes
  var FEE_RATE        = parseFloat(container.getAttribute("data-fee-rate")) || 0.015;
  var squadActive     = container.getAttribute("data-squad-active") === "true";
  var cryptoActive    = container.getAttribute("data-crypto-active") === "true";
  var CRYPTO_MIN      = parseFloat(container.getAttribute("data-crypto-min")) || 1.0;
  var SQUAD_PUBLIC_KEY = container.getAttribute("data-squad-public-key") || "";

  var currentUSD       = 0;
  var currentNGN       = 0;
  var activePaymentId  = null;   // OXAPay track_id
  var activePayLink    = null;   // OXAPay hosted page URL
  var pollInterval     = null;
  var activeSubMethod  = "card"; // within card-bank: 'card' or 'bank'

  function cur() {
    return window.TgCurrency || {
      rate: 1600, symbol: "₦",
      format: function (v) { return "₦" + v.toFixed(2); },
      render: function () {}
    };
  }

  function getActiveMethodId() {
    var active = container.querySelector("[data-method].is-active");
    return active ? active.getAttribute("data-method-id") : "dedicated";
  }

  function syncSymbol() {
    if (amountSymbol) amountSymbol.textContent = cur().symbol;
  }

  function syncInput() {
    if (!amountInput) return;
    var methodId = getActiveMethodId();
    if (methodId === "crypto") {
      amountInput.value = currentUSD > 0 ? currentUSD.toFixed(2) : "";
    } else {
      var displayValue = currentNGN > 0 ? currentNGN : (currentUSD * cur().rate);
      amountInput.value = displayValue > 0 ? displayValue.toFixed(2) : "";
    }
  }

  function syncSummary() {
    var methodId   = getActiveMethodId();
    var isCrypto   = (methodId === "crypto");
    var isDedicated = (methodId === "dedicated");
    var isCardBank  = (methodId === "card");

    // 0% fee on crypto and dedicated; 1.5% on card (not bank sub-method)
    var effectiveFeeRate = (isCrypto || isDedicated || activeSubMethod === "bank") ? 0.0 : FEE_RATE;
    var feeUSD   = currentUSD * effectiveFeeRate;
    var totalUSD = currentUSD + feeUSD;

    if (summaryAmount) summaryAmount.setAttribute("data-usd", currentUSD.toFixed(4));
    if (summaryFee)    summaryFee.setAttribute("data-usd", feeUSD.toFixed(4));
    if (summaryTotal)  summaryTotal.setAttribute("data-usd", totalUSD.toFixed(4));
    cur().render(container);

    // Crypto min warning
    var isUnderCryptoMin = isCrypto && currentUSD > 0 && currentUSD < CRYPTO_MIN;
    if (cryptoMinWarning && cryptoCurrEntered) {
      if (isUnderCryptoMin) {
        cryptoMinWarning.style.display = "";
        cryptoCurrEntered.textContent = "$" + currentUSD.toFixed(2);
      } else {
        cryptoMinWarning.style.display = "none";
      }
    }

    if (orderSummaryBlock) {
      orderSummaryBlock.style.display = isDedicated ? "none" : "";
    }

    // Button label & state
    if (confirmLabel) {
      if (isDedicated) {
        confirmLabel.textContent = "Use Dedicated Account";
      } else if (isCrypto) {
        if (currentUSD <= 0) {
          confirmLabel.textContent = "Enter Amount to Deposit";
        } else if (isUnderCryptoMin) {
          confirmLabel.textContent = "Minimum $" + CRYPTO_MIN.toFixed(2) + " Required";
        } else {
          var optEl = cryptoSelect ? cryptoSelect.options[cryptoSelect.selectedIndex] : null;
          var coin = optEl ? (optEl.getAttribute("data-coin") || optEl.value || "Crypto") : "Crypto";
          confirmLabel.textContent = "Pay $" + currentUSD.toFixed(2) + " in " + coin;
        }
      } else if (isCardBank && activeSubMethod === "bank") {
        confirmLabel.textContent = currentUSD > 0
          ? "Generate Transfer Account (₦" + currentNGN.toLocaleString("en-NG", {maximumFractionDigits: 0}) + ")"
          : "Enter Amount";
      } else if (isCardBank) {
        var totalNGN = totalUSD * cur().rate;
        confirmLabel.textContent = currentUSD > 0
          ? "Pay ₦" + totalNGN.toLocaleString("en-NG", {maximumFractionDigits: 0}) + " by Card"
          : "Enter Amount";
      } else {
        confirmLabel.textContent = "Confirm Deposit";
      }
    }

    if (submitBtn) {
      var disabledDedicated = isDedicated;
      var disabledCrypto    = isCrypto && (currentUSD <= 0 || isUnderCryptoMin || !cryptoActive);
      var disabledCard      = isCardBank && currentNGN < 100;
      submitBtn.disabled = (disabledDedicated || disabledCrypto || disabledCard);
    }
  }

  // Amount presets
  presetButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var usd = parseFloat(btn.getAttribute("data-usd")) || 0;
      var ngn = parseFloat(btn.getAttribute("data-ngn")) || (usd * cur().rate);
      currentUSD = usd;
      currentNGN = ngn;
      syncInput();
      syncSummary();
      presetButtons.forEach(function (b) { b.classList.remove("is-active"); });
      btn.classList.add("is-active");
    });
  });

  // Manual amount entry
  if (amountInput) {
    amountInput.addEventListener("input", function () {
      var val = parseFloat(amountInput.value) || 0;
      var methodId = getActiveMethodId();
      if (methodId === "crypto") {
        currentUSD = val;
        currentNGN = val * cur().rate;
      } else {
        currentNGN = val;
        currentUSD = val / cur().rate;
      }
      syncSummary();
      presetButtons.forEach(function (b) { b.classList.remove("is-active"); });
    });
  }

  // Method switching
  function syncMethodFields() {
    var methodId = getActiveMethodId();
    if (dedicatedFields) dedicatedFields.style.display = (methodId === "dedicated") ? "" : "none";
    if (cryptoFields)    cryptoFields.style.display    = (methodId === "crypto")    ? "" : "none";
    if (cardBankFields)  cardBankFields.style.display  = (methodId === "card")      ? "" : "none";

    if (defaultPresets) defaultPresets.style.display = (methodId === "crypto") ? "none" : "";
    if (cryptoPresets)  cryptoPresets.style.display  = (methodId === "crypto") ? "" : "none";

    if (amountSymbol) {
      amountSymbol.textContent = (methodId === "crypto") ? "$" : cur().symbol;
    }

    currentUSD = 0;
    currentNGN = 0;
    if (amountInput) amountInput.value = "";
    presetButtons.forEach(function (b) { b.classList.remove("is-active"); });

    syncSummary();
  }

  methodButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      methodButtons.forEach(function (b) { b.classList.remove("is-active"); });
      btn.classList.add("is-active");
      syncMethodFields();
    });
  });

  // Sub-method switching (card vs bank within card-bank tab)
  var subCardBtn     = document.getElementById("sub-card-btn");
  var subBankBtn     = document.getElementById("sub-bank-btn");
  var cardSection    = document.getElementById("card-section");
  var bankSection    = document.getElementById("bank-section");
  var bankTransferResult = document.getElementById("bank-transfer-result");

  function switchSubMethod(sub) {
    activeSubMethod = sub;
    if (subCardBtn) subCardBtn.classList.toggle("is-active", sub === "card");
    if (subBankBtn) subBankBtn.classList.toggle("is-active", sub === "bank");
    if (cardSection) cardSection.style.display = (sub === "card") ? "" : "none";
    if (bankSection) bankSection.style.display = (sub === "bank") ? "" : "none";
    syncSummary();
  }

  if (subCardBtn) subCardBtn.addEventListener("click", function () { switchSubMethod("card"); });
  if (subBankBtn) subBankBtn.addEventListener("click", function () { switchSubMethod("bank"); });

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

  // ---- QR CODE GENERATION (client-side via QRServer with QuickChart fallback) ----
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
            modalStatusPill.style.background   = "rgba(16, 185, 129, 0.15)";
            modalStatusPill.style.color        = "#10b981";
            modalStatusPill.style.borderColor  = "rgba(16, 185, 129, 0.35)";
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

  // ---- DEDICATED ACCOUNT CREATION ----
  var btnCreateAccount = document.getElementById("btn-create-dedicated-account");
  var accountResult    = document.getElementById("dedicated-account-result");

  if (btnCreateAccount) {
    btnCreateAccount.addEventListener("click", function () {
      var label = document.getElementById("create-account-label");
      btnCreateAccount.disabled = true;
      if (label) label.textContent = "Generating your account…";

      fetch("/api/payments/squad/virtual-account/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          btnCreateAccount.disabled = false;
          if (label) label.textContent = "Generate My Account";

          if (!data.success) {
            if (window.toast) window.toast(data.message || "Failed to create account. Please try again.", "error");
            return;
          }

          var acc = data.account || {};
          if (accountResult) {
            accountResult.style.display = "";
            accountResult.innerHTML =
              '<div style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); border-radius: var(--r-md); padding: 1rem; text-align: left;">' +
              '<div style="font-weight: 700; color: #10b981; margin-bottom: 0.5rem;">✓ Account Created Successfully!</div>' +
              '<div><strong>Bank:</strong> ' + (acc.bank_name || '') + '</div>' +
              '<div style="font-size: 1.2rem; font-weight: 800; font-family: monospace; margin-top: 0.35rem;">' + (acc.account_number || '') + '</div>' +
              '<div style="font-size: 0.8rem; color: var(--text-dim);">' + (acc.account_name || '') + '</div>' +
              '<div style="margin-top: 0.5rem; font-size: 0.78rem; color: var(--text-dim);">Reload the page to see your account details here.</div>' +
              '</div>';
          }

          if (btnCreateAccount) btnCreateAccount.style.display = "none";
          if (window.toast) window.toast("Dedicated account created! Reload to view it.", "success", 6000);
        })
        .catch(function () {
          btnCreateAccount.disabled = false;
          if (label) label.textContent = "Generate My Account";
          if (window.toast) window.toast("Network error. Please try again.", "error");
        });
    });
  }

  // ---- SUBMIT HANDLER ----
  if (submitBtn) {
    submitBtn.addEventListener("click", function () {
      var methodId = getActiveMethodId();

      // DEDICATED ACCOUNT - no submit flow needed
      if (methodId === "dedicated") {
        if (window.toast) window.toast("Transfer to your dedicated account anytime – it auto-credits your wallet.", "info", 5000);
        return;
      }

      // CRYPTO (OXAPay)
      if (methodId === "crypto") {
        if (currentUSD <= 0) {
          if (window.toast) window.toast("Please enter an amount to deposit.", "error");
          return;
        }
        if (currentUSD < CRYPTO_MIN) {
          if (window.toast) window.toast("Minimum crypto deposit is $" + CRYPTO_MIN.toFixed(2) + " USD.", "error");
          return;
        }

        var optEl           = cryptoSelect ? cryptoSelect.options[cryptoSelect.selectedIndex] : null;
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

            // OXAPay returns: track_id, pay_link, amount_usd, currency, network, order_id
            activePaymentId = data.track_id;
            activePayLink   = data.pay_link;

            if (modalTitle)   modalTitle.textContent   = "Pay $" + data.amount_usd + " in " + data.currency;
            if (modalOrderId) modalOrderId.textContent = data.order_id || ("OP-" + data.track_id);
            if (modalAmount)  modalAmount.textContent  = "$" + parseFloat(data.amount_usd).toFixed(2);
            if (modalNetwork) modalNetwork.textContent = data.currency + " / " + (data.network || selectedNetwork);

            // Set "Open Payment Page" button href
            if (btnOpenPage) {
              btnOpenPage.href = data.pay_link || "#";
              btnOpenPage.style.display = "";
            }

            // Generate QR code from pay_link URL
            if (data.pay_link) {
              renderQRCode(data.pay_link);
            }

            // Reset status badge
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

      // CARD / BANK
      if (methodId === "card") {
        if (currentNGN < 100) {
          if (window.toast) window.toast("Please enter an amount of at least ₦100.", "error");
          return;
        }

        // BANK TRANSFER - generate dynamic account
        if (activeSubMethod === "bank") {
          submitBtn.disabled = true;
          if (confirmLabel) confirmLabel.textContent = "Generating Transfer Account…";

          fetch("/api/payments/squad/bank-transfer/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ amount_ngn: currentNGN })
          })
            .then(function (res) { return res.json(); })
            .then(function (data) {
              submitBtn.disabled = false;
              syncSummary();

              if (!data.success) {
                if (window.toast) window.toast(data.message || "Failed to generate account.", "error");
                return;
              }

              if (bankTransferResult) {
                bankTransferResult.style.display = "";
                bankTransferResult.innerHTML =
                  '<div style="background: rgba(99,102,241,0.06); border: 1px solid rgba(99,102,241,0.2); border-radius: var(--r-md); padding: 1rem;">' +
                  '<div style="font-weight: 700; color: var(--text); margin-bottom: 0.5rem;">Transfer Details (valid 10 mins)</div>' +
                  '<div style="display: flex; flex-direction: column; gap: 0.4rem;">' +
                  '<div><span style="color:var(--text-dim);">Bank:</span> <strong>' + (data.bank_name || '') + '</strong></div>' +
                  '<div><span style="color:var(--text-dim);">Account:</span> <strong style="font-family:monospace; font-size:1.1rem;">' + (data.account_number || '') + '</strong>' +
                  ' <button type="button" onclick="copyToClipboard(\'' + data.account_number + '\', this)" class="btn btn-secondary btn-sm" style="padding:0.2rem 0.6rem; font-size:0.75rem;">Copy</button></div>' +
                  '<div><span style="color:var(--text-dim);">Name:</span> <strong>' + (data.account_name || '') + '</strong></div>' +
                  '<div><span style="color:var(--text-dim);">Amount:</span> <strong style="color:#6366f1;">₦' + currentNGN.toLocaleString('en-NG', {maximumFractionDigits: 2}) + '</strong></div>' +
                  '</div>' +
                  '<div style="font-size:0.78rem; color:var(--text-dim); margin-top:0.5rem; padding:0.5rem; background: rgba(245,158,11,0.08); border-radius: var(--r-sm); border: 1px solid rgba(245,158,11,0.2);">Send the <strong>exact amount</strong> above. Account expires in 10 minutes. Your wallet will be credited automatically.</div>' +
                  '</div>';
              }
              if (window.toast) window.toast("Transfer account generated! Send ₦" + currentNGN.toLocaleString() + " now.", "success", 8000);
            })
            .catch(function () {
              submitBtn.disabled = false;
              syncSummary();
              if (window.toast) window.toast("Network error. Please try again.", "error");
            });
          return;
        }

        // CARD PAYMENT - Squad inline
        if (!squadActive || !SQUAD_PUBLIC_KEY) {
          if (window.toast) window.toast("Card payments are not available right now. Please use another method.", "error");
          return;
        }

        submitBtn.disabled = true;
        if (confirmLabel) confirmLabel.textContent = "Initializing Card Payment…";

        fetch("/api/payments/squad/card/initiate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ amount_ngn: currentNGN })
        })
          .then(function (res) { return res.json(); })
          .then(function (data) {
            submitBtn.disabled = false;
            syncSummary();

            if (!data.success) {
              if (window.toast) window.toast(data.message || "Failed to start card payment.", "error");
              return;
            }

            // If checkout_url returned, open it
            if (data.checkout_url) {
              window.open(data.checkout_url, "_blank");
              return;
            }

            // Use Squad inline SDK if available
            if (window.squad) {
              var squadInstance = new window.squad({
                onclose: function () {
                  if (window.toast) window.toast("Payment window closed. Check your wallet if you completed payment.", "info", 5000);
                },
                onload: function () {},
                onpayment: function (resp) {
                  if (resp && (resp.transaction_status === "success" || resp.status === "success")) {
                    if (window.toast) window.toast("Payment received! Your wallet will be credited shortly.", "success", 6000);
                    setTimeout(function () { window.location.href = "/wallet"; }, 3000);
                  }
                },
                key: SQUAD_PUBLIC_KEY,
                email: (window.TgUser && window.TgUser.email) || "",
                amount: Math.round(currentNGN * 100), // kobo
                currency_code: "NGN",
                transaction_ref: data.reference
              });
              squadInstance.setup();
              squadInstance.open();
            } else {
              if (window.toast) window.toast("Redirecting to payment page…", "info");
              if (data.checkout_url) window.location.href = data.checkout_url;
            }
          })
          .catch(function () {
            submitBtn.disabled = false;
            syncSummary();
            if (window.toast) window.toast("Network error. Please try again.", "error");
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
