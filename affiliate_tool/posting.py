from __future__ import annotations

import textwrap
import urllib.parse
import webbrowser
from pathlib import Path

from .models import Product, RankedProduct


def format_vnd(value: int | None) -> str:
    if value is None:
        return "xem giá trong link"
    return f"{value:,}".replace(",", ".") + "đ"


def build_facebook_post(product: Product, reasons: list[str] | None = None) -> str:
    discount = ""
    if product.discount_percent:
        discount = f" | giảm khoảng {product.discount_percent:.0f}%"

    reason_lines = reasons[:3] if reasons else [
        "phù hợp nhóm đồ gia dụng, nên kiểm tra lại voucher và phí ship trước khi mua"
    ]
    body = [
        _opening_line(product),
        "",
        product.title,
        f"Giá tham khảo: {format_vnd(product.price)}{discount}",
        f"Shop: {product.shop_name or 'xem trong link'}",
        "",
        "Điểm nổi bật:",
        *[f"- {reason}" for reason in reason_lines],
        "",
        "Link sản phẩm:",
        product.url,
        "",
        "Lưu ý: Giá, voucher và tồn kho có thể thay đổi theo từng thời điểm.",
    ]
    return textwrap.dedent("\n".join(body)).strip()


def _opening_line(product: Product) -> str:
    title = product.title.lower()
    if "quạt" in title:
        return "Mình thấy mẫu quạt này khá đáng cân nhắc cho những ngày nóng:"
    if "đèn" in title or "den" in title:
        return "Có một món đồ gia dụng khá tiện để tham khảo hôm nay:"
    if "lau" in title or "chổi" in title or "choi" in title:
        return "Món dọn dẹp này nhìn khá thực dụng, mình lưu lại cho mọi người tham khảo:"
    if "giấy" in title or "giay" in title:
        return "Một món dùng hằng ngày, giá và tín hiệu bán khá ổn:"
    return "Hôm nay mình chọn được một món gia dụng đáng để cân nhắc:"


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
