window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  const message = event.data || {};
  if (message.type === "AHT_PING_EXTENSION") {
    window.postMessage({ type: "AHT_EXTENSION_READY" }, "*");
    return;
  }
  if (message.type === "AHT_GET_COOKIE_FROM_EXTENSION") {
    chrome.runtime.sendMessage(
      { type: "AHT_GET_SHOPEE_COOKIE" },
      (response) => {
        window.postMessage(
          {
            type: "AHT_COOKIE_FROM_EXTENSION_TO_PAGE",
            requestId: message.requestId,
            response: response || { ok: false, error: chrome.runtime.lastError && chrome.runtime.lastError.message }
          },
          "*"
        );
      }
    );
    return;
  }
  if (message.type === "AHT_ENRICH_PRODUCTS_FROM_PAGE") {
    chrome.runtime.sendMessage(
      { type: "AHT_ENRICH_PRODUCTS", payload: message.payload || {} },
      (response) => {
        window.postMessage(
          {
            type: "AHT_ENRICH_PRODUCTS_TO_PAGE",
            requestId: message.requestId,
            response: response || { ok: false, error: chrome.runtime.lastError && chrome.runtime.lastError.message }
          },
          "*"
        );
      }
    );
    return;
  }
  if (message.type === "AHT_FACEBOOK_POST_QUEUE_FROM_PAGE") {
    chrome.runtime.sendMessage(
      { type: "AHT_FACEBOOK_POST_QUEUE", payload: message.payload || {} },
      (response) => {
        window.postMessage(
          {
            type: "AHT_FACEBOOK_POST_QUEUE_TO_PAGE",
            requestId: message.requestId,
            response: response || { ok: false, error: chrome.runtime.lastError && chrome.runtime.lastError.message }
          },
          "*"
        );
      }
    );
    return;
  }
  if (message.type !== "AHT_DISCOVER_SHOPEE_FROM_PAGE") return;

  chrome.runtime.sendMessage(
    {
      type: "AHT_DISCOVER_SHOPEE",
      payload: message.payload || {}
    },
    (response) => {
      window.postMessage(
        {
          type: "AHT_DISCOVER_SHOPEE_TO_PAGE",
          requestId: message.requestId,
          response: response || { ok: false, error: chrome.runtime.lastError && chrome.runtime.lastError.message }
        },
        "*"
      );
    }
  );
});

window.postMessage({ type: "AHT_EXTENSION_READY" }, "*");
setTimeout(() => window.postMessage({ type: "AHT_EXTENSION_READY" }, "*"), 500);
setTimeout(() => window.postMessage({ type: "AHT_EXTENSION_READY" }, "*"), 1500);
