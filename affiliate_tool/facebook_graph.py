from __future__ import annotations

import json
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .facebook_auth import load_page_auth
from .config import get_env
from .models import Product
from .posting import build_facebook_post, build_facebook_reel_title


class FacebookGraphError(RuntimeError):
    pass


# Delay between consecutive posts to avoid Facebook's burst/spam detection.
_POST_INTERVAL_SECONDS = 25


@dataclass
class FacebookPostResult:
    product_id: str | None
    title: str
    ok: bool
    post_id: str | None = None
    object_id: str | None = None
    media_type: str | None = None
    comment_count: int = 0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def graph_configured() -> bool:
    return bool(load_page_auth() or (get_env("FACEBOOK_PAGE_ID") and get_env("FACEBOOK_PAGE_ACCESS_TOKEN")))


def publish_products_to_page(items: list[tuple[Product, str | None]]) -> list[FacebookPostResult]:
    stored_auth = load_page_auth()
    page_id = stored_auth.page_id if stored_auth else get_env("FACEBOOK_PAGE_ID")
    token = stored_auth.page_access_token if stored_auth else get_env("FACEBOOK_PAGE_ACCESS_TOKEN")
    version = get_env("META_GRAPH_VERSION", "v25.0") or "v25.0"
    if not page_id or not token:
        raise FacebookGraphError("Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN.")

    results: list[FacebookPostResult] = []
    for index, (product, post_text) in enumerate(items):
        if index > 0:
            # Space out posts so Facebook does not treat a quick burst as spam.
            time.sleep(_POST_INTERVAL_SECONDS)
        try:
            result = _publish_one(
                version=version,
                page_id=page_id,
                page_token=token,
                product=product,
                message=post_text or build_facebook_post(product, ["sản phẩm được chọn từ file link hàng loạt"]),
            )
            results.append(
                FacebookPostResult(
                    product_id=product.product_id,
                    title=product.title,
                    ok=result["ok"],
                    post_id=result.get("post_id"),
                    object_id=result.get("object_id"),
                    media_type=result.get("media_type"),
                    comment_count=int(result.get("comment_count") or 0),
                    warnings=list(result.get("warnings") or []),
                    error=result.get("error"),
                )
            )
        except FacebookGraphError as exc:
            results.append(
                FacebookPostResult(
                    product_id=product.product_id,
                    title=product.title,
                    ok=False,
                    error=str(exc),
                )
            )
    return results


def publish_stories_to_page(products: list[Product]) -> list[FacebookPostResult]:
    stored_auth = load_page_auth()
    page_id = stored_auth.page_id if stored_auth else get_env("FACEBOOK_PAGE_ID")
    token = stored_auth.page_access_token if stored_auth else get_env("FACEBOOK_PAGE_ACCESS_TOKEN")
    version = get_env("META_GRAPH_VERSION", "v25.0") or "v25.0"
    if not page_id or not token:
        raise FacebookGraphError("Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN.")

    results: list[FacebookPostResult] = []
    for index, product in enumerate(products):
        if index > 0:
            time.sleep(_POST_INTERVAL_SECONDS)
        try:
            result = _publish_story_one(version, page_id, token, product)
            results.append(
                FacebookPostResult(
                    product_id=product.product_id,
                    title=product.title,
                    ok=result["ok"],
                    post_id=result.get("post_id"),
                    object_id=result.get("object_id"),
                    media_type=result.get("media_type"),
                    warnings=list(result.get("warnings") or []),
                    error=result.get("error"),
                )
            )
        except FacebookGraphError as exc:
            results.append(
                FacebookPostResult(
                    product_id=product.product_id,
                    title=product.title,
                    ok=False,
                    error=str(exc),
                )
            )
    return results


def publish_reels_to_page(products: list[Product]) -> list[FacebookPostResult]:
    stored_auth = load_page_auth()
    page_id = stored_auth.page_id if stored_auth else get_env("FACEBOOK_PAGE_ID")
    token = stored_auth.page_access_token if stored_auth else get_env("FACEBOOK_PAGE_ACCESS_TOKEN")
    version = get_env("META_GRAPH_VERSION", "v25.0") or "v25.0"
    if not page_id or not token:
        raise FacebookGraphError("Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN.")

    results: list[FacebookPostResult] = []
    for index, product in enumerate(products):
        if index > 0:
            time.sleep(_POST_INTERVAL_SECONDS)
        try:
            result = _publish_reel_one(version, page_id, token, product)
            results.append(
                FacebookPostResult(
                    product_id=product.product_id,
                    title=product.title,
                    ok=result["ok"],
                    post_id=result.get("post_id"),
                    object_id=result.get("object_id"),
                    media_type=result.get("media_type"),
                    warnings=list(result.get("warnings") or []),
                    error=result.get("error"),
                )
            )
        except FacebookGraphError as exc:
            results.append(
                FacebookPostResult(
                    product_id=product.product_id,
                    title=product.title,
                    ok=False,
                    error=str(exc),
                )
            )
    return results


def publish_four_photos_to_page(items: list[tuple[Product, str | None]]) -> list[FacebookPostResult]:
    stored_auth = load_page_auth()
    page_id = stored_auth.page_id if stored_auth else get_env("FACEBOOK_PAGE_ID")
    token = stored_auth.page_access_token if stored_auth else get_env("FACEBOOK_PAGE_ACCESS_TOKEN")
    version = get_env("META_GRAPH_VERSION", "v25.0") or "v25.0"
    if not page_id or not token:
        raise FacebookGraphError("Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN.")

    results: list[FacebookPostResult] = []
    for index, (product, post_text) in enumerate(items):
        if index > 0:
            time.sleep(_POST_INTERVAL_SECONDS)
        try:
            result = _publish_four_photo_post(
                version=version,
                page_id=page_id,
                page_token=token,
                product=product,
                message=post_text or build_facebook_post(product, ["sản phẩm được chọn từ file link hàng loạt"]),
            )
            results.append(
                FacebookPostResult(
                    product_id=product.product_id,
                    title=product.title,
                    ok=result["ok"],
                    post_id=result.get("post_id"),
                    object_id=result.get("object_id"),
                    media_type=result.get("media_type"),
                    comment_count=int(result.get("comment_count") or 0),
                    warnings=list(result.get("warnings") or []),
                    error=result.get("error"),
                )
            )
        except FacebookGraphError as exc:
            results.append(
                FacebookPostResult(
                    product_id=product.product_id,
                    title=product.title,
                    ok=False,
                    error=str(exc),
                )
            )
    return results


def _publish_one(
    version: str,
    page_id: str,
    page_token: str,
    product: Product,
    message: str,
) -> dict:
    video_urls = _unique_urls([product.video_url, *product.video_urls])
    image_urls = _unique_urls([product.image_url, *product.image_urls])

    if video_urls:
        try:
            return _publish_video_post(version, page_id, page_token, message, video_urls[0], image_urls, product.url)
        except FacebookGraphError as exc:
            fallback_warning = f"Video bị Facebook từ chối, đã fallback sang ảnh/link: {exc}"
            if image_urls:
                result = _publish_photo_post(version, page_id, page_token, message, image_urls, product.url)
            else:
                result = _publish_feed_post(version, page_id, page_token, message, product.url)
            result["warnings"] = [fallback_warning, *result.get("warnings", [])]
            return result

    if image_urls:
        try:
            return _publish_photo_post(version, page_id, page_token, message, image_urls, product.url)
        except FacebookGraphError as exc:
            result = _publish_feed_post(version, page_id, page_token, message, product.url)
            result["warnings"] = [f"Ảnh bị Facebook từ chối, đã fallback sang link: {exc}", *result.get("warnings", [])]
            return result

    return _publish_feed_post(version, page_id, page_token, message, product.url)


def _publish_story_one(version: str, page_id: str, page_token: str, product: Product) -> dict:
    video_urls = _unique_urls([product.video_url, *product.video_urls])
    image_urls = _unique_urls([product.image_url, *product.image_urls])
    if video_urls:
        return _publish_video_story(version, page_id, page_token, video_urls[0], product.url)
    if image_urls:
        return _publish_photo_story(version, page_id, page_token, image_urls[0], product.url)
    raise FacebookGraphError("San pham chua co anh/video de dang tin.")


def _publish_reel_one(version: str, page_id: str, page_token: str, product: Product) -> dict:
    video_urls = _unique_urls([product.video_url, *product.video_urls])
    if not video_urls:
        raise FacebookGraphError("San pham chua co video de dang Reels.")
    return _publish_video_reel(
        version=version,
        page_id=page_id,
        page_token=page_token,
        product=product,
        video_url=video_urls[0],
    )


def _publish_video_post(
    version: str,
    page_id: str,
    page_token: str,
    message: str,
    video_url: str,
    image_urls: list[str],
    affiliate_url: str,
) -> dict:
    payload = _post_form(
        f"https://graph.facebook.com/{version}/{page_id}/videos",
        {
            "description": message,
            "file_url": video_url,
            "published": "true",
            "access_token": page_token,
        },
    )
    post_id = payload.get("post_id")
    object_id = str(post_id or payload.get("id") or "")
    if not object_id:
        raise FacebookGraphError(f"Facebook video publish did not return id: {payload}")
    link_comment = _comment_affiliate_link(version, object_id, page_token, affiliate_url)
    comments = _comment_media(version, object_id, page_token, image_urls[:8])
    warnings = [*link_comment["warnings"], *comments["warnings"]]
    if not post_id:
        warnings.append("Facebook đã nhận video nhưng chưa trả post_id; video có thể cần xử lý thêm trước khi hiện trên feed.")
    return {
        "ok": True,
        "post_id": str(post_id) if post_id else None,
        "object_id": object_id,
        "media_type": "video",
        "comment_count": link_comment["count"] + comments["count"],
        "warnings": warnings,
    }


def _publish_video_reel(
    version: str,
    page_id: str,
    page_token: str,
    product: Product,
    video_url: str,
) -> dict:
    start_payload = _post_form(
        f"https://graph.facebook.com/{version}/{page_id}/video_reels",
        {
            "upload_phase": "start",
            "access_token": page_token,
        },
    )
    video_id = str(start_payload.get("video_id") or "")
    upload_url = str(start_payload.get("upload_url") or "")
    if not video_id or not upload_url:
        raise FacebookGraphError(f"Facebook Reels start did not return upload data: {start_payload}")

    upload_payload = _post_with_headers(
        upload_url,
        {
            "Authorization": f"OAuth {page_token}",
            "file_url": video_url,
        },
    )
    if upload_payload and upload_payload.get("success") is False:
        raise FacebookGraphError(f"Facebook Reels upload failed: {upload_payload}")

    finish_payload = _post_form(
        f"https://graph.facebook.com/{version}/{page_id}/video_reels",
        {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "title": build_facebook_reel_title(product),
            "description": build_facebook_post(product, ["video sản phẩm đang có tín hiệu đáng chú ý"]),
            "access_token": page_token,
        },
    )
    post_id = str(finish_payload.get("post_id") or finish_payload.get("id") or "")
    if not finish_payload.get("success") and not post_id:
        raise FacebookGraphError(f"Facebook Reels finish failed: {finish_payload}")
    warnings = []
    if not post_id:
        warnings.append("Facebook đã nhận Reels; video có thể cần xử lý thêm trước khi hiện trên Page.")
    return {
        "ok": True,
        "post_id": post_id or None,
        "object_id": post_id or video_id,
        "media_type": "reel",
        "warnings": warnings,
    }


def _publish_four_photo_post(
    version: str,
    page_id: str,
    page_token: str,
    product: Product,
    message: str,
) -> dict:
    image_urls = _unique_urls([product.image_url, *product.image_urls])
    video_urls = _unique_urls([product.video_url, *product.video_urls])
    if not image_urls:
        raise FacebookGraphError("San pham chua co anh de dang bai 4 anh.")

    primary_images = image_urls[:4]
    extra_images = image_urls[4:12]
    attached_media: list[str] = []
    warnings: list[str] = []
    for index, image_url in enumerate(primary_images, start=1):
        try:
            filename, content_type, file_bytes = _read_remote_bytes(image_url)
            upload_payload = _post_multipart(
                f"https://graph.facebook.com/{version}/{page_id}/photos",
                fields={
                    "published": "false",
                    "access_token": page_token,
                },
                file_field="source",
                filename=filename,
                file_bytes=file_bytes,
                content_type=content_type,
            )
        except FacebookGraphError as exc:
            raise FacebookGraphError(f"Khong tai len duoc anh dai dien {index}: {exc}") from exc
        media_fbid = str(upload_payload.get("id") or "")
        if not media_fbid:
            raise FacebookGraphError(f"Facebook khong tra ve media id cho anh dai dien {index}: {upload_payload}")
        attached_media.append(json.dumps({"media_fbid": media_fbid}, ensure_ascii=False))

    payload = _post_form(
        f"https://graph.facebook.com/{version}/{page_id}/feed",
        {
            "message": message,
            **{f"attached_media[{index}]": media for index, media in enumerate(attached_media)},
            "published": "true",
            "access_token": page_token,
        },
    )
    post_id = str(payload.get("id") or "")
    if not post_id:
        raise FacebookGraphError(f"Facebook album 4 anh did not return post id: {payload}")

    link_comment = _comment_affiliate_link(version, post_id, page_token, product.url)
    image_comments = _comment_media(version, post_id, page_token, extra_images)
    video_comments = _comment_video_links(version, post_id, page_token, video_urls)
    warnings.extend(link_comment["warnings"])
    warnings.extend(image_comments["warnings"])
    warnings.extend(video_comments["warnings"])
    if len(primary_images) < 4:
        warnings.append(f"San pham chi co {len(primary_images)} anh hop le, chua du 4 anh dai dien.")
    return {
        "ok": True,
        "post_id": post_id,
        "object_id": post_id,
        "media_type": "photo_multi",
        "comment_count": link_comment["count"] + image_comments["count"] + video_comments["count"],
        "warnings": warnings,
    }


def _publish_video_story(
    version: str,
    page_id: str,
    page_token: str,
    video_url: str,
    affiliate_url: str,
) -> dict:
    start_payload = _post_form(
        f"https://graph.facebook.com/{version}/{page_id}/video_stories",
        {
            "upload_phase": "start",
            "access_token": page_token,
        },
    )
    video_id = str(start_payload.get("video_id") or "")
    upload_url = str(start_payload.get("upload_url") or "")
    if not video_id or not upload_url:
        raise FacebookGraphError(f"Facebook story video start did not return upload data: {start_payload}")

    _post_with_headers(
        upload_url,
        {
            "Authorization": f"OAuth {page_token}",
            "file_url": video_url,
        },
    )
    finish_fields = {
        "upload_phase": "finish",
        "video_id": video_id,
        "access_token": page_token,
    }
    payload, warnings = _finish_story_with_optional_link(
        f"https://graph.facebook.com/{version}/{page_id}/video_stories",
        finish_fields,
        affiliate_url,
    )
    post_id = str(payload.get("post_id") or payload.get("id") or "")
    if not payload.get("success") and not post_id:
        raise FacebookGraphError(f"Facebook story video finish failed: {payload}")
    return {
        "ok": True,
        "post_id": post_id or None,
        "object_id": post_id or video_id,
        "media_type": "story_video",
        "warnings": warnings,
    }


def _publish_photo_story(
    version: str,
    page_id: str,
    page_token: str,
    image_url: str,
    affiliate_url: str,
) -> dict:
    photo_payload = _post_form(
        f"https://graph.facebook.com/{version}/{page_id}/photos",
        {
            "url": image_url,
            "published": "false",
            "access_token": page_token,
        },
    )
    photo_id = str(photo_payload.get("id") or "")
    if not photo_id:
        raise FacebookGraphError(f"Facebook story photo upload did not return id: {photo_payload}")
    story_fields = {
        "photo_id": photo_id,
        "access_token": page_token,
    }
    payload, warnings = _finish_story_with_optional_link(
        f"https://graph.facebook.com/{version}/{page_id}/photo_stories",
        story_fields,
        affiliate_url,
    )
    post_id = str(payload.get("post_id") or payload.get("id") or "")
    if not payload.get("success") and not post_id:
        raise FacebookGraphError(f"Facebook photo story publish failed: {payload}")
    return {
        "ok": True,
        "post_id": post_id or None,
        "object_id": post_id or photo_id,
        "media_type": "story_photo",
        "warnings": warnings,
    }


def _finish_story_with_optional_link(url: str, fields: dict[str, str], affiliate_url: str) -> tuple[dict, list[str]]:
    payload = _post_form(url, fields)
    warnings: list[str] = []
    if affiliate_url:
        warnings.append(
            "Meta Page Stories API hien chi publish media; khong co tham so chinh thuc de tao link sticker clickable. "
            f"Link uu dai cua san pham la: {affiliate_url}"
        )
    return payload, warnings


def _publish_photo_post(
    version: str,
    page_id: str,
    page_token: str,
    message: str,
    image_urls: list[str],
    affiliate_url: str,
) -> dict:
    payload = _post_form(
        f"https://graph.facebook.com/{version}/{page_id}/photos",
        {
            "caption": f"{message}\n\nLink sản phẩm: {affiliate_url}",
            "url": image_urls[0],
            "published": "true",
            "access_token": page_token,
        },
    )
    post_id = payload.get("post_id")
    object_id = str(post_id or payload.get("id") or "")
    if not object_id:
        raise FacebookGraphError(f"Facebook photo publish did not return id: {payload}")
    link_comment = _comment_affiliate_link(version, object_id, page_token, affiliate_url)
    comments = _comment_media(version, object_id, page_token, image_urls[1:9])
    return {
        "ok": True,
        "post_id": str(post_id) if post_id else None,
        "object_id": object_id,
        "media_type": "photo",
        "comment_count": link_comment["count"] + comments["count"],
        "warnings": [*link_comment["warnings"], *comments["warnings"]],
    }


def _publish_feed_post(version: str, page_id: str, page_token: str, message: str, affiliate_url: str) -> dict:
    payload = _post_form(
        f"https://graph.facebook.com/{version}/{page_id}/feed",
        {
            "message": message,
            "link": affiliate_url,
            "published": "true",
            "access_token": page_token,
        },
    )
    post_id = payload.get("id")
    if not post_id:
        raise FacebookGraphError(f"Facebook Graph did not return post id: {payload}")
    link_comment = _comment_affiliate_link(version, str(post_id), page_token, affiliate_url)
    return {
        "ok": True,
        "post_id": str(post_id),
        "object_id": str(post_id),
        "media_type": "link",
        "comment_count": link_comment["count"],
        "warnings": link_comment["warnings"],
    }


def _comment_affiliate_link(version: str, object_id: str, page_token: str, affiliate_url: str) -> dict:
    if not affiliate_url:
        return {"count": 0, "warnings": []}
    message = f"Mua hàng ngay tại đây 👇\n{affiliate_url}"
    try:
        _post_form(
            f"https://graph.facebook.com/{version}/{object_id}/comments",
            {
                "message": message,
                "access_token": page_token,
            },
        )
        return {"count": 1, "warnings": []}
    except FacebookGraphError as exc:
        return {"count": 0, "warnings": [f"Không comment được link mua hàng: {exc}"]}


def _comment_media(version: str, object_id: str, page_token: str, image_urls: list[str]) -> dict:
    count = 0
    warnings: list[str] = []
    for index, image_url in enumerate(image_urls, start=1):
        # if not _is_commentable_image(image_url):
        #     continue
        try:
            _post_form(
                f"https://graph.facebook.com/{version}/{object_id}/comments",
                {
                    "message": f"Ảnh sản phẩm {index}",
                    "attachment_url": image_url,
                    "access_token": page_token,
                },
            )
            count += 1
        except FacebookGraphError as attachment_exc:
            # Khong fallback sang comment link text (link rac). Chi bo qua anh loi.
            warnings.append(f"Không đính được ảnh {index}: {attachment_exc}")
    return {"count": count, "warnings": warnings}


def _comment_video_links(version: str, object_id: str, page_token: str, video_urls: list[str]) -> dict:
    count = 0
    warnings: list[str] = []
    for index, video_url in enumerate(video_urls, start=1):
        try:
            _post_form(
                f"https://graph.facebook.com/{version}/{object_id}/comments",
                {
                    "message": f"Video sản phẩm {index}: {video_url}",
                    "access_token": page_token,
                },
            )
            count += 1
        except FacebookGraphError as exc:
            warnings.append(f"Không comment được video {index}: {exc}")
    return {"count": count, "warnings": warnings}


def _is_commentable_image(url: str | None) -> bool:
    """Chi nhan anh san pham that tu Shopee CDN; loai link rac/anh la."""
    try:
        from .discovery import is_product_image

        return is_product_image(url)
    except Exception:
        if not url or not url.startswith("http"):
            return False
        lowered = url.split("?", 1)[0].lower()
        if lowered.endswith((".svg", "/null", "/undefined")):
            return False
        return True


def _post_form(url: str, fields: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FacebookGraphError(_friendly_graph_error(exc.code, detail)) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise FacebookGraphError(f"Facebook Graph error: {exc}") from exc


def _post_with_headers(url: str, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(url, data=b"", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FacebookGraphError(_friendly_graph_error(exc.code, detail)) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise FacebookGraphError(f"Facebook Graph upload error: {exc}") from exc


def _post_multipart(
    url: str,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> dict:
    boundary = "----AffiliateHotTool" + uuid.uuid4().hex
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FacebookGraphError(_friendly_graph_error(exc.code, detail)) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise FacebookGraphError(f"Facebook Graph multipart upload error: {exc}") from exc


def _read_remote_bytes(url: str) -> tuple[str, str, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "AffiliateHotTool/0.3"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = response.read()
            content_type = response.headers.get_content_type() or "application/octet-stream"
            filename = _filename_from_url(url, content_type)
            return filename, content_type, data
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FacebookGraphError(_friendly_graph_error(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise FacebookGraphError(f"Khong tai duoc anh nguon de upload len Facebook: {exc}") from exc


def _filename_from_url(url: str, content_type: str) -> str:
    path = urllib.parse.urlparse(url).path
    name = path.rsplit("/", 1)[-1] or "image"
    if "." not in name:
        ext = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(content_type, ".bin")
        name += ext
    return name


def _unique_urls(values: list[str | None]) -> list[str]:
    urls: list[str] = []
    for value in values:
        if value and value not in urls:
            urls.append(value)
    return urls


def _friendly_graph_error(status: int, detail: str) -> str:
    try:
        payload = json.loads(detail)
        error = payload.get("error") or {}
        code = error.get("code")
        subcode = error.get("error_subcode")
        message = error.get("message") or detail
        if code == 190 and subcode == 463:
            return (
                "Facebook Page Access Token da het han. Dan User Token moi vao o 'Token lau dai' "
                "roi bam 'Dung token lau dai' de tool tu tao Page token vinh vien."
            )
        if code == 190:
            return (
                "Facebook token khong hop le hoac da het han. Dan User Token moi vao o 'Token lau dai' "
                f"roi bam 'Dung token lau dai'. Chi tiet: {message}"
            )
        if code in {200, 10}:
            return (
                "Token thieu quyen 'pages_manage_engagement' (de page tu binh luan), hoac app chua duoc cap quyen. "
                "Vao Graph API Explorer, them quyen pages_manage_engagement, tao lai User Token roi dan vao o 'Token lau dai'. "
                f"Chi tiet: {message}"
            )
        return f"Facebook Graph HTTP {status}: {message}"
    except (json.JSONDecodeError, TypeError):
        return f"Facebook Graph HTTP {status}: {detail[:500]}"
