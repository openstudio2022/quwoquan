#!/usr/bin/env python3
"""本地媒体 origin（alpha / prod-sim / gamma-local 共用）。

历史上 alpha 与 gamma-local 各自内嵌一份 `SimpleHTTPRequestHandler`，都忽略
HTTP Range：iOS AVPlayer 会先用 `Range: bytes=0-1` 探测随机读能力，服务端若
对探测返回 200 + 整文件，AVPlayer 判定不支持 seek 而卡在加载/无法播放。这里
收敛为单一实现，统一支持 Range(206)，并把 alpha 特有的会话头像 alias 作为可选
开关，避免第二真相源。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import posixpath
import re
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_DEFAULT_GROUP_AVATAR = "media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png"
_PHOTO_GROUP_AVATAR = "media/avatar/s/archived-avatar/group/fixture_conv_photo_group/v1/composite.png"
_CONVERSATION_AVATAR_ALIASES = {
    "conv_002": _DEFAULT_GROUP_AVATAR,
    "conv_006": _PHOTO_GROUP_AVATAR,
}
_PUBLIC_VERSIONED_SLICE_PATH = re.compile(
    r"^/media/(?:avatar|image|video|background|attachment)/s/"
    r"(?:[^/]+/)+v[1-9][0-9]*/(?:[^/]+/)*[^/]+$"
)
_PUBLIC_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
_PUBLIC_CORS_ALLOW_ORIGIN = "*"
_PUBLIC_CACHE_KEY_HEADER = "X-QWQ-Media-Cache-Key"


class LocalMediaOriginHandler(SimpleHTTPRequestHandler):
    root_dir = Path(".")
    server_label = "local-media-origin"
    # alpha / prod-sim 的 mock 会话使用会话头像占位路径，需要 alias 到群组合成
    # 头像；gamma-local 用真实 curated 资产，关闭。
    conversation_avatar_alias_enabled = False

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
        alias_target = self._resolve_alias(path)
        if alias_target is not None:
            self._serve_alias(alias_target, include_body=True)
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
        alias_target = self._resolve_alias(path)
        if alias_target is not None:
            self._serve_alias(alias_target, include_body=False)
            return
        if self._serve_byte_range(include_body=False):
            return
        super().do_HEAD()

    def translate_path(self, path: str) -> str:
        parts = urllib.parse.urlsplit(path)
        normalized = posixpath.normpath(urllib.parse.unquote(parts.path or "/"))
        resolved = self.root_dir
        for segment in Path(normalized.lstrip("/")).parts:
            if segment in {"", ".", ".."}:
                continue
            resolved = resolved / segment
        return str(resolved)

    def _resolve_alias(self, path: str) -> str | None:
        if not self.conversation_avatar_alias_enabled:
            return None
        parts = Path(path.lstrip("/")).parts
        conversation_id = self._conversation_avatar_alias_id(parts)
        if conversation_id is None:
            return None
        # 仅显式映射的 archive 会话走 alias；conv_grid_* 等差异化资产直出磁盘。
        return _CONVERSATION_AVATAR_ALIASES.get(conversation_id)

    @staticmethod
    def _conversation_avatar_alias_id(parts: tuple[str, ...]) -> str | None:
        # archive alpha/prod-sim 占位路径：
        #   /media/avatar/conversation/<conversation_id>/mock.png
        if (
            len(parts) == 6
            and parts[:3] == ("media", "avatar", "conversation")
            and parts[4] == "v1"
            and parts[5] == "mock.png"
        ):
            return parts[3]

        # 当前 App mock 合约路径：
        #   /media/avatar/s/archived-avatar/conversation/<conversation_id>/mock.png
        if (
            len(parts) == 8
            and parts[:5]
            == ("media", "avatar", "s", "archived-avatar", "conversation")
            and parts[6] == "v1"
            and parts[7] == "mock.png"
        ):
            return parts[5]

        return None

    def _serve_alias(self, relative_path: str, *, include_body: bool) -> None:
        file_path = self.root_dir / relative_path
        if not file_path.exists():
            self.send_error(404, f"alias target not found: {relative_path}")
            return
        payload = file_path.read_bytes() if include_body else b""
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

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
        "--enable-conversation-avatar-alias",
        action="store_true",
        help="启用 mock 会话头像 alias（alpha / prod-sim 需要；gamma-local 不需要）。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    LocalMediaOriginHandler.root_dir = Path(args.root_dir).resolve()
    LocalMediaOriginHandler.server_label = args.server_label
    LocalMediaOriginHandler.conversation_avatar_alias_enabled = (
        args.enable_conversation_avatar_alias
    )
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), LocalMediaOriginHandler)
    print(
        "[{label}] listening http://{host}:{port} root={root} range=on alias={alias}".format(
            label=args.server_label,
            host=args.listen_host,
            port=args.listen_port,
            root=LocalMediaOriginHandler.root_dir,
            alias="on" if args.enable_conversation_avatar_alias else "off",
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
