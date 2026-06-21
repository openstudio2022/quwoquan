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
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_DEFAULT_GROUP_AVATAR = "media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png"
_PHOTO_GROUP_AVATAR = "media/avatar/s/archived-avatar/group/fixture_conv_photo_group/v1/composite.png"
_CONVERSATION_AVATAR_ALIASES = {
    "conv_002": _DEFAULT_GROUP_AVATAR,
    "conv_006": _PHOTO_GROUP_AVATAR,
    "conv_grid_10": _DEFAULT_GROUP_AVATAR,
    "conv_grid_11": _PHOTO_GROUP_AVATAR,
    "conv_grid_12": _DEFAULT_GROUP_AVATAR,
}


class LocalMediaOriginHandler(SimpleHTTPRequestHandler):
    root_dir = Path(".")
    server_label = "local-media-origin"
    # alpha / prod-sim 的 mock 会话使用 `media/avatar/conversation/<id>/v1/mock.png`
    # 占位路径，需要 alias 到群组合成头像；gamma-local 用真实 curated 资产，关闭。
    conversation_avatar_alias_enabled = False

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
        if len(parts) != 6:
            return None
        if parts[:3] != ("media", "avatar", "conversation"):
            return None
        if parts[4] != "v1" or parts[5] != "mock.png":
            return None
        conversation_id = parts[3]
        return _CONVERSATION_AVATAR_ALIASES.get(conversation_id, _DEFAULT_GROUP_AVATAR)

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
        self.send_header("Cache-Control", "no-store")
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
