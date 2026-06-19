from __future__ import annotations

import mimetypes
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .models import Product


USER_AGENT = "Mozilla/5.0 AffiliateHotTool/0.1"


@dataclass
class ProductMedia:
    images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    title: str | None = None
    description: str | None = None


def collect_media(product: Product, scrape_url: bool = True) -> ProductMedia:
    media = ProductMedia(
        images=[url for url in [product.image_url, *product.image_urls] if url],
        videos=[url for url in [product.video_url, *product.video_urls] if url],
        title=product.title,
        description=product.description,
    )
    if scrape_url:
        scraped = scrape_public_metadata(product.source_url or product.url)
        media.images.extend(url for url in scraped.images if url not in media.images)
        media.videos.extend(url for url in scraped.videos if url not in media.videos)
        media.title = scraped.title or media.title
        media.description = scraped.description or media.description
    return media


def scrape_public_metadata(url: str) -> ProductMedia:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read(2_000_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, ValueError):
        return ProductMedia()

    return ProductMedia(
        images=_meta_values(html, ("og:image", "twitter:image", "og:image:url")),
        videos=_meta_values(html, ("og:video", "og:video:url", "twitter:player:stream")),
        title=_first_meta(html, ("og:title", "twitter:title")) or _title(html),
        description=_first_meta(html, ("og:description", "description", "twitter:description")),
    )


def download_media(media: ProductMedia, output_dir: str | Path, max_images: int = 5) -> dict[str, list[Path]]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    saved = {"images": [], "videos": []}

    for index, url in enumerate(media.images[:max_images], start=1):
        target = _download(url, path, f"image_{index}")
        if target:
            saved["images"].append(target)

    for index, url in enumerate(media.videos[:2], start=1):
        target = _download(url, path, f"video_{index}")
        if target:
            saved["videos"].append(target)

    return saved


def _download(url: str, output_dir: Path, stem: str) -> Path | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=45) as response:
            content_type = response.headers.get("Content-Type", "").split(";")[0]
            ext = mimetypes.guess_extension(content_type) or _ext_from_url(url) or ".bin"
            target = output_dir / f"{stem}{ext}"
            target.write_bytes(response.read())
            return target
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _meta_values(html: str, names: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for name in names:
        patterns = [
            rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(name)}["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']',
        ]
        for pattern in patterns:
            for match in re.findall(pattern, html, flags=re.IGNORECASE):
                value = _html_unescape(match)
                if value and value not in values:
                    values.append(value)
    return values


def _first_meta(html: str, names: tuple[str, ...]) -> str | None:
    values = _meta_values(html, names)
    return values[0] if values else None


def _title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return _html_unescape(re.sub(r"\s+", " ", match.group(1)).strip())


def _html_unescape(value: str) -> str:
    return (
        value.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def _ext_from_url(url: str) -> str | None:
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix
    return suffix if suffix and len(suffix) <= 6 else None
