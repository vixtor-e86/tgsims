/* ==========================================================================
   otp_history.js  -  OTP History Client-Side Search, Filter & Date Range
   Powers real-time search, service filter, status filter, calendar date range,
   and dynamic pagination for OTP records.
   ========================================================================== */
(function () {
  "use strict";

  function init() {
    var searchInput = document.querySelector("[data-otp-search]");
    var serviceSelect = document.querySelector("[data-otp-service-filter]");
    var statusSelect = document.querySelector("[data-otp-status-filter]");
    var dateDropdown = document.querySelector("[data-otp-date-dropdown]");
    var dateLabel = document.querySelector("[data-otp-date-text]");
    var datePresets = document.querySelectorAll("[data-date-range]");
    var dateStartInput = document.querySelector("[data-date-start]");
    var dateEndInput = document.querySelector("[data-date-end]");
    var applyDateBtn = document.querySelector("[data-apply-date-range]");
    var clearDateBtn = document.querySelector("[data-clear-date-range]");

    var rows = Array.from(document.querySelectorAll("[data-otp-row]"));
    var noMatchesRow = document.querySelector("[data-otp-no-matches]");
    var countEl = document.querySelector("[data-otp-count]");
    var footEl = document.querySelector("[data-otp-foot]");
    var prevBtn = document.querySelector("[data-page-prev]");
    var nextBtn = document.querySelector("[data-page-next]");
    var pageNumbersEl = document.querySelector("[data-page-numbers]");

    if (!rows.length && !noMatchesRow) return;

    var state = {
      query: "",
      service: "all",
      status: "all",
      dateRange: "all",
      startDate: null,
      endDate: null,
      page: 1,
      pageSize: 10,
      filteredRows: rows
    };

    function parseYMD(str) {
      if (!str) return null;
      var clean = str.trim().split(" ")[0];
      var parts = clean.split("-");
      if (parts.length !== 3) return null;
      var y = parseInt(parts[0], 10);
      var m = parseInt(parts[1], 10) - 1;
      var d = parseInt(parts[2], 10);
      if (isNaN(y) || isNaN(m) || isNaN(d)) return null;
      return new Date(y, m, d);
    }

    function rowMatches(row) {
      var s = (row.getAttribute("data-service") || "").toLowerCase();
      var p = (row.getAttribute("data-phone") || "").toLowerCase();
      var c = (row.getAttribute("data-code") || "").toLowerCase();
      var m = (row.getAttribute("data-msg") || "").toLowerCase();
      var st = (row.getAttribute("data-status") || "").toLowerCase();
      var dStr = row.getAttribute("data-date") || "";

      // 1. Service filter
      if (state.service !== "all" && s !== state.service.toLowerCase()) {
        return false;
      }

      // 2. Status filter
      if (state.status !== "all" && st !== state.status.toLowerCase()) {
        return false;
      }

      // 3. Search query
      if (state.query) {
        var q = state.query.toLowerCase();
        var match = s.indexOf(q) > -1 ||
                    p.indexOf(q) > -1 ||
                    c.indexOf(q) > -1 ||
                    m.indexOf(q) > -1;

        // Strip non-digits for phone / code matching if query contains digits
        if (!match) {
          var cleanQ = q.replace(/\D/g, "");
          if (cleanQ.length >= 2) {
            var cleanP = p.replace(/\D/g, "");
            var cleanC = c.replace(/\D/g, "");
            if (cleanP.indexOf(cleanQ) > -1 || cleanC.indexOf(cleanQ) > -1) {
              match = true;
            }
          }
        }

        if (!match) return false;
      }

      // 4. Date filter
      if (state.dateRange !== "all") {
        var rowDate = parseYMD(dStr);
        if (!rowDate) return false;

        var now = new Date();
        var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

        if (state.dateRange === "today") {
          if (rowDate.getTime() !== today.getTime()) return false;
        } else if (state.dateRange === "7d") {
          var d7 = new Date(today);
          d7.setDate(d7.getDate() - 7);
          if (rowDate < d7) return false;
        } else if (state.dateRange === "30d") {
          var d30 = new Date(today);
          d30.setDate(d30.getDate() - 30);
          if (rowDate < d30) return false;
        } else if (state.dateRange === "custom") {
          if (state.startDate && rowDate < state.startDate) return false;
          if (state.endDate && rowDate > state.endDate) return false;
        }
      }

      return true;
    }

    function renderPagination(totalMatches) {
      if (!pageNumbersEl) return;
      pageNumbersEl.innerHTML = "";

      var totalPages = Math.ceil(totalMatches / state.pageSize) || 1;
      if (state.page > totalPages) state.page = totalPages;
      if (state.page < 1) state.page = 1;

      if (prevBtn) prevBtn.disabled = state.page <= 1;
      if (nextBtn) nextBtn.disabled = state.page >= totalPages;

      if (totalPages <= 1) {
        if (prevBtn) prevBtn.style.display = "none";
        if (nextBtn) nextBtn.style.display = "none";
        return;
      } else {
        if (prevBtn) prevBtn.style.display = "";
        if (nextBtn) nextBtn.style.display = "";
      }

      function createBtn(pNum, isEllipsis) {
        if (isEllipsis) {
          var span = document.createElement("span");
          span.className = "page-dots";
          span.textContent = "…";
          span.style.padding = "0 4px";
          span.style.color = "var(--text-dim)";
          pageNumbersEl.appendChild(span);
          return;
        }
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "page-btn" + (pNum === state.page ? " is-active" : "");
        btn.textContent = pNum;
        btn.setAttribute("aria-label", "Page " + pNum);
        btn.addEventListener("click", function () {
          state.page = pNum;
          applyDisplay();
        });
        pageNumbersEl.appendChild(btn);
      }

      if (totalPages <= 7) {
        for (var i = 1; i <= totalPages; i++) {
          createBtn(i, false);
        }
      } else {
        createBtn(1, false);
        var start = Math.max(2, state.page - 1);
        var end = Math.min(totalPages - 1, state.page + 1);

        if (start > 2) createBtn(null, true);
        for (var j = start; j <= end; j++) {
          createBtn(j, false);
        }
        if (end < totalPages - 1) createBtn(null, true);
        createBtn(totalPages, false);
      }
    }

    function applyDisplay() {
      var matching = rows.filter(rowMatches);
      state.filteredRows = matching;

      var totalMatches = matching.length;
      var totalPages = Math.ceil(totalMatches / state.pageSize) || 1;
      if (state.page > totalPages) state.page = totalPages;

      var startIdx = (state.page - 1) * state.pageSize;
      var endIdx = startIdx + state.pageSize;

      // Hide all rows first
      rows.forEach(function (r) { r.style.display = "none"; });

      // Show only current page's matching rows
      matching.slice(startIdx, endIdx).forEach(function (r) {
        r.style.display = "";
      });

      // No matches notice
      if (noMatchesRow) {
        if (totalMatches === 0 && rows.length > 0) {
          noMatchesRow.classList.remove("hidden");
          noMatchesRow.style.display = "";
        } else {
          noMatchesRow.classList.add("hidden");
          noMatchesRow.style.display = "none";
        }
      }

      // Count string
      if (countEl) {
        if (totalMatches === 0) {
          countEl.textContent = rows.length === 0 ? "" : "No matching entries found";
        } else {
          var showingStart = startIdx + 1;
          var showingEnd = Math.min(endIdx, totalMatches);
          countEl.textContent = "Showing " + showingStart + " to " + showingEnd + " of " + totalMatches + " entries";
        }
      }

      if (footEl) {
        footEl.style.display = (totalMatches === 0 || rows.length === 0) ? "none" : "";
      }

      renderPagination(totalMatches);
    }

    /* ---- Event Listeners ---- */

    // Search query (input and native search clear)
    function onSearchChange() {
      state.query = searchInput.value.trim();
      state.page = 1;
      applyDisplay();
    }
    if (searchInput) {
      searchInput.addEventListener("input", onSearchChange);
      searchInput.addEventListener("search", onSearchChange);
    }

    // Service dropdown
    if (serviceSelect) {
      serviceSelect.addEventListener("change", function () {
        state.service = serviceSelect.value;
        state.page = 1;
        applyDisplay();
      });
    }

    // Status dropdown
    if (statusSelect) {
      statusSelect.addEventListener("change", function () {
        state.status = statusSelect.value;
        state.page = 1;
        applyDisplay();
      });
    }

    // Keep dropdown open when clicking inputs or custom container
    var dateMenu = dateDropdown ? dateDropdown.querySelector(".dropdown-menu") : null;
    if (dateMenu) {
      dateMenu.addEventListener("click", function (e) {
        if (
          !e.target.closest("[data-date-range]") &&
          !e.target.closest("[data-apply-date-range]") &&
          !e.target.closest("[data-clear-date-range]")
        ) {
          e.stopPropagation();
        }
      });
    }

    // Date range presets
    datePresets.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var range = btn.getAttribute("data-date-range");
        state.dateRange = range;
        state.startDate = null;
        state.endDate = null;
        state.page = 1;

        if (dateStartInput) dateStartInput.value = "";
        if (dateEndInput) dateEndInput.value = "";

        datePresets.forEach(function (b) { b.classList.remove("is-active"); });
        btn.classList.add("is-active");

        if (dateLabel) {
          dateLabel.textContent = btn.textContent;
        }

        if (dateDropdown) dateDropdown.classList.remove("is-open");

        applyDisplay();
      });
    });

    // Custom date range Apply
    if (applyDateBtn) {
      applyDateBtn.addEventListener("click", function () {
        var sVal = dateStartInput ? dateStartInput.value.trim() : "";
        var eVal = dateEndInput ? dateEndInput.value.trim() : "";

        if (!sVal && !eVal) {
          if (window.toast) window.toast("Please select a start or end date.", "info");
          return;
        }

        if (sVal && eVal && sVal > eVal) {
          if (window.toast) window.toast("Start date cannot be after end date.", "warning");
          return;
        }

        state.dateRange = "custom";
        state.startDate = parseYMD(sVal);
        state.endDate = parseYMD(eVal);
        state.page = 1;

        datePresets.forEach(function (b) { b.classList.remove("is-active"); });

        if (dateLabel) {
          if (sVal && eVal) dateLabel.textContent = sVal + " - " + eVal;
          else if (sVal) dateLabel.textContent = "From " + sVal;
          else dateLabel.textContent = "Until " + eVal;
        }

        if (dateDropdown) dateDropdown.classList.remove("is-open");

        applyDisplay();
      });
    }

    // Custom date range Reset
    if (clearDateBtn) {
      clearDateBtn.addEventListener("click", function () {
        if (dateStartInput) dateStartInput.value = "";
        if (dateEndInput) dateEndInput.value = "";

        state.dateRange = "all";
        state.startDate = null;
        state.endDate = null;
        state.page = 1;

        datePresets.forEach(function (b) {
          if (b.getAttribute("data-date-range") === "all") b.classList.add("is-active");
          else b.classList.remove("is-active");
        });

        if (dateLabel) {
          dateLabel.textContent = "All Time";
        }

        if (dateDropdown) dateDropdown.classList.remove("is-open");

        applyDisplay();
      });
    }

    // Enter key triggers apply on date inputs
    [dateStartInput, dateEndInput].forEach(function (inp) {
      if (!inp) return;
      inp.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          if (applyDateBtn) applyDateBtn.click();
        }
      });
    });

    // Prev / Next pagination buttons
    if (prevBtn) {
      prevBtn.addEventListener("click", function () {
        if (state.page > 1) {
          state.page--;
          applyDisplay();
        }
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        var totalPages = Math.ceil(state.filteredRows.length / state.pageSize) || 1;
        if (state.page < totalPages) {
          state.page++;
          applyDisplay();
        }
      });
    }

    // Initial paint
    applyDisplay();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
