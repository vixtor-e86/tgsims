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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
