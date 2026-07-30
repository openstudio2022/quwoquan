#!/usr/bin/env python3
"""Fail-closed HTTP plane for local topology and TLS probes.

This process deliberately owns no business object.  It exposes health and the
effective App endpoint projection, while every business query/command returns
``503 gate_block`` so prod-sim can never be mistaken for release evidence.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Type


def resolve_probe_response(
    method: str,
    path: str,
    *,
    mode: str,
    runtime_env: str,
    gateway_base_url: str = "",
    legal_base_url: str = "",
    product_ops_base_url: str = "",
    media_avatar_base_url: str = "",
    media_image_base_url: str = "",
    media_video_base_url: str = "",
    media_upload_base_url: str = "",
) -> tuple[int, dict[str, object]]:
    """Return the only responses the infrastructure probe is allowed to own."""
    normalized_path = path.partition("?")[0]
    if method == "GET" and normalized_path == "/healthz":
        return 200, {
            "status": "ok",
            "boundary": "infrastructure-probe",
            "runtimeEnv": runtime_env,
            "businessDataReady": False,
        }
    if method == "GET" and mode == "api" and normalized_path == "/config/app":
        return 200, {
            "appRuntimeEnv": runtime_env,
            "gatewayBaseUrl": gateway_base_url,
            "legalBaseUrl": legal_base_url,
            "productOpsBaseUrl": product_ops_base_url,
            "mediaAvatarBaseUrl": media_avatar_base_url,
            "mediaImageBaseUrl": media_image_base_url,
            "mediaVideoBaseUrl": media_video_base_url,
            "mediaUploadBaseUrl": media_upload_base_url,
            "businessDataReady": False,
        }
    return 503, {
        "status": "gate_block",
        "boundary": "infrastructure-probe",
        "businessDataReady": False,
        "message": "prod-sim does not provide business query or command results",
        "path": normalized_path,
    }


class InfrastructureProbeHandler(BaseHTTPRequestHandler):
    mode = "api"
    runtime_env = "prod"
    gateway_base_url = ""
    legal_base_url = ""
    product_ops_base_url = ""
    media_avatar_base_url = ""
    media_image_base_url = ""
    media_video_base_url = ""
    media_upload_base_url = ""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._dispatch("GET")

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._dispatch("HEAD", include_body=False)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._dispatch("PUT")

    def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._dispatch("DELETE")

    def _dispatch(self, method: str, *, include_body: bool = True) -> None:
        status, payload = resolve_probe_response(
            method,
            self.path,
            mode=self.mode,
            runtime_env=self.runtime_env,
            gateway_base_url=self.gateway_base_url,
            legal_base_url=self.legal_base_url,
            product_ops_base_url=self.product_ops_base_url,
            media_avatar_base_url=self.media_avatar_base_url,
            media_image_base_url=self.media_image_base_url,
            media_video_base_url=self.media_video_base_url,
            media_upload_base_url=self.media_upload_base_url,
        )
        self._send_json(payload, status=status, include_body=include_body)

    def _send_json(
        self,
        payload: dict[str, object],
        *,
        status: int = 200,
        include_body: bool = True,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body) if include_body else 0))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def configured_handler(args: argparse.Namespace) -> Type[InfrastructureProbeHandler]:
    class ConfiguredInfrastructureProbeHandler(InfrastructureProbeHandler):
        pass

    ConfiguredInfrastructureProbeHandler.mode = args.mode
    ConfiguredInfrastructureProbeHandler.runtime_env = args.runtime_env
    ConfiguredInfrastructureProbeHandler.gateway_base_url = args.gateway_base_url
    ConfiguredInfrastructureProbeHandler.legal_base_url = args.legal_base_url
    ConfiguredInfrastructureProbeHandler.product_ops_base_url = (
        args.product_ops_base_url
    )
    ConfiguredInfrastructureProbeHandler.media_avatar_base_url = (
        args.media_avatar_base_url
    )
    ConfiguredInfrastructureProbeHandler.media_image_base_url = args.media_image_base_url
    ConfiguredInfrastructureProbeHandler.media_video_base_url = args.media_video_base_url
    ConfiguredInfrastructureProbeHandler.media_upload_base_url = (
        args.media_upload_base_url
    )
    return ConfiguredInfrastructureProbeHandler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", required=True, type=int)
    parser.add_argument("--mode", choices=("api", "product-ops"), required=True)
    parser.add_argument("--runtime-env", default="prod")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--legal-base-url", default="")
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-avatar-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument("--media-video-base-url", default="")
    parser.add_argument("--media-upload-base-url", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer(
        (args.listen_host, args.listen_port),
        configured_handler(args),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
