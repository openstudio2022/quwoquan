#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockPublicPlaneHandler(BaseHTTPRequestHandler):
    mode: str = "api"
    runtime_env: str = "alpha"
    data_source: str = "mock"
    gateway_base_url: str = ""
    product_ops_base_url: str = ""
    media_base_url: str = ""

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(
                {
                    "status": "ok",
                    "mode": self.mode,
                    "runtimeEnv": self.runtime_env,
                }
            )
            return
        if self.mode == "api" and self.path == "/v1/config/app":
            self._send_json(
                {
                    "appRuntimeEnv": self.runtime_env,
                    "dataSource": self.data_source,
                    "gatewayBaseUrl": self.gateway_base_url,
                    "productOpsBaseUrl": self.product_ops_base_url,
                    "mediaBaseUrl": self.media_base_url,
                }
            )
            return
        if self.mode == "api" and self.path.startswith("/v1/content/feed"):
            self._send_json({"items": [], "mockBoundary": True})
            return
        if self.mode == "api" and self.path.startswith("/v1/chat/contacts"):
            self._send_json({"items": [], "mockBoundary": True})
            return
        self.send_error(404, f"{self.mode} mock route is not ready")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--mode", choices=["api", "product-ops"], default="api")
    parser.add_argument("--runtime-env", default="alpha")
    parser.add_argument("--data-source", default="mock")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-base-url", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    MockPublicPlaneHandler.mode = args.mode
    MockPublicPlaneHandler.runtime_env = args.runtime_env
    MockPublicPlaneHandler.data_source = args.data_source
    MockPublicPlaneHandler.gateway_base_url = args.gateway_base_url.rstrip("/")
    MockPublicPlaneHandler.product_ops_base_url = args.product_ops_base_url.rstrip("/")
    MockPublicPlaneHandler.media_base_url = args.media_base_url.rstrip("/")
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), MockPublicPlaneHandler)
    print(
        "[mock-public-plane] listening http://{host}:{port} mode={mode}".format(
            host=args.listen_host,
            port=args.listen_port,
            mode=args.mode,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
