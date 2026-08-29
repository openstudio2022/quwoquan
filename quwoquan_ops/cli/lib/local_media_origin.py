#!/usr/bin/env python3
"""本地媒体 origin（alpha / beta / gamma / prod-sim 共用）。

历史上 alpha 与 gamma-local 各自内嵌一份 `SimpleHTTPRequestHandler`，都忽略
HTTP Range：iOS AVPlayer 会先用 `Range: bytes=0-1` 探测随机读能力，服务端若
对探测返回 200 + 整文件，AVPlayer 判定不支持 seek 而卡在加载/无法播放。这里
收敛为单一实现并统一支持 Range(206)。所有业务媒体必须来自 release publicSliceKey
或正式上传 MediaAsset；origin 不维护会话头像 alias 或 fixture 路径。
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import posixpath
import re
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_PUBLIC_VERSIONED_SLICE_PATH = re.compile(
    r"^/media/(?:avatar|image|video|background|attachment)/s/"
    r"(?:[^/]+/)+v[1-9][0-9]*/(?:[^/]+/)*[^/]+$"
)
_PUBLIC_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
_PUBLIC_CORS_ALLOW_ORIGIN = "*"
_PUBLIC_CACHE_KEY_HEADER = "X-QWQ-Media-Cache-Key"
# 私有交付前缀只允许经短签 URL 访问（DEC-031 网络层边缘守卫）：本 origin
# 作为 quwoquan_service/runtime/media 共享私有交付协议的 adapter，在字节
# 交付边缘复算 HMAC-SHA256(signKey, '{path}-{t}') 并判定绝对到期。签名
# 缺失、伪造、篡改、过期或 signKey 未配置均 403（fail closed），协议与
# 前缀闭集的跨语言一致性由共享 parity 向量（content-service contracts 下
# private_delivery_signature_cases.json）在两侧 local_contract 锚定。
_PRIVATE_DELIVERY_PATH_PREFIXES = ("/media/objects/", "/media/processed/")
_PRIVATE_SIGN_KEY_DEFAULT_ENV = "CONTENT_CDN_SIGN_KEY"


def verify_private_delivery_signature(
    path: str,
    sign_hex: str,
    expires_raw: str,
    sign_key: str,
    now_unix: int,
) -> bool:
    """复算私有交付短签；与 Go VerifyPrivateDeliverySignature 同协议。"""
    if not sign_key.strip() or not path:
        return False
    try:
        expires = int(expires_raw.strip())
    except (ValueError, AttributeError):
        return False
    if expires <= 0 or now_unix > expires:
        return False
    try:
        provided = bytes.fromhex(sign_hex.strip())
    except (ValueError, AttributeError):
        return False
    if len(provided) != hashlib.sha256().digest_size:
        return False
    expected = hmac.new(
        sign_key.encode("utf-8"),
        f"{path}-{expires}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return hmac.compare_digest(provided, expected)


def _normalized_request_path(raw_path: str) -> str:
    """私有前缀守卫与文件解析共用的唯一路径归一化。

    dot-segment（`/foo/../media/...`）与双前导斜杠（`//media/...`）都必须在
    前缀匹配前消解，否则守卫看到的路径与 `translate_path` 实际服务的文件
    会分叉，形成匿名绕过。
    """
    normalized = posixpath.normpath(urllib.parse.unquote(raw_path or "/"))
    return "/" + normalized.lstrip("/")


class LocalMediaOriginHandler(SimpleHTTPRequestHandler):
    root_dir = Path(".")
    server_label = "local-media-origin"
    # None 表示 signKey 未配置：私有前缀整体 fail closed，不退回
    # “参数在场即放行”。
    private_sign_key: str | None = None
    def send_response(self, code: int, message: str | None = None) -> None:
        self._response_status = code
        self._cache_control_sent = False
        self._cors_allow_origin_sent = False
        self._public_cache_key_sent = False
        super().send_response(code, message)

    def send_header(self, keyword: str, value: str) -> None:
        normalized = keyword.lower()
        if normalized == "cache-control":
            self._cache_control_sent = True
        elif normalized == "access-control-allow-origin":
            self._cors_allow_origin_sent = True
        elif normalized == _PUBLIC_CACHE_KEY_HEADER.lower():
            self._public_cache_key_sent = True
        super().send_header(keyword, value)

    def end_headers(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path or "/"
        if path.startswith("/media/"):
            if not getattr(self, "_cors_allow_origin_sent", False):
                self.send_header("Access-Control-Allow-Origin", _PUBLIC_CORS_ALLOW_ORIGIN)
                self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
            if not getattr(self, "_cache_control_sent", False):
                self.send_header(
                    "Cache-Control",
                    self._cache_control_for_request(self.path) or "no-store",
                )
            cache_identity = self._cache_identity_for_request(self.path)
            if (
                cache_identity is not None
                and getattr(self, "_response_status", None) in {200, 206}
                and not getattr(self, "_public_cache_key_sent", False)
            ):
                self.send_header(_PUBLIC_CACHE_KEY_HEADER, cache_identity)
        super().end_headers()

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path or "/"
        if path == "/healthz":
            self._send_json({"status": "ok", "server": self.server_label})
            return
        if self._deny_unsigned_private_delivery():
            return
        # 视频等大文件需要 HTTP Range：iOS AVPlayer 会先用 `Range: bytes=0-1`
        # 探测；若服务端忽略 Range、对探测返回 200 + 整文件，AVPlayer 会判定
        # 不支持随机读而卡在加载/无法播放。这里对带 Range 的请求回 206。
        if self._serve_byte_range(include_body=True):
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        path = urllib.parse.urlsplit(self.path).path or "/"
        if path == "/healthz":
            self._send_json({"status": "ok", "server": self.server_label}, include_body=False)
            return
        if self._deny_unsigned_private_delivery(include_body=False):
            return
        if self._serve_byte_range(include_body=False):
            return
        super().do_HEAD()

    def _deny_unsigned_private_delivery(self, *, include_body: bool = True) -> bool:
        parsed = urllib.parse.urlsplit(self.path)
        path = _normalized_request_path(parsed.path)
        if not path.startswith(_PRIVATE_DELIVERY_PATH_PREFIXES):
            return False
        query = urllib.parse.parse_qs(parsed.query)
        sign_values = query.get("sign") or [""]
        expires_values = query.get("t") or [""]
        # 验签必须使用与 translate_path 同源的归一化 path，否则
        # percent-encoding / dot-segment 变体会让守卫与文件解析分叉。
        if self.private_sign_key and verify_private_delivery_signature(
            path,
            sign_values[0],
            expires_values[0],
            self.private_sign_key,
            int(time.time()),
        ):
            return False
        body = json.dumps(
            {"error": "private media delivery requires a valid signed URL"},
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(403)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)
        return True

    def translate_path(self, path: str) -> str:
        parts = urllib.parse.urlsplit(path)
        normalized = _normalized_request_path(parts.path)
        resolved = self.root_dir
        for segment in Path(normalized.lstrip("/")).parts:
            if segment in {"", ".", ".."}:
                continue
            resolved = resolved / segment
        return str(resolved)

    @staticmethod
    def _cache_control_for_path(path: str) -> str | None:
        normalized = urllib.parse.unquote(path or "/")
        if _PUBLIC_VERSIONED_SLICE_PATH.fullmatch(normalized):
            return _PUBLIC_IMMUTABLE_CACHE_CONTROL
        if normalized.startswith("/media/"):
            return "no-store"
        return None

    @classmethod
    def _cache_control_for_request(cls, raw_target: str) -> str | None:
        parsed = urllib.parse.urlsplit(raw_target)
        path = urllib.parse.unquote(parsed.path or "/")
        path_policy = cls._cache_control_for_path(path)
        if path_policy != _PUBLIC_IMMUTABLE_CACHE_CONTROL:
            return path_policy
        # The versioned public path is the sole cache identity. Any query,
        # including a redundant matching version, is outside that single track
        # and must not be admitted to long-lived shared caches.
        return _PUBLIC_IMMUTABLE_CACHE_CONTROL if parsed.query == "" else "no-store"

    @classmethod
    def _cache_identity_for_request(cls, raw_target: str) -> str | None:
        if cls._cache_control_for_request(raw_target) != _PUBLIC_IMMUTABLE_CACHE_CONTROL:
            return None
        path = urllib.parse.unquote(urllib.parse.urlsplit(raw_target).path or "/")
        return path

    def _serve_byte_range(self, *, include_body: bool) -> bool:
        range_header = self.headers.get("Range")
        if not range_header:
            return False
        file_path = Path(self.translate_path(self.path))
        if not file_path.is_file():
            return False
        file_size = file_path.stat().st_size
        byte_range = self._parse_byte_range(range_header, file_size)
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if byte_range is None:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            return True
        start, end = byte_range
        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if include_body:
            with file_path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        return True

    @staticmethod
    def _parse_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
        # 仅支持单段 `bytes=start-end` / `bytes=start-` / `bytes=-suffix`。
        if not range_header.startswith("bytes=") or file_size <= 0:
            return None
        spec = range_header[len("bytes="):].split(",", 1)[0].strip()
        if "-" not in spec:
            return None
        start_text, _, end_text = spec.partition("-")
        try:
            if start_text == "":
                suffix = int(end_text)
                if suffix <= 0:
                    return None
                start = max(0, file_size - suffix)
                end = file_size - 1
            else:
                start = int(start_text)
                end = int(end_text) if end_text else file_size - 1
        except ValueError:
            return None
        if start > end or start >= file_size:
            return None
        return start, min(end, file_size - 1)

    def _send_json(self, payload: dict[str, object], *, include_body: bool = True) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--root-dir", required=True)
    parser.add_argument(
        "--server-label",
        default="local-media-origin",
        help="healthz 中暴露的 server 标识，便于区分 alpha/prod-sim/gamma-local。",
    )
    parser.add_argument(
        "--private-sign-key-env",
        default=_PRIVATE_SIGN_KEY_DEFAULT_ENV,
        help=(
            "私有交付签名 secret 的环境变量名（与签发方同一 secret "
            "reference）。缺失时私有前缀整体 fail closed（403）。"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    LocalMediaOriginHandler.root_dir = Path(args.root_dir).resolve()
    LocalMediaOriginHandler.server_label = args.server_label
    sign_key = os.environ.get(args.private_sign_key_env, "").strip()
    LocalMediaOriginHandler.private_sign_key = sign_key or None
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), LocalMediaOriginHandler)
    print(
        "[{label}] listening http://{host}:{port} root={root} range=on "
        "private_delivery={mode}".format(
            label=args.server_label,
            host=args.listen_host,
            port=args.listen_port,
            root=LocalMediaOriginHandler.root_dir,
            mode=(
                "hmac-verify"
                if sign_key
                else f"fail-closed (missing {args.private_sign_key_env})"
            ),
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
