from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Product:
    title: str
    url: str
    product_id: str | None = None
    source_url: str | None = None
    price: int | None = None
    original_price: int | None = None
    sold_week: int | None = None
    sold_month: int | None = None
    rating: float | None = None
    review_count: int | None = None
    commission_rate: float | None = None
    shop_name: str | None = None
    category: str | None = None
    image_url: str | None = None
    image_urls: list[str] = field(default_factory=list)
    video_url: str | None = None
    video_urls: list[str] = field(default_factory=list)
    description: str | None = None

    @property
    def discount_percent(self) -> float:
        if not self.price or not self.original_price or self.original_price <= self.price:
            return 0.0
        return round((self.original_price - self.price) / self.original_price * 100, 1)

    @property
    def sales_signal(self) -> int:
        return self.sold_week or self.sold_month or 0


@dataclass
class RankedProduct:
    product: Product
    score: float
    reasons: list[str]
    source: str = "manual"
