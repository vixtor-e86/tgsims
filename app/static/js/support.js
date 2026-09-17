/* ==========================================================================
   TGSIMS  -  Realtime Support System & Floating Messenger Widget
   ========================================================================== */
(function() {
  "use strict";

  var currentTicketId = null;
  var currentTicketData = null;
  var chatPollTimer = null;
  var unreadPollTimer = null;

  // DOM Elements
  var fab = document.getElementById("support-fab");
  var fabBadge = document.getElementById("support-fab-badge");
  var widget = document.getElementById("support-widget");

  // Views
  var viewHome = document.getElementById("widget-view-home");
  var viewCreate = document.getElementById("widget-view-create");
  var viewChat = document.getElementById("widget-view-chat");

  // Chat elements
  var chatFeed = document.getElementById("widget-chat-feed");
  var chatInput = document.getElementById("widget-chat-input");
  var chatSendBtn = document.getElementById("widget-chat-send-btn");
  var chatTicketSubject = document.getElementById("widget-chat-subject");
  var chatTicketNum = document.getElementById("widget-chat-num");
  var chatTicketStatus = document.getElementById("widget-chat-status");
  var chatResolvedBanner = document.getElementById("widget-chat-resolved-banner");

  // Form elements
  var createForm = document.getElementById("widget-create-form");
  var subjectInput = document.getElementById("widget-subject-input");
  var messageInput = document.getElementById("widget-message-input");
  var selectedCategory = "general";

  // Topbar elements
  var topbarMailDot = document.getElementById("mail-unread-dot");
  var topbarMailBadge = document.getElementById("mail-unread-badge");
  var topbarNotifsList = document.getElementById("topbar-support-notifs");
  var markAllReadBtn = document.getElementById("mark-notifs-read-btn");

  /* ---- Widget Open / Close ---- */
  function toggleWidget() {
    if (!widget) return;
    var isOpen = widget.classList.contains("is-open");
    if (isOpen) {
      closeWidget();
    } else {
      openWidget();
    }
  }

  function openWidget(ticketId) {
    if (!widget) return;
    widget.classList.add("is-open");
    if (fab) fab.classList.add("is-active");

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
    if (!widget) return;
    widget.classList.remove("is-open");
    if (fab) fab.classList.remove("is-active");
    stopChatPolling();
  }

  window.openSupportWidget = openWidget;
  window.closeSupportWidget = closeWidget;

  /* ---- View Switching ---- */
  function switchView(viewName) {
    if (viewHome) viewHome.style.display = viewName === "home" ? "flex" : "none";
    if (viewCreate) viewCreate.style.display = viewName === "create" ? "flex" : "none";
    if (viewChat) viewChat.style.display = viewName === "chat" ? "flex" : "none";

    if (viewName !== "chat") {
      stopChatPolling();
    }
  }

  window.startNewSupportTicket = function() {
    switchView("create");
    if (subjectInput) setTimeout(function() { subjectInput.focus(); }, 100);
  };

  window.backToSupportHome = function() {
    switchView("home");
    loadUserTickets();
  };

  /* ---- Category Chips Selector ---- */
  document.querySelectorAll("[data-support-cat]").forEach(function(chip) {
    chip.addEventListener("click", function() {
      document.querySelectorAll("[data-support-cat]").forEach(function(c) { c.classList.remove("is-active"); });
      chip.classList.add("is-active");
      selectedCategory = chip.getAttribute("data-support-cat") || "general";
    });
  });

  /* ---- Create Ticket with Subject ---- */
  if (createForm) {
    createForm.addEventListener("submit", async function(e) {
      e.preventDefault();
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

      var submitBtn = document.getElementById("widget-create-submit-btn");
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
    });
  }

  /* ---- Load Tickets List for User ---- */
  async function loadUserTickets() {
    var listEl = document.getElementById("widget-tickets-container");
    if (!listEl) return;

    try {
      var res = await fetch("/api/support/tickets");
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

    if (chatFeed) {
      chatFeed.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-muted);font-size:0.85rem;">Loading conversation...</div>';
    }

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
    if (!chatFeed) return;
    var html = "";
    var isScrolledToBottom = chatFeed.scrollHeight - chatFeed.scrollTop <= chatFeed.clientHeight + 80;

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
        html += '<div class="chat-bubble-wrap is-support">' +
          '<div class="chat-bubble-author">' + escapeHtml(msg.sender_name || "Tgsims Support") + '</div>' +
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

  if (chatSendBtn) {
    chatSendBtn.addEventListener("click", sendMessage);
  }

  if (chatInput) {
    chatInput.addEventListener("keydown", function(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
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
      }
    } catch (e) {}
  }

  /* ---- Sync Unread Messages & Notifications for Topbar Mail & FAB ---- */
  async function syncUnreadCounts() {
    try {
      var res = await fetch("/api/support/unread");
      var data = await res.json();

      var unreadTotal = data.unread_total || 0;

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
      if (topbarNotifsList && data.notifications) {
        renderTopbarNotifications(data.notifications);
      }
    } catch (e) {}
  }

  function renderTopbarNotifications(notifs) {
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

      html += '<div class="notif-item ' + unreadCls + '" onclick="handleNotifClick(\'' + (n.ticket_id || '') + '\', \'' + n.id + '\')">' +
        '<div class="notif-item-title">' +
          '<span>' + escapeHtml(n.title) + '</span>' +
          unreadDot +
        '</div>' +
        '<div class="notif-item-msg">' + escapeHtml(n.message) + '</div>' +
        '<div class="notif-item-time">' + timeStr + '</div>' +
      '</div>';
    });

    topbarNotifsList.innerHTML = html;
  }

  window.handleNotifClick = async function(ticketId, notifId) {
    // Mark as read
    try {
      await fetch("/api/support/notifications/read", {
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

  if (markAllReadBtn) {
    markAllReadBtn.addEventListener("click", window.markAllSupportNotifsRead);
  }

  function escapeHtml(str) {
    if (!str) return "";
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /* ---- Init Event Listeners ---- */
  if (fab) {
    fab.addEventListener("click", toggleWidget);
  }

  // Poll unread counts periodically every 10 seconds
  syncUnreadCounts();
  unreadPollTimer = setInterval(syncUnreadCounts, 10000);

})();
