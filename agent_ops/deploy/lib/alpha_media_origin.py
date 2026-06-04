#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import posixpath
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_DEFAULT_GROUP_AVATAR = "media/avatar/group/fixture_conv_group/v1/composite.png"
_PHOTO_GROUP_AVATAR = "media/avatar/group/fixture_conv_photo_group/v1/composite.png"
_CONVERSATION_AVATAR_ALIASES = {
    "conv_002": _DEFAULT_GROUP_AVATAR,
    "conv_006": _PHOTO_GROUP_AVATAR,
    "conv_grid_10": _DEFAULT_GROUP_AVATAR,
    "conv_grid_11": _PHOTO_GROUP_AVATAR,
    "conv_grid_12": _DEFAULT_GROUP_AVATAR,
}


class AlphaMediaOriginHandler(SimpleHTTPRequestHandler):
    root_dir = Path(".")

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path or "/"
        if path == "/healthz":
            self._send_json({"status": "ok", "server": "alpha-media-origin"})
            return
        alias_target = self._resolve_alias(path)
        if alias_target is not None:
            self._serve_alias(alias_target, include_body=True)
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        path = urllib.parse.urlsplit(self.path).path or "/"
        if path == "/healthz":
            self._send_json({"status": "ok", "server": "alpha-media-origin"}, include_body=False)
            return
        alias_target = self._resolve_alias(path)
        if alias_target is not None:
            self._serve_alias(alias_target, include_body=False)
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    AlphaMediaOriginHandler.root_dir = Path(args.root_dir).resolve()
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), AlphaMediaOriginHandler)
    print(
        "[alpha-media-origin] listening http://{host}:{port} root={root}".format(
            host=args.listen_host,
            port=args.listen_port,
            root=AlphaMediaOriginHandler.root_dir,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
