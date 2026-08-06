"""spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004"""

import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from quwoquan_ops.cli.lib.local_media_origin import LocalMediaOriginHandler
from quwoquan_ops.cli.prod import render_prod_plane_stack


ROOT = Path(__file__).resolve().parents[3]
IMMUTABLE_POLICY = "public, max-age=31536000, immutable"


class LocalMediaOriginCachePolicyContractTest(unittest.TestCase):
    def test_real_head_and_range_share_query_free_cache_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            slice_path = Path(
                "media/video/s/asset/video-001/v12/source.mp4",
            )
            media_file = root / slice_path
            media_file.parent.mkdir(parents=True)
            media_file.write_bytes(b"0123456789")

            class Handler(LocalMediaOriginHandler):
                root_dir = root

                def log_message(self, _format: str, *_args: object) -> None:
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = (
                f"http://127.0.0.1:{server.server_port}/"
                f"{slice_path.as_posix()}"
            )
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, method="HEAD"),
                    timeout=2,
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(
                        response.headers["Cache-Control"],
                        IMMUTABLE_POLICY,
                    )
                    self.assertEqual(
                        response.headers["X-QWQ-Media-Cache-Key"],
                        f"/{slice_path.as_posix()}",
                    )
                    self.assertEqual(
                        response.headers["Access-Control-Allow-Origin"],
                        "*",
                    )

                with urllib.request.urlopen(
                    urllib.request.Request(
                        url,
                        headers={"Range": "bytes=0-1"},
                        method="GET",
                    ),
                    timeout=2,
                ) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.read(), b"01")
                    self.assertEqual(
                        response.headers["Cache-Control"],
                        IMMUTABLE_POLICY,
                    )
                    self.assertEqual(
                        response.headers["X-QWQ-Media-Cache-Key"],
                        f"/{slice_path.as_posix()}",
                    )

                with urllib.request.urlopen(
                    urllib.request.Request(f"{url}?v=12", method="HEAD"),
                    timeout=2,
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertIsNone(response.headers["X-QWQ-Media-Cache-Key"])
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)

    def test_versioned_public_slices_are_immutable(self) -> None:
        cases = (
            "/media/image/s/asset/image-001/v1/source.webp",
            "/media/video/s/asset/video-001/v12/source.mp4",
            "/media/video/s/asset/video-001/v12/preview/manifest.json",
            "/media/avatar/s/persona/user-001/v2/hash.png",
            "/media/background/s/homepage/home-001/v3/cover.jpg",
            "/media/attachment/s/asset/file-001/v4/source.pdf",
        )

        for path in cases:
            with self.subTest(path=path):
                self.assertEqual(
                    LocalMediaOriginHandler._cache_control_for_path(path),
                    IMMUTABLE_POLICY,
                )
                self.assertEqual(
                    LocalMediaOriginHandler._cache_control_for_request(path),
                    IMMUTABLE_POLICY,
                )
                self.assertEqual(
                    LocalMediaOriginHandler._cache_identity_for_request(path),
                    path,
                )

    def test_only_query_free_path_keeps_public_cache_identity(self) -> None:
        path = "/media/video/s/asset/video-001/v12/source.mp4"
        for query in (
            "v=12",
            "v=11",
            "sign=secret&t=1",
            "v=12&sign=secret",
            "variant=thumb",
            "v=12&v=12",
        ):
            with self.subTest(query=query):
                target = f"{path}?{query}"
                self.assertEqual(
                    LocalMediaOriginHandler._cache_control_for_request(target),
                    "no-store",
                )
                self.assertIsNone(
                    LocalMediaOriginHandler._cache_identity_for_request(target)
                )

    def test_private_or_unversioned_media_is_not_marked_immutable(self) -> None:
        cases = (
            "/media/image/private/sha256/deadbeef/source.webp",
            "/media/video/s/asset/video-001/source.mp4",
            "/media/avatar/conversation/conv-001/v1/mock.png",
            "/media/image/s/asset/image-001/v0/source.webp",
        )

        for path in cases:
            with self.subTest(path=path):
                self.assertEqual(
                    LocalMediaOriginHandler._cache_control_for_path(path),
                    "no-store",
                )

    def test_non_media_response_does_not_invent_cache_policy(self) -> None:
        self.assertIsNone(
            LocalMediaOriginHandler._cache_control_for_path("/healthz")
        )

    def test_gamma_and_rendered_prod_only_match_versioned_public_slices(self) -> None:
        matcher = (
            "^/media/(?:avatar|image|video|background|attachment)/s/"
            "(?:[^/]+/)+v[1-9][0-9]*/(?:[^/]+/)*[^/]+$"
        )
        gamma_caddy = (
            ROOT / "quwoquan_ops/environments/gamma/local/Caddyfile"
        ).read_text(encoding="utf-8")
        self.assertIn(matcher, gamma_caddy)
        self.assertIn(
            "vars_regexp canonical_media_query {http.request.uri.query}",
            gamma_caddy,
        )
        self.assertIn("{http.request.uri.query} ^$", gamma_caddy)
        self.assertIn('Cache-Control "no-store"', gamma_caddy)
        self.assertIn(f'Cache-Control "{IMMUTABLE_POLICY}"', gamma_caddy)
        self.assertIn('X-QWQ-Media-Cache-Key "{http.request.uri.path}"', gamma_caddy)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            render_prod_plane_stack._write_caddyfile(output, "prod")
            prod_caddy = (output / "runtime/Caddyfile").read_text(
                encoding="utf-8"
            )

        self.assertIn(matcher, prod_caddy)
        self.assertIn(
            "vars_regexp canonical_media_query {http.request.uri.query}",
            prod_caddy,
        )
        self.assertIn("{http.request.uri.query} ^$", prod_caddy)
        self.assertIn('Cache-Control "no-store"', prod_caddy)
        self.assertIn(f'Cache-Control "{IMMUTABLE_POLICY}"', prod_caddy)
        self.assertIn('X-QWQ-Media-Cache-Key "{http.request.uri.path}"', prod_caddy)

    def test_alpha_beta_and_prod_sim_publish_the_same_cache_contract(self) -> None:
        sources = (
            ROOT / "quwoquan_ops/cli/alpha/content_release_runtime.py",
            ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh",
            ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh",
        )
        for source in sources:
            with self.subTest(source=source.relative_to(ROOT).as_posix()):
                content = source.read_text(encoding="utf-8")
                self.assertIn("canonical_media_query", content)
                self.assertIn("{http.request.uri.query} ^$", content)
                self.assertIn("no-store", content)
                self.assertIn("public, max-age=31536000, immutable", content)
                self.assertIn("X-QWQ-Media-Cache-Key", content)
