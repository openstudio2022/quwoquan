"""DEC-031 网络层边缘守卫：本地 media origin 作为共享私有交付协议的
adapter，对私有前缀（media/objects/**、media/processed/**）在字节交付
边缘复算 HMAC-SHA256 签名并判定绝对到期。签名缺失、伪造、篡改、过期
或 signKey 未配置均 403（fail closed），公开 /s/ 切片保持匿名可达。
跨语言协议一致性由 content-service contracts 下的共享 parity 向量锚定。
"""

import hashlib
import hmac
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from quwoquan_ops.cli.lib.local_media_origin import (
    LocalMediaOriginHandler,
    verify_private_delivery_signature,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SHARED_CASES_PATH = (
    _REPO_ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "media"
    / "media_asset"
    / "private_delivery_signature_cases.json"
)


def _sign(path: str, expires: int, key: str) -> str:
    return hmac.new(
        key.encode("utf-8"),
        f"{path}-{expires}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class PrivateDeliverySignatureParityTest(unittest.TestCase):
    """Python verifier 与 Go verifier 消费同一份共享向量，单侧漂移即失败。"""

    def test_shared_cases_verify_identically(self) -> None:
        document = json.loads(_SHARED_CASES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            document["schema"], "content_media_private_delivery_signature_cases"
        )
        self.assertTrue(document["cases"])
        for case in document["cases"]:
            with self.subTest(case["name"]):
                self.assertIs(
                    verify_private_delivery_signature(
                        case["path"],
                        case["sign"],
                        str(case["expires"]),
                        document["signKey"],
                        int(document["nowUnix"]),
                    ),
                    case["wantValid"],
                )

    def test_shared_prefix_closed_set_matches_local_guard(self) -> None:
        document = json.loads(_SHARED_CASES_PATH.read_text(encoding="utf-8"))
        from quwoquan_ops.cli.lib.local_media_origin import (
            _PRIVATE_DELIVERY_PATH_PREFIXES,
        )

        self.assertEqual(
            tuple(document["privatePathPrefixes"]),
            _PRIVATE_DELIVERY_PATH_PREFIXES,
        )

    def test_missing_sign_key_fails_closed(self) -> None:
        self.assertFalse(
            verify_private_delivery_signature(
                "/media/objects/sha256/aa/bb/cc.jpg",
                _sign("/media/objects/sha256/aa/bb/cc.jpg", 2**62, "any"),
                str(2**62),
                "",
                int(time.time()),
            )
        )


class LocalMediaOriginPrivateDeliveryContractTest(unittest.TestCase):
    SIGN_KEY = "origin-contract-test-key"

    def _serve(
        self, root: Path, *, sign_key: str | None
    ) -> tuple[ThreadingHTTPServer, threading.Thread]:
        class Handler(LocalMediaOriginHandler):
            root_dir = root
            private_sign_key = sign_key

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        return server, worker

    def test_private_prefixes_require_authentic_unexpired_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cas_key = "media/objects/sha256/aa/bb/" + "a" * 64 + ".jpg"
            public_key = "media/image/s/asset/image-001/v1/source.webp"
            for key in (cas_key, public_key):
                target = root / key
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"payload")
            server, worker = self._serve(root, sign_key=self.SIGN_KEY)
            base = f"http://127.0.0.1:{server.server_port}"
            fresh = int(time.time()) + 600
            stale = int(time.time()) - 600
            good_query = f"sign={_sign('/' + cas_key, fresh, self.SIGN_KEY)}&t={fresh}"
            try:
                # 无签名的私有 CAS GET/HEAD 必须 403。
                for method in ("GET", "HEAD"):
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        urllib.request.urlopen(
                            urllib.request.Request(
                                f"{base}/{cas_key}", method=method
                            ),
                            timeout=2,
                        )
                    self.assertEqual(denied.exception.code, 403)
                # 参数在场但伪造 / 单参 / 过期 / 篡改到期，一律 403。
                for query in (
                    "sign=abc&t=99",
                    f"sign={_sign('/' + cas_key, fresh, self.SIGN_KEY)}",
                    f"t={fresh}",
                    f"sign={_sign('/' + cas_key, stale, self.SIGN_KEY)}&t={stale}",
                    f"sign={_sign('/' + cas_key, fresh, self.SIGN_KEY)}&t={fresh + 1}",
                    f"sign={_sign('/' + cas_key, fresh, 'wrong-key')}&t={fresh}",
                ):
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        urllib.request.urlopen(
                            f"{base}/{cas_key}?{query}", timeout=2
                        )
                    self.assertEqual(denied.exception.code, 403)
                # 真实且未过期的签名放行，GET 与 Range 均可。
                with urllib.request.urlopen(
                    f"{base}/{cas_key}?{good_query}", timeout=2
                ) as response:
                    self.assertEqual(response.status, 200)
                range_request = urllib.request.Request(
                    f"{base}/{cas_key}?{good_query}",
                    headers={"Range": "bytes=0-1"},
                )
                with urllib.request.urlopen(range_request, timeout=2) as response:
                    self.assertEqual(response.status, 206)
                # 公开切片保持匿名可达。
                with urllib.request.urlopen(
                    f"{base}/{public_key}", timeout=2
                ) as response:
                    self.assertEqual(response.status, 200)
                # 路径变体不得绕过守卫：dot-segment 与双前导斜杠在前缀
                # 匹配前必须归一化到 translate_path 实际服务的同一路径。
                for variant in (
                    f"/ignored/../{cas_key}",
                    f"//{cas_key}",
                    f"/./{cas_key}",
                ):
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        urllib.request.urlopen(f"{base}{variant}", timeout=2)
                    self.assertEqual(denied.exception.code, 403)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)

    def test_missing_sign_key_fails_closed_for_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cas_key = "media/objects/sha256/aa/bb/" + "b" * 64 + ".jpg"
            public_key = "media/image/s/asset/image-002/v1/source.webp"
            for key in (cas_key, public_key):
                target = root / key
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"payload")
            server, worker = self._serve(root, sign_key=None)
            base = f"http://127.0.0.1:{server.server_port}"
            fresh = int(time.time()) + 600
            try:
                # signKey 未配置：即使签名真实也 403，不退回参数在场即放行。
                query = f"sign={_sign('/' + cas_key, fresh, self.SIGN_KEY)}&t={fresh}"
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(f"{base}/{cas_key}?{query}", timeout=2)
                self.assertEqual(denied.exception.code, 403)
                # 公开切片不受影响。
                with urllib.request.urlopen(
                    f"{base}/{public_key}", timeout=2
                ) as response:
                    self.assertEqual(response.status, 200)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
