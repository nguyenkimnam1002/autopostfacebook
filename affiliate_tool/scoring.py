from __future__ import annotations

import math
import random

from .models import Product, RankedProduct


HOME_KEYWORDS = (
    "gia dung",
    "đồ gia dụng",
    "do gia dung",
    "nhà cửa",
    "nha cua",
    "bếp",
    "bep",
    "nồi",
    "noi",
    "máy xay",
    "may xay",
    "máy hút bụi",
    "may hut bui",
    "quạt",
    "quat",
    "kệ",
    "ke",
    "lau nhà",
    "lau nha",
)


def is_home_product(product: Product) -> bool:
    text = f"{product.title} {product.category or ''}".lower()
    return any(keyword in text for keyword in HOME_KEYWORDS)


def rank_products(products: list[Product], limit: int = 7) -> list[RankedProduct]:
    ranked = [_rank_one(product) for product in products if is_home_product(product)]
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]


def score_products(products: list[Product], limit: int | None = None) -> list[RankedProduct]:
    ranked = [_rank_one(product) for product in products]
    for item in ranked:
        item.score = round(item.score + random.uniform(0, 2.5), 2)
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit] if limit else ranked


def _rank_one(product: Product) -> RankedProduct:
    sales = math.log10(product.sales_signal + 1) * 30
    rating = (product.rating or 0) * 10
    reviews = math.log10((product.review_count or 0) + 1) * 8
    discount = min(product.discount_percent, 60) * 0.5
    commission = (product.commission_rate or 0) * 1.5

    score = sales + rating + reviews + discount + commission
    reasons: list[str] = []

    if product.sales_signal:
        reasons.append(f"bán gần đây: {product.sales_signal}")
    if product.rating:
        reasons.append(f"đánh giá {product.rating:.1f}/5")
    if product.discount_percent:
        reasons.append(f"giảm {product.discount_percent:.0f}%")
    if product.commission_rate:
        reasons.append(f"hoa hồng {product.commission_rate:.1f}%")

    return RankedProduct(product=product, score=round(score, 2), reasons=reasons)
