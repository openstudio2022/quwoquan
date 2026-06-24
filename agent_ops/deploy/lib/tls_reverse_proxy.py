#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ssl
from http.server import ThreadingHTTPServer

from http_reverse_proxy import ReverseProxyHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-base-url", required=True)
    parser.add_argument("--cert-file", required=True)
    parser.add_argument("--key-file", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ReverseProxyHandler.upstream_base_url = args.target_base_url.rstrip("/")
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), ReverseProxyHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=args.cert_file, keyfile=args.key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(
        "[tls-reverse-proxy] listening "
        f"https://{args.listen_host}:{args.listen_port} -> "
        f"{ReverseProxyHandler.upstream_base_url}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
