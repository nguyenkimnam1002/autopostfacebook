from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import get_env, load_dotenv
from .discovery import DiscoveryError, discover_shopee_hot_products, parse_keywords
from .exporter import export_daily_package
from .groq_analyzer import DEFAULT_MODEL, GroqUnavailable, rank_with_groq
from .loaders import load_products_from_csv
from .models import Product
from .posting import build_facebook_post, open_facebook_page, ranked_to_lines, save_post
from .scoring import rank_products


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Affiliate assistant for home appliance products in Vietnam."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    rank_parser = subparsers.add_parser("rank", help="Rank products from a CSV export/copy.")
    rank_parser.add_argument("--csv", required=True, help="Path to product CSV.")
    rank_parser.add_argument("--limit", type=int, default=7, help="Number of products to keep.")
    rank_parser.add_argument("--use-groq", action="store_true", help="Use Groq first, fallback to local scoring.")
    rank_parser.add_argument("--model", help="Groq model name. Defaults to GROQ_MODEL or a safe default.")

    discover_parser = subparsers.add_parser("discover", help="Find hot home products from Shopee public search.")
    discover_parser.add_argument("--keywords", help="Comma/newline separated keywords.")
    discover_parser.add_argument("--per-keyword", type=int, default=20)
    discover_parser.add_argument("--limit", type=int, default=7)
    discover_parser.add_argument("--use-groq", action="store_true", help="Use Groq first, fallback to local scoring.")
    discover_parser.add_argument("--model", help="Groq model name. Defaults to GROQ_MODEL or a safe default.")

    daily_parser = subparsers.add_parser(
        "daily",
        help="Rank products and export daily folders with post.txt plus product media.",
    )
    daily_parser.add_argument("--csv", required=True, help="Path to product CSV.")
    daily_parser.add_argument("--limit", type=int, default=7, help="Number of products to export.")
    daily_parser.add_argument("--output-root", default="daily_out", help="Root folder for daily packages.")
    daily_parser.add_argument("--use-groq", action="store_true", help="Use Groq first, fallback to local scoring.")
    daily_parser.add_argument("--model", help="Groq model name. Defaults to GROQ_MODEL or a safe default.")
    daily_parser.add_argument(
        "--no-download-assets",
        action="store_true",
        help="Create posts and metadata only; do not fetch images/videos.",
    )

    daily_discover_parser = subparsers.add_parser(
        "daily-discover",
        help="Discover hot products from Shopee and export daily folders.",
    )
    daily_discover_parser.add_argument("--keywords", help="Comma/newline separated keywords.")
    daily_discover_parser.add_argument("--per-keyword", type=int, default=20)
    daily_discover_parser.add_argument("--limit", type=int, default=7)
    daily_discover_parser.add_argument("--output-root", default="daily_out")
    daily_discover_parser.add_argument("--use-groq", action="store_true")
    daily_discover_parser.add_argument("--model", help="Groq model name. Defaults to GROQ_MODEL or a safe default.")
    daily_discover_parser.add_argument("--no-download-assets", action="store_true")

    post_parser = subparsers.add_parser("post-manual", help="Create one Facebook post draft.")
    post_parser.add_argument("--title", required=True)
    post_parser.add_argument("--url", required=True)
    post_parser.add_argument("--price", type=int)
    post_parser.add_argument("--original-price", type=int)
    post_parser.add_argument("--sold-week", type=int)
    post_parser.add_argument("--sold-month", type=int)
    post_parser.add_argument("--rating", type=float)
    post_parser.add_argument("--review-count", type=int)
    post_parser.add_argument("--commission-rate", type=float)
    post_parser.add_argument("--shop-name")
    post_parser.add_argument("--category", default="Do gia dung")
    post_parser.add_argument("--output-dir", default="out")
    post_parser.add_argument("--facebook-page-url", help="Open this Facebook Page after saving draft.")

    web_parser = subparsers.add_parser("web", help="Run the localhost web interface.")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    load_dotenv()

    if args.command == "rank":
        products = load_products_from_csv(args.csv)
        ranked = _rank_products(products, limit=args.limit, use_groq=args.use_groq, model=args.model)
        print("\n".join(ranked_to_lines(ranked)))
        return

    if args.command == "discover":
        products = _discover_products(args.keywords, args.per_keyword)
        ranked = _rank_products(products, limit=args.limit, use_groq=args.use_groq, model=args.model)
        print(f"Discovered candidates: {len(products)}")
        print("\n".join(ranked_to_lines(ranked)))
        return

    if args.command == "daily":
        products = load_products_from_csv(args.csv)
        ranked = _rank_products(products, limit=args.limit, use_groq=args.use_groq, model=args.model)
        output_dir = export_daily_package(
            ranked,
            output_root=args.output_root,
            download_assets=not args.no_download_assets,
        )
        print(f"Exported daily package: {output_dir}")
        print("\n".join(ranked_to_lines(ranked)))
        return

    if args.command == "daily-discover":
        products = _discover_products(args.keywords, args.per_keyword)
        ranked = _rank_products(products, limit=args.limit, use_groq=args.use_groq, model=args.model)
        output_dir = export_daily_package(
            ranked,
            output_root=args.output_root,
            download_assets=not args.no_download_assets,
        )
        print(f"Discovered candidates: {len(products)}")
        print(f"Exported daily package: {output_dir}")
        print("\n".join(ranked_to_lines(ranked)))
        return

    if args.command == "post-manual":
        product = Product(
            title=args.title,
            url=args.url,
            price=args.price,
            original_price=args.original_price,
            sold_week=args.sold_week,
            sold_month=args.sold_month,
            rating=args.rating,
            review_count=args.review_count,
            commission_rate=args.commission_rate,
            shop_name=args.shop_name,
            category=args.category,
        )
        ranked = rank_products([product], limit=1)
        reasons = ranked[0].reasons if ranked else []
        post = build_facebook_post(product, reasons)
        path = save_post(post, Path(args.output_dir))
        print(f"Saved draft: {path}")
        print()
        print(post)
        if args.facebook_page_url:
            open_facebook_page(args.facebook_page_url, post)
        return

    if args.command == "web":
        from .web_app import run_server

        run_server(host=args.host, port=args.port)


def _discover_products(keywords: str | None, per_keyword: int) -> list[Product]:
    try:
        products = discover_shopee_hot_products(
            keywords=parse_keywords(keywords),
            per_keyword=per_keyword,
        )
    except DiscoveryError as exc:
        raise SystemExit(f"Could not discover Shopee products: {exc}") from exc
    if not products:
        raise SystemExit("No Shopee products discovered.")
    return products


def _rank_products(products: list[Product], limit: int, use_groq: bool, model: str | None):
    if use_groq:
        try:
            return rank_with_groq(
                products,
                api_key=get_env("GROQ_API_KEY"),
                model=model or get_env("GROQ_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
                limit=limit,
            )
        except GroqUnavailable as exc:
            print(f"Groq unavailable, falling back to local scoring: {exc}", file=sys.stderr)
    return rank_products(products, limit=limit)


if __name__ == "__main__":
    main()
