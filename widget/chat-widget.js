/*!
 * Embeddable RAG chat widget. Drop-in for any website:
 *
 *   <script src="https://YOUR-API/static/chat-widget.js" defer></script>
 *
 * Optional attributes on the script tag:
 *   data-api="https://YOUR-API"   (defaults to the origin the script is loaded from)
 *   data-title="Ask us anything"
 *   data-welcome="Hi! How can I help?"
 *   data-color="#4f46e5"
 *   data-position="right|left"
 *
 * Styles live in a Shadow DOM, so the host page's CSS can't break the widget.
 */
(function () {
  "use strict";
  if (window.__ragChatWidget) return;
  window.__ragChatWidget = true;

  var script =
    document.currentScript || document.querySelector('script[src*="chat-widget"]');
  var ds = (script && script.dataset) || {};
  var apiBase = (ds.api || (script && script.src ? new URL(script.src).origin : ""))
    .replace(/\/$/, "");
  var color = ds.color || "#4f46e5";
  var side = ds.position === "left" ? "left" : "right";
  var title = ds.title || "Chat with us";
  var welcome = ds.welcome || "Hi! How can I help you today?";

  var CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .launcher { position: fixed; bottom: 20px; ${side}: 20px; width: 56px; height: 56px; border-radius: 50%;
      background: ${color}; color: #fff; border: 0; cursor: pointer; font-size: 26px;
      box-shadow: 0 6px 20px rgba(0,0,0,.25); z-index: 2147483646; }
    .panel { position: fixed; bottom: 90px; ${side}: 20px; width: 360px; max-width: calc(100vw - 24px);
      height: 520px; max-height: calc(100vh - 110px); background: #fff; color: #1f2937; border-radius: 14px;
      box-shadow: 0 12px 40px rgba(0,0,0,.28); display: none; flex-direction: column; overflow: hidden;
      z-index: 2147483647; }
    .panel.open { display: flex; }
    .header { background: ${color}; color: #fff; padding: 14px 16px; font-weight: 600; font-size: 15px;
      display: flex; justify-content: space-between; align-items: center; }
    .close { background: none; border: 0; color: #fff; font-size: 20px; cursor: pointer; line-height: 1; }
    .messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; background: #f9fafb; }
    .msg { max-width: 85%; padding: 9px 12px; border-radius: 12px; font-size: 14px; line-height: 1.45;
      white-space: pre-wrap; word-wrap: break-word; }
    .bot { background: #fff; border: 1px solid #e5e7eb; align-self: flex-start; }
    .user { background: ${color}; color: #fff; align-self: flex-end; }
    .src { font-size: 11px; color: #6b7280; margin-top: 6px; }
    .typing { color: #9ca3af; font-style: italic; }
    .form { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #e5e7eb; background: #fff; }
    .input { flex: 1; border: 1px solid #d1d5db; border-radius: 8px; padding: 9px 11px; font-size: 14px; outline: none; }
    .input:focus { border-color: ${color}; }
    .send { background: ${color}; color: #fff; border: 0; border-radius: 8px; padding: 0 14px; cursor: pointer; font-size: 14px; }
    .send:disabled { opacity: .5; cursor: not-allowed; }
    @media (max-width: 480px) { .panel { bottom: 0; ${side}: 0; width: 100vw; max-width: 100vw; height: 100vh; max-height: 100vh; border-radius: 0; } }
  `;

  var host = document.createElement("div");
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML =
    "<style>" + CSS + "</style>" +
    '<button class="launcher" aria-label="Open chat">\u{1F4AC}</button>' +
    '<div class="panel" role="dialog" aria-label="Chat">' +
    '  <div class="header"><span class="title"></span><button class="close" aria-label="Close chat">\u00D7</button></div>' +
    '  <div class="messages" aria-live="polite"></div>' +
    '  <div class="form"><input class="input" type="text" placeholder="Type your question..." maxlength="1000" />' +
    '  <button class="send">Send</button></div>' +
    "</div>";
  document.body.appendChild(host);

  var $ = function (s) { return root.querySelector(s); };
  var launcher = $(".launcher"), panel = $(".panel"), box = $(".messages");
  var input = $(".input"), send = $(".send");
  $(".title").textContent = title;

  function addMessage(text, who, sources) {
    var el = document.createElement("div");
    el.className = "msg " + who;
    el.textContent = text;
    if (sources && sources.length) {
      var s = document.createElement("div");
      s.className = "src";
      s.textContent = "\u{1F4C4} Source: " + sources.join(", ");
      el.appendChild(s);
    }
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
    return el;
  }

  function toggle(open) {
    panel.classList.toggle("open", open);
    if (open) input.focus();
  }

  async function ask() {
    var q = input.value.trim();
    if (!q || send.disabled) return;
    input.value = "";
    addMessage(q, "user");
    send.disabled = true;
    var typing = addMessage("Thinking...", "bot typing");

    try {
      var res = await fetch(apiBase + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q }),
      });
      typing.remove();
      if (res.status === 429) return addMessage("You're sending messages too quickly. Please wait a moment.", "bot");
      if (!res.ok) return addMessage("Sorry, something went wrong. Please try again.", "bot");
      var data = await res.json();
      addMessage(data.answer, "bot", data.sources);
    } catch (e) {
      typing.remove();
      addMessage("Can't reach the assistant right now. Please try again later.", "bot");
    } finally {
      send.disabled = false;
      input.focus();
    }
  }

  launcher.addEventListener("click", function () { toggle(!panel.classList.contains("open")); });
  $(".close").addEventListener("click", function () { toggle(false); });
  send.addEventListener("click", ask);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") ask();
    if (e.key === "Escape") toggle(false);
  });

  // Pull the title/greeting configured on the server (.env), unless overridden by data-* attributes.
  addMessage(welcome, "bot");
  fetch(apiBase + "/config")
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (cfg) {
      if (!cfg) return;
      if (!ds.title && cfg.bot_name) $(".title").textContent = cfg.bot_name;
      if (!ds.welcome && cfg.welcome_message) box.firstChild.textContent = cfg.welcome_message;
    })
    .catch(function () {});
})();
