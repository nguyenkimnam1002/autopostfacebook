from __future__ import annotations

import json
import re
import shlex
import urllib.error
import urllib.parse
import urllib.request

from .config import get_env
from .models import Product
from .shopee_session import ShopeeSessionError, fetch_json_in_shopee_chrome


DEFAULT_HOME_KEYWORDS = [
    "may xay sinh to",
    "noi chien khong dau",
    "cay lau nha",
    "ke bep",
    "may hut bui mini",
    "noi com dien",
    "hop dung thuc pham",
    "quat dien",
    "den ngu",
    "may say toc",
]


class DiscoveryError(RuntimeError):
    pass


def discover_shopee_hot_products(
    keywords: list[str] | None = None,
    per_keyword: int = 20,
    max_products: int = 80,
    cookie: str | None = None,
    headers_override: dict[str, str] | None = None,
    use_browser: bool = False,
) -> list[Product]:
    selected_keywords = [item.strip() for item in (keywords or DEFAULT_HOME_KEYWORDS) if item.strip()]
    if not selected_keywords:
        selected_keywords = DEFAULT_HOME_KEYWORDS

    products_by_key: dict[str, Product] = {}
    errors: list[str] = []
    for keyword in selected_keywords:
        try:
            for product in _fetch_shopee_keyword(
                keyword,
                limit=per_keyword,
                cookie=cookie,
                headers_override=headers_override,
                use_browser=use_browser,
            ):
                dedupe_key = product.url
                existing = products_by_key.get(dedupe_key)
                if existing is None or product.sales_signal > existing.sales_signal:
                    products_by_key[dedupe_key] = product
                if len(products_by_key) >= max_products:
                    return list(products_by_key.values())
        except DiscoveryError as exc:
            errors.append(f"{keyword}: {exc}")

    products = list(products_by_key.values())
    if not products and errors:
        raise DiscoveryError("; ".join(errors[:3]))
    return products


def parse_keywords(text: str | None) -> list[str]:
    if not text:
        return DEFAULT_HOME_KEYWORDS
    return [item.strip() for item in re.split(r"[,;\n]+", text) if item.strip()]


def headers_from_curl(curl_text: str | None) -> dict[str, str]:
    if not curl_text:
        return {}
    try:
        parts = shlex.split(curl_text, posix=False)
    except ValueError:
        parts = curl_text.split()

    headers: dict[str, str] = {}
    index = 0
    while index < len(parts):
        token = parts[index].strip('"').strip("'")
        if token in ("-H", "--header") and index + 1 < len(parts):
            raw_header = parts[index + 1].strip().strip('"').strip("'")
            if ":" in raw_header:
                key, value = raw_header.split(":", 1)
                headers[key.strip()] = value.strip()
            index += 2
            continue
        if token.startswith("-H") and ":" in token[2:]:
            raw_header = token[2:].strip().strip('"').strip("'")
            key, value = raw_header.split(":", 1)
            headers[key.strip()] = value.strip()
        index += 1
    return headers


def _fetch_shopee_keyword(
    keyword: str,
    limit: int,
    cookie: str | None = None,
    headers_override: dict[str, str] | None = None,
    use_browser: bool = False,
) -> list[Product]:
    params = {
        "by": "sales",
        "keyword": keyword,
        "limit": str(max(1, min(limit, 60))),
        "newest": "0",
        "order": "desc",
        "page_type": "search",
        "scenario": "PAGE_GLOBAL_SEARCH",
        "version": "2",
    }
    url = "https://shopee.vn/api/v4/search/search_items?" + urllib.parse.urlencode(params)
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Referer": "https://shopee.vn/search?keyword=" + urllib.parse.quote(keyword),
        "X-Requested-With": "XMLHttpRequest",
    }
    if headers_override:
        for key, value in headers_override.items():
            lower = key.lower()
            if lower in ("host", "content-length", "accept-encoding"):
                continue
            headers[key] = value

    shopee_cookie = cookie or get_env("SHOPEE_COOKIE")
    if not shopee_cookie and headers_override:
        shopee_cookie = headers_override.get("Cookie") or headers_override.get("cookie")
    if shopee_cookie:
        headers["Cookie"] = shopee_cookie
        csrf = _cookie_value(shopee_cookie, "csrftoken") or _cookie_value(shopee_cookie, "csrf_token")
        if csrf:
            headers["X-CSRFToken"] = csrf

    if use_browser:
        try:
            payload = fetch_json_in_shopee_chrome(url)
        except ShopeeSessionError as exc:
            raise DiscoveryError(f"Chrome fetch failed: {exc}") from exc
    else:
        request = urllib.request.Request(
            url,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DiscoveryError(f"Shopee HTTP {exc.code}: {detail[:160]}") from exc
        except urllib.error.URLError as exc:
            raise DiscoveryError(f"Shopee network error: {exc}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DiscoveryError("Shopee returned non-JSON response") from exc

    raw_items = (payload.get("items") or payload.get("data", {}).get("items") or [])
    products: list[Product] = []
    for raw in raw_items:
        item = raw.get("item_basic") or raw.get("item") or raw
        product = _product_from_shopee_item(item, keyword)
        if product:
            products.append(product)
    return products


def parse_shopee_ids(url: str | None) -> tuple[str, str] | None:
    """Extract (shop_id, item_id) from common Shopee product URL formats."""
    if not url:
        return None
    patterns = (
        r"/product/(\d+)/(\d+)",
        r"-i\.(\d+)\.(\d+)",
        r"[?&]shopid=(\d+)&itemid=(\d+)",
        r"i\.(\d+)\.(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2)
    return None


def _shopee_get_json(
    url: str,
    cookie: str | None,
    headers_override: dict[str, str] | None,
    use_browser: bool,
    referer: str | None = None,
) -> dict:
    if use_browser:
        try:
            return fetch_json_in_shopee_chrome(url)
        except ShopeeSessionError as exc:
            raise DiscoveryError(f"Chrome fetch failed: {exc}") from exc

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "x-api-source": "pc",
    }
    if referer:
        headers["Referer"] = referer
    if headers_override:
        for key, value in headers_override.items():
            lower = key.lower()
            if lower in ("host", "content-length", "accept-encoding"):
                continue
            headers[key] = value

    shopee_cookie = cookie or get_env("SHOPEE_COOKIE")
    if not shopee_cookie and headers_override:
        shopee_cookie = headers_override.get("Cookie") or headers_override.get("cookie")
    if shopee_cookie:
        headers["Cookie"] = shopee_cookie
        csrf = _cookie_value(shopee_cookie, "csrftoken") or _cookie_value(shopee_cookie, "csrf_token")
        if csrf:
            headers["X-CSRFToken"] = csrf

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DiscoveryError(f"Shopee HTTP {exc.code}: {detail[:160]}") from exc
    except urllib.error.URLError as exc:
        raise DiscoveryError(f"Shopee network error: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise DiscoveryError("Shopee returned non-JSON response") from exc


def fetch_product_media(
    source_url: str | None,
    cookie: str | None = None,
    headers_override: dict[str, str] | None = None,
    use_browser: bool = False,
) -> dict:
    """Fetch image and video URLs for a single Shopee product via its PDP API."""
    ids = parse_shopee_ids(source_url)
    if not ids:
        return {"images": [], "videos": []}
    shop_id, item_id = ids
    api_url = f"https://shopee.vn/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}"
    payload = _shopee_get_json(api_url, cookie, headers_override, use_browser, referer=source_url)
    data = payload.get("data") or {}
    item = data.get("item") or payload.get("item") or {}
    product_images = data.get("product_images") or {}

    images: list[str] = []

    def add_image(image_id: str | None) -> None:
        if not image_id:
            return
        url = _image_url(image_id)
        if is_product_image(url) and url not in images:
            images.append(url)

    add_image(item.get("image"))
    for image_id in product_images.get("images") or []:
        add_image(image_id)
    for image_id in item.get("images") or []:
        add_image(image_id)

    videos: list[str] = []

    def add_video(video: dict | None) -> None:
        if not isinstance(video, dict):
            return
        url = _video_url(video)
        if url and url not in videos:
            videos.append(url)

    add_video(product_images.get("video"))
    for video in product_images.get("shopee_video_info_list") or []:
        add_video(video)
    for video in item.get("video_info_list") or []:
        add_video(video)

    return {"images": images, "videos": videos}


def enrich_products_with_media(
    products: list[Product],
    cookie: str | None = None,
    headers_override: dict[str, str] | None = None,
    use_browser: bool = False,
    limit: int | None = None,
) -> list[str]:
    """Fill missing image/video URLs on products in-place. Returns warnings."""
    errors: list[str] = []
    targets = products if limit is None else products[:limit]
    for product in targets:
        clean_existing = [url for url in [product.image_url, *product.image_urls] if is_product_image(url)]
        product.image_url = clean_existing[0] if clean_existing else None
        product.image_urls = clean_existing[1:]

        try:
            media = fetch_product_media(
                product.source_url or product.url,
                cookie=cookie,
                headers_override=headers_override,
                use_browser=use_browser,
            )
        except DiscoveryError as exc:
            errors.append(f"{(product.title or '')[:32]}: {exc}")
            continue

        if media["images"]:
            product.image_url = media["images"][0]
            product.image_urls = media["images"][1:]
        if media["videos"]:
            merged_videos: list[str] = []
            for url in [product.video_url, *product.video_urls, *media["videos"]]:
                if url and url not in merged_videos:
                    merged_videos.append(url)
            product.video_url = merged_videos[0]
            product.video_urls = merged_videos[1:]
    return errors


def _product_from_shopee_item(item: dict, keyword: str) -> Product | None:
    title = item.get("name")
    shopid = item.get("shopid")
    itemid = item.get("itemid")
    if not title or not shopid or not itemid:
        return None

    price = _shopee_price(item.get("price") or item.get("price_min"))
    original_price = _shopee_price(item.get("price_before_discount") or item.get("price_max_before_discount"))
    rating_info = item.get("item_rating") or {}
    rating_count = rating_info.get("rating_count") or []
    review_count = sum(value for value in rating_count if isinstance(value, int)) if rating_count else None
    images = [_image_url(image_id) for image_id in item.get("images") or [] if image_id]
    if item.get("image"):
        images.insert(0, _image_url(item["image"]))

    video_urls: list[str] = []
    for video in item.get("video_info_list") or []:
        url = _video_url(video)
        if url:
            video_urls.append(url)

    return Product(
        title=title,
        url=_product_url(title, shopid, itemid),
        price=price,
        original_price=original_price,
        sold_week=item.get("sold") or None,
        sold_month=item.get("historical_sold") or None,
        rating=rating_info.get("rating_star"),
        review_count=review_count,
        commission_rate=None,
        shop_name=item.get("shop_name"),
        category=f"Shopee search: {keyword}",
        image_url=images[0] if images else None,
        image_urls=images[1:],
        video_urls=video_urls,
        description=item.get("welcome_package_info"),
    )


def _shopee_price(value: int | float | None) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value) / 100000))
    except (TypeError, ValueError):
        return None


def _product_url(title: str, shopid: int, itemid: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u00C0-\u1EF9]+", "-", title).strip("-")
    return f"https://shopee.vn/{urllib.parse.quote(slug)}-i.{shopid}.{itemid}"


_PRODUCT_IMAGE_HOSTS = (
    "down-vn.img.susercontent.com",
    "cf.shopee.vn",
    "cvi.shopee.vn",
    "deo.shopeemobile.com",
    "susercontent.com",
)


def is_product_image(url: str | None) -> bool:
    """Return True only for authentic Shopee product-gallery image URLs."""
    if not url or not isinstance(url, str):
        return False
    value = url.strip()
    if not value.lower().startswith("http"):
        return False
    lowered = value.lower()
    if "/product/" in lowered or lowered.endswith(("/null", "/undefined", ".svg")):
        return False
    if "avatar" in lowered or "/logo" in lowered:
        return False
    host = urllib.parse.urlparse(value).netloc.lower()
    if not any(host == h or host.endswith("." + h) or h in host for h in _PRODUCT_IMAGE_HOSTS):
        return False
    return "/file/" in lowered


def _image_url(image_id: str) -> str:
    if image_id.startswith("http"):
        return image_id
    return f"https://down-vn.img.susercontent.com/file/{image_id}"


def _video_url(video: dict) -> str | None:
    def pick(node):
        if isinstance(node, dict):
            return node.get("url") or node.get("file_url")
        return None

    for key in ("default_format", "format"):
        url = pick(video.get(key))
        if url:
            return url
    for item in video.get("formats") or []:
        url = pick(item)
        if url:
            return url
    return video.get("url") or video.get("file_url")


def _cookie_value(cookie: str, name: str) -> str | None:
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        if key == name:
            return value
    return None
