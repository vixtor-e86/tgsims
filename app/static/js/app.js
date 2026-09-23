/* ==========================================================================
   app.js  -  shared UI interactions
   Declarative, attribute-driven so markup stays clean and portable:
     [data-sidebar-toggle]         toggle mobile sidebar
     [data-dropdown]  > [data-dropdown-trigger] + [data-dropdown-menu]
     [data-modal-open="id"] / [data-modal-close]
     [data-accordion] > [data-acc-item] > [data-acc-head]
     [data-tab="key"] + [data-panel="key"]  (within a [data-tabs] group)
     [data-copy="text"]            copy to clipboard
     [data-password-toggle]        reveal/hide sibling password input
   ========================================================================== */
(function () {
  "use strict";

  /* ---- Toasts (also exposed globally) ------------------------------------ */
  var ICONS = {
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
    error:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
    info:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
  };

  function ensureStack() {
    var stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      document.body.appendChild(stack);
    }
    return stack;
  }

  function toast(message, type, timeout) {
    type = type || "info";
    var el = document.createElement("div");
    el.className = "toast is-" + type;
    el.setAttribute("role", "status");
    el.innerHTML =
      '<span class="toast-ico">' + (ICONS[type] || ICONS.info) + "</span>" +
      "<span>" + message + "</span>";
    ensureStack().appendChild(el);
    var life = timeout || 3800;
    var t = setTimeout(dismiss, life);
    function dismiss() {
      clearTimeout(t);
      el.classList.add("leaving");
      el.addEventListener("animationend", function () { el.remove(); });
    }
    el.addEventListener("click", dismiss);
    return el;
  }
  window.toast = toast;

  /* ---- Sidebar (mobile) -------------------------------------------------- */
  function initSidebar() {
    var sidebar = document.querySelector(".sidebar");
    var scrim = document.querySelector(".sidebar-scrim");
    if (!sidebar) return;

    function open() {
      sidebar.classList.add("is-open");
      if (scrim) scrim.classList.add("is-open");
      document.body.style.overflow = "hidden";
    }
    function close() {
      sidebar.classList.remove("is-open");
      if (scrim) scrim.classList.remove("is-open");
      document.body.style.overflow = "";
    }

    document.querySelectorAll("[data-sidebar-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        sidebar.classList.contains("is-open") ? close() : open();
      });
    });

    document.querySelectorAll("[data-sidebar-close]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        close();
      });
    });

    if (scrim) scrim.addEventListener("click", close);

    sidebar.querySelectorAll(".side-link").forEach(function (link) {
      link.addEventListener("click", function () {
        if (window.innerWidth <= 900) close();
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
  }

  /* ---- Landing mobile navigation drawer ----------------------------------- */
  function initLandingMenu() {
    var toggleBtn = document.querySelector("[data-lp-menu-toggle]");
    var menu = document.getElementById("lp-mobile-menu");
    if (!toggleBtn || !menu) return;

    function toggleMenu() {
      var isOpen = menu.classList.toggle("is-open");
      toggleBtn.classList.toggle("is-active", isOpen);
      toggleBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }
    function closeMenu() {
      menu.classList.remove("is-open");
      toggleBtn.classList.remove("is-active");
      toggleBtn.setAttribute("aria-expanded", "false");
    }

    toggleBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      toggleMenu();
    });

    menu.querySelectorAll(".lp-mobile-link, .lp-mobile-auth a").forEach(function (link) {
      link.addEventListener("click", closeMenu);
    });

    document.addEventListener("click", function (e) {
      if (!menu.contains(e.target) && !toggleBtn.contains(e.target)) {
        closeMenu();
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeMenu();
    });
  }

  /* ---- Dropdowns --------------------------------------------------------- */
  function initDropdowns() {
    document.querySelectorAll("[data-dropdown]").forEach(function (dd) {
      var trigger = dd.querySelector("[data-dropdown-trigger]");
      if (!trigger) return;
      trigger.addEventListener("click", function (e) {
        e.stopPropagation();
        var wasOpen = dd.classList.contains("is-open");
        closeAll();
        if (!wasOpen) dd.classList.add("is-open");
      });
    });
    function closeAll() {
      document.querySelectorAll("[data-dropdown].is-open")
        .forEach(function (d) { d.classList.remove("is-open"); });
    }
    document.addEventListener("click", closeAll);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeAll();
    });
  }

  /* ---- Modals ------------------------------------------------------------ */
  function openModal(id) {
    var m = document.getElementById(id);
    if (!m) return;
    m.classList.add("is-open");
    document.body.style.overflow = "hidden";
    var focusable = m.querySelector("input, button, select, textarea");
    if (focusable) setTimeout(function () { focusable.focus(); }, 60);
  }
  function closeModal(m) {
    if (typeof m === "string") m = document.getElementById(m);
    if (!m) return;
    m.classList.remove("is-open");
    document.body.style.overflow = "";
  }
  window.openModal = openModal;
  window.closeModal = closeModal;

  function initModals() {
    document.querySelectorAll("[data-modal-open]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openModal(btn.getAttribute("data-modal-open"));
      });
    });
    document.querySelectorAll(".modal").forEach(function (m) {
      m.addEventListener("click", function (e) {
        if (e.target === m || e.target.hasAttribute("data-modal-close")) closeModal(m);
      });
      m.querySelectorAll("[data-modal-close]").forEach(function (b) {
        b.addEventListener("click", function () { closeModal(m); });
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        var open = document.querySelector(".modal.is-open");
        if (open) closeModal(open);
      }
    });
  }

  /* ---- Accordion --------------------------------------------------------- */
  function initAccordion() {
    document.querySelectorAll("[data-accordion]").forEach(function (acc) {
      var single = acc.hasAttribute("data-accordion-single");
      acc.querySelectorAll("[data-acc-item]").forEach(function (item) {
        var head = item.querySelector("[data-acc-head]");
        var body = item.querySelector(".acc-body");
        if (!head || !body) return;
        head.addEventListener("click", function () {
          var isOpen = item.classList.contains("is-open");
          if (single) {
            acc.querySelectorAll("[data-acc-item].is-open").forEach(function (o) {
              o.classList.remove("is-open");
              var b = o.querySelector(".acc-body");
              if (b) b.style.maxHeight = null;
            });
          }
          if (isOpen) {
            item.classList.remove("is-open");
            body.style.maxHeight = null;
          } else {
            item.classList.add("is-open");
            body.style.maxHeight = body.scrollHeight + "px";
          }
        });
      });
    });
  }

  /* ---- Tabs -------------------------------------------------------------- */
  function initTabs() {
    document.querySelectorAll("[data-tabs]").forEach(function (group) {
      var tabs = group.querySelectorAll("[data-tab]");
      var panels = group.querySelectorAll("[data-panel]");
      tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
          var key = tab.getAttribute("data-tab");
          tabs.forEach(function (t) { t.classList.toggle("is-active", t === tab); });
          panels.forEach(function (p) {
            p.classList.toggle("hidden", p.getAttribute("data-panel") !== key);
          });
        });
      });
    });
  }

  /* ---- Copy to clipboard ------------------------------------------------- */
  function initCopy() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-copy]");
      if (!btn) return;
      var text = btn.getAttribute("data-copy");
      var done = function () { toast("Copied to clipboard", "success", 1800); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(function () { fallback(text); done(); });
      } else { fallback(text); done(); }
    });
    function fallback(text) {
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      ta.remove();
    }
  }

  /* ---- Password reveal --------------------------------------------------- */
  function initPasswordToggles() {
    document.querySelectorAll("[data-password-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var wrap = btn.closest(".input-group");
        var input = wrap && wrap.querySelector("input");
        if (!input) return;
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.classList.toggle("is-showing", show);
        btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      });
    });
  }

  /* ---- Flash messages -> toasts ----------------------------------------- */
  function initFlashes() {
    document.querySelectorAll("[data-flash]").forEach(function (el) {
      toast(el.getAttribute("data-flash-msg"), el.getAttribute("data-flash-type") || "info");
      el.remove();
    });
  }

  /* ---- Form submit button spinner --------------------------------------- */
  function initFormSubmitSpinners() {
    document.addEventListener("submit", function (e) {
      var form = e.target;
      if (!form || form.tagName !== "FORM") return;
      if (e.defaultPrevented) return;

      var btn = form.querySelector('button[type="submit"]');
      if (!btn || btn.classList.contains("is-loading")) return;

      var loadingText = btn.getAttribute("data-loading-text") || "Please wait...";
      setTimeout(function () {
        if (!e.defaultPrevented) {
          btn.disabled = true;
          btn.classList.add("is-loading");
          btn.innerHTML = '<span class="spinner"></span> <span>' + loadingText + '</span>';
        }
      }, 10);
    });
  }

  /* ---- User In-App Notifications & Topbar Bell Center ------------------- */
  function initUserNotifications() {
    var bellTrigger = document.getElementById("topbar-bell-trigger");
    var bellDot = document.getElementById("bell-unread-dot");
    var bellBadge = document.getElementById("bell-unread-badge");
    var headerBadge = document.getElementById("bell-header-badge");
    var notifContainer = document.getElementById("topbar-user-notifs");
    var markAllBtn = document.getElementById("mark-user-notifs-read-btn");
    var cachedUserNotifs = [];

    if (!bellTrigger || !notifContainer) return;

    function formatTimeAgo(isoStr) {
      if (!isoStr) return "";
      try {
        var cleanStr = isoStr.replace("Z", "+00:00").replace(" ", "T");
        var d = new Date(cleanStr);
        var diff = Math.floor((Date.now() - d.getTime()) / 1000);
        if (isNaN(diff) || diff < 0) return "Just now";
        if (diff < 60) return "Just now";
        if (diff < 3600) return Math.floor(diff / 60) + "m ago";
        if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
        var days = Math.floor(diff / 86400);
        if (days === 1) return "Yesterday";
        if (days < 7) return days + "d ago";
        return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      } catch (e) {
        return "";
      }
    }

    function adaptCurrencyText(text) {
      if (!text || typeof text !== "string") return text || "";
      if (!window.TgCurrency) return text;

      var active = window.TgCurrency.active || "NGN";
      var rate = Number(window.TG_NGN_PER_USD) || (window.TgCurrency && window.TgCurrency.rate) || 1600;

      // 1. Dual notation: "$10.00 (≈ ₦16,000.00)" or "$10.00 (₦16,000.00)"
      text = text.replace(/\$([0-9]+(?:\.[0-9]+)?)\s*\((?:≈\s*)?₦[0-9,]+(?:\.[0-9]+)?\)/gi, function (_, usdVal) {
        var num = parseFloat(usdVal);
        return isNaN(num) ? _ : window.TgCurrency.format(num);
      });

      // 2. Dual notation reversed: "₦16,000.00 ($10.00)" or "₦16,000.00 (≈$10.00)"
      text = text.replace(/₦[0-9,]+(?:\.[0-9]+)?\s*\((?:≈\s*)?\$([0-9]+(?:\.[0-9]+)?)\)/gi, function (_, usdVal) {
        var num = parseFloat(usdVal);
        return isNaN(num) ? _ : window.TgCurrency.format(num);
      });

      // 3. Standalone currency conversions
      if (active === "NGN") {
        // Convert $X.XX or $X to Naira
        text = text.replace(/\$([0-9]+(?:\.[0-9]+)?)/g, function (match, usdVal) {
          var num = parseFloat(usdVal);
          if (isNaN(num)) return match;
          return window.TgCurrency.format(num);
        });
      } else {
        // Convert ₦Y,YYY.YY or ₦Y to USD
        text = text.replace(/₦([0-9,]+(?:\.[0-9]+)?)/g, function (match, ngnVal) {
          var cleanNgn = ngnVal.replace(/,/g, "");
          var num = parseFloat(cleanNgn);
          if (isNaN(num)) return match;
          var usdEquiv = num / rate;
          return window.TgCurrency.format(usdEquiv);
        });
      }

      return text;
    }

    function getTypeMeta(type) {
      var t = (type || "system").toLowerCase();
      var walletIco = '<svg style="width:14px;height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12V8H6a2 2 0 0 1-2-2c0-1.1.9-2 2-2h12v4"></path><path d="M4 6v12c0 1.1.9 2 2 2h14v-4"></path><path d="M18 12a2 2 0 0 0 0 4h4v-4z"></path></svg>';
      var depositIco = '<svg style="width:14px;height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><polyline points="19 12 12 19 5 12"></polyline></svg>';
      var orderIco = '<svg style="width:14px;height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
      var refundIco = '<svg style="width:14px;height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>';
      var promoIco = '<svg style="width:14px;height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>';
      var updateIco = '<svg style="width:14px;height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
      var systemIco = '<svg style="width:14px;height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>';

      if (t === "deposit") {
        return { label: "Deposit", bg: "rgba(16, 185, 129, 0.12)", color: "#10b981", icon: depositIco };
      } else if (t === "wallet" || t === "debit" || t === "admin_credit" || t === "admin_debit") {
        return { label: "Wallet", bg: "rgba(37, 99, 235, 0.12)", color: "var(--brand)", icon: walletIco };
      } else if (t === "order" || t === "purchase") {
        return { label: "Order", bg: "rgba(16, 185, 129, 0.12)", color: "#10b981", icon: orderIco };
      } else if (t === "refund") {
        return { label: "Refund", bg: "rgba(245, 158, 11, 0.12)", color: "#f59e0b", icon: refundIco };
      } else if (t === "promo") {
        return { label: "Promo", bg: "rgba(236, 72, 153, 0.12)", color: "#ec4899", icon: promoIco };
      } else if (t === "update") {
        return { label: "Update", bg: "rgba(6, 182, 212, 0.12)", color: "#06b6d4", icon: updateIco };
      }
      return { label: "System", bg: "rgba(100, 116, 139, 0.12)", color: "var(--text-muted)", icon: systemIco };
    }

    function renderNotifications(items) {
      cachedUserNotifs = items || [];
      if (!items || items.length === 0) {
        notifContainer.innerHTML = '<div style="padding: 2.5rem 1rem; text-align: center; color: var(--text-muted); font-size: 0.82rem;">No notifications yet</div>';
        return;
      }

      var html = "";
      items.forEach(function (n) {
        var isUnread = !n.is_read;
        var meta = getTypeMeta(n.type);
        var timeStr = formatTimeAgo(n.created_at);
        var adaptedTitle = adaptCurrencyText(n.title || 'Notification');
        var adaptedMsg = adaptCurrencyText(n.message || '');

        html += '<div class="user-notif-item' + (isUnread ? ' is-unread' : '') + '" data-notif-id="' + escapeHtml(n.id) + '" style="display: flex; gap: 0.75rem; padding: 0.8rem 1rem; border-bottom: 1px solid var(--border); cursor: default; user-select: text; transition: background 0.15s ease; position: relative; max-width: 100%; box-sizing: border-box;' + (isUnread ? ' background: rgba(37, 99, 235, 0.05);' : '') + '">';
        
        // Icon / avatar
        html += '<div style="width: 32px; height: 32px; border-radius: var(--r-full); background: ' + meta.bg + '; color: ' + meta.color + '; display: grid; place-items: center; font-size: 0.85rem; font-weight: 800; flex-shrink: 0; margin-top: 2px;">' + meta.icon + '</div>';
        
        // Content
        html += '<div style="flex: 1; min-width: 0; max-width: 100%; overflow: hidden;">';
        html += '<div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 0.4rem; margin-bottom: 0.15rem;">';
        html += '<span style="font-size: 0.82rem; font-weight: ' + (isUnread ? '800' : '600') + '; color: var(--text); overflow-wrap: anywhere; word-break: break-word; line-height: 1.25;">' + escapeHtml(adaptedTitle) + '</span>';
        html += '<span style="font-size: 0.68rem; color: var(--text-dim); white-space: nowrap; flex-shrink: 0; margin-top: 1px;">' + timeStr + '</span>';
        html += '</div>';

        html += '<div style="font-size: 0.76rem; color: var(--text-muted); line-height: 1.45; word-break: break-word; overflow-wrap: anywhere; white-space: normal; margin-top: 0.2rem;">' + escapeHtml(adaptedMsg) + '</div>';

        html += '<div style="display: flex; align-items: center; justify-content: space-between; margin-top: 0.35rem;">';
        html += '<span style="display: inline-block; font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; padding: 1px 6px; border-radius: 4px; background: ' + meta.bg + '; color: ' + meta.color + ';">' + meta.label + '</span>';
        if (isUnread) {
          html += '<span style="width: 7px; height: 7px; border-radius: 50%; background: var(--brand); display: inline-block;"></span>';
        }
        html += '</div>';

        html += '</div></div>';
      });

      notifContainer.innerHTML = html;
    }

    function escapeHtml(str) {
      if (!str) return "";
      var div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }

    function updateBadgeUI(count) {
      var unread = parseInt(count, 10) || 0;
      if (unread > 0) {
        if (bellDot) bellDot.style.display = "block";
        if (bellBadge) {
          bellBadge.style.display = "block";
          bellBadge.textContent = unread > 99 ? "99+" : unread;
        }
        if (headerBadge) {
          headerBadge.style.display = "inline-block";
          headerBadge.textContent = unread + " new";
        }
      } else {
        if (bellDot) bellDot.style.display = "none";
        if (bellBadge) bellBadge.style.display = "none";
        if (headerBadge) headerBadge.style.display = "none";
      }
    }

    async function syncNotifications(full) {
      var url = full ? "/api/notifications" : "/api/notifications/unread";
      try {
        var res = await fetch(url);
        if (!res.ok) return;
        var data = await res.json();
        if (data.success) {
          updateBadgeUI(data.unread_count);
          if (data.notifications) {
            renderNotifications(data.notifications);
          }
        }
      } catch (e) {}
    }

    // Trigger on open
    bellTrigger.addEventListener("click", function () {
      syncNotifications(true);
    });

    // Mark single notification as read quietly on click without reloading or navigating away
    notifContainer.addEventListener("click", function (e) {
      var item = e.target.closest(".user-notif-item");
      if (!item) return;

      var notifId = item.getAttribute("data-notif-id");

      if (item.classList.contains("is-unread")) {
        item.classList.remove("is-unread");
        item.style.background = "";
        var dot = item.querySelector('span[style*="border-radius: 50%"]');
        if (dot) dot.remove();

        fetch("/api/notifications/read", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ notification_id: notifId })
        }).then(function () {
          syncNotifications(false);
        }).catch(function () {});
      }
    });

    // Mark all read
    if (markAllBtn) {
      markAllBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();

        updateBadgeUI(0);
        notifContainer.querySelectorAll(".user-notif-item.is-unread").forEach(function (el) {
          el.classList.remove("is-unread");
          el.style.background = "";
          var dot = el.querySelector('span[style*="border-radius: 50%"]');
          if (dot) dot.remove();
        });

        fetch("/api/notifications/read", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ notification_id: "all" })
        }).then(function () {
          if (window.toast) window.toast("All notifications marked as read", "info");
          syncNotifications(false);
        }).catch(function () {});
      });
    }

    // Re-render notifications on currency toggle switch
    document.addEventListener("currencychange", function () {
      if (cachedUserNotifs && cachedUserNotifs.length > 0) {
        renderNotifications(cachedUserNotifs);
      }
    });

    // Initial sync & periodic 5-second polling
    syncNotifications(false);
    setInterval(function () {
      syncNotifications(false);
    }, 5000);
  }

  /* ---- Boot -------------------------------------------------------------- */
  function init() {
    initSidebar();
    initLandingMenu();
    initDropdowns();
    initModals();
    initAccordion();
    initTabs();
    initCopy();
    initPasswordToggles();
    initFlashes();
    initFormSubmitSpinners();
    initUserNotifications();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
