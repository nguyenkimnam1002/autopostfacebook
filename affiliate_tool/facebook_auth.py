from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import get_env


AUTH_FILE = Path("data/facebook_auth.json")
STATE_FILE = Path("data/facebook_oauth_state.json")
SCOPES = ("pages_show_list", "pages_read_engagement", "pages_manage_posts", "pages_manage_engagement")

# Cac quyen bat buoc de dang bai + comment len Page.
REQUIRED_SCOPES = SCOPES
SCOPE_LABELS = {
    "pages_show_list": "Xem danh sach Page",
    "pages_read_engagement": "Doc tuong tac Page",
    "pages_manage_posts": "Dang bai len Page",
    "pages_manage_engagement": "Binh luan / tra loi tren Page",
}


class FacebookAuthError(RuntimeError):
    pass


@dataclass
class StoredPageAuth:
    page_id: str
    page_name: str
    page_access_token: str
    user_access_token: str | None = None
    user_expires_at: int | None = None


def app_configured() -> bool:
    return bool(get_env("FACEBOOK_APP_ID") and get_env("FACEBOOK_APP_SECRET"))


def load_page_auth() -> StoredPageAuth | None:
    if not AUTH_FILE.exists():
        return None
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    page_token = str(data.get("page_access_token") or "")
    page_id = str(data.get("page_id") or "")
    if not page_token or not page_id:
        return None
    return StoredPageAuth(
        page_id=page_id,
        page_name=str(data.get("page_name") or page_id),
        page_access_token=page_token,
        user_access_token=data.get("user_access_token"),
        user_expires_at=data.get("user_expires_at"),
    )


def create_login_url(redirect_uri: str) -> str:
    app_id = _required_env("FACEBOOK_APP_ID")
    state = secrets.token_urlsafe(24)
    _write_json(STATE_FILE, {"state": state, "redirect_uri": redirect_uri, "created_at": int(time.time())})
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "auth_type": "rerequest",
    }
    config_id = get_env("FACEBOOK_LOGIN_CONFIG_ID")
    if config_id:
        params["config_id"] = config_id
        params["override_default_response_type"] = "true"
    else:
        params["scope"] = ",".join(SCOPES)
    return f"https://www.facebook.com/{_version()}/dialog/oauth?{urllib.parse.urlencode(params)}"


def complete_login(query: dict[str, list[str]], redirect_uri: str) -> StoredPageAuth:
    if "error" in query:
        raise FacebookAuthError(query.get("error_description", query["error"])[0])
    code = _first(query, "code")
    state = _first(query, "state")
    if not code:
        raise FacebookAuthError("Facebook callback khong co code.")
    _validate_state(state, redirect_uri)

    try:
        short_user = _exchange_code_for_user_token(code, redirect_uri)
    except FacebookAuthError as exc:
        _write_oauth_error("exchange_code", str(exc))
        raise FacebookAuthError(f"Loi doi OAuth code sang user token: {exc}") from exc
    try:
        long_user = _exchange_for_long_lived_user_token(short_user["access_token"])
    except FacebookAuthError as exc:
        _write_oauth_error("exchange_long_lived", str(exc))
        raise FacebookAuthError(f"Loi doi sang long-lived token: {exc}") from exc
    user_token = str(long_user["access_token"])
    expires_in = int(long_user.get("expires_in") or 0)
    try:
        pages = _get_pages(user_token)
        page = _pick_page(pages)
    except FacebookAuthError as exc:
        _write_oauth_error("get_pages", str(exc))
        raise FacebookAuthError(f"Loi lay Page token: {exc}") from exc

    auth = {
        "page_id": str(page["id"]),
        "page_name": str(page.get("name") or page["id"]),
        "page_access_token": str(page["access_token"]),
        "user_access_token": user_token,
        "user_expires_at": int(time.time()) + expires_in if expires_in else None,
        "obtained_at": int(time.time()),
    }
    _write_json(AUTH_FILE, auth)
    try:
        STATE_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return load_page_auth() or StoredPageAuth(
        page_id=auth["page_id"],
        page_name=auth["page_name"],
        page_access_token=auth["page_access_token"],
        user_access_token=auth["user_access_token"],
        user_expires_at=auth["user_expires_at"],
    )


def exchange_user_token_to_page_auth(user_token: str) -> StoredPageAuth:
    """Turn a (short-lived) Facebook USER token into a long-lived Page token and persist it.

    Page tokens derived from a long-lived user token do not expire as long as the
    user keeps the app authorized, which removes the recurring "token het han" problem.
    """
    token = (user_token or "").strip()
    if not token:
        raise FacebookAuthError("Chua nhap token. Hay dan User Token tu Graph API Explorer.")
    if not app_configured():
        raise FacebookAuthError("Thieu FACEBOOK_APP_ID hoac FACEBOOK_APP_SECRET trong .env.")

    expires_in = 0
    try:
        long_user = _exchange_for_long_lived_user_token(token)
        token = str(long_user.get("access_token") or token)
        expires_in = int(long_user.get("expires_in") or 0)
    except FacebookAuthError:
        # Already long-lived, or not exchangeable; keep using it to read pages.
        pass

    pages = _get_pages(token)
    page = _pick_page(pages)
    auth = {
        "page_id": str(page["id"]),
        "page_name": str(page.get("name") or page["id"]),
        "page_access_token": str(page["access_token"]),
        "user_access_token": token,
        "user_expires_at": int(time.time()) + expires_in if expires_in else None,
        "obtained_at": int(time.time()),
    }
    _write_json(AUTH_FILE, auth)
    return load_page_auth() or StoredPageAuth(
        page_id=auth["page_id"],
        page_name=auth["page_name"],
        page_access_token=auth["page_access_token"],
        user_access_token=auth["user_access_token"],
        user_expires_at=auth["user_expires_at"],
    )


def inspect_token(token: str) -> dict:
    """Hoi Facebook xem token co hop le va co nhung quyen (scope) nao.

    Tra ve dict: {is_valid, scopes, granted_required, missing_required, expires_at}.
    """
    token = (token or "").strip()
    if not token:
        raise FacebookAuthError("Chua nhap token de kiem tra.")
    if not app_configured():
        raise FacebookAuthError("Thieu FACEBOOK_APP_ID hoac FACEBOOK_APP_SECRET trong .env.")
    app_token = f"{_required_env('FACEBOOK_APP_ID')}|{_required_env('FACEBOOK_APP_SECRET')}"
    payload = _get_json(
        f"https://graph.facebook.com/{_version()}/debug_token",
        {"input_token": token, "access_token": app_token},
    )
    data = payload.get("data") or {}
    scopes = [str(s) for s in (data.get("scopes") or [])]
    granted = [s for s in REQUIRED_SCOPES if s in scopes]
    missing = [s for s in REQUIRED_SCOPES if s not in scopes]
    return {
        "is_valid": bool(data.get("is_valid")),
        "scopes": scopes,
        "granted_required": granted,
        "missing_required": missing,
        "expires_at": int(data.get("expires_at") or 0),
    }


def _exchange_code_for_user_token(code: str, redirect_uri: str) -> dict:
    return _get_json(
        f"https://graph.facebook.com/{_version()}/oauth/access_token",
        {
            "client_id": _required_env("FACEBOOK_APP_ID"),
            "client_secret": _required_env("FACEBOOK_APP_SECRET"),
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )


def _exchange_for_long_lived_user_token(short_token: str) -> dict:
    return _get_json(
        f"https://graph.facebook.com/{_version()}/oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": _required_env("FACEBOOK_APP_ID"),
            "client_secret": _required_env("FACEBOOK_APP_SECRET"),
            "fb_exchange_token": short_token,
        },
    )


def _get_pages(user_token: str) -> list[dict]:
    payload = _get_json(
        f"https://graph.facebook.com/{_version()}/me/accounts",
        {
            "fields": "id,name,access_token",
            "access_token": user_token,
        },
    )
    pages = payload.get("data") or []
    if not pages:
        raise FacebookAuthError("Tai khoan Facebook nay khong tra ve Page nao co quyen quan ly.")
    return pages


def _pick_page(pages: list[dict]) -> dict:
    preferred_id = get_env("FACEBOOK_PAGE_ID")
    if preferred_id:
        for page in pages:
            if str(page.get("id")) == str(preferred_id):
                if page.get("access_token"):
                    return page
                break
        raise FacebookAuthError("Khong tim thay Page ID trong danh sach Page cua tai khoan vua ket noi.")
    for page in pages:
        if page.get("access_token"):
            return page
    raise FacebookAuthError("Facebook khong tra ve Page access token.")


def _validate_state(state: str | None, redirect_uri: str) -> None:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FacebookAuthError("Khong tim thay OAuth state. Hay bam Ket noi Facebook lai.") from exc
    if not state or state != data.get("state") or redirect_uri != data.get("redirect_uri"):
        raise FacebookAuthError("OAuth state khong hop le. Hay bam Ket noi Facebook lai.")
    if int(time.time()) - int(data.get("created_at") or 0) > 900:
        raise FacebookAuthError("OAuth state da het han. Hay bam Ket noi Facebook lai.")


def _get_json(url: str, params: dict[str, str]) -> dict:
    request_url = f"{url}?{urllib.parse.urlencode(params)}"
    last_network_error: urllib.error.URLError | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request_url, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FacebookAuthError(_friendly_error(detail)) from exc
        except urllib.error.URLError as exc:
            last_network_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise FacebookAuthError(f"Network error sau 3 lan thu: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise FacebookAuthError(f"Facebook tra ve response khong phai JSON: {exc}") from exc
    raise FacebookAuthError(f"Network error: {last_network_error}")


def _friendly_error(detail: str) -> str:
    try:
        payload = json.loads(detail)
        message = (payload.get("error") or {}).get("message")
        return str(message or detail)
    except json.JSONDecodeError:
        return detail[:500]


def _version() -> str:
    return get_env("META_GRAPH_VERSION", "v25.0") or "v25.0"


def _required_env(name: str) -> str:
    value = get_env(name)
    if not value:
        raise FacebookAuthError(f"Thieu {name} trong .env.")
    return value


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_oauth_error(stage: str, message: str) -> None:
    _write_json(
        Path("data/facebook_oauth_error.json"),
        {
            "stage": stage,
            "message": message,
            "created_at": int(time.time()),
        },
    )


def _first(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    return values[0] if values else None
