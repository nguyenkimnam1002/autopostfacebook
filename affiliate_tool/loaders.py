from __future__ import annotations

import csv
import io
import unicodedata
from pathlib import Path

from .models import Product


ALIASES = {
    "product_id": ("product_id", "ma_san_pham", "ma san pham", "ma s n ph m"),
    "title": ("title", "name", "product_name", "ten", "ten_san_pham", "ten san pham", "ten s n ph m"),
    "url": ("url", "affiliate_link", "link uu dai", "link u ai", "link ai", "link san pham", "link s n ph m"),
    "source_url": ("source_url", "product_url", "link san pham", "link s n ph m"),
    "price": ("price", "gia", "sale_price"),
    "original_price": ("original_price", "gia_goc", "gia goc", "list_price"),
    "sold_week": ("sold_week", "sold_7d", "ban_tuan", "da ban tuan"),
    "sold_month": ("sold_month", "sold_30d", "ban_thang", "da ban thang", "doanh thu"),
    "rating": ("rating", "danh_gia", "danh gia"),
    "review_count": ("review_count", "reviews", "so_danh_gia", "so danh gia"),
    "commission_rate": ("commission_rate", "commission", "hoa_hong", "ti le hoa hong", "t l hoa h ng"),
    "shop_name": ("shop_name", "shop", "ten cua hang", "ten c a hang", "ten shop"),
    "category": ("category", "nganh_hang", "nganh hang"),
    "image_url": ("image_url", "image", "anh"),
    "image_urls": ("image_urls", "images", "anh_san_pham", "anh san pham"),
    "video_url": ("video_url", "video"),
    "video_urls": ("video_urls", "videos", "video_san_pham", "video san pham"),
    "description": ("description", "mo_ta", "mo ta"),
}


def load_products_from_csv(path: str | Path) -> list[Product]:
    products: list[Product] = []
    text = _read_csv_text(path)
    dialect = _sniff_dialect(text)
    with io.StringIO(text, newline="") as file:
        reader = csv.DictReader(file, dialect=dialect)
        for row in reader:
            normalized = {
                _field: _get(
                    row,
                    aliases,
                    allow_fuzzy=_field not in {"image_url", "image_urls", "video_url", "video_urls"},
                )
                for _field, aliases in ALIASES.items()
            }
            title = normalized["title"] or ""
            affiliate_url = normalized["url"] or ""
            if not title or not affiliate_url:
                continue
            products.append(
                Product(
                    title=title,
                    url=affiliate_url,
                    product_id=_product_id(normalized["product_id"]),
                    source_url=normalized["source_url"] or affiliate_url,
                    price=_to_int(normalized["price"]),
                    original_price=_to_int(normalized["original_price"]),
                    sold_week=_to_int(normalized["sold_week"]),
                    sold_month=_to_int(normalized["sold_month"]),
                    rating=_to_float(normalized["rating"]),
                    review_count=_to_int(normalized["review_count"]),
                    commission_rate=_to_float(normalized["commission_rate"]),
                    shop_name=normalized["shop_name"],
                    category=normalized["category"],
                    image_url=normalized["image_url"],
                    image_urls=_split_urls(normalized["image_urls"]),
                    video_url=normalized["video_url"],
                    video_urls=_split_urls(normalized["video_urls"]),
                    description=normalized["description"],
                )
            )
    return products


def _read_csv_text(path: str | Path) -> str:
    raw_path = Path(path)
    last_error: UnicodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "cp1258", "latin-1"):
        try:
            return raw_path.read_text(encoding=encoding)
        except UnicodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return raw_path.read_text(encoding="utf-8-sig")


def _sniff_dialect(text: str):
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        class Fallback(csv.excel):
            delimiter = "\t" if "\t" in sample else ","
        return Fallback


def _get(row: dict[str, str], aliases: tuple[str, ...], allow_fuzzy: bool = True) -> str | None:
    normalized_map = {_normalize_key(key): value for key, value in row.items()}
    for alias in aliases:
        normalized_alias = _normalize_key(alias)
        value = normalized_map.get(normalized_alias)
        if value is not None:
            return value.strip() if isinstance(value, str) else value
        if allow_fuzzy:
            for key, candidate in normalized_map.items():
                if _fuzzy_key_match(key, normalized_alias):
                    return candidate.strip() if isinstance(candidate, str) else candidate
    return None


def _normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().replace("_", " ").replace("?", " ").split())


def _fuzzy_key_match(key: str, alias: str) -> bool:
    key_tokens = set(key.split())
    alias_tokens = set(alias.split())
    if not key_tokens or not alias_tokens:
        return False
    return len(key_tokens & alias_tokens) >= min(2, len(alias_tokens))


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    text = value.strip().lower().replace("₫", "").replace("đ", "").replace("+", "")
    multiplier = 1
    if "triệu" in text or "tr" in text or text.endswith("m"):
        multiplier = 1_000_000
    elif text.endswith("k"):
        multiplier = 1_000
    text = (
        text.replace("triệu", "")
        .replace("tr", "")
        .removesuffix("m")
        .removesuffix("k")
        .strip()
    )
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return int(round(float(text) * multiplier))
    except ValueError:
        clean = "".join(char for char in value if char.isdigit())
        return int(clean) if clean else None


def _product_id(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    text = value.strip()
    try:
        if "e+" in text.lower():
            return str(int(float(text)))
    except ValueError:
        pass
    digits = "".join(char for char in text if char.isdigit())
    return digits or text


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    clean = value.replace("%", "").replace(",", ".").strip()
    try:
        return float(clean)
    except ValueError:
        return None


def _split_urls(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.replace("\n", ";").replace("|", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]
