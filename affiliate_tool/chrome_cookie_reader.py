from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import sqlite3
import tempfile
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


class ChromeCookieError(RuntimeError):
    pass


@dataclass
class CookieProfile:
    browser: str
    profile: str
    cookie: str
    count: int


def find_shopee_cookie_from_browsers() -> CookieProfile:
    profiles = list(_iter_cookie_profiles())
    if not profiles:
        raise ChromeCookieError("Khong tim thay cookie Shopee/Affiliate trong Chrome/Edge profile nao.")
    profiles.sort(key=lambda item: (_score_cookie(item.cookie), item.count), reverse=True)
    return profiles[0]


def _iter_cookie_profiles():
    for browser, user_data in _candidate_user_data_dirs():
        local_state = user_data / "Local State"
        if not local_state.exists():
            continue
        try:
            master_key = _get_master_key(local_state)
        except ChromeCookieError:
            continue
        for cookie_db in user_data.glob("*/Network/Cookies"):
            profile = cookie_db.parent.parent.name
            try:
                cookie = _read_cookie_db(cookie_db, master_key)
            except ChromeCookieError:
                continue
            if cookie:
                yield CookieProfile(browser=browser, profile=profile, cookie=cookie, count=cookie.count("="))


def _candidate_user_data_dirs():
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    candidates = [
        ("Chrome", local / "Google" / "Chrome" / "User Data"),
        ("Chrome Beta", local / "Google" / "Chrome Beta" / "User Data"),
        ("Chrome Dev", local / "Google" / "Chrome Dev" / "User Data"),
        ("Edge", local / "Microsoft" / "Edge" / "User Data"),
        ("Brave", local / "BraveSoftware" / "Brave-Browser" / "User Data"),
        ("CocCoc", local / "CocCoc" / "Browser" / "User Data"),
        ("Opera", roaming / "Opera Software" / "Opera Stable"),
    ]
    for browser, path in candidates:
        if path.exists():
            yield browser, path


def _get_master_key(local_state: Path) -> bytes:
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
        encrypted_key = base64.b64decode(data["os_crypt"]["encrypted_key"])
    except (KeyError, ValueError, OSError) as exc:
        raise ChromeCookieError(f"Khong doc duoc Local State: {local_state}") from exc
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    return _crypt_unprotect_data(encrypted_key)


def _read_cookie_db(cookie_db: Path, master_key: bytes) -> str:
    temp_path = Path(tempfile.gettempdir()) / f"affiliate_tool_cookies_{os.getpid()}_{cookie_db.parent.parent.name}.sqlite"
    try:
        shutil.copy2(cookie_db, temp_path)
        conn = sqlite3.connect(temp_path)
        try:
            rows = conn.execute(
                """
                select host_key, name, value, encrypted_value
                from cookies
                where host_key like '%shopee.vn'
                order by host_key, name
                """
            ).fetchall()
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        raise ChromeCookieError(f"Khong doc duoc cookie db: {cookie_db}") from exc
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

    pairs: list[str] = []
    seen: set[str] = set()
    for _host, name, value, encrypted_value in rows:
        if not name or name in seen:
            continue
        decrypted = value or _decrypt_cookie_value(encrypted_value, master_key)
        if decrypted is None:
            continue
        seen.add(name)
        pairs.append(f"{name}={decrypted}")
    return "; ".join(pairs)


def _decrypt_cookie_value(encrypted_value: bytes, master_key: bytes) -> str | None:
    if not encrypted_value:
        return None
    encrypted = bytes(encrypted_value)
    try:
        if encrypted.startswith((b"v10", b"v11", b"v20")):
            return _aes_gcm_decrypt(master_key, encrypted[3:15], encrypted[15:-16], encrypted[-16:]).decode(
                "utf-8",
                errors="replace",
            )
        return _crypt_unprotect_data(encrypted).decode("utf-8", errors="replace")
    except Exception:
        return None


def _score_cookie(cookie: str) -> int:
    score = 0
    for marker in ("SPC_EC=", "SPC_ST=", "SPC_U=", "SPC_T_ID=", "SPC_R_T_ID=", "csrftoken="):
        if marker in cookie:
            score += 10
    if "affiliate" in cookie.lower():
        score += 5
    return score


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt_unprotect_data(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_buffer = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ChromeCookieError("Windows DPAPI khong giai ma duoc cookie key.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> bytes:
    bcrypt = ctypes.windll.bcrypt
    h_alg = ctypes.c_void_p()
    h_key = ctypes.c_void_p()
    status = bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(h_alg), "AES", None, 0)
    if status != 0:
        raise ChromeCookieError(f"BCryptOpenAlgorithmProvider failed: {status}")
    try:
        chaining = ctypes.create_unicode_buffer("ChainingModeGCM")
        status = bcrypt.BCryptSetProperty(
            h_alg,
            "ChainingMode",
            ctypes.cast(chaining, ctypes.POINTER(ctypes.c_ubyte)),
            ctypes.sizeof(chaining),
            0,
        )
        if status != 0:
            raise ChromeCookieError(f"BCryptSetProperty failed: {status}")
        key_buffer = ctypes.create_string_buffer(key)
        status = bcrypt.BCryptGenerateSymmetricKey(
            h_alg,
            ctypes.byref(h_key),
            None,
            0,
            ctypes.cast(key_buffer, ctypes.POINTER(ctypes.c_ubyte)),
            len(key),
            0,
        )
        if status != 0:
            raise ChromeCookieError(f"BCryptGenerateSymmetricKey failed: {status}")
        try:
            auth_info = _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
            auth_info.cbSize = ctypes.sizeof(auth_info)
            auth_info.dwInfoVersion = 1
            nonce_buffer = ctypes.create_string_buffer(nonce)
            tag_buffer = ctypes.create_string_buffer(tag)
            auth_info.pbNonce = ctypes.cast(nonce_buffer, ctypes.POINTER(ctypes.c_ubyte))
            auth_info.cbNonce = len(nonce)
            auth_info.pbTag = ctypes.cast(tag_buffer, ctypes.POINTER(ctypes.c_ubyte))
            auth_info.cbTag = len(tag)
            input_buffer = ctypes.create_string_buffer(ciphertext)
            output_buffer = ctypes.create_string_buffer(len(ciphertext))
            result_size = wintypes.ULONG()
            status = bcrypt.BCryptDecrypt(
                h_key,
                ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)),
                len(ciphertext),
                ctypes.byref(auth_info),
                None,
                0,
                ctypes.cast(output_buffer, ctypes.POINTER(ctypes.c_ubyte)),
                len(ciphertext),
                ctypes.byref(result_size),
                0,
            )
            if status != 0:
                raise ChromeCookieError(f"BCryptDecrypt failed: {status}")
            return output_buffer.raw[: result_size.value]
        finally:
            if h_key:
                bcrypt.BCryptDestroyKey(h_key)
    finally:
        if h_alg:
            bcrypt.BCryptCloseAlgorithmProvider(h_alg, 0)


class _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.ULONG),
        ("dwInfoVersion", wintypes.ULONG),
        ("pbNonce", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbNonce", wintypes.ULONG),
        ("pbAuthData", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbAuthData", wintypes.ULONG),
        ("pbTag", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbTag", wintypes.ULONG),
        ("pbMacContext", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbMacContext", wintypes.ULONG),
        ("cbAAD", wintypes.ULONG),
        ("cbData", ctypes.c_ulonglong),
        ("dwFlags", wintypes.ULONG),
    ]
