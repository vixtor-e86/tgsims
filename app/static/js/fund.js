/* ==========================================================================
   fund.js  -  Fund Your Wallet page interactions
   - Preset amount pills (set USD canonical, render active currency)
   - Manual amount entry (user types active currency, convert to USD)
   - Payment method cards (single-select; card fields shown only for "card")
   - Live order summary: deposit + processing fee (1.5%) + total
   - Dynamic confirm-button label ("Confirm Deposit of ₦X")
   - Re-renders on currency switch
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
  var submitBtn = container.querySelector("[data-fund-submit]");
  var confirmLabel = container.querySelector("[data-confirm-label]");
  var summaryAmount = container.querySelector("[data-summary-amount]");
  var summaryFee = container.querySelector("[data-summary-fee]");
  var summaryTotal = container.querySelector("[data-summary-total]");

  var FEE_RATE = parseFloat(container.getAttribute("data-fee-rate")) || 0.015;
  var currentUSD = 0; // Canonical amount in USD

  function cur() { return window.TgCurrency; }

  // Reflect the active currency symbol next to the amount input.
  function syncSymbol() {
    if (amountSymbol) amountSymbol.textContent = cur().symbol;
  }

  // Show the active-currency equivalent of currentUSD in the input.
  function syncInput() {
    if (!amountInput) return;
    var displayValue = currentUSD * cur().rate;
    amountInput.value = displayValue > 0 ? displayValue.toFixed(2) : "";
  }

  // Recompute deposit / fee / total and the confirm-button label.
  function syncSummary() {
    var feeUSD = currentUSD * FEE_RATE;
    var totalUSD = currentUSD + feeUSD;

    if (summaryAmount) summaryAmount.setAttribute("data-usd", currentUSD.toFixed(4));
    if (summaryFee) summaryFee.setAttribute("data-usd", feeUSD.toFixed(4));
    if (summaryTotal) summaryTotal.setAttribute("data-usd", totalUSD.toFixed(4));
    cur().render(container);

    if (confirmLabel) {
      confirmLabel.textContent = currentUSD > 0
        ? "Confirm Deposit of " + cur().format(totalUSD, { decimals: 2 })
        : "Confirm Deposit";
    }
    if (submitBtn) submitBtn.disabled = currentUSD <= 0;
  }

  function clearPresetActive() {
    presetButtons.forEach(function (b) { b.classList.remove("is-active"); });
  }

  // Preset pill: set canonical USD from data-usd.
  presetButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      currentUSD = parseFloat(btn.getAttribute("data-usd")) || 0;
      syncInput();
      syncSummary();
      clearPresetActive();
      btn.classList.add("is-active");
    });
  });

  // Manual entry: user types in the active currency → convert to USD canonical.
  if (amountInput) {
    amountInput.addEventListener("input", function () {
      var displayValue = parseFloat(amountInput.value) || 0;
      currentUSD = displayValue / cur().rate;
      syncSummary();
      clearPresetActive();
    });
  }

  // Payment method cards: single-select; card fields only for the "card" method.
  function syncCardFields() {
    if (!cardFields) return;
    var active = container.querySelector("[data-method].is-active");
    var isCard = active && active.getAttribute("data-method-id") === "card";
    cardFields.style.display = isCard ? "" : "none";
  }

  methodButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      methodButtons.forEach(function (b) { b.classList.remove("is-active"); });
      btn.classList.add("is-active");
      syncCardFields();
    });
  });

  // Confirm deposit.
  if (submitBtn) {
    submitBtn.addEventListener("click", function () {
      if (currentUSD <= 0) {
        window.toast("Please enter an amount to fund.", "error");
        return;
      }
      var activeMethod = container.querySelector("[data-method].is-active");
      if (!activeMethod) {
        window.toast("Please select a payment method.", "error");
        return;
      }
      var methodLabel = activeMethod.querySelector(".pay-method-label").textContent.trim();
      var totalUSD = currentUSD * (1 + FEE_RATE);
      window.toast(
        "Processing " + cur().format(totalUSD, { decimals: 2 }) + " via " + methodLabel + "…",
        "info",
        4000
      );
      // Placeholder for real gateway redirect.
    });
  }

  // Re-render on currency switch (symbol, input echo, summary, button label).
  document.addEventListener("currencychange", function () {
    syncSymbol();
    syncInput();
    syncSummary();
  });

  // Initial state.
  syncSymbol();
  syncCardFields();
  syncSummary();
})();
