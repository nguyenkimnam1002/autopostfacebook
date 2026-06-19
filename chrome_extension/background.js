const DEFAULT_KEYWORDS = [
  "may xay sinh to",
  "noi chien khong dau",
  "cay lau nha",
  "ke bep",
  "may hut bui mini",
  "noi com dien",
  "hop dung thuc pham",
  "quat dien"
];

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "AHT_GET_SHOPEE_COOKIE") {
    getShopeeCookie()
      .then((cookie) => sendResponse({ ok: true, cookie }))
      .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
    return true;
  }
  if (message && message.type === "AHT_ENRICH_PRODUCTS") {
    enrichProducts(message.payload || {})
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
    return true;
  }
  if (message && message.type === "AHT_FACEBOOK_POST_QUEUE") {
    runFacebookPostQueue(message.payload || {})
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
    return true;
  }
  if (!message || message.type !== "AHT_DISCOVER_SHOPEE") return false;
  discoverShopee(message.payload || {})
    .then((payload) => sendResponse({ ok: true, payload }))
    .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
  return true;
});

async function getShopeeCookie() {
  const cookies = await chrome.cookies.getAll({ domain: "shopee.vn" });
  const pairs = [];
  const seen = new Set();
  for (const cookie of cookies) {
    if (!cookie.name || seen.has(cookie.name)) continue;
    seen.add(cookie.name);
    pairs.push(`${cookie.name}=${cookie.value || ""}`);
  }
  if (!pairs.length) {
    throw new Error("Chua co cookie Shopee trong Chrome. Hay dang nhap Shopee/Affiliate roi thu lai.");
  }
  return pairs.join("; ");
}

async function runFacebookPostQueue(payload) {
  const pageUrl = String(payload.pageUrl || "");
  const queue = Array.isArray(payload.queue) ? payload.queue : [];
  const autoPost = Boolean(payload.autoPost);
  if (!pageUrl.includes("facebook.com/")) throw new Error("Facebook fanpage URL khong hop le.");
  if (!queue.length) throw new Error("Chua co bai dang nao trong hang doi.");

  const tab = await getOrCreateFacebookTab(pageUrl);
  const results = [];
  for (const item of queue) {
    await chrome.tabs.update(tab.id, { url: pageUrl, active: true });
    await waitForTabComplete(tab.id);
    await delay(3500);
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: fillFacebookComposer,
      args: [item.post || "", autoPost]
    });
    results.push({
      product_id: item.product_id || null,
      title: item.title || "",
      ok: Boolean(result && result.ok),
      posted: Boolean(result && result.posted),
      error: result && result.error
    });
    if (!autoPost) break;
    await delay(7000);
  }
  return { results, autoPost };
}

async function getOrCreateFacebookTab(pageUrl) {
  const tabs = await chrome.tabs.query({ url: ["https://facebook.com/*", "https://www.facebook.com/*"] });
  const existing = tabs.find((tab) => tab.id && tab.url && tab.url.startsWith(pageUrl));
  if (existing) return existing;
  const tab = await chrome.tabs.create({ url: pageUrl, active: true });
  await waitForTabComplete(tab.id);
  return tab;
}

async function fillFacebookComposer(postText, autoPost) {
  function visible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  }

  function byText(selector, values) {
    const lowered = values.map((value) => value.toLowerCase());
    return Array.from(document.querySelectorAll(selector)).find((el) => {
      const text = (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim().toLowerCase();
      return visible(el) && lowered.some((value) => text.includes(value));
    });
  }

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function setNativeText(el, text) {
    el.focus();
    document.execCommand("selectAll", false, null);
    document.execCommand("insertText", false, text);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  }

  try {
    const composerButton =
      byText('[role="button"], div[aria-label], span', [
        "bạn đang nghĩ gì",
        "what's on your mind",
        "tạo bài viết",
        "create post"
      ]) || document.querySelector('[aria-label*="Bạn đang nghĩ gì"], [aria-label*="Create post"]');
    if (!composerButton) return { ok: false, error: "Khong tim thay nut/khung tao bai viet tren fanpage." };
    composerButton.click();
    await wait(2500);

    let editor = Array.from(document.querySelectorAll('[contenteditable="true"][role="textbox"], [contenteditable="true"]'))
      .filter(visible)
      .pop();
    if (!editor) {
      const dialog = document.querySelector('[role="dialog"]');
      editor = dialog && Array.from(dialog.querySelectorAll('[contenteditable="true"]')).filter(visible).pop();
    }
    if (!editor) return { ok: false, error: "Khong tim thay o nhap noi dung bai viet." };
    setNativeText(editor, postText);
    await wait(1200);

    if (!autoPost) return { ok: true, posted: false };

    const dialog = document.querySelector('[role="dialog"]') || document;
    const postButton = Array.from(dialog.querySelectorAll('[role="button"], div[aria-label]')).find((el) => {
      const text = (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim().toLowerCase();
      const disabled = el.getAttribute("aria-disabled") === "true" || el.getAttribute("disabled") !== null;
      return visible(el) && !disabled && ["đăng", "post"].includes(text);
    });
    if (!postButton) return { ok: false, error: "Da dien noi dung nhung khong tim thay nut Dang kha dung." };
    postButton.click();
    return { ok: true, posted: true };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
}

async function enrichProducts(payload) {
  const products = Array.isArray(payload.products) ? payload.products : [];
  const limit = clamp(Number(payload.limit || products.length), 1, 500);
  const output = [];
  const errors = [];
  const scanTarget = await createHiddenShopeeScanTarget();
  try {
    for (const product of products.slice(0, limit)) {
      try {
        const url = product.source_url || product.url;
        if (!url || !String(url).startsWith("https://shopee.vn/")) {
          output.push(product);
          continue;
        }
        await chrome.tabs.update(scanTarget.tabId, { url, active: false });
        await waitForTabComplete(scanTarget.tabId);
        await delay(3500);
        const [{ result: apiResult }] = await chrome.scripting.executeScript({
          target: { tabId: scanTarget.tabId },
          func: scrapeProductDetailFromApi,
          args: [url]
        });
        let result = apiResult;
        if (!result || !result.ok) {
          const [{ result: domResult }] = await chrome.scripting.executeScript({
            target: { tabId: scanTarget.tabId },
            func: scrapeProductMediaFromPage
          });
          result = domResult;
        }
        if (result && result.ok) {
          const cleanedTitle = cleanShopeeTitle(result.title);
          const canUseShopeeTitle = shouldReplaceTitle(product.title) && isUsefulProductTitle(cleanedTitle);
          const canUseMedia = isUsefulProductTitle(cleanedTitle) || isSameProductPage(result.pageUrl, product);
          const resultImages = canUseMedia ? (result.images || []) : [];
          const resultVideos = canUseMedia ? (result.videos || []) : [];
          output.push({
            ...product,
            title: canUseShopeeTitle ? cleanedTitle : product.title,
            image_url: product.image_url || resultImages[0] || null,
            image_urls: unique([...(product.image_urls || []), ...(resultImages.slice(product.image_url ? 0 : 1))]),
            video_url: product.video_url || resultVideos[0] || null,
            video_urls: unique([...(product.video_urls || []), ...(resultVideos.slice(product.video_url ? 0 : 1))]),
            description: product.description || result.description || null
          });
        } else {
          errors.push(`${product.product_id || product.title}: ${(result && result.error) || "khong lay duoc media"}`);
          output.push(product);
        }
      } catch (error) {
        errors.push(`${product.product_id || product.title}: ${error.message || error}`);
        output.push(product);
      }
    }
  } finally {
    try {
      await chrome.windows.remove(scanTarget.windowId);
    } catch {}
  }
  return { products: output, errors };
}

async function createHiddenShopeeScanTarget() {
  const win = await chrome.windows.create({
    url: "https://shopee.vn/",
    focused: false,
    state: "minimized",
    type: "normal"
  });
  const tab = (win.tabs || [])[0];
  if (!tab || !tab.id || !win.id) throw new Error("Khong tao duoc cua so nen de quet Shopee.");
  await waitForTabComplete(tab.id);
  return { windowId: win.id, tabId: tab.id };
}

function unique(values) {
  return Array.from(new Set((values || []).filter(Boolean)));
}

function shouldReplaceTitle(title) {
  return !title || String(title).includes("?") || String(title).includes("�");
}

function cleanShopeeTitle(title) {
  return String(title || "")
    .replace(/\s*\|\s*Shopee.*$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

async function fetchProductDetailFromBackground(productUrl) {
  const ids = parseShopeeProductIds(productUrl);
  if (!ids) return { ok: false, error: "khong tach duoc shop_id/item_id" };
  try {
    const res = await fetch(`https://shopee.vn/api/v4/pdp/get_pc?shop_id=${ids.shopId}&item_id=${ids.itemId}`, {
      credentials: "include",
      headers: {
        accept: "application/json",
        "x-requested-with": "XMLHttpRequest"
      }
    });
    const text = await res.text();
    if (!res.ok) return { ok: false, error: `Shopee detail HTTP ${res.status}: ${text.slice(0, 160)}` };
    return productDetailFromShopeePayload(JSON.parse(text), productUrl);
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
}

function parseShopeeProductIds(url) {
  const text = String(url || "");
  let match = text.match(/\/product\/(\d+)\/(\d+)/);
  if (match) return { shopId: match[1], itemId: match[2] };
  match = text.match(/(?:^|-)i\.(\d+)\.(\d+)/);
  if (match) return { shopId: match[1], itemId: match[2] };
  return null;
}

function productDetailFromShopeePayload(payload, pageUrl) {
  const data = (payload && payload.data) || {};
  const item = (payload && (payload.item || data.item || data)) || {};
  const productImages = data.product_images || {};
  const images = [];
  function addImage(id) {
    const url = shopeeImageUrl(id);
    if (url) images.push(url);
  }
  addImage(item.image);
  for (const id of productImages.images || []) addImage(id);
  for (const id of item.images || []) addImage(id);
  const videos = [];
  function addVideo(video) {
    const url = shopeeVideoUrl(video);
    if (url) videos.push(url);
  }
  addVideo(productImages.video);
  for (const video of productImages.shopee_video_info_list || []) addVideo(video);
  for (const video of item.video_info_list || []) {
    addVideo(video);
  }
  return {
    ok: true,
    pageUrl,
    title: item.name || item.title || "",
    description: item.description || "",
    images: unique(images).slice(0, 12),
    videos: unique(videos).slice(0, 4)
  };
}

function shopeeImageUrl(id) {
  if (!id) return null;
  if (String(id).startsWith("http")) return id;
  return `https://down-vn.img.susercontent.com/file/${id}`;
}

function shopeeVideoUrl(video) {
  for (const key of ["default_format", "format"]) {
    if (video && video[key] && (video[key].url || video[key].file_url)) return video[key].url || video[key].file_url;
  }
  for (const item of (video && video.formats) || []) {
    if (item && (item.url || item.file_url)) return item.url || item.file_url;
  }
  return video && (video.url || video.file_url);
}

function isUsefulProductTitle(title) {
  const text = String(title || "").replace(/\s+/g, " ").trim();
  const lower = text.toLowerCase();
  if (text.length < 12) return false;
  return ![
    "shopee việt nam",
    "shopee viet nam",
    "hot deals",
    "best prices",
    "search results",
    "mua sắm online",
    "mua sam online"
  ].some((marker) => lower.includes(marker));
}

function isSameProductPage(pageUrl, product) {
  const value = String(pageUrl || "");
  const productId = String((product && product.product_id) || "");
  if (productId && value.includes(productId)) return true;
  const source = String((product && product.source_url) || "");
  const ids = source.match(/(?:\/product\/|\.i\.)(\d+)[/.](\d+)/);
  return Boolean(ids && value.includes(ids[2]));
}

function scrapeProductDetailFromApi(productUrl) {
  function parseIds(url) {
    const text = String(url || "");
    let match = text.match(/\/product\/(\d+)\/(\d+)/);
    if (match) return { shopId: match[1], itemId: match[2] };
    match = text.match(/(?:^|-)i\.(\d+)\.(\d+)/);
    if (match) return { shopId: match[1], itemId: match[2] };
    return null;
  }
  function imageUrl(id) {
    if (!id) return null;
    if (String(id).startsWith("http")) return id;
    return `https://down-vn.img.susercontent.com/file/${id}`;
  }
  function videoUrl(video) {
    for (const key of ["default_format", "format"]) {
      if (video && video[key] && (video[key].url || video[key].file_url)) return video[key].url || video[key].file_url;
    }
    for (const item of (video && video.formats) || []) {
      if (item && (item.url || item.file_url)) return item.url || item.file_url;
    }
    return video && (video.url || video.file_url);
  }
  function pageUnique(values) {
    return Array.from(new Set((values || []).filter(Boolean)));
  }
  return (async () => {
    try {
      const ids = parseIds(productUrl || location.href);
      if (!ids) return { ok: false, error: "khong tach duoc shop_id/item_id" };
      const res = await fetch(`/api/v4/pdp/get_pc?shop_id=${ids.shopId}&item_id=${ids.itemId}`, {
        credentials: "include",
        headers: {
          accept: "application/json",
          "x-requested-with": "XMLHttpRequest"
        }
      });
      const text = await res.text();
      if (!res.ok) return { ok: false, error: `Shopee detail HTTP ${res.status}: ${text.slice(0, 160)}` };
      const payload = JSON.parse(text);
      const data = payload.data || {};
      const item = payload.item || data.item || data || {};
      const productImages = data.product_images || {};
      const images = [];
      function addImage(id) {
        const url = imageUrl(id);
        if (url) images.push(url);
      }
      addImage(item.image);
      for (const id of productImages.images || []) addImage(id);
      for (const id of item.images || []) addImage(id);
      const videos = [];
      function addVideo(video) {
        const url = videoUrl(video);
        if (url) videos.push(url);
      }
      addVideo(productImages.video);
      for (const video of productImages.shopee_video_info_list || []) addVideo(video);
      for (const video of item.video_info_list || []) {
        addVideo(video);
      }
      return {
        ok: true,
        pageUrl: location.href,
        title: item.name || item.title || "",
        description: item.description || "",
        images: pageUnique(images).slice(0, 12),
        videos: pageUnique(videos).slice(0, 4)
      };
    } catch (error) {
      return { ok: false, error: String(error && error.message ? error.message : error) };
    }
  })();
}

function scrapeProductMediaFromPage() {
  function pageUnique(values) {
    return Array.from(new Set((values || []).filter(Boolean)));
  }
  function abs(value) {
    try {
      return new URL(value, location.href).href;
    } catch {
      return "";
    }
  }
  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }
  try {
    const scriptText = Array.from(document.scripts).map((script) => script.textContent || "").join("\n");
    const imageCandidates = [
      ...Array.from(document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"]')).map((el) => el.content)
    ]
      .map(abs)
      .flatMap((url) => String(url || "").split(/\s*,\s*/).map((item) => item.trim().split(/\s+/)[0]))
      .filter((url) => url && url.includes("susercontent.com/file/") && !url.includes("data:image") && !url.includes("avatar") && !url.includes("logo") && !url.includes("facebook"));
    const videoCandidates = [
      ...Array.from(document.querySelectorAll('meta[property="og:video"], meta[property="og:video:url"]')).map((el) => el.content),
      ...Array.from(document.querySelectorAll("video source, video")).map((el) => el.src || el.currentSrc),
      ...Array.from(scriptText.matchAll(/https?:\\?\/\\?\/[^"']+\.(?:mp4|m3u8)[^"']*/gi)).map((match) => match[0].replaceAll("\\/", "/")),
      ...Array.from(scriptText.matchAll(/"file_url"\s*:\s*"([^"]+)"/gi)).map((match) => match[1].replaceAll("\\/", "/"))
    ]
      .map(abs)
      .filter((url) => url && !url.startsWith("blob:"));
    const title = clean(document.querySelector('meta[property="og:title"]')?.content || document.title);
    const description = clean(
      document.querySelector('meta[property="og:description"]')?.content ||
        document.querySelector('meta[name="description"]')?.content ||
        ""
    );
    return {
      ok: true,
      pageUrl: location.href,
      title,
      description,
      images: pageUnique(imageCandidates).slice(0, 12),
      videos: pageUnique(videoCandidates).slice(0, 4)
    };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
}

async function discoverShopee(payload) {
  const keywords = parseKeywords(payload.keywords);
  const perKeyword = clamp(Number(payload.perKeyword || 20), 1, 60);
  const maxProducts = clamp(Number(payload.maxProducts || 100), 1, 300);
  const productsByUrl = new Map();
  const errors = [];

  for (const keyword of keywords) {
    try {
      const items = await fetchKeywordWithFallback(keyword, perKeyword);
      for (const product of items) {
        if (!productsByUrl.has(product.url)) productsByUrl.set(product.url, product);
        if (productsByUrl.size >= maxProducts) break;
      }
    } catch (error) {
      errors.push(`${keyword}: ${error.message || error}`);
    }
    if (productsByUrl.size >= maxProducts) break;
  }

  const products = Array.from(productsByUrl.values());
  if (!products.length && errors.length) {
    throw new Error(errors.slice(0, 3).join("; "));
  }

  return { products, errors };
}

async function fetchKeywordWithFallback(keyword, limit) {
  try {
    return await fetchKeyword(keyword, limit);
  } catch (error) {
    const message = String(error && error.message ? error.message : error);
    if (!message.includes("Shopee HTTP 403")) throw error;
    return fetchKeywordInShopeeTab(keyword, limit);
  }
}

async function fetchKeyword(keyword, limit) {
  const params = new URLSearchParams({
    by: "sales",
    keyword,
    limit: String(limit),
    newest: "0",
    order: "desc",
    page_type: "search",
    scenario: "PAGE_GLOBAL_SEARCH",
    version: "2"
  });
  const url = `https://shopee.vn/api/v4/search/search_items?${params.toString()}`;
  const res = await fetch(url, {
    credentials: "include",
    headers: {
      accept: "application/json",
      "x-requested-with": "XMLHttpRequest"
    }
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Shopee HTTP ${res.status}: ${text.slice(0, 180)}`);
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error("Shopee returned non-JSON response");
  }
  const rawItems = payload.items || (payload.data && payload.data.items) || [];
  return rawItems.map((raw) => productFromShopeeItem(raw.item_basic || raw.item || raw, keyword)).filter(Boolean);
}

async function fetchKeywordInShopeeTab(keyword, limit) {
  const tab = await getShopeeTab(keyword);
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: fetchKeywordFromPage,
    args: [keyword, limit]
  });
  if (result && result.ok) {
    return result.products || [];
  }

  return scrapeKeywordInShopeeTab(tab.id, keyword, limit, (result && result.error) || "Shopee tab fetch failed");
}

async function getShopeeTab(keyword) {
  const tabs = await chrome.tabs.query({ url: ["https://shopee.vn/*", "https://affiliate.shopee.vn/*"] });
  const existing = tabs.find((tab) => tab.id && tab.url && tab.url.startsWith("https://shopee.vn/"));
  if (existing) return existing;

  const tab = await chrome.tabs.create({
    url: `https://shopee.vn/search?keyword=${encodeURIComponent(keyword)}`,
    active: false
  });
  await waitForTabComplete(tab.id);
  return tab;
}

function waitForTabComplete(tabId) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("Shopee tab load timeout"));
    }, 20000);
    function listener(updatedTabId, changeInfo) {
      if (updatedTabId !== tabId || changeInfo.status !== "complete") return;
      clearTimeout(timeout);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }
    chrome.tabs.get(tabId, (tab) => {
      if (chrome.runtime.lastError) {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (tab.status === "complete") {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    });
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function scrapeKeywordInShopeeTab(tabId, keyword, limit, previousError) {
  const searchUrl = `https://shopee.vn/search?keyword=${encodeURIComponent(keyword)}&sortBy=sales`;
  await chrome.tabs.update(tabId, { url: searchUrl, active: false });
  await waitForTabComplete(tabId);
  await delay(3500);
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: scrapeProductsFromSearchPage,
    args: [keyword, limit]
  });
  if (!result || !result.ok || !(result.products || []).length) {
    throw new Error(`${previousError}; DOM scrape failed: ${(result && result.error) || "khong thay san pham tren trang search"}`);
  }
  return result.products || [];
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function scrapeProductsFromSearchPage(keyword, limit) {
  function absoluteUrl(href) {
    try {
      return new URL(href, location.origin).href;
    } catch {
      return "";
    }
  }

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function parsePrice(text) {
    const match = cleanText(text).match(/(?:₫|đ)\s*([0-9.,]+)/i) || cleanText(text).match(/([0-9][0-9.,]{3,})/);
    if (!match) return null;
    const value = match[1].replace(/[^\d]/g, "");
    return value ? Number(value) : null;
  }

  function parseSold(text) {
    const normalized = cleanText(text).toLowerCase();
    const match = normalized.match(/đã bán\s*([0-9.,]+)\s*([kKmM]?)/) || normalized.match(/sold\s*([0-9.,]+)\s*([kKmM]?)/);
    if (!match) return null;
    const base = Number(match[1].replace(",", "."));
    if (!Number.isFinite(base)) return null;
    const suffix = match[2].toLowerCase();
    if (suffix === "k") return Math.round(base * 1000);
    if (suffix === "m") return Math.round(base * 1000000);
    return Math.round(base);
  }

  try {
    const max = Math.max(1, Math.min(Number(limit) || 20, 60));
    const links = Array.from(document.querySelectorAll('a[href*="-i."], a[href*="/product/"]'));
    const products = [];
    const seen = new Set();
    for (const link of links) {
      const url = absoluteUrl(link.getAttribute("href") || "");
      if (!url || seen.has(url)) continue;
      const card = link.closest("li, div") || link;
      const text = cleanText(card.innerText || link.innerText || "");
      const image = card.querySelector("img") || link.querySelector("img");
      const title = cleanText(
        image && image.alt && image.alt.length > 8
          ? image.alt
          : (link.getAttribute("title") || text.split("₫")[0] || text.split("đ")[0])
      );
      if (!title || title.length < 8) continue;
      seen.add(url);
      products.push({
        title,
        url,
        price: parsePrice(text),
        original_price: null,
        sold_week: parseSold(text),
        sold_month: parseSold(text),
        rating: null,
        review_count: null,
        commission_rate: null,
        shop_name: null,
        category: `Shopee DOM search: ${keyword}`,
        image_url: image ? (image.currentSrc || image.src || null) : null,
        image_urls: [],
        video_urls: [],
        description: text.slice(0, 300)
      });
      if (products.length >= max) break;
    }
    return { ok: true, products };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
}

async function fetchKeywordFromPage(keyword, limit) {
  function pageShopeePrice(value) {
    if (value === null || value === undefined) return null;
    return Math.round(Number(value) / 100000);
  }

  function pageImageUrl(id) {
    if (!id) return null;
    if (String(id).startsWith("http")) return id;
    return `https://down-vn.img.susercontent.com/file/${id}`;
  }

  function pageVideoUrl(video) {
    for (const key of ["default_format", "format"]) {
      if (video && video[key] && (video[key].url || video[key].file_url)) return video[key].url || video[key].file_url;
    }
    for (const item of (video && video.formats) || []) {
      if (item && (item.url || item.file_url)) return item.url || item.file_url;
    }
    return video && (video.url || video.file_url);
  }

  function pageProductUrl(title, shopid, itemid) {
    const slug = String(title).replace(/[^a-zA-Z0-9\u00C0-\u1EF9]+/g, "-").replace(/^-+|-+$/g, "");
    return `https://shopee.vn/${encodeURIComponent(slug)}-i.${shopid}.${itemid}`;
  }

  function pageProductFromShopeeItem(item) {
    if (!item || !item.name || !item.shopid || !item.itemid) return null;
    const rating = item.item_rating || {};
    const ratingCount = Array.isArray(rating.rating_count) ? rating.rating_count : [];
    const images = [];
    if (item.image) images.push(pageImageUrl(item.image));
    for (const id of item.images || []) images.push(pageImageUrl(id));
    const videos = [];
    for (const video of item.video_info_list || []) {
      const url = pageVideoUrl(video);
      if (url) videos.push(url);
    }
    return {
      title: item.name,
      url: pageProductUrl(item.name, item.shopid, item.itemid),
      price: pageShopeePrice(item.price || item.price_min),
      original_price: pageShopeePrice(item.price_before_discount || item.price_max_before_discount),
      sold_week: item.sold || null,
      sold_month: item.historical_sold || null,
      rating: rating.rating_star || null,
      review_count: ratingCount.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0) || null,
      commission_rate: null,
      shop_name: item.shop_name || null,
      category: `Shopee tab search: ${keyword}`,
      image_url: images[0] || null,
      image_urls: images.slice(1),
      video_urls: videos,
      description: null
    };
  }

  try {
    const params = new URLSearchParams({
      by: "sales",
      keyword,
      limit: String(Math.max(1, Math.min(Number(limit) || 20, 60))),
      newest: "0",
      order: "desc",
      page_type: "search",
      scenario: "PAGE_GLOBAL_SEARCH",
      version: "2"
    });
    const res = await fetch(`/api/v4/search/search_items?${params.toString()}`, {
      credentials: "include",
      headers: {
        accept: "application/json",
        "x-requested-with": "XMLHttpRequest"
      }
    });
    const text = await res.text();
    if (!res.ok) return { ok: false, error: `Shopee tab HTTP ${res.status}: ${text.slice(0, 180)}` };
    const payload = JSON.parse(text);
    const rawItems = payload.items || (payload.data && payload.data.items) || [];
    return {
      ok: true,
      products: rawItems.map((raw) => pageProductFromShopeeItem(raw.item_basic || raw.item || raw)).filter(Boolean)
    };
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
}

function productFromShopeeItem(item, keyword) {
  if (!item || !item.name || !item.shopid || !item.itemid) return null;
  const rating = item.item_rating || {};
  const ratingCount = Array.isArray(rating.rating_count) ? rating.rating_count : [];
  const images = [];
  if (item.image) images.push(imageUrl(item.image));
  for (const id of item.images || []) images.push(imageUrl(id));
  const videos = [];
  for (const video of item.video_info_list || []) {
    const url = videoUrl(video);
    if (url) videos.push(url);
  }

  return {
    title: item.name,
    url: productUrl(item.name, item.shopid, item.itemid),
    price: shopeePrice(item.price || item.price_min),
    original_price: shopeePrice(item.price_before_discount || item.price_max_before_discount),
    sold_week: item.sold || null,
    sold_month: item.historical_sold || null,
    rating: rating.rating_star || null,
    review_count: ratingCount.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0) || null,
    commission_rate: null,
    shop_name: item.shop_name || null,
    category: `Chrome extension Shopee search: ${keyword}`,
    image_url: images[0] || null,
    image_urls: images.slice(1),
    video_urls: videos,
    description: null
  };
}

function parseKeywords(text) {
  if (!text) return DEFAULT_KEYWORDS;
  const values = String(text).split(/[,;\n]+/).map((item) => item.trim()).filter(Boolean);
  return values.length ? values : DEFAULT_KEYWORDS;
}

function shopeePrice(value) {
  if (value === null || value === undefined) return null;
  return Math.round(Number(value) / 100000);
}

function productUrl(title, shopid, itemid) {
  const slug = String(title).replace(/[^a-zA-Z0-9\u00C0-\u1EF9]+/g, "-").replace(/^-+|-+$/g, "");
  return `https://shopee.vn/${encodeURIComponent(slug)}-i.${shopid}.${itemid}`;
}

function imageUrl(id) {
  if (!id) return null;
  if (String(id).startsWith("http")) return id;
  return `https://down-vn.img.susercontent.com/file/${id}`;
}

function videoUrl(video) {
  for (const key of ["default_format", "format"]) {
    if (video && video[key] && (video[key].url || video[key].file_url)) return video[key].url || video[key].file_url;
  }
  for (const item of (video && video.formats) || []) {
    if (item && (item.url || item.file_url)) return item.url || item.file_url;
  }
  return video && (video.url || video.file_url);
}

function clamp(value, min, max) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}
