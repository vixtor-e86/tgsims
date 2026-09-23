/* ==========================================================================
   TGSIMS  -  Realtime Support System & Floating Messenger Widget
   ========================================================================== */
(function() {
  "use strict";

  var currentTicketId = null;
  var currentTicketData = null;
  var chatPollTimer = null;
  var unreadPollTimer = null;

  // DOM Elements (retrieved dynamically or cached)
  function getEl(id) { return document.getElementById(id); }

  /* ---- Widget Open / Close ---- */
  function toggleWidget() {
    var widget = getEl("support-widget");
    if (!widget) return;
    if (widget.classList.contains("is-open")) {
      closeWidget();
    } else {
      openWidget();
    }
  }

  function openWidget(ticketId) {
    var widget = getEl("support-widget");
    var fab = getEl("support-fab");
    var backdrop = getEl("support-backdrop");
    var fabBadge = getEl("support-fab-badge");
    var topbarMailDot = getEl("mail-unread-dot");
    var topbarMailBadge = getEl("mail-unread-badge");

    if (!widget) return;
    widget.classList.add("is-open");
    if (backdrop) backdrop.classList.add("is-open");
    if (fab) fab.classList.add("is-active");

    var isAuth = widget.getAttribute("data-authenticated") === "true";

    // Instant 0ms visual feedback: hide unread badges immediately on open!
    if (fabBadge) fabBadge.style.display = "none";
    if (topbarMailDot) topbarMailDot.style.display = "none";
    if (topbarMailBadge) topbarMailBadge.style.display = "none";

    if (!isAuth) {
      switchView("login");
      return;
    }

    if (ticketId) {
      loadTicketConversation(ticketId);
    } else if (currentTicketId) {
      switchView("chat");
      pollChatMessages();
    } else {
      switchView("home");
      loadUserTickets();
    }
  }

  function closeWidget() {
    var widget = getEl("support-widget");
    var fab = getEl("support-fab");
    var backdrop = getEl("support-backdrop");

    if (!widget) return;
    widget.classList.remove("is-open");
    if (backdrop) backdrop.classList.remove("is-open");
    if (fab) fab.classList.remove("is-active");
    stopChatPolling();
  }

  window.openSupportWidget = openWidget;
  window.closeSupportWidget = closeWidget;

  /* ---- View Switching ---- */
  function switchView(viewName) {
    var viewLogin = getEl("widget-view-login");
    var viewHome = getEl("widget-view-home");
    var viewCreate = getEl("widget-view-create");
    var viewChat = getEl("widget-view-chat");

    if (viewLogin) viewLogin.style.display = viewName === "login" ? "flex" : "none";
    if (viewHome) viewHome.style.display = viewName === "home" ? "flex" : "none";
    if (viewCreate) viewCreate.style.display = viewName === "create" ? "flex" : "none";
    if (viewChat) viewChat.style.display = viewName === "chat" ? "flex" : "none";

    if (viewName !== "chat") {
      stopChatPolling();
    }
  }

  window.startNewSupportTicket = function() {
    var widget = getEl("support-widget");
    var isAuth = widget && widget.getAttribute("data-authenticated") === "true";
    if (!isAuth) {
      switchView("login");
      openWidget();
      return;
    }
    switchView("create");
    var subjectInput = getEl("widget-subject-input");
    if (subjectInput) setTimeout(function() { subjectInput.focus(); }, 100);
  };

  window.backToSupportHome = function() {
    switchView("home");
    loadUserTickets();
  };

  /* ---- Category Chips Selector ---- */
  var selectedCategory = "general";
  document.addEventListener("click", function(e) {
    var chip = e.target.closest("[data-support-cat]");
    if (chip) {
      document.querySelectorAll("[data-support-cat]").forEach(function(c) { c.classList.remove("is-active"); });
      chip.classList.add("is-active");
      selectedCategory = chip.getAttribute("data-support-cat") || "general";
    }
  });

  /* ---- Create Ticket with Subject ---- */
  document.addEventListener("submit", async function(e) {
    if (e.target && e.target.id === "widget-create-form") {
      e.preventDefault();
      var subjectInput = getEl("widget-subject-input");
      var messageInput = getEl("widget-message-input");
      var submitBtn = getEl("widget-create-submit-btn");

      var subject = (subjectInput ? subjectInput.value : "").trim();
      var message = (messageInput ? messageInput.value : "").trim();

      if (!subject || subject.length < 3) {
        if (window.toast) window.toast("Please enter a subject (at least 3 characters)", "error");
        if (subjectInput) subjectInput.focus();
        return;
      }

      if (!message) {
        if (window.toast) window.toast("Please enter your message", "error");
        if (messageInput) messageInput.focus();
        return;
      }

      if (submitBtn) submitBtn.disabled = true;

      try {
        var res = await fetch("/api/support/tickets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            subject: subject,
            message: message,
            category: selectedCategory
          })
        });
        var data = await res.json();

        if (data.success && data.ticket) {
          if (subjectInput) subjectInput.value = "";
          if (messageInput) messageInput.value = "";
          if (window.toast) window.toast("Ticket created successfully!", "success");

          // Transition straight into Messenger chat view
          await loadTicketConversation(data.ticket.id);
          syncUnreadCounts();
        } else {
          if (window.toast) window.toast(data.message || "Could not create ticket", "error");
        }
      } catch (err) {
        if (window.toast) window.toast("Network error. Please try again.", "error");
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    }
  });

  /* ---- Load Tickets List for User ---- */
  async function loadUserTickets() {
    var listEl = getEl("widget-tickets-container");
    if (!listEl) return;

    var widget = getEl("support-widget");
    if (widget && widget.getAttribute("data-authenticated") !== "true") {
      switchView("login");
      return;
    }

    try {
      var res = await fetch("/api/support/tickets");
      if (res.status === 401) {
        if (widget) widget.setAttribute("data-authenticated", "false");
        switchView("login");
        return;
      }
      var data = await res.json();
      if (data.success && data.tickets) {
        renderTicketsList(data.tickets, listEl);
      }
    } catch (e) {
      listEl.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--text-muted);font-size:0.8rem;">Unable to load tickets</div>';
    }
  }

  function renderTicketsList(tickets, container) {
    if (!tickets || tickets.length === 0) {
      container.innerHTML = '<div style="padding:2rem 1rem;text-align:center;color:var(--text-muted);font-size:0.82rem;">' +
        'No conversation history yet.<br>Click "Send us a message" above to start!</div>';
      return;
    }

    var html = "";
    tickets.forEach(function(t) {
      var statusBadgeClass = t.status === "open" ? "badge-danger" : (t.status === "pending" ? "badge-warning" : (t.status === "resolved" ? "badge-success" : "badge-secondary"));
      var timeStr = (t.updated_at || "").substring(0, 10);
      var unreadPill = (t.unread_user_count && t.unread_user_count > 0) ?
        '<span class="badge" style="background:var(--hue-danger);color:#fff;font-size:0.65rem;padding:0.15rem 0.4rem;border-radius:999px;">' + t.unread_user_count + ' new</span>' : '';

      html += '<div class="widget-ticket-item" onclick="window.openSupportWidget(\'' + t.id + '\')">' +
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.25rem;">' +
          '<span style="font-weight:700;font-size:0.82rem;color:var(--brand);font-family:var(--font-mono);">#' + escapeHtml(t.ticket_number) + '</span>' +
          '<div style="display:flex;align-items:center;gap:0.35rem;">' +
            unreadPill +
            '<span class="badge badge-dot ' + statusBadgeClass + '" style="font-size:0.7rem;text-transform:capitalize;">' + escapeHtml(t.status) + '</span>' +
          '</div>' +
        '</div>' +
        '<div style="font-weight:600;font-size:0.88rem;color:var(--text);margin-bottom:0.25rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' +
          escapeHtml(t.subject) +
        '</div>' +
        '<div style="display:flex;align-items:center;justify-content:space-between;font-size:0.72rem;color:var(--text-muted);">' +
          '<span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:210px;">' + escapeHtml(t.last_message || "Ticket opened") + '</span>' +
          '<span>' + timeStr + '</span>' +
        '</div>' +
      '</div>';
    });

    container.innerHTML = html;
  }

  /* ---- Load Ticket Chat Conversation ---- */
  async function loadTicketConversation(ticketId) {
    currentTicketId = ticketId;
    switchView("chat");

    var chatFeed = getEl("widget-chat-feed");
    if (chatFeed) {
      chatFeed.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-muted);font-size:0.85rem;">Loading conversation...</div>';
    }

    // Instant 0ms clear indicator
    var fabBadge = getEl("support-fab-badge");
    var topbarMailDot = getEl("mail-unread-dot");
    var topbarMailBadge = getEl("mail-unread-badge");
    if (fabBadge) fabBadge.style.display = "none";
    if (topbarMailDot) topbarMailDot.style.display = "none";
    if (topbarMailBadge) topbarMailBadge.style.display = "none";

    try {
      var res = await fetch("/api/support/tickets/" + ticketId);
      var data = await res.json();
      if (data.success) {
        currentTicketData = data.ticket;
        updateChatHeader(data.ticket);
        renderMessages(data.messages || []);
        startChatPolling();
        syncUnreadCounts();
      } else {
        if (window.toast) window.toast(data.message || "Failed to load ticket", "error");
        switchView("home");
      }
    } catch (err) {
      if (window.toast) window.toast("Error loading ticket", "error");
    }
  }

  function updateChatHeader(ticket) {
    if (!ticket) return;
    var chatTicketSubject = getEl("widget-chat-subject");
    var chatTicketNum = getEl("widget-chat-num");
    var chatTicketStatus = getEl("widget-chat-status");
    var chatResolvedBanner = getEl("widget-chat-resolved-banner");

    if (chatTicketSubject) chatTicketSubject.textContent = ticket.subject || "Support Request";
    if (chatTicketNum) chatTicketNum.textContent = "#" + (ticket.ticket_number || "");
    if (chatTicketStatus) {
      chatTicketStatus.textContent = ticket.status || "open";
      chatTicketStatus.className = "badge badge-dot " +
        (ticket.status === "open" ? "badge-danger" : (ticket.status === "pending" ? "badge-warning" : (ticket.status === "resolved" ? "badge-success" : "badge-secondary")));
    }
    if (chatResolvedBanner) {
      chatResolvedBanner.style.display = ticket.status === "resolved" ? "block" : "none";
    }
  }

  function renderMessages(messages) {
    var chatFeed = getEl("widget-chat-feed");
    if (!chatFeed) return;
    var html = "";
    var isScrolledToBottom = chatFeed.scrollHeight - chatFeed.scrollTop <= chatFeed.clientHeight + 90;

    messages.forEach(function(msg) {
      var timeStr = (msg.created_at || "").substring(11, 16);
      if (msg.sender_role === "system") {
        html += '<div class="chat-system-pill">' + escapeHtml(msg.message) + '</div>';
      } else if (msg.sender_role === "user") {
        html += '<div class="chat-bubble-wrap is-user">' +
          '<div class="chat-bubble">' + escapeHtml(msg.message) + '</div>' +
          '<div class="chat-bubble-time">' + timeStr + '</div>' +
        '</div>';
      } else {
        // ALWAYS display "Support" as author (never user/admin personal names)
        html += '<div class="chat-bubble-wrap is-support">' +
          '<div class="chat-bubble-author">Support</div>' +
          '<div class="chat-bubble">' + escapeHtml(msg.message) + '</div>' +
          '<div class="chat-bubble-time">' + timeStr + '</div>' +
        '</div>';
      }
    });

    chatFeed.innerHTML = html;
    if (isScrolledToBottom) {
      chatFeed.scrollTop = chatFeed.scrollHeight;
    }
  }

  /* ---- Send Message ---- */
  async function sendMessage() {
    var chatInput = getEl("widget-chat-input");
    var chatSendBtn = getEl("widget-chat-send-btn");
    var chatResolvedBanner = getEl("widget-chat-resolved-banner");

    if (!currentTicketId || !chatInput) return;
    var text = chatInput.value.trim();
    if (!text) return;

    if (chatSendBtn) chatSendBtn.disabled = true;

    try {
      var res = await fetch("/api/support/tickets/" + currentTicketId + "/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });
      var data = await res.json();
      if (data.success) {
        chatInput.value = "";
        chatInput.style.height = "auto";
        await pollChatMessages();
        if (chatResolvedBanner) chatResolvedBanner.style.display = "none";
        syncUnreadCounts();
      } else {
        if (window.toast) window.toast(data.message || "Failed to send message", "error");
      }
    } catch (e) {
      if (window.toast) window.toast("Network error sending message", "error");
    } finally {
      if (chatSendBtn) chatSendBtn.disabled = false;
      chatInput.focus();
    }
  }

  /* ---- Realtime Chat Polling (Every 3s when chat view is active) ---- */
  function startChatPolling() {
    stopChatPolling();
    chatPollTimer = setInterval(pollChatMessages, 3000);
  }

  function stopChatPolling() {
    if (chatPollTimer) {
      clearInterval(chatPollTimer);
      chatPollTimer = null;
    }
  }

  async function pollChatMessages() {
    var widget = getEl("support-widget");
    var chatTicketStatus = getEl("widget-chat-status");
    var chatResolvedBanner = getEl("widget-chat-resolved-banner");

    if (!currentTicketId || !widget || !widget.classList.contains("is-open")) return;
    try {
      var res = await fetch("/api/support/tickets/" + currentTicketId + "/messages");
      var data = await res.json();
      if (data.success && data.messages) {
        renderMessages(data.messages);
        if (data.ticket_status && chatTicketStatus) {
          chatTicketStatus.textContent = data.ticket_status;
          if (chatResolvedBanner) {
            chatResolvedBanner.style.display = data.ticket_status === "resolved" ? "block" : "none";
          }
        }
        // Messages are now marked read on server; sync unread indicators immediately
        syncUnreadCounts();
      }
    } catch (e) {}
  }

  /* ---- Sync Unread Messages & Notifications for Topbar Mail & FAB ---- */
  async function syncUnreadCounts() {
    var widget = getEl("support-widget");
    if (!widget || widget.getAttribute("data-authenticated") !== "true") {
      return;
    }
    try {
      var res = await fetch("/api/support/unread");
      if (res.status === 401) {
        widget.setAttribute("data-authenticated", "false");
        if (unreadPollTimer) clearInterval(unreadPollTimer);
        return;
      }
      var data = await res.json();

      var unreadTotal = data.unread_total || 0;
      var fabBadge = getEl("support-fab-badge");
      var topbarMailDot = getEl("mail-unread-dot");
      var topbarMailBadge = getEl("mail-unread-badge");

      // Update FAB badge
      if (fabBadge) {
        if (unreadTotal > 0) {
          fabBadge.style.display = "flex";
          fabBadge.textContent = unreadTotal > 9 ? "9+" : unreadTotal;
        } else {
          fabBadge.style.display = "none";
        }
      }

      // Update Topbar Mail icon indicators
      if (topbarMailDot && topbarMailBadge) {
        if (unreadTotal > 0) {
          topbarMailDot.style.display = "block";
          topbarMailBadge.style.display = "block";
          topbarMailBadge.textContent = unreadTotal > 9 ? "9+" : unreadTotal;
        } else {
          topbarMailDot.style.display = "none";
          topbarMailBadge.style.display = "none";
        }
      }

      // Render notifications in topbar dropdown
      var topbarNotifsList = getEl("topbar-support-notifs");
      if (topbarNotifsList && data.notifications) {
        renderTopbarNotifications(data.notifications);
      }
    } catch (e) {}
  }

  var cachedSupportNotifs = [];

  function adaptCurrencyInText(text) {
    if (!text || typeof text !== "string") return text || "";
    if (!window.TgCurrency) return text;
    var active = window.TgCurrency.active || "NGN";
    var rate = Number(window.TG_NGN_PER_USD) || (window.TgCurrency && window.TgCurrency.rate) || 1600;

    text = text.replace(/\$([0-9]+(?:\.[0-9]+)?)\s*\((?:≈\s*)?₦[0-9,]+(?:\.[0-9]+)?\)/gi, function (_, usdVal) {
      var num = parseFloat(usdVal);
      return isNaN(num) ? _ : window.TgCurrency.format(num);
    });

    text = text.replace(/₦[0-9,]+(?:\.[0-9]+)?\s*\((?:≈\s*)?\$([0-9]+(?:\.[0-9]+)?)\)/gi, function (_, usdVal) {
      var num = parseFloat(usdVal);
      return isNaN(num) ? _ : window.TgCurrency.format(num);
    });

    if (active === "NGN") {
      text = text.replace(/\$([0-9]+(?:\.[0-9]+)?)/g, function (match, usdVal) {
        var num = parseFloat(usdVal);
        return isNaN(num) ? match : window.TgCurrency.format(num);
      });
    } else {
      text = text.replace(/₦([0-9,]+(?:\.[0-9]+)?)/g, function (match, ngnVal) {
        var cleanNgn = ngnVal.replace(/,/g, "");
        var num = parseFloat(cleanNgn);
        if (isNaN(num)) return match;
        return window.TgCurrency.format(num / rate);
      });
    }
    return text;
  }

  function renderTopbarNotifications(notifs) {
    cachedSupportNotifs = notifs || [];
    var topbarNotifsList = getEl("topbar-support-notifs");
    if (!topbarNotifsList) return;
    if (!notifs || notifs.length === 0) {
      topbarNotifsList.innerHTML = '<div style="padding:2rem 1rem;text-align:center;color:var(--text-muted);font-size:0.82rem;">No support notifications</div>';
      return;
    }

    var html = "";
    notifs.forEach(function(n) {
      var timeStr = (n.created_at || "").substring(0, 16).replace("T", " ");
      var unreadCls = n.is_read ? "" : "is-unread";
      var unreadDot = n.is_read ? "" : '<span style="width:6px;height:6px;border-radius:50%;background:var(--hue-danger);display:inline-block;"></span>';
      var adaptedTitle = adaptCurrencyInText(n.title || '');
      var adaptedMsg = adaptCurrencyInText(n.message || '');

      html += '<div class="notif-item ' + unreadCls + '" onclick="handleNotifClick(\'' + (n.ticket_id || '') + '\', \'' + n.id + '\')" style="overflow-wrap: anywhere; word-break: break-word;">' +
        '<div class="notif-item-title" style="display:flex; justify-content:space-between; align-items:center;">' +
          '<span style="overflow-wrap: anywhere; word-break: break-word;">' + escapeHtml(adaptedTitle) + '</span>' +
          unreadDot +
        '</div>' +
        '<div class="notif-item-msg" style="overflow-wrap: anywhere; word-break: break-word; white-space: normal;">' + escapeHtml(adaptedMsg) + '</div>' +
        '<div class="notif-item-time">' + timeStr + '</div>' +
      '</div>';
    });

    topbarNotifsList.innerHTML = html;
  }

  document.addEventListener("currencychange", function () {
    if (cachedSupportNotifs && cachedSupportNotifs.length > 0) {
      renderTopbarNotifications(cachedSupportNotifs);
    }
  });

  window.handleNotifClick = async function(ticketId, notifId) {
    // Instant 0ms clear
    var topbarMailDot = getEl("mail-unread-dot");
    var topbarMailBadge = getEl("mail-unread-badge");
    var fabBadge = getEl("support-fab-badge");
    if (topbarMailDot) topbarMailDot.style.display = "none";
    if (topbarMailBadge) topbarMailBadge.style.display = "none";
    if (fabBadge) fabBadge.style.display = "none";

    // Mark as read on server
    try {
      fetch("/api/support/notifications/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notification_id: notifId })
      });
    } catch (e) {}

    // Close topbar dropdown if open
    document.querySelectorAll("[data-dropdown].is-open").forEach(function(d) {
      d.classList.remove("is-open");
    });

    // Open ticket in support chat
    if (ticketId) {
      openWidget(ticketId);
    } else {
      openWidget();
    }
    syncUnreadCounts();
  };

  window.markAllSupportNotifsRead = async function() {
    var topbarMailDot = getEl("mail-unread-dot");
    var topbarMailBadge = getEl("mail-unread-badge");
    var fabBadge = getEl("support-fab-badge");
    if (topbarMailDot) topbarMailDot.style.display = "none";
    if (topbarMailBadge) topbarMailBadge.style.display = "none";
    if (fabBadge) fabBadge.style.display = "none";

    try {
      await fetch("/api/support/notifications/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notification_id: "all" })
      });
      syncUnreadCounts();
      if (window.toast) window.toast("All notifications marked as read", "info");
    } catch (e) {}
  };

  function escapeHtml(str) {
    if (!str) return "";
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /* ---- Event Delegations: Works Reliably on ALL Pages ---- */

  // 1. Click FAB or any support trigger
  document.addEventListener("click", function(e) {
    var fabTarget = e.target.closest("#support-fab, [data-support-fab], [data-support-toggle]");
    if (fabTarget) {
      e.preventDefault();
      e.stopPropagation();
      toggleWidget();
      return;
    }

    var openChatTarget = e.target.closest("[data-support-ticket-id]");
    if (openChatTarget) {
      e.preventDefault();
      e.stopPropagation();
      var tid = openChatTarget.getAttribute("data-support-ticket-id");
      openWidget(tid);
      return;
    }

    var markReadBtn = e.target.closest("#mark-notifs-read-btn");
    if (markReadBtn) {
      e.preventDefault();
      window.markAllSupportNotifsRead();
      return;
    }

    var sendBtn = e.target.closest("#widget-chat-send-btn");
    if (sendBtn) {
      e.preventDefault();
      sendMessage();
      return;
    }
  });

  // 2. Click outside modal closes it (Desktop + Mobile)
  document.addEventListener("click", function(e) {
    var widget = getEl("support-widget");
    var fab = getEl("support-fab");
    var backdrop = getEl("support-backdrop");

    if (!widget || !widget.classList.contains("is-open")) return;

    // If click is on the backdrop, close immediately
    if (backdrop && (e.target === backdrop || backdrop.contains(e.target))) {
      closeWidget();
      return;
    }

    // If click is inside widget, or on FAB, or on the topbar dropdown/mail button, don't close
    if (widget.contains(e.target) || (fab && fab.contains(e.target)) ||
        e.target.closest("#support-fab") ||
        e.target.closest("#support-messages-dropdown") ||
        e.target.closest("[data-support-ticket-id]") ||
        e.target.closest(".widget-ticket-item")) {
      return;
    }

    // Otherwise it was an outside click: close the modal!
    closeWidget();
  });

  // 3. Escape key closes modal
  document.addEventListener("keydown", function(e) {
    var widget = getEl("support-widget");
    if (e.key === "Escape" && widget && widget.classList.contains("is-open")) {
      closeWidget();
    }
  });

  // 4. Enter to send message in chat textarea
  document.addEventListener("keydown", function(e) {
    if (e.target && e.target.id === "widget-chat-input") {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    }
  });

  // Fast periodic unread sync (every 3.5s for snappy notification feedback for logged-in users)
  var widgetEl = getEl("support-widget");
  if (widgetEl && widgetEl.getAttribute("data-authenticated") === "true") {
    syncUnreadCounts();
    unreadPollTimer = setInterval(syncUnreadCounts, 3500);
  }

})();
