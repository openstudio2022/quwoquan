#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.client import HTTPConnection, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class ReverseProxyHandler(BaseHTTPRequestHandler):
    upstream_base_url: str = ""

    def do_GET(self) -> None:
        self._forward()

    def do_HEAD(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def do_PUT(self) -> None:
        self._forward()

    def do_PATCH(self) -> None:
        self._forward()

    def do_DELETE(self) -> None:
        self._forward()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _forward(self) -> None:
        if self.path == "/healthz":
            payload = (
                '{"status":"ok","proxy":"http-reverse-proxy","upstreamBaseUrl":"%s"}'
                % self.upstream_base_url
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
            return
        parsed_base = urlsplit(self.upstream_base_url.rstrip("/"))
        conn_cls = HTTPSConnection if parsed_base.scheme == "https" else HTTPConnection
        path = self.path
        if parsed_base.path:
            path = f"{parsed_base.path.rstrip('/')}/{self.path.lstrip('/')}"
        body_len = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(body_len) if body_len > 0 else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        conn = conn_cls(parsed_base.hostname, parsed_base.port, timeout=30)
        try:
            conn.request(self.command, path, body=body, headers=headers)
            upstream = conn.getresponse()
            payload = upstream.read()
        except Exception as exc:  # noqa: BLE001
            self.send_error(502, f"reverse proxy failed: {exc}")
            return
        finally:
            conn.close()

        self.send_response(upstream.status)
        for key, value in upstream.getheaders():
            if key.lower() in {"connection", "transfer-encoding"}:
                continue
            self.send_header(key, value)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-base-url", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ReverseProxyHandler.upstream_base_url = args.target_base_url.rstrip("/")
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), ReverseProxyHandler)
    print(
        f"[http-reverse-proxy] listening http://{args.listen_host}:{args.listen_port} -> {ReverseProxyHandler.upstream_base_url}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
