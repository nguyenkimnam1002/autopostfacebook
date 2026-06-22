from __future__ import annotations

import textwrap
import urllib.parse
import webbrowser
from pathlib import Path

from .models import Product, RankedProduct


def build_facebook_post(product: Product, reasons: list[str] | None = None) -> str:
    reason_lines = reasons[:3] if reasons else [
        "phù hợp nhóm đồ gia dụng, nên kiểm tra lại voucher và phí ship trong link trước khi mua"
    ]
    body = [
        _product_title(product),
        f"Shop: {product.shop_name or 'xem trong link'}",
        "",
        "Điểm nổi bật:",
        *[f"- {reason}" for reason in reason_lines],
        "",
        "Link sản phẩm:",
        product.url,
        "",
        "Lưu ý: voucher và tồn kho có thể thay đổi theo từng thời điểm.",
    ]
    return textwrap.dedent("\n".join(body)).strip()


def build_facebook_reel_title(product: Product) -> str:
    return _product_title(product)


def _product_title(product: Product) -> str:
    return product.title.strip()


def save_post(text: str, output_dir: str | Path, filename: str = "facebook_post.txt") -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    target = path / filename
    target.write_text(text, encoding="utf-8")
    return target


def open_facebook_page(page_url: str, post_text: str | None = None) -> None:
    if post_text:
        encoded = urllib.parse.quote(post_text[:1800])
        webbrowser.open(f"{page_url}?draft_text={encoded}")
    else:
        webbrowser.open(page_url)


def ranked_to_lines(items: list[RankedProduct]) -> list[str]:
    lines = []
    for index, item in enumerate(items, start=1):
        product = item.product
        reasons = "; ".join(item.reasons) if item.reasons else "chưa có tín hiệu phụ"
        lines.append(f"{index}. {product.title} | score={item.score} | source={item.source} | {reasons}")
    return lines
