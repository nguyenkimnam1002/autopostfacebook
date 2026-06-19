from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .media import collect_media, download_media
from .models import RankedProduct
from .posting import build_facebook_post


def export_daily_package(
    ranked: list[RankedProduct],
    output_root: str | Path,
    run_date: date | None = None,
    download_assets: bool = True,
) -> Path:
    day = run_date or date.today()
    day_dir = Path(output_root) / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for index, item in enumerate(ranked, start=1):
        folder_name = item.product.product_id or f"{index:02d}-{_slug(item.product.title)}"
        product_dir = day_dir / _slug(folder_name, max_length=80)
        product_dir.mkdir(parents=True, exist_ok=True)

        media = collect_media(item.product, scrape_url=download_assets)
        post = build_facebook_post(item.product, item.reasons)
        (product_dir / "post.txt").write_text(post, encoding="utf-8")
        (product_dir / "product.json").write_text(
            json.dumps(
                {
                    "title": item.product.title,
                    "product_id": item.product.product_id,
                    "affiliate_url": item.product.url,
                    "source_url": item.product.source_url,
                    "score": item.score,
                    "source": item.source,
                    "reasons": item.reasons,
                    "price": item.product.price,
                    "original_price": item.product.original_price,
                    "sold_week": item.product.sold_week,
                    "sold_month": item.product.sold_month,
                    "rating": item.product.rating,
                    "review_count": item.product.review_count,
                    "commission_rate": item.product.commission_rate,
                    "shop_name": item.product.shop_name,
                    "category": item.product.category,
                    "detected_images": media.images,
                    "detected_videos": media.videos,
                    "detected_description": media.description,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        saved = download_media(media, product_dir) if download_assets else {"images": [], "videos": []}
        summary.append(
            {
                "rank": index,
                "title": item.product.title,
                "score": item.score,
                "source": item.source,
                "folder": str(product_dir),
                "images": [str(path) for path in saved["images"]],
                "videos": [str(path) for path in saved["videos"]],
            }
        )

    (day_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return day_dir


def _slug(text: str, max_length: int = 60) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u00C0-\u1EF9]+", "-", text).strip("-").lower()
    return slug[:max_length].strip("-") or "product"
