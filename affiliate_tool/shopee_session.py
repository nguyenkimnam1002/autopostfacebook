from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_DEBUG_PORT = 9222
SHOPEE_URL = "https://shopee.vn"


class ShopeeSessionError(RuntimeError):
    pass


def open_login_browser(port: int = DEFAULT_DEBUG_PORT) -> int:
    if _debug_endpoint_ready(port):
        return port

    chrome = _find_chrome()
    profile_dir = Path("shopee_chrome_profile").resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--disable-default-apps",
        SHOPEE_URL,
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if _debug_endpoint_ready(port):
            return port
        time.sleep(0.5)
    raise ShopeeSessionError("Chrome da mo nhung remote debugging chua san sang.")


def open_default_profile_browser(port: int = DEFAULT_DEBUG_PORT) -> int:
    if _debug_endpoint_ready(port):
        return port

    chrome = _find_chrome()
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--disable-default-apps",
        SHOPEE_URL,
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if _debug_endpoint_ready(port):
            return port
        time.sleep(0.5)
    raise ShopeeSessionError(
        "Khong bat duoc remote debugging tren Chrome profile chinh. "
        "Hay dong tat ca cua so Chrome truoc, roi bam lai nut nay. "
        "Neu Chrome dang mo san, Chrome se chi mo tab moi va khong bat debug port."
    )


def read_shopee_cookie(port: int = DEFAULT_DEBUG_PORT) -> str:
    if not _debug_endpoint_ready(port):
        raise ShopeeSessionError("Chua thay Chrome login profile. Bam 'Mo Chrome dang nhap Shopee' truoc.")

    ws_url = _browser_ws_url(port)
    client = _CdpWebSocket(ws_url)
    try:
        target_id = _get_or_create_shopee_target(client, port)
        if not target_id:
            raise ShopeeSessionError("Khong tao duoc Shopee tab trong Chrome debug profile.")
        attached = client.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = attached.get("sessionId")
        if not session_id:
            raise ShopeeSessionError("Khong attach duoc Shopee tab.")
        cookies_payload = client.call("Network.getAllCookies", session_id=session_id)
    finally:
        client.close()

    cookies = cookies_payload.get("cookies") or []
    shopee_cookies = [
        cookie
        for cookie in cookies
        if "shopee.vn" in (cookie.get("domain") or "")
        and cookie.get("name")
        and cookie.get("value") is not None
    ]
    if not shopee_cookies:
        raise ShopeeSessionError("Chua co cookie Shopee. Hay login Shopee trong Chrome vua mo roi thu lai.")
    return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in shopee_cookies)


def fetch_json_in_shopee_chrome(url: str, port: int = DEFAULT_DEBUG_PORT) -> dict:
    if not _debug_endpoint_ready(port):
        raise ShopeeSessionError("Chua thay Chrome debug. Hay bam 'Mo Chrome chinh' hoac 'Mo Chrome login' truoc.")

    ws_url = _browser_ws_url(port)
    client = _CdpWebSocket(ws_url)
    try:
        target_id = _get_or_create_shopee_target(client, port)
        if not target_id:
            raise ShopeeSessionError("Khong tao duoc Shopee tab trong Chrome.")
        attached = client.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = attached.get("sessionId")
        if not session_id:
            raise ShopeeSessionError("Khong attach duoc Shopee tab.")

        time.sleep(2)
        expression = f"""
        (async () => {{
          const res = await fetch({json.dumps(url)}, {{
            credentials: 'include',
            headers: {{
              'accept': 'application/json',
              'x-requested-with': 'XMLHttpRequest'
            }}
          }});
          const text = await res.text();
          return {{ status: res.status, text }};
        }})()
        """
        evaluated = client.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "timeout": 30000,
            },
            session_id=session_id,
        )
    finally:
        client.close()

    result = evaluated.get("result") or {}
    value = result.get("value") or {}
    status = value.get("status")
    text = value.get("text") or ""
    if status != 200:
        raise ShopeeSessionError(f"Chrome fetch Shopee HTTP {status}: {text[:200]}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ShopeeSessionError("Chrome fetch Shopee returned non-JSON response") from exc


def _get_or_create_shopee_target(client: "_CdpWebSocket", port: int) -> str | None:
    target_id = _existing_shopee_target_id(port)
    if target_id:
        return target_id
    created = client.call("Target.createTarget", {"url": SHOPEE_URL})
    return created.get("targetId")


def _existing_shopee_target_id(port: int) -> str | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as response:
            targets = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    for item in targets or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "page":
            continue
        url = str(item.get("url") or "")
        if "shopee.vn" not in url:
            continue
        target_id = item.get("id") or item.get("targetId")
        if target_id:
            return str(target_id)
    return None


def _find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise ShopeeSessionError("Khong tim thay Chrome/Edge. Co the set CHROME_PATH trong .env.")


def _debug_endpoint_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def _browser_ws_url(port: int) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    ws_url = payload.get("webSocketDebuggerUrl")
    if not ws_url:
        raise ShopeeSessionError("Chrome debug endpoint khong tra ve WebSocket URL.")
    return ws_url


class _CdpWebSocket:
    def __init__(self, ws_url: str):
        parsed = urllib.parse.urlparse(ws_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path
        if parsed.query:
            self.path += "?" + parsed.query
        self.sock = socket.create_connection((self.host, self.port), timeout=5)
        self.next_id = 1
        self._handshake()

    def call(self, method: str, params: dict | None = None, session_id: str | None = None) -> dict:
        message_id = self.next_id
        self.next_id += 1
        payload: dict = {"id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        if session_id:
            payload["sessionId"] = session_id
        self._send_json(payload)
        while True:
            message = self._recv_json()
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise ShopeeSessionError(f"CDP error: {message['error']}")
            return message.get("result") or {}

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ShopeeSessionError("WebSocket handshake voi Chrome that bai.")

        accept = None
        for line in response.decode("latin1", errors="ignore").split("\r\n"):
            if line.lower().startswith("sec-websocket-accept:"):
                accept = line.split(":", 1)[1].strip()
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if accept != expected:
            raise ShopeeSessionError("Chrome WebSocket accept key khong hop le.")

    def _send_json(self, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        header = bytearray([0x81])
        length = len(data)
        mask_bit = 0x80
        if length < 126:
            header.append(mask_bit | length)
        elif length < 65536:
            header.append(mask_bit | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_json(self) -> dict:
        first = self._recv_exact(2)
        opcode = first[0] & 0x0F
        if opcode == 0x8:
            raise ShopeeSessionError("Chrome dong WebSocket.")
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        masked = bool(first[1] & 0x80)
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length)
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return json.loads(payload.decode("utf-8"))

    def _recv_exact(self, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.sock.recv(length - len(chunks))
            if not chunk:
                raise ShopeeSessionError("Mat ket noi Chrome WebSocket.")
            chunks.extend(chunk)
        return bytes(chunks)
