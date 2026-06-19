from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request

from .models import Product, RankedProduct
from .scoring import score_products


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqUnavailable(RuntimeError):
    pass


def rank_with_groq(
    products: list[Product],
    api_key: str | None,
    model: str = DEFAULT_MODEL,
    limit: int = 7,
) -> list[RankedProduct]:
    if not api_key:
        raise GroqUnavailable("missing GROQ_API_KEY")

    candidates = score_products(products, limit=min(max(limit * 4, limit), len(products) or limit))
    run_nonce = f"{int(time.time())}-{random.randint(1000, 9999)}"
    payload_products = [
        {
            "index": index,
            "title": item.product.title,
            "url": item.product.url,
            "price": item.product.price,
            "original_price": item.product.original_price,
            "sold_week": item.product.sold_week,
            "sold_month": item.product.sold_month,
            "rating": item.product.rating,
            "review_count": item.product.review_count,
            "commission_rate": item.product.commission_rate,
            "shop_name": item.product.shop_name,
            "category": item.product.category,
            "fallback_score": item.score,
            "fallback_reasons": item.reasons,
            "rotation_hint": random.random(),
        }
        for index, item in enumerate(candidates)
    ]
    prompt = {
        "task": "Rank Vietnamese home appliance affiliate products for Facebook posting.",
        "rules": [
            "Prefer products with strong recent sales, high commission, good price appeal, useful mass-market demand, and clear Facebook posting angle.",
            "Use Shopee sales/revenue, commission, price, shop info, media availability, and description when present.",
            "Diversify the list so repeated runs do not always pick identical products when scores are close.",
            "Return only JSON. No markdown.",
            "Use product index values from the input only.",
        ],
        "run_context": f"Daily hot-pick run nonce {run_nonce}. If multiple products are close, use rotation_hint to vary choices and keep the page fresh.",
        "output_schema": {
            "items": [
                {
                    "index": 0,
                    "score": 0,
                    "reasons": ["short Vietnamese reason"],
                    "facebook_angle": "short Vietnamese hook",
                }
            ]
        },
        "limit": limit,
        "products": payload_products,
    }
    request_body = {
        "model": model,
        "temperature": 0.45,
        "max_completion_tokens": 1800,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a careful affiliate merchandising analyst. Output valid JSON only.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }
    data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        GROQ_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GroqUnavailable(f"Groq HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise GroqUnavailable(f"Groq network error: {exc}") from exc

    try:
        completion = json.loads(body)
        content = completion["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        groq_items = parsed.get("items", [])
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        raise GroqUnavailable("Groq returned an unreadable response") from exc

    ranked: list[RankedProduct] = []
    by_index = {index: item for index, item in enumerate(candidates)}
    for raw_item in groq_items:
        index = raw_item.get("index")
        fallback = by_index.get(index)
        if fallback is None:
            continue
        reasons = raw_item.get("reasons") or fallback.reasons
        if raw_item.get("facebook_angle"):
            reasons = [str(raw_item["facebook_angle"])] + [str(reason) for reason in reasons]
        ranked.append(
            RankedProduct(
                product=fallback.product,
                score=float(raw_item.get("score") or fallback.score),
                reasons=[str(reason) for reason in reasons][:5],
                source="groq",
            )
        )
    if not ranked:
        raise GroqUnavailable("Groq returned no usable product ranking")
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]
