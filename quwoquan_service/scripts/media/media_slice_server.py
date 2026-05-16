#!/usr/bin/env python3
from __future__ import annotations

import argparse
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from media_slice_registry import (
    DEFAULT_REGISTRY_PATH,
    WORKSPACE_ROOT,
    load_registry,
    normalize_object_key,
    resolve_local_file,
    resolve_slice_entry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18088)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--workspace-root", default=str(WORKSPACE_ROOT))
    return parser.parse_args()


class MediaSliceHandler(BaseHTTPRequestHandler):
    server_version = "QuwoquanMediaSliceHTTP/1.0"

    def do_GET(self) -> None:  # noqa: N802
        self._serve(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve(send_body=False)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[media-slice-server] {self.address_string()} - {format % args}")

    def _serve(self, send_body: bool) -> None:
        registry = self.server.registry  # type: ignore[attr-defined]
        workspace_root = Path(self.server.workspace_root)  # type: ignore[attr-defined]
        normalized_path = normalize_object_key(self.path)
        if normalized_path == "healthz":
            self._serve_healthz(send_body)
            return
        object_key = normalize_object_key(self.path)
        if not object_key:
            self.send_error(HTTPStatus.NOT_FOUND, "empty object key")
            return
        entry = resolve_slice_entry(registry, object_key)
        if not entry:
            self.send_error(HTTPStatus.NOT_FOUND, f"slice not found for {object_key}")
            return

        origin_type = str(entry.get("originType", "")).strip()
        if origin_type == "local_root":
            target = resolve_local_file(registry, object_key, workspace_root=workspace_root)
            if target is None or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, f"media file not found: {object_key}")
                return
            self._serve_local_file(target, entry, object_key, send_body)
            return

        origin_base = str(entry.get("originBaseUrl", "")).strip().rstrip("/")
        if origin_base:
            self._proxy_remote(origin_base, entry, object_key, send_body)
            return

        self.send_error(HTTPStatus.BAD_GATEWAY, f"unsupported origin type for {object_key}: {origin_type}")

    def _serve_local_file(
        self,
        target: Path,
        entry: dict[str, Any],
        object_key: str,
        send_body: bool,
    ) -> None:
        mime, _ = mimetypes.guess_type(str(target))
        stat = target.stat()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("X-Quwoquan-Slice-Id", str(entry.get("sliceId", "")))
        self.send_header("X-Quwoquan-Origin-Type", str(entry.get("originType", "")))
        self.send_header("X-Quwoquan-Object-Key", object_key)
        self.end_headers()
        if send_body:
            with target.open("rb") as handle:
                self.wfile.write(handle.read())

    def _proxy_remote(
        self,
        origin_base: str,
        entry: dict[str, Any],
        object_key: str,
        send_body: bool,
    ) -> None:
        upstream = f"{origin_base}/{quote(object_key)}"
        request = Request(upstream, method="GET" if send_body else "HEAD")
        try:
            with urlopen(request, timeout=15) as response:
                self.send_response(response.status)
                for key, value in response.headers.items():
                    lower = key.lower()
                    if lower in {"connection", "transfer-encoding", "content-length"}:
                        continue
                    self.send_header(key, value)
                body = response.read() if send_body else b""
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Quwoquan-Slice-Id", str(entry.get("sliceId", "")))
                self.send_header("X-Quwoquan-Origin-Type", str(entry.get("originType", "")))
                self.send_header("X-Quwoquan-Upstream", upstream)
                self.end_headers()
                if send_body:
                    self.wfile.write(body)
        except HTTPError as exc:
            self.send_error(exc.code, f"upstream error: {upstream}")
        except URLError as exc:
            self.send_error(HTTPStatus.BAD_GATEWAY, f"upstream unavailable: {exc.reason}")

    def _serve_healthz(self, send_body: bool) -> None:
        body = b"ok\n"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(body)


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    server = ThreadingHTTPServer((args.bind, args.port), MediaSliceHandler)
    server.registry = registry  # type: ignore[attr-defined]
    server.workspace_root = args.workspace_root  # type: ignore[attr-defined]
    print(
        f"[media-slice-server] listening on http://{args.bind}:{args.port} "
        f"registry={args.registry}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[media-slice-server] shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
