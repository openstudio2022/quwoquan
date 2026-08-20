"""local_contract: release-bound 媒体交付契约门禁的正负例。

门禁没有可单独调用的判定函数，只有一个 module 级 `ROOT` 与一次整仓扫描，
所以这里把 `ROOT` 指到临时树，再用门禁自己声明的 `_required_markers()` 反向
物化一棵"恰好合规"的合成仓库。这样合成树与判据同源：任何一条 marker 或禁令
被删掉，合成树的对应负例立刻不再报红，而不是靠真实仓库碰巧还留着违规样本。
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_data/scripts/verify/verify_media_release_contract.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_media_release_contract_companion",
        MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append(path: Path, text: str) -> None:
    _write(path, path.read_text(encoding="utf-8") + text)


class MediaReleaseContractGateTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gate = _load_module()
        self.gate.ROOT = self.root
        # 合规基线由门禁自己的 owner/marker 声明生成：每个 owner 落盘一份只含
        # 其全部 marker 的文件，扫描面因此只有本用例显式注入的那一条违规。
        self.owners = dict(self.gate._required_markers())
        for path, markers in self.owners.items():
            _write(path, "\n".join(markers) + "\n")
        self.scripts = self.root / "quwoquan_data" / "scripts"
        self.content_service = (
            self.root / "quwoquan_service" / "services" / "content-service"
        )

    def _violations(self) -> list[str]:
        return self.gate._contract_violations()

    def _assert_rejected(self, needle: str) -> None:
        violations = self._violations()
        self.assertTrue(
            any(needle in item for item in violations),
            msg=f"expected a violation containing {needle!r}, got {violations}",
        )
        self.assertEqual(self.gate.main(), 2)

    def test_declared_contract_owners_are_accepted(self) -> None:
        self.assertEqual(self._violations(), [])
        self.assertEqual(self.gate.main(), 0)

    def test_missing_contract_owner_is_rejected(self) -> None:
        resolver = next(
            path
            for path in self.owners
            if path.name == "media_asset_manifest_resolver.dart"
        )
        resolver.unlink()
        self._assert_rejected("required contract owner missing")

    def test_dropped_marker_is_rejected(self) -> None:
        # release_runtime 的 media-sync.json 是环境 ship 侧读取清单的唯一入口；
        # 它消失意味着 release 与环境之间的媒体交付面断开而没有任何编译错误。
        runtime = (
            self.scripts / "content" / "release" / "environment" / "release_runtime.py"
        )
        markers = [
            marker for marker in self.owners[runtime] if marker != '"media-sync.json"'
        ]
        _write(runtime, "\n".join(markers) + "\n")
        self._assert_rejected("missing media contract marker '\"media-sync.json\"'")

    def test_stub_media_domain_is_rejected(self) -> None:
        _append(
            self.scripts / "core" / "media_asset_url.py",
            'STUB_BASE = "https://cdn.example/media"\n',
        )
        self._assert_rejected("forbidden stub media domain")

    def test_retired_ship_path_is_rejected(self) -> None:
        _append(
            self.scripts / "core" / "media_asset_url.py",
            "from quwoquan_data.scripts.ship import upload\n",
        )
        self._assert_rejected("retired media ship path")

    def test_private_object_key_projection_is_rejected(self) -> None:
        # 私有 objectKey 直接拼 mediaBaseURL 会把 CAS 私有键投影成对外 URL；
        # public slice 派生是唯一合法出口，所以这条拼接必须在门禁面报红。
        _append(
            self.content_service / "cmd" / "import" / "main.go",
            'key := strings.TrimLeft(asset.ObjectKey, "/")\n',
        )
        self._assert_rejected("forbidden mediaBaseURL + private objectKey projection")

    def test_generic_media_base_url_flag_is_rejected(self) -> None:
        _append(
            self.scripts / "content" / "release" / "environment" / "importers.py",
            'flags = ["--media-base-url"]\n',
        )
        self._assert_rejected("generic media base URL is retired")

    def test_retired_video_frame_route_is_rejected(self) -> None:
        _append(
            self.scripts / "content" / "post" / "video" / "materialize.py",
            "MODE = 'rights_cleared_image_sequence'\n",
        )
        self._assert_rejected("retired video frame route")

    def test_test_sources_are_outside_the_scan(self) -> None:
        # 门禁刻意不扫测试树：负例样本本来就要写出被禁形态。这条把"排除"钉成
        # 判据的一部分，避免有人为了让扫描更"严"而顺手删掉排除条件。
        forbidden = (
            'BASE = "https://cdn.example/media"\n'
            "from quwoquan_data.scripts.ship import upload\n"
            'FLAG = "--media-base-url"\n'
            "MODE = 'rights_cleared_image_sequence'\n"
        )
        _write(self.scripts / "tests" / "media_case.py", forbidden)
        _write(self.scripts / "core" / "media_asset_url_test.py", forbidden)
        self.assertEqual(self._violations(), [])
        self.assertEqual(self.gate.main(), 0)

    def test_retired_video_package_module_is_rejected(self) -> None:
        _write(
            self.scripts / "content" / "post" / "video" / "package.py",
            "def package() -> None:\n    return None\n",
        )
        self._assert_rejected("retired image-sequence video package still exists")

    def test_opaque_unicode_public_segment_is_rejected(self) -> None:
        _append(
            self.root / "quwoquan_service" / "runtime" / "media" / "asset_ref.go",
            'const prefix = "unicode-"\n',
        )
        self._assert_rejected("retired opaque unicode- public asset segment")

    def test_retired_video_frame_schema_field_is_rejected(self) -> None:
        _append(
            self.root / "quwoquan_data" / "schema" / "content" / "compose.schema.json",
            '"sourceFrames"\n',
        )
        self._assert_rejected("retired video frame schema route")

    def test_release_importer_media_authority_bypass_is_rejected(self) -> None:
        importer, _entity, _user = self.gate._release_import_roots()
        _append(importer / "runtime.go", "url := BuildPublicMediaURL(asset)\n")
        self._assert_rejected("release importer bypasses MediaAsset authority")

    def test_canonical_layer_environment_url_field_is_rejected(self) -> None:
        canonical = self.scripts / "content" / "release" / "canonical"
        _write(canonical / "promote.py", 'FIELD = "cdnUrl"\n')
        self._assert_rejected("canonical layer owns environment field")

    def test_environment_url_owners_stay_exempt(self) -> None:
        # gate.py 与 media_asset_url.py 是环境 URL 字段的唯一归属方，必须能
        # 书写这些字段名；豁免消失会让契约的持有者自己被门禁判违规。
        canonical = self.scripts / "content" / "release" / "canonical"
        _append(canonical / "gate.py", 'FIELD = "cdnUrl"\n')
        _append(self.scripts / "core" / "media_asset_url.py", 'FIELD = "videoUrl"\n')
        self.assertEqual(self._violations(), [])
        self.assertEqual(self.gate.main(), 0)

    def test_real_repository_satisfies_the_media_contract(self) -> None:
        self.assertEqual(_load_module()._contract_violations(), [])


if __name__ == "__main__":
    unittest.main()
