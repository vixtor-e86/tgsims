/* ==========================================================================
   us_canada.js  -  Order US & Canada Numbers
   Dedicated high-reliability cellular line ordering for US and Canada.
   Handles country toggle, reliability package selection, carrier line routing,
   service selection, live currency formatting, and direct checkout redirect.
   ========================================================================== */
(function () {
  "use strict";

  /* Inline glyphs for high-profile services */
  var G = {
    chat: '<path d="M21 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z"/>',
    send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/>',
    mail: '<rect x="2.5" y="4.5" width="19" height="15" rx="2.5"/><path d="m3 6 9 7 9-7"/>',
    camera: '<path d="M4 8a2 2 0 0 1 2-2h1.5l1-1.5h5L16 6h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.5" r="3.2"/>',
    sparkles: '<path d="M12 3l1.8 4.7L18.5 9l-4.7 1.8L12 15l-1.8-4.2L5.5 9l4.7-1.3L12 3z"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/>',
    bank: '<path d="M3 10 12 4l9 6"/><path d="M4 10h16v9H4z"/><path d="M8 10v9M12 10v9M16 10v9M3 21h18"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    card: '<rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/>',
    flame: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    check: '<path d="M20 6 9 17l-5-5"/>'
  };

  function svg(inner) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + inner + "</svg>";
  }

  function svcVisual(id, name) {
    var n = (name || id).toLowerCase();
    if (n.indexOf("whatsapp") > -1) return { cls: "svc-whatsapp", svg: G.chat };
    if (n.indexOf("telegram") > -1) return { cls: "svc-telegram", svg: G.send };
    if (n.indexOf("google") > -1 || n.indexOf("gmail") > -1) return { cls: "svc-google", svg: G.mail };
    if (n.indexOf("instagram") > -1) return { cls: "svc-instagram", svg: G.camera };
    if (n.indexOf("openai") > -1 || n.indexOf("chatgpt") > -1 || n.indexOf("claude") > -1) return { cls: "svc-openai", svg: G.sparkles };
    if (n.indexOf("tinder") > -1 || n.indexOf("bumble") > -1) return { cls: "svc-tinder", svg: G.flame };
    if (n.indexOf("bank") > -1 || n.indexOf("zelle") > -1 || n.indexOf("cash app") > -1) return { cls: "svc-generic", svg: G.bank };
    if (n.indexOf("apple") > -1) return { cls: "svc-generic", svg: G.shield };
    if (n.indexOf("paypal") > -1) return { cls: "svc-generic", svg: G.card };
    if (n.indexOf("facebook") > -1) return { cls: "svc-facebook", letter: "f" };
    if (n.indexOf("tiktok") > -1) return { cls: "svc-tiktok", letter: "T" };
    return { cls: "svc-generic", letter: name.charAt(0).toUpperCase() };
  }

  function flagBadge(code) {
    return '<span class="flag-badge">' +
      code.split("").map(function (ch) { return "<i>" + ch + "</i>"; }).join("") +
      "</span>";
  }

  function init() {
    var root = document.querySelector("[data-usca]");
    if (!root) return;

    var endpoint = root.getAttribute("data-endpoint") || "/api/purchase-us-canada";
    var config = {};
    try {
      config = JSON.parse(root.getAttribute("data-config") || "{}");
    } catch (e) {
      config = {};
    }

    var countries = config.countries || [];
    var packages = config.packages || [];
    var providers = config.providers || [];
    var services = config.services || [];

    var countryCards = root.querySelectorAll("[data-usca-country]");
    var pkgCards = root.querySelectorAll("[data-usca-pkg]");
    var serviceGrid = root.querySelector("[data-usca-service-grid]");
    var serviceSearch = root.querySelector("[data-usca-service-search]");

    var reviewCountry = root.querySelector("[data-review-country]");
    var reviewPkg = root.querySelector("[data-review-pkg]");
    var reviewService = root.querySelector("[data-review-service]");
    var reviewScreen = root.querySelector("[data-review-screen]");
    var reviewPrice = root.querySelector("[data-review-price]");
    var submit = root.querySelector("[data-usca-submit]");

    var state = {
      country: countries[0] || { country_code: "US", country_name: "United States" },
      pkg: packages[2] || packages[0] || { id: "whatsapp_guaranteed", name: "Ultra Clean WhatsApp Line", price_usd: 2.50 },
      provider: providers[0] || { id: "auto", name: "Express Dynamic Line" },
      service: services[0] || { id: "whatsapp", name: "WhatsApp" }
    };

    function priceRender() {
      if (window.TgCurrency && window.TgCurrency.render) {
        window.TgCurrency.render(root);
      }
    }

    /* ---- Render services grid ---- */
    function renderServices(filter) {
      if (!serviceGrid) return;
      serviceGrid.innerHTML = "";
      var q = (filter || "").trim().toLowerCase();
      var shown = services.filter(function (s) {
        return !q || s.name.toLowerCase().indexOf(q) > -1 || (s.category && s.category.toLowerCase().indexOf(q) > -1);
      });

      if (!shown.length) {
        serviceGrid.innerHTML = '<div class="tile-empty">No services match your search.</div>';
        return;
      }

      shown.forEach(function (s) {
        var vis = svcVisual(s.id, s.name);
        var glyph = vis.svg
          ? svg(vis.svg)
          : '<span style="font-weight:800;font-size:1.15rem;line-height:1;">' + vis.letter + "</span>";

        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "opt-tile";
        btn.dataset.id = s.id;
        btn.dataset.name = s.name;
        if (state.service && state.service.id === s.id) {
          btn.classList.add("is-selected");
        }

        btn.innerHTML =
          '<span class="opt-tile-check">' + svg(G.check) + "</span>" +
          '<span class="svc-ico ' + vis.cls + '">' + glyph + "</span>" +
          '<span class="opt-tile-name">' + s.name + "</span>" +
          '<span class="opt-tile-sub" data-usd="' + state.pkg.price_usd + '">' + state.pkg.price_usd + "</span>";

        serviceGrid.appendChild(btn);
      });

      priceRender();
    }

    /* ---- Update Review Card ---- */
    function updateReview() {
      if (reviewCountry && state.country) {
        reviewCountry.innerHTML = flagBadge(state.country.country_code) +
          "<span>" + state.country.country_name + " (" + state.country.dial + ")</span>";
      }

      if (reviewPkg && state.pkg) {
        reviewPkg.textContent = state.pkg.name;
      }

      if (reviewService && state.service) {
        reviewService.textContent = state.service.name;
      }

      if (reviewScreen && state.pkg) {
        if (state.pkg.id === "whatsapp_guaranteed") {
          reviewScreen.className = "badge badge-success";
          reviewScreen.textContent = "WhatsApp Verified Unbanned";
        } else if (state.pkg.id === "vip_private") {
          reviewScreen.className = "badge badge-warning";
          reviewScreen.textContent = "Bank & FinTech Certified";
        } else {
          reviewScreen.className = "badge badge-brand";
          reviewScreen.textContent = state.pkg.reliability || "Cellular Direct";
        }
      }

      if (reviewPrice && state.pkg) {
        reviewPrice.setAttribute("data-usd", String(state.pkg.price_usd));
      }

      if (submit) {
        submit.disabled = !(state.country && state.pkg && state.service);
      }

      priceRender();
    }

    /* ---- Events: Country selection ---- */
    countryCards.forEach(function (card) {
      card.addEventListener("click", function () {
        var code = card.getAttribute("data-usca-country");
        var c = countries.filter(function (x) { return x.country_code === code; })[0];
        if (!c) return;
        state.country = c;

        countryCards.forEach(function (el) { el.classList.remove("is-selected"); });
        card.classList.add("is-selected");

        updateReview();
      });
    });

    /* ---- Events: Package selection ---- */
    pkgCards.forEach(function (card) {
      card.addEventListener("click", function () {
        var pkgId = card.getAttribute("data-usca-pkg");
        var p = packages.filter(function (x) { return x.id === pkgId; })[0];
        if (!p) return;
        state.pkg = p;

        pkgCards.forEach(function (el) { el.classList.remove("is-selected"); });
        card.classList.add("is-selected");

        // Update tile prices in the service grid
        if (serviceGrid) {
          serviceGrid.querySelectorAll(".opt-tile-sub").forEach(function (sub) {
            sub.setAttribute("data-usd", String(p.price_usd));
          });
        }

        updateReview();
      });
    });

    /* ---- Events: Service selection ---- */
    if (serviceGrid) {
      serviceGrid.addEventListener("click", function (e) {
        var tile = e.target.closest(".opt-tile");
        if (!tile) return;
        var sId = tile.dataset.id;
        var s = services.filter(function (x) { return x.id === sId; })[0];
        if (!s) return;
        state.service = s;

        serviceGrid.querySelectorAll(".opt-tile").forEach(function (el) {
          el.classList.toggle("is-selected", el.dataset.id === sId);
        });

        updateReview();
      });
    }

    /* ---- Events: Search service ---- */
    if (serviceSearch) {
      serviceSearch.addEventListener("input", function () {
        renderServices(serviceSearch.value);
      });
    }

    /* ---- Submit Purchase ---- */
    if (submit) {
      submit.addEventListener("click", function () {
        if (submit.disabled || !state.country || !state.pkg || !state.service) return;

        var origHtml = submit.innerHTML;
        submit.disabled = true;
        submit.classList.add("is-loading");
        submit.setAttribute("aria-busy", "true");
        submit.innerHTML = '<span class="spinner"></span> <span>Ordering Number...</span>';

        var payload = {
          country_code: state.country.country_code,
          country_name: state.country.country_name,
          package_id: state.pkg.id,
          provider_id: state.provider ? state.provider.id : "auto",
          service_name: state.service.name,
          price: state.pkg.price_usd
        };

        fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        })
          .then(function (res) {
            if (res.status === 401) {
              window.location.href = "/auth/login";
              throw new Error("Please sign in to complete your order.");
            }
            return res.json().then(function (data) { return { ok: res.ok, data: data }; });
          })
          .then(function (r) {
            if (!r.ok) throw new Error(r.data.message || "Could not allocate number.");
            submit.innerHTML = '<span class="spinner"></span> <span>Number Activated! Redirecting...</span>';
            if (window.toast) window.toast(r.data.message || "Number ordered successfully!", "success");
            setTimeout(function () {
              window.location.href = r.data.redirect_url || "/sims/my-sims";
            }, 600);
          })
          .catch(function (err) {
            if (window.toast) window.toast(err.message || "Unable to complete order. Try again.", "error");
            submit.disabled = false;
            submit.classList.remove("is-loading");
            submit.removeAttribute("aria-busy");
            submit.innerHTML = origHtml;
          });
      });
    }

    /* ---- Listen for currency change ---- */
    document.addEventListener("currencychange", function () {
      priceRender();
    });

    /* ---- Initial paint ---- */
    renderServices("");
    updateReview();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
