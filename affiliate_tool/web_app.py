from __future__ import annotations

import cgi
import json
import mimetypes
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .chrome_cookie_reader import ChromeCookieError, find_shopee_cookie_from_browsers
from .config import get_env, load_dotenv
from .discovery import (
    DiscoveryError,
    discover_shopee_hot_products,
    enrich_products_with_media,
    headers_from_curl,
    parse_keywords,
)
from .exporter import export_daily_package
from .facebook_auth import (
    FacebookAuthError,
    SCOPE_LABELS,
    app_configured,
    complete_login,
    create_login_url,
    exchange_user_token_to_page_auth,
    inspect_token,
    load_page_auth,
)
from .facebook_graph import (
    graph_configured,
    publish_four_photos_to_page,
    publish_products_to_page,
    publish_reels_to_page,
    publish_stories_to_page,
)
from .groq_analyzer import DEFAULT_MODEL, GroqUnavailable, rank_with_groq
from .loaders import load_products_from_csv
from .models import Product, RankedProduct
from .posting import build_facebook_post
from .scoring import score_products
from .shopee_session import (
    ShopeeSessionError,
    open_default_profile_browser,
    open_login_browser,
    read_shopee_cookie,
)


APP_PATH = "/affiliate_hot_tool"


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    load_dotenv()
    server = ThreadingHTTPServer((host, port), AffiliateHandler)
    print(f"Affiliate Hot Tool running at http://{host}:{port}{APP_PATH}")
    server.serve_forever()


class AffiliateHandler(BaseHTTPRequestHandler):
    server_version = "AffiliateHotTool/0.3"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", APP_PATH):
            self._send_html(_page())
            return
        if parsed.path == f"{APP_PATH}/facebook/callback":
            self._handle_facebook_callback(parsed)
            return
        if parsed.path == f"{APP_PATH}/health":
            self._send_json({"ok": True})
            return
        if parsed.path == f"{APP_PATH}/api/archive-media":
            self._handle_archive_media(parsed)
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == f"{APP_PATH}/api/open-shopee-login":
            self._handle_open_shopee_login()
            return
        if parsed.path == f"{APP_PATH}/api/open-default-chrome":
            self._handle_open_default_chrome()
            return
        if parsed.path == f"{APP_PATH}/api/read-shopee-cookie":
            self._handle_read_shopee_cookie()
            return
        if parsed.path == f"{APP_PATH}/api/auto-detect-cookie":
            self._handle_auto_detect_cookie()
            return
        if parsed.path == f"{APP_PATH}/api/analyze":
            self._handle_analyze(export=False)
            return
        if parsed.path == f"{APP_PATH}/api/export":
            self._handle_analyze(export=True)
            return
        if parsed.path == f"{APP_PATH}/api/analyze-products":
            self._handle_analyze_products()
            return
        if parsed.path == f"{APP_PATH}/api/enrich-media":
            self._handle_enrich_media()
            return
        if parsed.path == f"{APP_PATH}/api/facebook-queue":
            self._handle_facebook_queue()
            return
        if parsed.path == f"{APP_PATH}/api/facebook-four-photo-queue":
            self._handle_facebook_four_photo_queue()
            return
        if parsed.path == f"{APP_PATH}/api/facebook-story-queue":
            self._handle_facebook_story_queue()
            return
        if parsed.path == f"{APP_PATH}/api/facebook-reel-queue":
            self._handle_facebook_reel_queue()
            return
        if parsed.path == f"{APP_PATH}/api/facebook-auth-start":
            self._handle_facebook_auth_start()
            return
        if parsed.path == f"{APP_PATH}/api/facebook-auth-status":
            self._handle_facebook_auth_status()
            return
        if parsed.path == f"{APP_PATH}/api/facebook-token-exchange":
            self._handle_facebook_token_exchange()
            return
        if parsed.path == f"{APP_PATH}/api/archive-dates":
            self._handle_archive_dates()
            return
        if parsed.path == f"{APP_PATH}/api/archive-products":
            self._handle_archive_products()
            return
        if parsed.path == f"{APP_PATH}/api/export-products":
            self._handle_export_products()
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _handle_facebook_callback(self, parsed) -> None:
        redirect_uri = _facebook_redirect_uri(self)
        try:
            auth = complete_login(urllib.parse.parse_qs(parsed.query), redirect_uri)
            self._send_html(
                f"""<!doctype html><meta charset="utf-8">
                <body style="font-family:Arial;padding:24px">
                <h2>Đã kết nối Facebook Page</h2>
                <p>Page: <strong>{auth.page_name}</strong> ({auth.page_id})</p>
                <p>Bạn có thể đóng tab này và quay lại Affiliate Hot Tool.</p>
                <script>setTimeout(() => window.close(), 1200);</script>
                </body>"""
            )
        except FacebookAuthError as exc:
            self._send_html(
                f"""<!doctype html><meta charset="utf-8">
                <body style="font-family:Arial;padding:24px;color:#991b1b">
                <h2>Kết nối Facebook lỗi</h2><p>{exc}</p>
                </body>""",
                status=500,
            )

    def _handle_facebook_auth_start(self) -> None:
        try:
            if not app_configured():
                raise FacebookAuthError("Thiếu FACEBOOK_APP_ID hoặc FACEBOOK_APP_SECRET trong .env.")
            self._send_json({"ok": True, "login_url": create_login_url(_facebook_redirect_uri(self))})
        except FacebookAuthError as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_facebook_auth_status(self) -> None:
        auth = load_page_auth()
        self._send_json(
            {
                "ok": True,
                "app_configured": app_configured(),
                "graph_configured": graph_configured(),
                "connected": bool(auth),
                "page_id": auth.page_id if auth else None,
                "page_name": auth.page_name if auth else None,
                "user_expires_at": auth.user_expires_at if auth else None,
            }
        )

    def _handle_facebook_token_exchange(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            token = str(body.get("token") or "").strip()
            auth = exchange_user_token_to_page_auth(token)
            # Kiem tra token vua luu co du quyen khong, bao cao cho nguoi dung.
            try:
                info = inspect_token(auth.page_access_token)
            except Exception:
                info = {"is_valid": True, "scopes": [], "granted_required": [], "missing_required": []}
            granted = info.get("granted_required") or []
            missing = info.get("missing_required") or []
            granted_labels = [SCOPE_LABELS.get(s, s) for s in granted]
            missing_labels = [SCOPE_LABELS.get(s, s) for s in missing]
            total = len(granted) + len(missing)
            if missing:
                message = (
                    f"Token hop le cho Page '{auth.page_name}' nhung CON THIEU "
                    f"{len(missing)}/{total} quyen: {', '.join(missing_labels)}. "
                    "Hay tao lai token va tich du cac quyen do."
                )
            else:
                message = (
                    f"Token hop le voi du {len(granted)} quyen: {', '.join(granted_labels)}. "
                    f"Ban duoc su dung token nay cho Page '{auth.page_name}'. "
                    "Tu gio dang bai khong con bi het han token nua."
                )
            self._send_json(
                {
                    "ok": True,
                    "page_id": auth.page_id,
                    "page_name": auth.page_name,
                    "granted_scopes": granted,
                    "missing_scopes": missing,
                    "all_required_granted": not missing,
                    "message": message,
                }
            )
        except FacebookAuthError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_open_shopee_login(self) -> None:
        try:
            port = open_login_browser()
            self._send_json(
                {
                    "ok": True,
                    "debug_port": port,
                    "message": "Da mo Chrome profile rieng. Hay dang nhap Shopee trong cua so do.",
                }
            )
        except ShopeeSessionError as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_open_default_chrome(self) -> None:
        try:
            port = open_default_profile_browser()
            self._send_json(
                {
                    "ok": True,
                    "debug_port": port,
                    "message": "Da mo Chrome debug fallback.",
                }
            )
        except ShopeeSessionError as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_read_shopee_cookie(self) -> None:
        try:
            cookie = read_shopee_cookie()
            self._send_json(
                {
                    "ok": True,
                    "cookie": cookie,
                    "message": "Da lay cookie Shopee tu Chrome profile rieng.",
                }
            )
        except ShopeeSessionError as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_auto_detect_cookie(self) -> None:
        try:
            profile = find_shopee_cookie_from_browsers()
            self._send_json(
                {
                    "ok": True,
                    "browser": profile.browser,
                    "profile": profile.profile,
                    "cookie": profile.cookie,
                    "message": f"Da tim cookie Shopee trong {profile.browser}/{profile.profile}.",
                }
            )
        except ChromeCookieError as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_analyze(self, export: bool) -> None:
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            limit = _to_int(_field_value(form, "limit"), default=7)
            use_groq = _field_value(form, "use_groq") == "1"
            download_assets = _field_value(form, "download_assets") == "1"
            output_root = _field_value(form, "output_root") or "daily_out"
            source = _field_value(form, "source") or "discover"
            products, source_warning = _load_products(form, source)
            if source == "bulk_csv":
                ranked, rank_warning = _score_bulk(products), None
            else:
                ranked, rank_warning = _rank(products, limit=limit, use_groq=use_groq)
            warning = " ".join(item for item in [source_warning, rank_warning] if item)
            payload = {
                "warning": warning or None,
                "source": source,
                "candidate_count": len(products),
                "count": len(ranked),
                "items": [_ranked_to_dict(item) for item in ranked],
            }
            if export:
                day_dir = export_daily_package(
                    ranked,
                    output_root=output_root,
                    download_assets=download_assets,
                )
                payload["exported_dir"] = str(day_dir)
            self._send_json(payload)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_analyze_products(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            products = [_product_from_dict(item) for item in body.get("products", [])]
            products = [product for product in products if product.title and product.url]
            limit = _to_int(str(body.get("limit") or ""), default=7)
            use_groq = bool(body.get("use_groq"))
            export = bool(body.get("export"))
            download_assets = bool(body.get("download_assets"))
            output_root = body.get("output_root") or "daily_out"
            ranked, rank_warning = _rank(products, limit=limit, use_groq=use_groq)
            payload = {
                "warning": rank_warning,
                "source": "extension",
                "candidate_count": len(products),
                "count": len(ranked),
                "items": [_ranked_to_dict(item) for item in ranked],
            }
            if export:
                day_dir = export_daily_package(
                    ranked,
                    output_root=output_root,
                    download_assets=download_assets,
                )
                payload["exported_dir"] = str(day_dir)
            self._send_json(payload)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_enrich_media(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            raw_items = body.get("products", [])
            products = [_product_from_dict(item) for item in raw_items]

            cookie = str(body.get("shopee_cookie") or "").strip() or None
            cookie, use_browser, source_note = _shopee_media_source(cookie)
            force_refresh_media = bool(body.get("force_refresh_media"))
            if not use_browser and not cookie:
                self._send_json(
                    {
                        "ok": True,
                        "products": raw_items,
                        "enriched": 0,
                        "warning": (
                            "Chua co phien Shopee de lay anh/video. Hay bam 'Mo Chrome dang nhap Shopee' "
                            "va dang nhap Shopee, hoac bam 'Lay cookie Shopee', roi kiem tra lai."
                        ),
                    }
                )
                return

            errors = enrich_products_with_media(
                products,
                cookie=cookie,
                use_browser=use_browser,
                refresh_existing=force_refresh_media,
            )
            enriched_count = 0
            for raw_item, product in zip(raw_items, products):
                if not isinstance(raw_item, dict):
                    continue
                before = json.dumps(
                    {
                        "image_url": raw_item.get("image_url"),
                        "image_urls": raw_item.get("image_urls") or [],
                        "video_url": raw_item.get("video_url"),
                        "video_urls": raw_item.get("video_urls") or [],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                if product.image_url:
                    raw_item["image_url"] = product.image_url
                    raw_item["image_urls"] = product.image_urls
                if product.video_url:
                    raw_item["video_url"] = product.video_url
                    raw_item["video_urls"] = product.video_urls
                after = json.dumps(
                    {
                        "image_url": raw_item.get("image_url"),
                        "image_urls": raw_item.get("image_urls") or [],
                        "video_url": raw_item.get("video_url"),
                        "video_urls": raw_item.get("video_urls") or [],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                if after != before:
                    enriched_count += 1

            warning_parts = [source_note] if source_note else []
            if errors:
                warning_parts.append("Mot so SP chua lay duoc media: " + "; ".join(errors[:3]))
            self._send_json(
                {
                    "ok": True,
                    "products": raw_items,
                    "enriched": enriched_count,
                    "warning": " ".join(warning_parts) or None,
                }
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_facebook_queue(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            page_url = str(body.get("page_url") or "").strip()
            use_graph = graph_configured()
            if not use_graph and not _looks_like_facebook_page_url(page_url):
                raise ValueError("Chi ho tro URL fanpage Facebook, khong ho tro profile ca nhan.")
            raw_items = body.get("products", [])
            if len(raw_items) > 5:
                raise ValueError("Moi lan chi nen dang toi da 5 san pham.")
            products = [_product_from_dict(item) for item in body.get("products", [])]
            products = [product for product in products if product.title and product.url]
            if use_graph:
                graph_items = [
                    (product, raw_item.get("post") if isinstance(raw_item, dict) else None)
                    for raw_item, product in zip(raw_items, products)
                ]
                results = publish_products_to_page(graph_items)
                ok_count = sum(1 for item in results if item.ok)
                failed = [item for item in results if not item.ok]
                if ok_count and failed:
                    message = (
                        f"Da dang {ok_count}/{len(results)} bai. "
                        + "Bai loi: "
                        + "; ".join(f"{item.title[:40]} ({item.error})" for item in failed)
                    )
                elif not ok_count:
                    message = "Khong dang duoc bai nao: " + "; ".join(
                        f"{item.title[:40]} ({item.error})" for item in failed
                    )
                else:
                    message = f"Da dang {ok_count} bai qua Meta Graph API."
                self._send_json(
                    {
                        "ok": ok_count > 0,
                        "all_ok": ok_count == len(results),
                        "posted_via_graph": True,
                        "count": len(results),
                        "ok_count": ok_count,
                        "results": [item.__dict__ for item in results],
                        "message": message,
                    },
                    status=200,
                )
                return
            queue = []
            for raw_item, product in zip(raw_items, products):
                post = raw_item.get("post") or build_facebook_post(product, ["san pham duoc chon tu file link hang loat"])
                queue.append(
                    {
                        "product_id": product.product_id,
                        "title": product.title,
                        "page_url": page_url,
                        "post": post,
                    }
                )
            self._send_json(
                {
                    "ok": True,
                    "count": len(queue),
                    "queue": queue,
                    "message": "Da tao hang doi bai dang Facebook.",
                }
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_facebook_story_queue(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            if not graph_configured():
                raise ValueError("Can ket noi Facebook Graph API truoc khi dang tin.")
            raw_items = body.get("products", [])
            if len(raw_items) > 5:
                raise ValueError("Moi lan chi nen dang toi da 5 tin.")
            products = [_product_from_dict(item) for item in raw_items]
            products = [product for product in products if product.title and product.url]
            results = publish_stories_to_page(products)
            ok_count = sum(1 for item in results if item.ok)
            failed = [item for item in results if not item.ok]
            if ok_count and failed:
                message = (
                    f"Da dang {ok_count}/{len(results)} tin. "
                    + "Tin loi: "
                    + "; ".join(f"{item.title[:40]} ({item.error})" for item in failed)
                )
            elif not ok_count:
                message = "Khong dang duoc tin nao: " + "; ".join(
                    f"{item.title[:40]} ({item.error})" for item in failed
                )
            else:
                message = f"Da dang {ok_count} tin anh/video qua Meta Graph API."
            self._send_json(
                {
                    "ok": ok_count > 0,
                    "all_ok": ok_count == len(results),
                    "posted_via_graph": True,
                    "count": len(results),
                    "ok_count": ok_count,
                    "results": [item.__dict__ for item in results],
                    "message": message,
                },
                status=200,
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_facebook_four_photo_queue(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            if not graph_configured():
                raise ValueError("Can ket noi Facebook Graph API truoc khi dang bai 4 anh.")
            raw_items = body.get("products", [])
            if len(raw_items) > 5:
                raise ValueError("Moi lan chi nen dang toi da 5 bai 4 anh.")
            normalized_items = [
                _absolutize_item_media_urls(item, self.headers.get("Host") or "127.0.0.1:8001")
                for item in raw_items
            ]
            products = [_product_from_dict(item) for item in normalized_items]
            products = [product for product in products if product.title and product.url]
            missing_image = [
                product.title[:40]
                for product in products
                if not (product.image_url or product.image_urls)
            ]
            if missing_image:
                raise ValueError("Dang bai 4 anh chi nhan san pham co anh. Thieu anh: " + "; ".join(missing_image))
            graph_items = [
                (product, raw_item.get("post") if isinstance(raw_item, dict) else None)
                for raw_item, product in zip(normalized_items, products)
            ]
            results = publish_four_photos_to_page(graph_items)
            ok_count = sum(1 for item in results if item.ok)
            failed = [item for item in results if not item.ok]
            if ok_count and failed:
                message = (
                    f"Da dang {ok_count}/{len(results)} bai 4 anh. "
                    + "Bai loi: "
                    + "; ".join(f"{item.title[:40]} ({item.error})" for item in failed)
                )
            elif not ok_count:
                message = "Khong dang duoc bai 4 anh nao: " + "; ".join(
                    f"{item.title[:40]} ({item.error})" for item in failed
                )
            else:
                message = f"Da dang {ok_count} bai 4 anh qua Meta Graph API."
            self._send_json(
                {
                    "ok": ok_count > 0,
                    "all_ok": ok_count == len(results),
                    "posted_via_graph": True,
                    "count": len(results),
                    "ok_count": ok_count,
                    "results": [item.__dict__ for item in results],
                    "message": message,
                },
                status=200,
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_facebook_reel_queue(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            if not graph_configured():
                raise ValueError("Can ket noi Facebook Graph API truoc khi dang thước phim.")
            raw_items = body.get("products", [])
            if len(raw_items) > 5:
                raise ValueError("Moi lan chi nen dang toi da 5 thước phim.")
            products = [_product_from_dict(item) for item in raw_items]
            products = [product for product in products if product.title and product.url]
            missing_video = [
                product.title[:40]
                for product in products
                if not (product.video_url or product.video_urls)
            ]
            if missing_video:
                raise ValueError("Chi dang Reels cho san pham co video. Thieu video: " + "; ".join(missing_video))
            results = publish_reels_to_page(products)
            ok_count = sum(1 for item in results if item.ok)
            failed = [item for item in results if not item.ok]
            if ok_count and failed:
                message = (
                    f"Da dang {ok_count}/{len(results)} thước phim. "
                    + "Reels loi: "
                    + "; ".join(f"{item.title[:40]} ({item.error})" for item in failed)
                )
            elif not ok_count:
                message = "Khong dang duoc thước phim nao: " + "; ".join(
                    f"{item.title[:40]} ({item.error})" for item in failed
                )
            else:
                message = f"Da dang {ok_count} thước phim qua Meta Graph API."
            self._send_json(
                {
                    "ok": ok_count > 0,
                    "all_ok": ok_count == len(results),
                    "posted_via_graph": True,
                    "count": len(results),
                    "ok_count": ok_count,
                    "results": [item.__dict__ for item in results],
                    "message": message,
                },
                status=200,
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_archive_dates(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            output_root = body.get("output_root") or "out"
            dates = _archive_dates(output_root)
            self._send_json({"ok": True, "dates": dates})
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_archive_products(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            output_root = body.get("output_root") or "out"
            selected_date = str(body.get("date") or "").strip()
            items = _archive_products(output_root, selected_date)
            self._send_json(
                {
                    "ok": True,
                    "date": selected_date,
                    "count": len(items),
                    "items": items,
                }
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_archive_media(self, parsed) -> None:
        try:
            query = urllib.parse.parse_qs(parsed.query)
            output_root = query.get("output_root", ["out"])[0] or "out"
            selected_date = query.get("date", [""])[0]
            folder = query.get("folder", [""])[0]
            filename = query.get("file", [""])[0]
            path = _archive_media_path(output_root, selected_date, folder, filename)
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=404)

    def _handle_export_products(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw_body = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw_body or "{}")
            products = [_product_from_dict(item) for item in body.get("products", [])]
            products = [product for product in products if product.title and product.url]
            output_root = body.get("output_root") or "out"
            download_assets = bool(body.get("download_assets"))
            ranked = [_ranked_from_dict(item, product) for item, product in zip(body.get("products", []), products)]
            day_dir = export_daily_package(
                ranked,
                output_root=output_root,
                download_assets=download_assets,
            )
            self._send_json(
                {
                    "ok": True,
                    "exported_dir": str(day_dir),
                    "count": len(ranked),
                    "items": [_ranked_to_dict(item) for item in ranked],
                }
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _send_html(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _load_products(form: cgi.FieldStorage, source: str) -> tuple[list[Product], str | None]:
    if source in {"csv", "bulk_csv"}:
        csv_path = _save_upload(form)
        return load_products_from_csv(csv_path), None
    keywords = parse_keywords(_field_value(form, "keywords"))
    per_keyword = _to_int(_field_value(form, "per_keyword"), default=20)
    shopee_cookie = _field_value(form, "shopee_cookie")
    shopee_curl = _field_value(form, "shopee_curl")
    use_browser = not shopee_cookie and not shopee_curl
    try:
        return discover_shopee_hot_products(
            keywords=keywords,
            per_keyword=per_keyword,
            cookie=shopee_cookie,
            headers_override=headers_from_curl(shopee_curl),
            use_browser=use_browser,
        ), None
    except DiscoveryError as exc:
        raise ValueError(
            "Khong lay duoc san pham tu Shopee. "
            "Neu dang dung extension, hay reload extension va refresh trang tool. "
            "Neu van loi, dung tam che do CSV hoac dan Copy as cURL. "
            f"Chi tiet: {exc}"
        ) from exc


def _shopee_media_source(cookie: str | None) -> tuple[str | None, bool, str | None]:
    """Prefer reusing the logged-in Chrome session by extracting its cookie and fetching in the background."""
    from .shopee_session import DEFAULT_DEBUG_PORT, _debug_endpoint_ready

    if _debug_endpoint_ready(DEFAULT_DEBUG_PORT):
        try:
            return (
                read_shopee_cookie(DEFAULT_DEBUG_PORT),
                False,
                "Dang dung cookie tu Chrome login Shopee de lay media trong nen, khong mo tab moi.",
            )
        except ShopeeSessionError:
            pass
    if cookie:
        return cookie, False, "Dang dung cookie Shopee truc tiep (neu thieu anh, hay mo Chrome dang nhap Shopee)."
    return None, False, None


def _product_from_dict(item: dict) -> Product:
    return Product(
        title=str(item.get("title") or ""),
        url=str(item.get("url") or ""),
        product_id=str(item.get("product_id") or "") or None,
        source_url=str(item.get("source_url") or "") or None,
        price=_optional_int(item.get("price")),
        original_price=_optional_int(item.get("original_price")),
        sold_week=_optional_int(item.get("sold_week")),
        sold_month=_optional_int(item.get("sold_month")),
        rating=_optional_float(item.get("rating")),
        review_count=_optional_int(item.get("review_count")),
        commission_rate=_optional_float(item.get("commission_rate")),
        shop_name=item.get("shop_name"),
        category=item.get("category"),
        image_url=item.get("image_url"),
        image_urls=[str(value) for value in item.get("image_urls") or [] if value],
        video_url=item.get("video_url"),
        video_urls=[str(value) for value in item.get("video_urls") or [] if value],
        description=item.get("description"),
    )


def _absolutize_item_media_urls(item: dict, host: str) -> dict:
    if not isinstance(item, dict):
        return item
    normalized = dict(item)
    normalized["image_url"] = _absolutize_media_url(normalized.get("image_url"), host)
    normalized["image_urls"] = [_absolutize_media_url(value, host) for value in normalized.get("image_urls") or [] if value]
    normalized["video_url"] = _absolutize_media_url(normalized.get("video_url"), host)
    normalized["video_urls"] = [_absolutize_media_url(value, host) for value in normalized.get("video_urls") or [] if value]
    return normalized


def _absolutize_media_url(value: object, host: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        return f"http://{host}{raw}"
    return raw


def _save_upload(form: cgi.FieldStorage) -> Path:
    item = form["csv_file"] if "csv_file" in form else None
    if item is None or not getattr(item, "file", None) or not item.filename:
        raise ValueError("Chua chon file CSV.")

    upload_dir = Path("web_uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(item.filename or "products.csv").name
    target = upload_dir / filename
    with target.open("wb") as file:
        file.write(item.file.read())
    return target


def _rank(products: list[Product], limit: int, use_groq: bool) -> tuple[list[RankedProduct], str | None]:
    if use_groq:
        try:
            ranked = rank_with_groq(
                products,
                api_key=get_env("GROQ_API_KEY"),
                model=get_env("GROQ_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
                limit=limit,
            )
            return ranked[:limit], None
        except GroqUnavailable as exc:
            return score_products(products, limit=limit), f"Groq loi hoac het quota, da fallback local: {exc}"
    return score_products(products, limit=limit), None


def _score_bulk(products: list[Product]) -> list[RankedProduct]:
    return score_products(products)


def _ranked_from_dict(item: dict, product: Product) -> RankedProduct:
    return RankedProduct(
        product=product,
        score=_optional_float(item.get("score")) or 0,
        reasons=[str(value) for value in item.get("reasons") or [] if value],
        source=str(item.get("source") or "manual"),
    )


def _ranked_to_dict(item: RankedProduct) -> dict:
    product = item.product
    image_urls = _best_urls(product.image_urls, [])
    video_urls = _best_urls(product.video_urls, [])
    return {
        "title": product.title,
        "product_id": product.product_id,
        "url": product.url,
        "source_url": product.source_url,
        "score": item.score,
        "source": item.source,
        "reasons": item.reasons,
        "post": build_facebook_post(product, item.reasons),
        "price": product.price,
        "original_price": product.original_price,
        "sold_week": product.sold_week,
        "sold_month": product.sold_month,
        "rating": product.rating,
        "review_count": product.review_count,
        "commission_rate": product.commission_rate,
        "shop_name": product.shop_name,
        "category": product.category,
        "image_url": product.image_url or (image_urls[0] if image_urls else None),
        "image_urls": product.image_urls,
        "video_url": product.video_url or (video_urls[0] if video_urls else None),
        "video_urls": product.video_urls,
        "description": product.description,
    }


def _looks_like_facebook_page_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    if host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        return False
    if not path:
        return False
    blocked_prefixes = ("profile.php", "me", "friends", "groups", "people")
    return not any(path.lower().startswith(prefix) for prefix in blocked_prefixes)


def _best_urls(primary: list[str], fallback: list[str]) -> list[str]:
    values: list[str] = []
    for url in [*primary, *fallback]:
        if url and url not in values:
            values.append(url)
    return values


def _archive_dates(output_root: str | Path) -> list[dict]:
    root = Path(output_root)
    if not root.exists() or not root.is_dir():
        return []
    dates: list[dict] = []
    for day_dir in root.iterdir():
        if not day_dir.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_dir.name):
            continue
        count = len([path for path in day_dir.iterdir() if path.is_dir() and (path / "product.json").exists()])
        dates.append({"date": day_dir.name, "count": count})
    return sorted(dates, key=lambda item: item["date"], reverse=True)


def _archive_products(output_root: str | Path, selected_date: str) -> list[dict]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", selected_date):
        raise ValueError("Ngay archive khong hop le. Dinh dang dung la YYYY-MM-DD.")
    day_dir = Path(output_root) / selected_date
    if not day_dir.exists() or not day_dir.is_dir():
        raise ValueError(f"Khong tim thay thu muc output cho ngay {selected_date}.")

    summary_rank: dict[str, dict] = {}
    summary_path = day_dir / "summary.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = []
        if isinstance(summary, list):
            for index, item in enumerate(summary, start=1):
                if not isinstance(item, dict):
                    continue
                folder = Path(str(item.get("folder") or "")).name
                if folder:
                    summary_rank[folder] = {
                        "rank": item.get("rank") or index,
                        "score": item.get("score"),
                        "images": item.get("images") or [],
                        "videos": item.get("videos") or [],
                    }

    items: list[dict] = []
    for product_path in day_dir.glob("*/product.json"):
        try:
            data = json.loads(product_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        post_path = product_path.parent / "post.txt"
        try:
            post_text = post_path.read_text(encoding="utf-8") if post_path.exists() else ""
        except OSError:
            post_text = ""
        item = _archive_product_to_item(
            data=data,
            post_text=post_text,
            output_root=output_root,
            folder_name=product_path.parent.name,
            selected_date=selected_date,
            summary_info=summary_rank.get(product_path.parent.name, {}),
        )
        if item:
            items.append(item)

    return sorted(items, key=lambda item: (_optional_int(item.get("rank")) or 999999, item.get("title") or ""))


def _archive_product_to_item(
    data: dict,
    post_text: str,
    output_root: str | Path,
    folder_name: str,
    selected_date: str,
    summary_info: dict,
) -> dict | None:
    title = str(data.get("title") or "").strip()
    affiliate_url = str(data.get("affiliate_url") or data.get("url") or "").strip()
    if not title or not affiliate_url:
        return None
    image_urls = [str(url) for url in data.get("detected_images") or data.get("image_urls") or [] if url]
    if data.get("image_url"):
        image_urls.insert(0, str(data["image_url"]))
    video_urls = [str(url) for url in data.get("detected_videos") or data.get("video_urls") or [] if url]
    if data.get("video_url"):
        video_urls.insert(0, str(data["video_url"]))
    local_images, local_videos = _archive_media_urls(output_root, selected_date, folder_name, summary_info)
    image_urls = _best_urls(local_images, image_urls)
    video_urls = _best_urls(local_videos, video_urls)
    reasons = [str(value) for value in data.get("reasons") or [] if value]
    score = _optional_float(data.get("score"))
    if score is None:
        score = _optional_float(summary_info.get("score"))
    product = Product(
        title=title,
        url=affiliate_url,
        product_id=str(data.get("product_id") or folder_name) or None,
        source_url=str(data.get("source_url") or "") or None,
        price=_optional_int(data.get("price")),
        original_price=_optional_int(data.get("original_price")),
        sold_week=_optional_int(data.get("sold_week")),
        sold_month=_optional_int(data.get("sold_month")),
        rating=_optional_float(data.get("rating")),
        review_count=_optional_int(data.get("review_count")),
        commission_rate=_optional_float(data.get("commission_rate")),
        shop_name=data.get("shop_name"),
        category=data.get("category"),
        image_url=image_urls[0] if image_urls else None,
        image_urls=image_urls[1:],
        video_url=video_urls[0] if video_urls else None,
        video_urls=video_urls[1:],
        description=data.get("detected_description") or data.get("description"),
    )
    item = _ranked_to_dict(RankedProduct(product=product, score=score or 0, reasons=reasons, source=f"old-{selected_date}"))
    item["post"] = post_text or item["post"]
    item["rank"] = _optional_int(summary_info.get("rank")) or None
    item["archive_date"] = selected_date
    return item


def _archive_media_urls(
    output_root: str | Path,
    selected_date: str,
    folder_name: str,
    summary_info: dict,
) -> tuple[list[str], list[str]]:
    try:
        folder = _archive_folder_path(output_root, selected_date, folder_name)
    except ValueError:
        return [], []
    summary_images = _summary_media_names(summary_info.get("images"), folder)
    summary_videos = _summary_media_names(summary_info.get("videos"), folder)
    image_names = _best_urls(summary_images, _media_filenames(folder, {"jpg", "jpeg", "png", "webp", "gif"}))
    video_names = _best_urls(summary_videos, _media_filenames(folder, {"mp4", "webm", "mov", "m4v"}))
    return (
        [_archive_media_url(output_root, selected_date, folder_name, name) for name in image_names],
        [_archive_media_url(output_root, selected_date, folder_name, name) for name in video_names],
    )


def _summary_media_names(values: object, folder: Path) -> list[str]:
    names: list[str] = []
    for value in values or []:
        name = Path(str(value)).name
        if name and (folder / name).exists() and name not in names:
            names.append(name)
    return names


def _media_filenames(folder: Path, extensions: set[str]) -> list[str]:
    names: list[str] = []
    for path in sorted(folder.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        ext = path.suffix.lower().lstrip(".")
        if ext in extensions:
            names.append(path.name)
    return names


def _archive_media_url(output_root: str | Path, selected_date: str, folder_name: str, filename: str) -> str:
    params = urllib.parse.urlencode(
        {
            "output_root": str(output_root),
            "date": selected_date,
            "folder": folder_name,
            "file": filename,
        }
    )
    return f"{APP_PATH}/api/archive-media?{params}"


def _archive_media_path(output_root: str | Path, selected_date: str, folder_name: str, filename: str) -> Path:
    if Path(filename).name != filename:
        raise ValueError("Ten file media khong hop le.")
    path = _archive_folder_path(output_root, selected_date, folder_name) / filename
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Khong tim thay file media archive.") from exc
    folder = _archive_folder_path(output_root, selected_date, folder_name).resolve(strict=True)
    if folder not in resolved.parents:
        raise ValueError("Duong dan media archive khong hop le.")
    if resolved.suffix.lower().lstrip(".") not in {"jpg", "jpeg", "png", "webp", "gif", "mp4", "webm", "mov", "m4v"}:
        raise ValueError("Dinh dang media archive khong duoc ho tro.")
    return resolved


def _archive_folder_path(output_root: str | Path, selected_date: str, folder_name: str) -> Path:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", selected_date):
        raise ValueError("Ngay archive khong hop le.")
    if Path(folder_name).name != folder_name or not folder_name:
        raise ValueError("Thu muc san pham archive khong hop le.")
    root = Path(output_root).resolve()
    folder = (root / selected_date / folder_name).resolve()
    if root not in folder.parents:
        raise ValueError("Duong dan archive khong hop le.")
    if not folder.exists() or not folder.is_dir():
        raise ValueError("Khong tim thay thu muc san pham archive.")
    return folder


def _facebook_redirect_uri(handler: BaseHTTPRequestHandler) -> str:
    configured = get_env("FACEBOOK_REDIRECT_URI")
    if configured:
        return configured
    host = handler.headers.get("Host") or "127.0.0.1:8001"
    return f"http://{host}{APP_PATH}/facebook/callback"


def _field_value(form: cgi.FieldStorage, name: str) -> str | None:
    if name not in form:
        return None
    value = form[name].value
    return value if isinstance(value, str) else None


def _to_int(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except ValueError:
        return default


def _optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _optional_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _page() -> str:
    return r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Affiliate Hot Tool</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #687385;
      --line: #d9dee7;
      --accent: #116b5f;
      --accent-dark: #0b5148;
      --warn: #9a5b00;
      --danger: #a83232;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
    header { padding: 22px 28px; background: #fff; border-bottom: 1px solid var(--line); }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    header p { margin: 6px 0 0; color: var(--muted); }
    main { display: grid; grid-template-columns: 390px 1fr; gap: 18px; padding: 18px; max-width: 1480px; margin: 0 auto; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }
    label { display: block; font-size: 13px; color: var(--muted); margin: 14px 0 6px; }
    input[type="file"], input[type="number"], input[type="text"], textarea {
      width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 10px; font-size: 14px; background: #fff;
    }
    textarea { min-height: 96px; resize: vertical; }
    .radio, .check { display: flex; align-items: center; gap: 8px; margin-top: 10px; color: var(--text); font-size: 14px; }
    .hint { color: var(--muted); font-size: 12px; line-height: 1.45; margin-top: 6px; }
    .actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 16px; }
    button { border: 0; border-radius: 6px; padding: 11px 12px; background: var(--accent); color: #fff; font-weight: 700; cursor: pointer; }
    button.secondary { background: #34495e; }
    button:hover { background: var(--accent-dark); }
    button.secondary:hover { background: #243545; }
    button:disabled, button.secondary:disabled { background: #b8c2cc; color: #eef2f5; cursor: not-allowed; opacity: .65; }
    button:disabled:hover, button.secondary:disabled:hover { background: #b8c2cc; }
    .status { margin-top: 12px; min-height: 22px; color: var(--muted); font-size: 14px; line-height: 1.45; }
    .warning { color: var(--warn); }
    .error { color: var(--danger); }
    .progress-wrap { margin-top: 12px; display: none; }
    .progress-wrap.active { display: block; }
    .progress-track { width: 100%; height: 16px; background: #e9edf2; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
    .progress-bar { width: 0%; height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-dark)); transition: width .35s ease; }
    .progress-label { margin-top: 6px; font-size: 12px; color: var(--muted); }
    table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
    th, td { padding: 11px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { background: #edf1f5; text-align: left; font-size: 13px; color: #3c4654; }
    td { font-size: 14px; }
    tr:hover td { background: #fbfcfd; }
    a { color: var(--accent); }
    .thumb { width: 72px; height: 72px; object-fit: cover; border-radius: 6px; border: 1px solid var(--line); background: #f8fafc; display: block; }
    .media-note { margin-top: 4px; font-size: 11px; color: var(--muted); }
    .pill { display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 3px 8px; font-size: 12px; color: #334155; background: #f8fafc; }
    .post { white-space: pre-wrap; font-size: 13px; max-width: 360px; color: #263342; }
    .list-controls { margin-bottom: 10px; padding: 10px 12px; background: #fff; border: 1px solid var(--line); border-radius: 8px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
    .list-controls .radio { margin: 0; }
    .archive-picker { display: none; align-items: center; gap: 8px; flex-wrap: wrap; }
    .archive-picker.active { display: flex; }
    .archive-picker input[type="date"] { border: 1px solid var(--line); border-radius: 6px; padding: 9px 10px; font-size: 14px; background: #fff; }
    .archive-picker button { padding: 9px 12px; }
    .list-meta { color: var(--muted); font-size: 12px; margin-left: auto; }
    .select-all { display: inline-flex; align-items: center; gap: 8px; margin: 0; color: #3c4654; font-size: 13px; }
    .selection-badge {
      position: fixed; right: 18px; bottom: 18px; z-index: 30; display: none;
      padding: 10px 14px; border-radius: 999px; background: rgba(23, 32, 42, .92); color: #fff;
      font-size: 13px; font-weight: 700; box-shadow: 0 10px 24px rgba(15, 23, 42, .18);
    }
    .selection-badge.active { display: inline-flex; align-items: center; }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; padding: 12px; }
      .table-wrap { overflow-x: auto; }
      table { min-width: 1080px; }
      .list-meta { width: 100%; margin-left: 0; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Affiliate Hot Tool</h1>
    <p>Upload CSV link hang loat, kiem tra san pham tren Shopee, chon top hot bang Groq, va dang Fanpage.</p>
  </header>
  <main>
    <section class="panel">
      <form id="toolForm">
        <input name="source" type="hidden" value="bulk_csv">
        <input name="limit" type="hidden" value="10">
        <input name="use_groq" type="hidden" value="1">

        <label>CSV link hang loat / san pham</label>
        <input name="csv_file" type="file" accept=".csv">
        <div class="hint">Ho tro file Shopee Affiliate co cot Ma san pham, Ten san pham, Link san pham, Link uu dai. He thong se doc toan bo CSV va sap xep theo diem hot de ban chon san pham dang.</div>
        <div id="extensionStatus" class="hint">Extension: dang kiem tra...</div>

        <label>Thu muc export</label>
        <input name="output_root" type="text" value="out">

        <label class="check"><input name="download_assets" type="checkbox" value="1" checked> Tai anh/video khi kiem tra</label>

        <label>Phien Shopee (de lay anh/video san pham)</label>
        <div class="actions">
          <button type="button" id="shopeeLoginBtn" class="secondary">Mo Chrome login Shopee</button>
          <button type="button" id="shopeeCookieBtn" class="secondary">Lay cookie Shopee</button>
        </div>
        <div id="shopeeStatus" class="hint">Shopee: chua co phien. Mo Chrome login Shopee de tool lay anh/video san pham.</div>

        <div class="actions">
          <button type="button" id="analyzeBtn">Kiem tra san pham HOT</button>
        </div>
        <label>Facebook fanpage URL</label>
        <input name="facebook_page_url" type="text" placeholder="Chi can khi chua cau hinh Graph API">
        <div class="actions">
          <button type="button" id="facebookConnectBtn" class="secondary">Ket noi Facebook</button>
          <button type="button" id="facebookStatusBtn" class="secondary">Kiem tra token</button>
        </div>
        <div id="facebookAuthStatus" class="hint">Facebook Graph: dang kiem tra...</div>
        <label>Token lau dai (dan User Token tu Graph API Explorer)</label>
        <textarea id="facebookTokenInput" placeholder="Dan User Token vao day roi bam 'Dung token lau dai'"></textarea>
        <div class="actions">
          <button type="button" id="facebookTokenBtn" class="secondary">Dung token lau dai</button>
        </div>
        <div class="hint">Mo Graph API Explorer, chon app, cap quyen pages_show_list + pages_read_engagement + pages_manage_posts + pages_manage_engagement, tao User Token roi dan vao day. Tool tu doi sang Page token vinh vien, het canh token het han. Quyen pages_manage_engagement de page tu binh luan link mua hang + anh phu.</div>
        <label class="check"><input name="facebook_auto_post" type="checkbox" value="1"> Tu bam Dang sau khi dien noi dung</label>
        <div class="actions">
          <button type="button" id="facebookBtn" class="secondary">Dang bai len Fanpage</button>
          <button type="button" id="facebookFourPhotoBtn" class="secondary">Dang bai 4 anh</button>
          <button type="button" id="facebookStoryBtn" class="secondary">Dang tin Anh/Video</button>
          <button type="button" id="facebookReelBtn" class="secondary">Dang thước phim</button>
        </div>
        <div class="hint">Dang bai len Fanpage co the uu tien video neu san pham co video. Dang bai 4 anh chi dang toi da 4 anh dai dien, khong dang video; video va anh con lai se duoc comment kem link mua hang. Dang tin Anh/Video se uu tien video; neu khong co video thi dung anh dau tien. Dang thước phim chi nhan san pham co video. Facebook Page Stories API hien chua ho tro gan link sticker clickable qua Graph API.</div>
        <div id="status" class="status"></div>
        <div id="postProgress" class="progress-wrap">
          <div class="progress-track"><div id="postProgressBar" class="progress-bar"></div></div>
          <div id="postProgressLabel" class="progress-label"></div>
        </div>
      </form>
    </section>
    <section>
      <div class="list-controls">
        <label class="radio"><input type="radio" name="productListMode" value="new" checked> San pham moi</label>
        <label class="radio"><input type="radio" name="productListMode" value="old"> San pham cu</label>
        <div id="archivePicker" class="archive-picker">
          <input id="archiveDate" type="date">
          <button type="button" id="loadArchiveBtn" class="secondary">Tai san pham cu</button>
        </div>
        <div id="listMeta" class="list-meta">Dang hien thi san pham moi tu CSV.</div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th><label class="select-all"><input id="pickAllProducts" type="checkbox"> Chon</label></th>
              <th>Anh</th>
              <th>Ma SP</th>
              <th>San pham</th>
              <th>Diem</th>
              <th>Tin hieu</th>
              <th>Bai Facebook</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody id="results">
            <tr><td colspan="9">Chon file CSV link hang loat roi bam Kiem tra san pham HOT.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
  <div id="selectionBadge" class="selection-badge">Da chon 0 san pham</div>
  <script>
    const form = document.getElementById("toolForm");
    const statusBox = document.getElementById("status");
    const extensionStatus = document.getElementById("extensionStatus");
    const facebookAuthStatus = document.getElementById("facebookAuthStatus");
    const shopeeStatus = document.getElementById("shopeeStatus");
    const results = document.getElementById("results");
    const postProgress = document.getElementById("postProgress");
    const postProgressBar = document.getElementById("postProgressBar");
    const postProgressLabel = document.getElementById("postProgressLabel");
    const archivePicker = document.getElementById("archivePicker");
    const archiveDate = document.getElementById("archiveDate");
    const loadArchiveBtn = document.getElementById("loadArchiveBtn");
    const pickAllProducts = document.getElementById("pickAllProducts");
    const selectionBadge = document.getElementById("selectionBadge");
    const listMeta = document.getElementById("listMeta");
    let extensionReady = false;
    let currentItems = [];
    let newItems = [];
    let archiveItems = [];
    let selectedProductKeys = new Set();
    let shopeeCookie = "";
    let graphReady = false;
    document.getElementById("analyzeBtn").addEventListener("click", submitTool);
    document.getElementById("facebookBtn").addEventListener("click", prepareFacebookQueue);
    document.getElementById("facebookFourPhotoBtn").addEventListener("click", prepareFacebookFourPhotoQueue);
    document.getElementById("facebookStoryBtn").addEventListener("click", prepareFacebookStoryQueue);
    document.getElementById("facebookReelBtn").addEventListener("click", prepareFacebookReelQueue);
    document.getElementById("facebookConnectBtn").addEventListener("click", connectFacebook);
    document.getElementById("facebookStatusBtn").addEventListener("click", refreshFacebookAuthStatus);
    document.getElementById("shopeeLoginBtn").addEventListener("click", openShopeeLogin);
    document.getElementById("shopeeCookieBtn").addEventListener("click", readShopeeCookie);
    document.getElementById("facebookTokenBtn").addEventListener("click", exchangeFacebookToken);
    loadArchiveBtn.addEventListener("click", loadArchiveProducts);
    pickAllProducts.addEventListener("change", togglePickAllProducts);
    form.output_root.addEventListener("change", refreshArchiveDates);
    results.addEventListener("change", onResultSelectionChange);
    document.querySelectorAll('input[name="productListMode"]').forEach(input => {
      input.addEventListener("change", switchProductListMode);
    });
    (function setupTokenButtonState() {
      const tokenInput = document.getElementById("facebookTokenInput");
      const tokenBtn = document.getElementById("facebookTokenBtn");
      const syncTokenBtn = () => { tokenBtn.disabled = !tokenInput.value.trim(); };
      tokenInput.addEventListener("input", syncTokenBtn);
      syncTokenBtn();
    })();
    window.addEventListener("message", (event) => {
      if (event.source === window && event.data && event.data.type === "AHT_EXTENSION_READY") {
        extensionReady = true;
        extensionStatus.textContent = "Extension: da ket noi.";
      }
    });
    setTimeout(() => {
      if (!extensionReady) extensionStatus.textContent = "Extension: khong bat buoc. Tool dang chay bang backend on dinh.";
    }, 1200);
    pingExtension();
    refreshFacebookAuthStatus();
    refreshArchiveDates();

    function selectedProductListMode() {
      return (document.querySelector('input[name="productListMode"]:checked') || {}).value || "new";
    }

    function switchProductListMode() {
      const mode = selectedProductListMode();
      archivePicker.classList.toggle("active", mode === "old");
      if (mode === "old") {
        listMeta.textContent = archiveItems.length
          ? `Dang hien thi ${archiveItems.length} san pham cu ngay ${archiveDate.value}.`
          : "Chon ngay va bam Tai san pham cu.";
        render(archiveItems);
      } else {
        listMeta.textContent = newItems.length
          ? `Dang hien thi ${newItems.length} san pham moi tu CSV.`
          : "Dang hien thi san pham moi tu CSV.";
        render(newItems);
      }
    }

    async function refreshArchiveDates() {
      try {
        const res = await fetch("/affiliate_hot_tool/api/archive-dates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ output_root: form.output_root.value || "out" })
        });
        const payload = await res.json();
        if (!res.ok || payload.error) throw new Error(payload.error || "Khong doc duoc danh sach ngay output");
        const dates = payload.dates || [];
        if (dates.length && !archiveDate.value) {
          archiveDate.value = dates[0].date;
          archiveDate.max = dates[0].date;
        }
        if (dates.length) archiveDate.min = dates[dates.length - 1].date;
      } catch (err) {
        listMeta.textContent = "Chua doc duoc danh sach output cu: " + err.message;
      }
    }

    async function loadArchiveProducts() {
      const day = archiveDate.value;
      if (!day) {
        statusBox.className = "status error";
        statusBox.textContent = "Hay chon ngay de tai san pham cu.";
        return;
      }
      statusBox.className = "status warning";
      statusBox.textContent = `Dang tai san pham cu ngay ${day}...`;
      loadArchiveBtn.disabled = true;
      try {
        const res = await fetch("/affiliate_hot_tool/api/archive-products", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ output_root: form.output_root.value || "out", date: day })
        });
        const payload = await res.json();
        if (!res.ok || payload.error) throw new Error(payload.error || "Khong tai duoc san pham cu");
        archiveItems = payload.items || [];
        document.querySelector('input[name="productListMode"][value="old"]').checked = true;
        archivePicker.classList.add("active");
        render(archiveItems);
        statusBox.className = "status";
        statusBox.textContent = `Da tai ${archiveItems.length} san pham cu tu output ngay ${day}.`;
        listMeta.textContent = `Dang hien thi ${archiveItems.length} san pham cu ngay ${day}.`;
        await enrichMediaViaBackend();
      } catch (err) {
        statusBox.className = "status error";
        statusBox.textContent = err.message;
      } finally {
        loadArchiveBtn.disabled = false;
      }
    }

    async function connectFacebook() {
      statusBox.className = "status warning";
      statusBox.textContent = "Dang mo Facebook Login de ket noi Page...";
      try {
        const res = await fetch("/affiliate_hot_tool/api/facebook-auth-start", { method: "POST" });
        const payload = await res.json();
        if (!res.ok || payload.error) throw new Error(payload.error || "Khong tao duoc link ket noi Facebook");
        window.open(payload.login_url, "_blank", "noopener,noreferrer");
        statusBox.textContent = "Da mo Facebook Login. Sau khi cap quyen xong, bam Kiem tra token.";
      } catch (err) {
        statusBox.className = "status error";
        statusBox.textContent = err.message;
      }
    }

    async function exchangeFacebookToken() {
      const input = document.getElementById("facebookTokenInput");
      const token = (input.value || "").trim();
      if (!token) {
        facebookAuthStatus.textContent = "Facebook Graph: hay dan User Token vao o ben tren truoc.";
        return;
      }
      facebookAuthStatus.textContent = "Facebook Graph: dang doi sang Page token lau dai...";
      try {
        const res = await fetch("/affiliate_hot_tool/api/facebook-token-exchange", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token })
        });
        const payload = await res.json();
        if (!res.ok || payload.error) throw new Error(payload.error || "Khong doi duoc token");
        input.value = "";
        document.getElementById("facebookTokenBtn").disabled = true;
        facebookAuthStatus.textContent = payload.message || "Facebook Graph: da luu Page token lau dai.";
        refreshFacebookAuthStatus();
      } catch (err) {
        facebookAuthStatus.textContent = "Facebook Graph: " + err.message;
      }
    }

    async function openShopeeLogin() {
      shopeeStatus.textContent = "Shopee: dang mo Chrome login...";
      try {
        const res = await fetch("/affiliate_hot_tool/api/open-shopee-login", { method: "POST" });
        const payload = await res.json();
        if (!res.ok || payload.error) throw new Error(payload.error || "Khong mo duoc Chrome login Shopee");
        shopeeStatus.textContent = "Shopee: da mo Chrome login. Sau khi dang nhap xong, tool se uu tien dung cookie tu phien nay de lay media trong nen, khong mo tab moi.";
      } catch (err) {
        shopeeStatus.textContent = "Shopee: " + err.message;
      }
    }

    async function readShopeeCookie() {
      shopeeStatus.textContent = "Shopee: dang lay cookie...";
      try {
        const res = await fetch("/affiliate_hot_tool/api/read-shopee-cookie", { method: "POST" });
        const payload = await res.json();
        if (!res.ok || payload.error) throw new Error(payload.error || "Khong lay duoc cookie Shopee");
        shopeeCookie = payload.cookie || "";
        shopeeStatus.textContent = "Shopee: da lay cookie phien dang nhap.";
      } catch (err) {
        shopeeStatus.textContent = "Shopee: " + err.message;
      }
    }

    async function enrichMediaViaBackend() {
      const items = currentItems || [];
      const refreshAll = selectedProductListMode() === "old";
      const need = items
        .map((it, idx) => ({ it, idx }))
        .filter(x => x.it && (x.it.source_url || x.it.url) && (refreshAll || (!x.it.image_url && !x.it.video_url)));
      if (!need.length) return;
      const chunkSize = 4;
      let lastWarning = "";
      for (let start = 0; start < need.length; start += chunkSize) {
        const slice = need.slice(start, start + chunkSize);
        statusBox.className = "status warning";
        statusBox.textContent = refreshAll
          ? `Dang lam moi anh/video san pham cu: ${Math.min(start + slice.length, need.length)}/${need.length}...`
          : `Dang lay anh/video san pham: ${Math.min(start + slice.length, need.length)}/${need.length}...`;
        try {
          const res = await fetch("/affiliate_hot_tool/api/enrich-media", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ products: slice.map(x => x.it), shopee_cookie: shopeeCookie, force_refresh_media: refreshAll })
          });
          const payload = await res.json();
          if (!res.ok || payload.error) { lastWarning = payload.error || "loi lay media"; break; }
          (payload.products || []).forEach((p, i) => {
            const target = slice[i];
            if (target) currentItems[target.idx] = p;
          });
          if (selectedProductListMode() === "new") newItems = currentItems;
          if (selectedProductListMode() === "old") archiveItems = currentItems;
          render(currentItems);
          if (payload.warning) {
            lastWarning = payload.warning;
            if ((payload.enriched || 0) === 0 && start === 0) break;
          }
        } catch (e) {
          lastWarning = e.message;
          break;
        }
      }
      if (lastWarning) {
        statusBox.className = "status warning";
        statusBox.textContent = "Lay anh/video: " + lastWarning;
      }
    }

    async function refreshFacebookAuthStatus() {
      try {
        const res = await fetch("/affiliate_hot_tool/api/facebook-auth-status", { method: "POST" });
        const payload = await res.json();
        if (!res.ok || payload.error) throw new Error(payload.error || "Khong kiem tra duoc Facebook token");
        graphReady = !!payload.graph_configured;
        if (!payload.app_configured) {
          facebookAuthStatus.textContent = "Facebook Graph: can cau hinh FACEBOOK_APP_ID va FACEBOOK_APP_SECRET trong .env de dung ket noi tu dong.";
        } else if (payload.connected) {
          facebookAuthStatus.textContent = `Facebook Graph: da ket noi Page ${payload.page_name || payload.page_id}.`;
        } else {
          facebookAuthStatus.textContent = "Facebook Graph: chua ket noi OAuth. Bam Ket noi Facebook de lay token tu dong.";
        }
      } catch (err) {
        facebookAuthStatus.textContent = "Facebook Graph: " + err.message;
      }
    }

    async function submitTool() {
      statusBox.className = "status";
      statusBox.textContent = "Dang doc CSV...";
      const data = new FormData(form);
      if (!form.csv_file.files.length) {
        statusBox.className = "status error";
        statusBox.textContent = "Ban can chon file CSV link hang loat.";
        return;
      }
      try {
        const res = await fetch("/affiliate_hot_tool/api/analyze", {
          method: "POST",
          body: data
        });
        const payload = await res.json();
        if (!res.ok || payload.error) throw new Error(payload.error || "Request loi");
        const ranked = payload;
        if (extensionReady && ranked.items && ranked.items.length) {
          statusBox.className = "status warning";
          statusBox.textContent = "Dang thu lay anh/video san pham qua extension...";
          try {
            const enriched = await enrichProductsInChunks(ranked.items);
            ranked.items = enriched.products || ranked.items;
            if (enriched.errors && enriched.errors.length) {
              payload.warning = [payload.warning, "Mot so san pham chua lay duoc media: " + enriched.errors.slice(0, 3).join("; ")].filter(Boolean).join(" ");
            }
          } catch (mediaErr) {
            payload.warning = [payload.warning, "Bo qua media extension: " + mediaErr.message].filter(Boolean).join(" ");
          }
        }
        statusBox.textContent = "Dang ghi thu muc out theo ngay...";
        const exported = await exportProducts(ranked.items || [], data);
        newItems = exported.items || ranked.items || [];
        document.querySelector('input[name="productListMode"][value="new"]').checked = true;
        archivePicker.classList.remove("active");
        render(newItems);
        listMeta.textContent = `Dang hien thi ${newItems.length} san pham moi tu CSV.`;
        refreshArchiveDates();
        const parts = [];
        if (payload.warning || ranked.warning) parts.push([payload.warning, ranked.warning].filter(Boolean).join(" "));
        if (exported.exported_dir) parts.push("Da export: " + exported.exported_dir);
        parts.push("Nguon ung vien: " + (payload.candidate_count || 0) + " san pham.");
        parts.push("Danh sach hien thi: " + (ranked.count || (ranked.items || []).length) + " san pham, da sap xep theo diem hot.");
        statusBox.className = (payload.warning || ranked.warning) ? "status warning" : "status";
        statusBox.textContent = parts.join(" ");
        await enrichMediaViaBackend();
      } catch (err) {
        statusBox.className = "status error";
        statusBox.textContent = err.message;
      }
    }

    async function enrichProductsInChunks(products) {
      const chunkSize = 3;
      const output = [];
      const errors = [];
      for (let start = 0; start < products.length; start += chunkSize) {
        const chunk = products.slice(start, start + chunkSize);
        statusBox.textContent = `Dang lay anh/mo ta/video trong nen: ${Math.min(start + chunk.length, products.length)}/${products.length}...`;
        const enriched = await enrichProductsWithExtension(chunk);
        output.push(...(enriched.products || chunk));
        errors.push(...(enriched.errors || []));
      }
      return { products: output, errors };
    }

    function enrichProductsWithExtension(products) {
      return new Promise((resolve, reject) => {
        const requestId = "aht-enrich-" + Date.now() + "-" + Math.random().toString(16).slice(2);
        const timer = setTimeout(() => {
          window.removeEventListener("message", onMessage);
          resolve({ products, errors: ["extension timeout"] });
        }, Math.max(18000, products.length * 8000));
        function onMessage(event) {
          if (event.source !== window || !event.data || event.data.type !== "AHT_ENRICH_PRODUCTS_TO_PAGE") return;
          if (event.data.requestId !== requestId) return;
          clearTimeout(timer);
          window.removeEventListener("message", onMessage);
          const response = event.data.response || {};
          if (!response.ok) resolve({ products, errors: [response.error || "Extension enrich loi"] });
          else resolve(response.payload || { products });
        }
        window.addEventListener("message", onMessage);
        window.postMessage({ type: "AHT_ENRICH_PRODUCTS_FROM_PAGE", requestId, payload: { products } }, "*");
      });
    }

    async function exportProducts(products, data) {
      const res = await fetch("/affiliate_hot_tool/api/export-products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          products,
          output_root: data.get("output_root") || "out",
          download_assets: data.get("download_assets") === "1"
        })
      });
      const payload = await res.json();
      if (!res.ok || payload.error) throw new Error(payload.error || "Export products loi");
      return payload;
    }

    function productSelectionKey(item, index) {
      if (item && item.product_id) return `id:${item.product_id}`;
      if (item && item.url) return `url:${item.url}`;
      return `row:${index}`;
    }

    function syncSelectedProductKeysFromDom() {
      selectedProductKeys = new Set(
        Array.from(document.querySelectorAll(".pick-product:checked"))
          .map(input => input.dataset.key)
          .filter(Boolean)
      );
    }

    function updateSelectionUi() {
      const checkboxes = Array.from(document.querySelectorAll(".pick-product"));
      const checkedCount = checkboxes.filter(input => input.checked).length;
      const total = checkboxes.length;
      pickAllProducts.checked = total > 0 && checkedCount === total;
      pickAllProducts.indeterminate = checkedCount > 0 && checkedCount < total;
      selectionBadge.textContent = checkedCount ? `Da chon ${checkedCount} san pham` : "Da chon 0 san pham";
      selectionBadge.classList.toggle("active", checkedCount > 0);
    }

    function onResultSelectionChange(event) {
      const target = event.target;
      if (!target || !target.classList || !target.classList.contains("pick-product")) return;
      syncSelectedProductKeysFromDom();
      updateSelectionUi();
    }

    function togglePickAllProducts() {
      const checked = !!pickAllProducts.checked;
      document.querySelectorAll(".pick-product").forEach(input => {
        input.checked = checked;
      });
      syncSelectedProductKeysFromDom();
      updateSelectionUi();
    }

    function pingExtension() {
      extensionReady = false;
      extensionStatus.textContent = "Extension: dang ping, chi dung cho fallback Facebook/Shopee neu can...";
      window.postMessage({ type: "AHT_PING_EXTENSION" }, "*");
      setTimeout(() => {
        if (!extensionReady) extensionStatus.textContent = "Extension: khong bat buoc. Tool dang chay bang backend on dinh.";
      }, 1200);
    }

    async function analyzeExtensionProducts(products, exportMode, data) {
      const res = await fetch("/affiliate_hot_tool/api/analyze-products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          products,
          export: exportMode,
          limit: Number(data.get("limit") || 7),
          output_root: data.get("output_root") || "out",
          use_groq: data.get("use_groq") === "1",
          download_assets: data.get("download_assets") === "1"
        })
      });
      const payload = await res.json();
      if (!res.ok || payload.error) throw new Error(payload.error || "Backend analyze-products loi");
      return payload;
    }

    function render(items) {
      currentItems = items || [];
      if (!items.length) {
        results.innerHTML = '<tr><td colspan="9">Khong co san pham phu hop.</td></tr>';
        pickAllProducts.checked = false;
        pickAllProducts.indeterminate = false;
        selectionBadge.classList.remove("active");
        selectionBadge.textContent = "Da chon 0 san pham";
        return;
      }
      results.innerHTML = items.map((item, index) => `
        <tr>
          <td>${index + 1}</td>
          <td><input class="pick-product" type="checkbox" data-index="${index}" data-key="${escapeAttr(productSelectionKey(item, index))}" ${selectedProductKeys.has(productSelectionKey(item, index)) ? "checked" : ""}></td>
          <td>${mediaPreview(item)}</td>
          <td>${escapeHtml(item.product_id || "")}</td>
          <td><strong>${escapeHtml(item.title)}</strong><br><span class="pill">${escapeHtml(item.source)}</span></td>
          <td>${escapeHtml(String(item.score))}</td>
          <td>${(item.reasons || []).map(escapeHtml).join("<br>")}</td>
          <td><div class="post">${escapeHtml(item.post || "")}</div></td>
          <td><a href="${escapeAttr(item.url)}" target="_blank" rel="noreferrer">Mo link</a></td>
        </tr>
      `).join("");
      syncSelectedProductKeysFromDom();
      updateSelectionUi();
    }

    function sleep(ms) {
      return new Promise(resolve => setTimeout(resolve, ms));
    }

    function showPostProgress(total) {
      postProgress.classList.add("active");
      postProgressBar.style.width = "0%";
      postProgressLabel.textContent = `Chuan bi dang ${total} bai...`;
    }

    function updatePostProgress(done, total, label) {
      const percent = total ? Math.round((done / total) * 100) : 0;
      postProgressBar.style.width = percent + "%";
      postProgressLabel.textContent = `${label} (${percent}%)`;
    }

    function hidePostProgress() {
      setTimeout(() => postProgress.classList.remove("active"), 1500);
    }

    async function postSelectedViaGraph(selected, pageUrl, postBtn) {
      const total = selected.length;
      const allResults = [];
      if (postBtn) postBtn.disabled = true;
      showPostProgress(total);
      statusBox.className = "status warning";
      try {
        for (let i = 0; i < total; i++) {
          const product = selected[i];
          const shortTitle = (product.title || "").slice(0, 30);
          updatePostProgress(i, total, `Dang dang bai ${i + 1}/${total}: ${shortTitle}`);
          statusBox.textContent = `Dang dang bai ${i + 1}/${total} len fanpage, khong dang tin...`;
          let payload;
          try {
            const res = await fetch("/affiliate_hot_tool/api/facebook-queue", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ page_url: pageUrl, products: [product] })
            });
            payload = await res.json();
          } catch (netErr) {
            allResults.push({ ok: false, title: product.title, error: netErr.message });
            updatePostProgress(i + 1, total, `Loi mang o bai ${i + 1}/${total}`);
            continue;
          }
          const r = (payload.results || [])[0] || {
            ok: !!payload.ok,
            title: product.title,
            error: payload.error || (payload.ok ? null : "Khong dang duoc")
          };
          allResults.push(r);
          updatePostProgress(i + 1, total, r.ok ? `Da dang ${i + 1}/${total}` : `Bai ${i + 1} loi`);
          if (i < total - 1) {
            // Cho 20-30s giua cac bai de tranh Facebook chan spam.
            for (let s = 20; s >= 1; s--) {
              statusBox.textContent = `Da dang ${i + 1}/${total}. Cho ${s}s truoc khi dang bai tiep theo...`;
              await sleep(1000);
            }
          }
        }
        const okCount = allResults.filter(r => r.ok).length;
        const failed = allResults.filter(r => !r.ok);
        updatePostProgress(total, total, okCount === total ? "Hoan tat" : `Xong, ${okCount}/${total} thanh cong`);
        if (okCount === total) {
          statusBox.className = "status";
          statusBox.textContent = `Da dang ${okCount}/${total} bai len fanpage kem comment link mua hang.`;
        } else if (okCount > 0) {
          statusBox.className = "status warning";
          statusBox.textContent = `Da dang ${okCount}/${total} bai. Bai loi: ` +
            failed.map(r => `${(r.title || "").slice(0, 30)} (${r.error})`).join("; ");
        } else {
          statusBox.className = "status error";
          statusBox.textContent = "Khong dang duoc bai nao: " +
            failed.map(r => `${(r.title || "").slice(0, 30)} (${r.error})`).join("; ");
        }
      } finally {
        if (postBtn) postBtn.disabled = false;
        hidePostProgress();
      }
    }

    async function postSelectedStoriesViaGraph(selected, storyBtn) {
      const total = selected.length;
      const allResults = [];
      if (storyBtn) storyBtn.disabled = true;
      showPostProgress(total);
      statusBox.className = "status warning";
      try {
        for (let i = 0; i < total; i++) {
          const product = selected[i];
          const shortTitle = (product.title || "").slice(0, 30);
          const hasVideo = Boolean(product.video_url || (product.video_urls || []).length);
          const hasImage = Boolean(product.image_url || (product.image_urls || []).length);
          if (!hasVideo && !hasImage) {
            allResults.push({ ok: false, title: product.title, error: "San pham chua co anh/video de dang tin" });
            updatePostProgress(i + 1, total, `Tin ${i + 1} thieu media`);
            continue;
          }
          updatePostProgress(i, total, `Dang tin ${i + 1}/${total}: ${shortTitle}`);
          statusBox.textContent = `Dang tin ${i + 1}/${total} (${hasVideo ? "video" : "anh"}) len Page...`;
          let payload;
          try {
            const res = await fetch("/affiliate_hot_tool/api/facebook-story-queue", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ products: [product] })
            });
            payload = await res.json();
          } catch (netErr) {
            allResults.push({ ok: false, title: product.title, error: netErr.message });
            updatePostProgress(i + 1, total, `Loi mang o tin ${i + 1}/${total}`);
            continue;
          }
          const r = (payload.results || [])[0] || {
            ok: !!payload.ok,
            title: product.title,
            error: payload.error || (payload.ok ? null : "Khong dang duoc tin")
          };
          allResults.push(r);
          updatePostProgress(i + 1, total, r.ok ? `Da dang tin ${i + 1}/${total}` : `Tin ${i + 1} loi`);
          if (i < total - 1) {
            for (let s = 20; s >= 1; s--) {
              statusBox.textContent = `Da xu ly ${i + 1}/${total} tin. Cho ${s}s truoc khi dang tin tiep theo...`;
              await sleep(1000);
            }
          }
        }
        const okCount = allResults.filter(r => r.ok).length;
        const failed = allResults.filter(r => !r.ok);
        const warnings = allResults.flatMap(r => r.warnings || []);
        updatePostProgress(total, total, okCount === total ? "Hoan tat dang tin" : `Xong, ${okCount}/${total} tin thanh cong`);
        if (okCount === total) {
          statusBox.className = warnings.length ? "status warning" : "status";
          statusBox.textContent = `Da dang ${okCount}/${total} tin anh/video.` + (warnings.length ? " Luu y: " + warnings.slice(0, 2).join(" ") : "");
        } else if (okCount > 0) {
          statusBox.className = "status warning";
          statusBox.textContent = `Da dang ${okCount}/${total} tin. Tin loi: ` +
            failed.map(r => `${(r.title || "").slice(0, 30)} (${r.error})`).join("; ");
        } else {
          statusBox.className = "status error";
          statusBox.textContent = "Khong dang duoc tin nao: " +
            failed.map(r => `${(r.title || "").slice(0, 30)} (${r.error})`).join("; ");
        }
      } finally {
        if (storyBtn) storyBtn.disabled = false;
        hidePostProgress();
      }
    }

    async function postSelectedFourPhotosViaGraph(selected, photoBtn) {
      const total = selected.length;
      const allResults = [];
      if (photoBtn) photoBtn.disabled = true;
      showPostProgress(total);
      statusBox.className = "status warning";
      try {
        for (let i = 0; i < total; i++) {
          const product = selected[i];
          const shortTitle = (product.title || "").slice(0, 30);
          const hasImage = Boolean(product.image_url || (product.image_urls || []).length);
          if (!hasImage) {
            allResults.push({ ok: false, title: product.title, error: "San pham chua co anh de dang bai 4 anh" });
            updatePostProgress(i + 1, total, `Bai 4 anh ${i + 1} thieu anh`);
            continue;
          }
          updatePostProgress(i, total, `Dang bai 4 anh ${i + 1}/${total}: ${shortTitle}`);
          statusBox.textContent = `Dang bai 4 anh ${i + 1}/${total} len Page...`;
          let payload;
          try {
            const res = await fetch("/affiliate_hot_tool/api/facebook-four-photo-queue", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ products: [product] })
            });
            payload = await res.json();
          } catch (netErr) {
            allResults.push({ ok: false, title: product.title, error: netErr.message });
            updatePostProgress(i + 1, total, `Loi mang o bai 4 anh ${i + 1}/${total}`);
            continue;
          }
          const r = (payload.results || [])[0] || {
            ok: !!payload.ok,
            title: product.title,
            error: payload.error || (payload.ok ? null : "Khong dang duoc bai 4 anh")
          };
          allResults.push(r);
          updatePostProgress(i + 1, total, r.ok ? `Da dang bai 4 anh ${i + 1}/${total}` : `Bai 4 anh ${i + 1} loi`);
          if (i < total - 1) {
            for (let s = 20; s >= 1; s--) {
              statusBox.textContent = `Da xu ly ${i + 1}/${total} bai 4 anh. Cho ${s}s truoc khi dang tiep...`;
              await sleep(1000);
            }
          }
        }
        const okCount = allResults.filter(r => r.ok).length;
        const failed = allResults.filter(r => !r.ok);
        const warnings = allResults.flatMap(r => r.warnings || []);
        updatePostProgress(total, total, okCount === total ? "Hoan tat dang bai 4 anh" : `Xong, ${okCount}/${total} bai 4 anh thanh cong`);
        if (okCount === total) {
          statusBox.className = warnings.length ? "status warning" : "status";
          statusBox.textContent = `Da dang ${okCount}/${total} bai 4 anh.` + (warnings.length ? " Luu y: " + warnings.slice(0, 3).join(" ") : "");
        } else if (okCount > 0) {
          statusBox.className = "status warning";
          statusBox.textContent = `Da dang ${okCount}/${total} bai 4 anh. Bai loi: ` +
            failed.map(r => `${(r.title || "").slice(0, 30)} (${r.error})`).join("; ");
        } else {
          statusBox.className = "status error";
          statusBox.textContent = "Khong dang duoc bai 4 anh nao: " +
            failed.map(r => `${(r.title || "").slice(0, 30)} (${r.error})`).join("; ");
        }
      } finally {
        if (photoBtn) photoBtn.disabled = false;
        hidePostProgress();
      }
    }

    async function postSelectedReelsViaGraph(selected, reelBtn) {
      const total = selected.length;
      const allResults = [];
      if (reelBtn) reelBtn.disabled = true;
      showPostProgress(total);
      statusBox.className = "status warning";
      try {
        for (let i = 0; i < total; i++) {
          const product = selected[i];
          const shortTitle = (product.title || "").slice(0, 30);
          const hasVideo = Boolean(product.video_url || (product.video_urls || []).length);
          if (!hasVideo) {
            allResults.push({ ok: false, title: product.title, error: "San pham chua co video de dang thước phim" });
            updatePostProgress(i + 1, total, `Reels ${i + 1} thieu video`);
            continue;
          }
          updatePostProgress(i, total, `Dang thước phim ${i + 1}/${total}: ${shortTitle}`);
          statusBox.textContent = `Dang thước phim ${i + 1}/${total} len Page...`;
          let payload;
          try {
            const res = await fetch("/affiliate_hot_tool/api/facebook-reel-queue", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ products: [product] })
            });
            payload = await res.json();
          } catch (netErr) {
            allResults.push({ ok: false, title: product.title, error: netErr.message });
            updatePostProgress(i + 1, total, `Loi mang o Reels ${i + 1}/${total}`);
            continue;
          }
          const r = (payload.results || [])[0] || {
            ok: !!payload.ok,
            title: product.title,
            error: payload.error || (payload.ok ? null : "Khong dang duoc thước phim")
          };
          allResults.push(r);
          updatePostProgress(i + 1, total, r.ok ? `Da dang Reels ${i + 1}/${total}` : `Reels ${i + 1} loi`);
          if (i < total - 1) {
            for (let s = 20; s >= 1; s--) {
              statusBox.textContent = `Da xu ly ${i + 1}/${total} thước phim. Cho ${s}s truoc khi dang tiep...`;
              await sleep(1000);
            }
          }
        }
        const okCount = allResults.filter(r => r.ok).length;
        const failed = allResults.filter(r => !r.ok);
        const warnings = allResults.flatMap(r => r.warnings || []);
        updatePostProgress(total, total, okCount === total ? "Hoan tat dang Reels" : `Xong, ${okCount}/${total} Reels thanh cong`);
        if (okCount === total) {
          statusBox.className = warnings.length ? "status warning" : "status";
          statusBox.textContent = `Da dang ${okCount}/${total} thước phim.` + (warnings.length ? " Luu y: " + warnings.slice(0, 2).join(" ") : "");
        } else if (okCount > 0) {
          statusBox.className = "status warning";
          statusBox.textContent = `Da dang ${okCount}/${total} thước phim. Reels loi: ` +
            failed.map(r => `${(r.title || "").slice(0, 30)} (${r.error})`).join("; ");
        } else {
          statusBox.className = "status error";
          statusBox.textContent = "Khong dang duoc thước phim nao: " +
            failed.map(r => `${(r.title || "").slice(0, 30)} (${r.error})`).join("; ");
        }
      } finally {
        if (reelBtn) reelBtn.disabled = false;
        hidePostProgress();
      }
    }

    async function prepareFacebookQueue() {
      statusBox.className = "status";
      const pageUrl = form.facebook_page_url.value.trim();
      const selected = Array.from(document.querySelectorAll(".pick-product:checked"))
        .map(input => currentItems[Number(input.dataset.index)])
        .filter(Boolean);
      if (!selected.length) {
        statusBox.className = "status error";
        statusBox.textContent = "Hay tick it nhat mot san pham truoc khi chuan bi dang Fanpage.";
        return;
      }
      if (selected.length > 5) {
        statusBox.className = "status error";
        statusBox.textContent = "Moi lan chi duoc tick toi da 5 san pham de dang Fanpage.";
        return;
      }
      const postBtn = document.getElementById("facebookBtn");
      try {
        if (graphReady) {
          await postSelectedViaGraph(selected, pageUrl, postBtn);
          return;
        }
        const res = await fetch("/affiliate_hot_tool/api/facebook-queue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ page_url: pageUrl, products: selected })
        });
        const payload = await res.json();
        if (!res.ok || (payload.error && !payload.posted_via_graph)) {
          const failed = (payload.results || []).filter(item => !item.ok);
          const details = failed.map(item => item.error || item.title).join("; ");
          throw new Error(payload.error || details || "Khong tao duoc hang doi Facebook");
        }
        if (payload.posted_via_graph) {
          const failed = (payload.results || []).filter(item => !item.ok);
          statusBox.className = failed.length ? (payload.ok_count ? "status warning" : "status error") : "status";
          statusBox.textContent = payload.message || `Da dang ${payload.count} bai len fanpage qua Meta Graph API.`;
          return;
        }
        if (!pageUrl) {
          throw new Error("Chua cau hinh Graph API thi can nhap Facebook fanpage URL de fallback automation.");
        }
        const first = payload.queue && payload.queue[0];
        const autoPost = form.facebook_auto_post.checked;
        if (extensionReady) {
          statusBox.className = "status warning";
          statusBox.textContent = autoPost
            ? "Dang gui hang doi sang Facebook va se tu bam Dang..."
            : "Dang mo fanpage va dien bai dau tien vao khung tao bai...";
          const fbResult = await runFacebookPostQueue(payload.queue || [], pageUrl, autoPost);
          const failed = (fbResult.results || []).filter(item => !item.ok);
          if (failed.length) {
            throw new Error("Facebook automation loi: " + failed.map(item => item.error || item.title).join("; "));
          }
          statusBox.className = autoPost ? "status warning" : "status";
          statusBox.textContent = autoPost
            ? `Da gui ${fbResult.results.length} bai sang Facebook. Hay kiem tra page de chac chan bai da len dung noi.`
            : "Da dien bai dau tien vao fanpage. Kiem tra noi dung roi bam Dang; sau do quay lai chon bai tiep theo neu can.";
          return;
        }
        if (first && navigator.clipboard) await navigator.clipboard.writeText(first.post);
        if (first) window.open(first.page_url, "_blank", "noopener,noreferrer");
        statusBox.className = "status warning";
        statusBox.textContent = `Da tao ${payload.count} bai theo thu tu da tick. Da copy bai dau tien va mo fanpage; hay kiem tra dung fanpage truoc khi bam Dang.`;
      } catch (err) {
        statusBox.className = "status error";
        statusBox.textContent = err.message;
      }
    }

    async function prepareFacebookStoryQueue() {
      statusBox.className = "status";
      const selected = Array.from(document.querySelectorAll(".pick-product:checked"))
        .map(input => currentItems[Number(input.dataset.index)])
        .filter(Boolean);
      if (!selected.length) {
        statusBox.className = "status error";
        statusBox.textContent = "Hay tick it nhat mot san pham truoc khi dang tin.";
        return;
      }
      if (selected.length > 5) {
        statusBox.className = "status error";
        statusBox.textContent = "Moi lan chi duoc tick toi da 5 san pham de dang tin.";
        return;
      }
      if (!graphReady) {
        statusBox.className = "status error";
        statusBox.textContent = "Can ket noi Facebook Graph API truoc khi dang tin Anh/Video.";
        return;
      }
      const missingMedia = selected.filter(item => !(item.video_url || (item.video_urls || []).length || item.image_url || (item.image_urls || []).length));
      if (missingMedia.length) {
        statusBox.className = "status error";
        statusBox.textContent = "Mot so san pham chua co anh/video. Hay bam Kiem tra san pham HOT lai sau khi da co phien Shopee.";
        return;
      }
      await postSelectedStoriesViaGraph(selected, document.getElementById("facebookStoryBtn"));
    }

    async function prepareFacebookFourPhotoQueue() {
      statusBox.className = "status";
      const selected = Array.from(document.querySelectorAll(".pick-product:checked"))
        .map(input => currentItems[Number(input.dataset.index)])
        .filter(Boolean);
      if (!selected.length) {
        statusBox.className = "status error";
        statusBox.textContent = "Hay tick it nhat mot san pham truoc khi dang bai 4 anh.";
        return;
      }
      if (selected.length > 5) {
        statusBox.className = "status error";
        statusBox.textContent = "Moi lan chi duoc tick toi da 5 san pham de dang bai 4 anh.";
        return;
      }
      if (!graphReady) {
        statusBox.className = "status error";
        statusBox.textContent = "Can ket noi Facebook Graph API truoc khi dang bai 4 anh.";
        return;
      }
      const missingImage = selected.filter(item => !(item.image_url || (item.image_urls || []).length));
      if (missingImage.length) {
        statusBox.className = "status error";
        statusBox.textContent = "Dang bai 4 anh chi nhan san pham co anh. San pham thieu anh: " +
          missingImage.map(item => (item.title || "").slice(0, 35)).join("; ");
        return;
      }
      await postSelectedFourPhotosViaGraph(selected, document.getElementById("facebookFourPhotoBtn"));
    }

    async function prepareFacebookReelQueue() {
      statusBox.className = "status";
      const selected = Array.from(document.querySelectorAll(".pick-product:checked"))
        .map(input => currentItems[Number(input.dataset.index)])
        .filter(Boolean);
      if (!selected.length) {
        statusBox.className = "status error";
        statusBox.textContent = "Hay tick it nhat mot san pham truoc khi dang thước phim.";
        return;
      }
      if (selected.length > 5) {
        statusBox.className = "status error";
        statusBox.textContent = "Moi lan chi duoc tick toi da 5 san pham de dang thước phim.";
        return;
      }
      if (!graphReady) {
        statusBox.className = "status error";
        statusBox.textContent = "Can ket noi Facebook Graph API truoc khi dang thước phim.";
        return;
      }
      const missingVideo = selected.filter(item => !(item.video_url || (item.video_urls || []).length));
      if (missingVideo.length) {
        statusBox.className = "status error";
        statusBox.textContent = "Dang thước phim chi nhan san pham co video. San pham thieu video: " +
          missingVideo.map(item => (item.title || "").slice(0, 35)).join("; ");
        return;
      }
      await postSelectedReelsViaGraph(selected, document.getElementById("facebookReelBtn"));
    }

    function runFacebookPostQueue(queue, pageUrl, autoPost) {
      return new Promise((resolve, reject) => {
        const requestId = "aht-facebook-" + Date.now() + "-" + Math.random().toString(16).slice(2);
        const timer = setTimeout(() => {
          window.removeEventListener("message", onMessage);
          reject(new Error("Facebook automation timeout."));
        }, Math.max(60000, queue.length * 20000));
        function onMessage(event) {
          if (event.source !== window || !event.data || event.data.type !== "AHT_FACEBOOK_POST_QUEUE_TO_PAGE") return;
          if (event.data.requestId !== requestId) return;
          clearTimeout(timer);
          window.removeEventListener("message", onMessage);
          const response = event.data.response || {};
          if (!response.ok) reject(new Error(response.error || "Facebook automation loi"));
          else resolve(response.payload || { results: [] });
        }
        window.addEventListener("message", onMessage);
        window.postMessage({
          type: "AHT_FACEBOOK_POST_QUEUE_FROM_PAGE",
          requestId,
          payload: { queue, pageUrl, autoPost }
        }, "*");
      });
    }

    function escapeHtml(value) {
      return String(value || "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function escapeAttr(value) {
      return escapeHtml(value || "");
    }
    function mediaPreview(item) {
      const imageCount = [item.image_url, ...(item.image_urls || [])].filter(Boolean).length;
      const videoCount = [item.video_url, ...(item.video_urls || [])].filter(Boolean).length;
      if (item.video_url) {
        return `<video class="thumb" src="${escapeAttr(item.video_url)}" controls muted preload="metadata"></video><div class="media-note">${videoCount} video, ${imageCount} anh</div>`;
      }
      if (item.image_url) {
        return `<img class="thumb" src="${escapeAttr(item.image_url)}" alt="" referrerpolicy="no-referrer" loading="lazy" onerror="this.style.display='none'"><div class="media-note">${imageCount} anh</div>`;
      }
      return '<span class="hint">Chua co media</span>';
    }
  </script>
</body>
</html>"""
