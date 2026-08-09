/* ==========================================================================
   theme.js  -  dark/light theme controller
   The initial theme is applied by an inline <head> snippet (see base template)
   to avoid a flash. This module wires up the toggle buttons and reacts to
   system changes.
   ========================================================================== */
(function () {
  "use strict";

  var STORAGE_KEY = "tgsims-theme";
  var root = document.documentElement;

  function systemPref() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }

  function stored() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }

  function currentTheme() {
    return root.getAttribute("data-theme") || stored() || systemPref();
  }

  function apply(theme, persist) {
    root.setAttribute("data-theme", theme);
    if (persist) {
      try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
    }
    // Keep any toggle controls in sync (aria + label).
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    });
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: theme } }));
  }

  // Smoothly transition colors only when the user actively toggles.
  function toggle() {
    var next = currentTheme() === "dark" ? "light" : "dark";
    root.classList.add("theme-transition");
    apply(next, true);
    window.setTimeout(function () { root.classList.remove("theme-transition"); }, 260);
  }

  function init() {
    // Ensure attribute is set even if the inline snippet was skipped.
    apply(currentTheme(), false);

    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.addEventListener("click", toggle);
    });

    // Follow the OS only while the user hasn't made an explicit choice.
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      var onChange = function (e) {
        if (!stored()) apply(e.matches ? "dark" : "light", false);
      };
      if (mq.addEventListener) mq.addEventListener("change", onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.TgTheme = { toggle: toggle, apply: apply, current: currentTheme };
})();
