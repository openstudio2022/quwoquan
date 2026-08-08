"""锁定 page_object_contract 路径同步工具的行为契约。

覆盖：唯一定位才修、幂等、外科手术式改写、git 重命名链优先、无法唯一定位必须
报人工裁决，以及全部 object-presentation 页面的 owner/participant/public-seam REVIEW。
"""

from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


ROOT = Path(__file__).resolve().parents[3]
SUBJECT_PATH = ROOT / "quwoquan_service/scripts/contracts/sync_page_object_source_paths.py"


def _load_subject():
    name = "sync_page_object_source_paths_under_test"
    specification = importlib.util.spec_from_file_location(name, SUBJECT_PATH)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    # dataclasses 解析 field(default_factory=...) 时会回查 sys.modules，必须先注册。
    sys.modules[name] = module
    # 仓库禁止源码树出现 __pycache__，加载被测脚本时不得写字节码。
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        specification.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


subject = _load_subject()


CONTRACT_HEADER = """contract_id: app_page_object_contract
schema: app_page_object_contract
source_path_root: quwoquan_app
description: |
  测试用最小契约；本文件的注释与 flow-style 必须逐字节保留。

pages:
"""


def page_block(
    page_id: str,
    source_path: str,
    *,
    entry_widget: str,
    object_ids: list[str],
    page_kind: str = "routed",
    mount_evidence: list[str] | None = None,
) -> str:
    lines = [
        f"  - page_id: {page_id}",
        f"    source_path: {source_path}",
        f"    page_kind: {page_kind}",
        f"    object_ids: [{', '.join(object_ids)}]",
        "    capability_requirements: { all_of: [], any_of: [] }",
        f"    entry_widget: {entry_widget}",
    ]
    if mount_evidence is not None:
        lines.append(f"    mount_evidence: [{', '.join(mount_evidence)}]")
    return "\n".join(lines) + "\n\n"


class PageObjectSourcePathSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / subject.APP_DIR_NAME
        self.contract = self.root / subject.CONTRACT_REL
        self.contract.parent.mkdir(parents=True)

    # -- 构造 ---------------------------------------------------------------

    def write_dart(self, relative: str, widget: str) -> None:
        target = self.app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"class {widget} extends StatelessWidget {{}}\n", encoding="utf-8"
        )

    def write_dart_text(self, relative: str, text: str) -> None:
        target = self.app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    @staticmethod
    def service_shape(path: str):
        parts = Path(path).parts
        if (
            len(parts) < 7
            or parts[0] != "lib"
            or parts[1] != "service"
            or parts[5] not in {"domain", "application", "adapters", "presentation"}
        ):
            return None
        return parts[2].removesuffix("_service"), parts[3], parts[4], parts[5]

    def write_contract(self, *blocks: str) -> None:
        self.contract.write_text(CONTRACT_HEADER + "".join(blocks), encoding="utf-8")

    def run_sync(self, *, write: bool = True, shape_of=None, disk_scan_paths=None):
        return subject.sync(
            self.root,
            write=write,
            shape_of=shape_of,
            disk_scan_paths=disk_scan_paths,
        )

    # -- 契约 ---------------------------------------------------------------

    def test_no_drift_leaves_file_untouched(self) -> None:
        self.write_dart("lib/ui/circle/pages/circle_detail_page.dart", "CircleDetailPage")
        self.write_contract(
            page_block(
                "circle.detail",
                "lib/ui/circle/pages/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )
        before = self.contract.read_bytes()
        report = self.run_sync()
        self.assertEqual(report.drift_total, 0)
        self.assertFalse(report.changed)
        self.assertEqual(self.contract.read_bytes(), before)

    def test_unique_basename_match_is_repaired_surgically(self) -> None:
        self.write_dart(
            "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
            "CircleDetailPage",
        )
        self.write_contract(
            page_block(
                "circle.detail",
                "lib/ui/circle/pages/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )
        before = self.contract.read_text(encoding="utf-8")
        report = self.run_sync()

        self.assertEqual([fix.page_id for fix in report.fixes], ["circle.detail"])
        self.assertEqual(report.fixes[0].field_name, "source_path")
        self.assertEqual(
            report.fixes[0].new_path,
            "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
        )
        self.assertEqual(report.manual, [])
        self.assertTrue(report.changed)

        after = self.contract.read_text(encoding="utf-8")
        changed = [
            (old, new)
            for old, new in zip(before.splitlines(), after.splitlines())
            if old != new
        ]
        self.assertEqual(len(changed), 1, changed)
        self.assertIn("source_path:", changed[0][1])
        # 注释、flow-style 与空行必须逐字节保留。
        self.assertIn("capability_requirements: { all_of: [], any_of: [] }", after)
        self.assertIn("测试用最小契约", after)

    def test_second_run_is_idempotent(self) -> None:
        self.write_dart(
            "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
            "CircleDetailPage",
        )
        self.write_contract(
            page_block(
                "circle.detail",
                "lib/ui/circle/pages/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )
        self.run_sync()
        first = self.contract.read_bytes()
        second_report = self.run_sync()
        self.assertEqual(second_report.drift_total, 0)
        self.assertFalse(second_report.changed)
        self.assertEqual(self.contract.read_bytes(), first)

    def test_check_mode_never_writes(self) -> None:
        self.write_dart(
            "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
            "CircleDetailPage",
        )
        self.write_contract(
            page_block(
                "circle.detail",
                "lib/ui/circle/pages/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )
        before = self.contract.read_bytes()
        report = self.run_sync(write=False)
        self.assertEqual(len(report.fixes), 1)
        self.assertFalse(report.changed)
        self.assertEqual(self.contract.read_bytes(), before)

    def test_missing_file_requires_manual_decision(self) -> None:
        self.write_contract(
            page_block(
                "circle.detail",
                "lib/ui/circle/pages/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )
        before = self.contract.read_bytes()
        report = self.run_sync()
        self.assertEqual(report.fixes, [])
        self.assertEqual([item.page_id for item in report.manual], ["circle.detail"])
        self.assertEqual(self.contract.read_bytes(), before)

    def test_multiple_candidates_require_manual_decision(self) -> None:
        for relative in (
            "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
            "lib/service/content_service/content/post/presentation/circle_detail_page.dart",
        ):
            self.write_dart(relative, "CircleDetailPage")
        self.write_contract(
            page_block(
                "circle.detail",
                "lib/ui/circle/pages/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )
        before = self.contract.read_bytes()
        report = self.run_sync()
        self.assertEqual(report.fixes, [])
        self.assertEqual(len(report.manual), 1)
        self.assertEqual(len(report.manual[0].candidates), 2)
        self.assertEqual(self.contract.read_bytes(), before)

    def test_entry_widget_narrows_same_name_candidates(self) -> None:
        self.write_dart(
            "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
            "CircleDetailPage",
        )
        self.write_dart(
            "lib/service/content_service/content/post/presentation/circle_detail_page.dart",
            "SomethingElsePage",
        )
        self.write_contract(
            page_block(
                "circle.detail",
                "lib/ui/circle/pages/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )
        report = self.run_sync()
        self.assertEqual(report.manual, [])
        self.assertEqual(
            report.fixes[0].new_path,
            "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
        )

    def test_new_path_must_not_steal_another_page_claim(self) -> None:
        self.write_dart(
            "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
            "CircleDetailPage",
        )
        self.write_contract(
            page_block(
                "circle.detail_owner",
                "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            ),
            page_block(
                "circle.detail_stale",
                "lib/ui/circle/pages/circle_detail_page.dart",
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            ),
        )
        report = self.run_sync()
        self.assertEqual(report.fixes, [])
        self.assertEqual([item.page_id for item in report.manual], ["circle.detail_stale"])

    def test_mount_evidence_path_is_synced(self) -> None:
        self.write_dart(
            "lib/service/circle_service/circle_management/circle/presentation/circle_shell.dart", "CircleShell"
        )
        (self.app / "lib/service/circle_service/circle_management/circle/presentation/circle_shell.dart").write_text(
            "class CircleShell {}\nconst mounted = ObjectDetailGlobalBottomNav();\n",
            encoding="utf-8",
        )
        self.write_dart(
            "lib/app/shell/object_detail_global_bottom_nav.dart",
            "ObjectDetailGlobalBottomNav",
        )
        self.write_contract(
            page_block(
                "app.object_detail_bottom_navigation",
                "lib/app/shell/object_detail_global_bottom_nav.dart",
                entry_widget="ObjectDetailGlobalBottomNav",
                object_ids=[],
                mount_evidence=["lib/ui/circle/widgets/circle_shell.dart"],
            )
        )
        report = self.run_sync()
        self.assertEqual(report.manual, [])
        self.assertEqual(
            [(fix.field_name, fix.new_path) for fix in report.fixes],
            [
                (
                    "mount_evidence",
                    "lib/service/circle_service/circle_management/circle/presentation/circle_shell.dart",
                )
            ],
        )
        document = yaml.safe_load(self.contract.read_text(encoding="utf-8"))
        self.assertEqual(
            document["pages"][0]["mount_evidence"],
            ["lib/service/circle_service/circle_management/circle/presentation/circle_shell.dart"],
        )

    def test_multi_object_page_with_declared_physical_owner_is_not_reported(self) -> None:
        source = "lib/service/assistant_service/assistant/assistant_run/presentation/session_page.dart"
        self.write_dart(source, "SessionPage")
        self.write_contract(
            page_block(
                "assistant.personal_session",
                source,
                entry_widget="SessionPage",
                object_ids=["assistant.assistant_run", "notification.notification"],
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(
            [
                item
                for item in report.review
                if item.kind == "object_presentation_participant_drift"
            ],
            [],
        )

    def test_multi_object_page_missing_physical_owner_is_reported(self) -> None:
        source = "lib/service/assistant_service/assistant/assistant_run/presentation/session_page.dart"
        self.write_dart(source, "SessionPage")
        self.write_contract(
            page_block(
                "assistant.personal_session",
                source,
                entry_widget="SessionPage",
                object_ids=["assistant.assistant_session", "notification.notification"],
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        finding = next(
            item
            for item in report.review
            if item.kind == "object_presentation_participant_drift"
        )
        self.assertEqual(finding.page_id, "assistant.personal_session")
        self.assertIn("派生 physical owner assistant.assistant_run 未出现在 object_ids", finding.detail)
        self.assertIn("notification.notification", finding.detail)

    def test_unresolvable_object_presentation_is_reported(self) -> None:
        source = "lib/service/fake_service/fake_context/fake_owner/presentation/fake_page.dart"
        self.write_dart(source, "FakeShellPage")
        self.write_contract(
            page_block(
                "app.fake_shell",
                source,
                entry_widget="FakeShellPage",
                object_ids=["ops.app_release", "ops.recovery_failure"],
            )
        )

        report = self.run_sync(shape_of=lambda _: None)
        self.assertEqual(len(report.review), 1)
        self.assertIn("无法从 ContractGraph roster", report.review[0].detail)

    def test_duplicate_participant_set_is_reported(self) -> None:
        source = "lib/service/assistant_service/assistant/assistant_run/presentation/session_page.dart"
        self.write_dart(source, "SessionPage")
        self.write_contract(
            page_block(
                "assistant.personal_session",
                source,
                entry_widget="SessionPage",
                object_ids=["assistant.assistant_run", "assistant.assistant_run"],
            )
        )

        report = self.run_sync(
            shape_of=self.service_shape
        )
        self.assertEqual(len(report.review), 1)
        self.assertIn("重复 participant", report.review[0].detail)
        self.assertIn("assistant.assistant_run", report.review[0].detail)

    def test_route_less_runtime_shell_is_outside_object_owner_review(self) -> None:
        source = "lib/runtime/shell/recovery/startup_recovery_page.dart"
        self.write_dart(source, "StartupRecoveryPage")
        self.write_contract(
            page_block(
                "app.startup_recovery",
                source,
                entry_widget="StartupRecoveryPage",
                object_ids=["ops.app_release", "ops.recovery_failure"],
                page_kind="shell",
            )
        )

        report = self.run_sync(shape_of=lambda _: None)
        self.assertEqual(report.review, [])

    def test_single_object_page_in_presentation_is_not_reported(self) -> None:
        source = "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart"
        self.write_dart(source, "CircleDetailPage")
        self.write_contract(
            page_block(
                "circle.detail",
                source,
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(
            [
                item
                for item in report.review
                if item.kind == "object_presentation_participant_drift"
            ],
            [],
        )

    def test_empty_routed_object_page_is_reported(self) -> None:
        source = (
            "lib/service/circle_service/circle_management/circle/"
            "presentation/circle_detail_page.dart"
        )
        self.write_dart(source, "CircleDetailPage")
        self.write_contract(
            page_block(
                "circle.detail",
                source,
                entry_widget="CircleDetailPage",
                object_ids=[],
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(len(report.review), 1)
        self.assertIn("physical owner circle.circle 未出现在 object_ids", report.review[0].detail)

    def test_single_other_participant_on_routed_page_is_reported(self) -> None:
        source = (
            "lib/service/circle_service/circle_management/circle/"
            "presentation/circle_detail_page.dart"
        )
        self.write_dart(source, "CircleDetailPage")
        self.write_contract(
            page_block(
                "circle.detail",
                source,
                entry_widget="CircleDetailPage",
                object_ids=["content.post"],
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(len(report.review), 1)
        self.assertIn("physical owner circle.circle 未出现在 object_ids", report.review[0].detail)

    def test_embedded_cross_object_public_consumer_need_not_claim_physical_owner(self) -> None:
        source = (
            "lib/service/content_service/media/media_upload_session/"
            "presentation/camera_capture_page.dart"
        )
        filter_port = (
            "lib/service/content_service/media/filter_catalog_release/"
            "application/public/image_editor_filter_catalog.dart"
        )
        self.write_dart_text(
            filter_port,
            "abstract interface class ImageEditorFilterCatalog {}\n",
        )
        self.write_dart_text(
            source,
            "import 'package:quwoquan_app/service/content_service/media/"
            "filter_catalog_release/application/public/"
            "image_editor_filter_catalog.dart';\n"
            "class CameraCapturePage extends StatelessWidget {\n"
            "  CameraCapturePage(this.catalog);\n"
            "  final ImageEditorFilterCatalog catalog;\n"
            "}\n",
        )
        self.write_contract(
            page_block(
                "media.camera_capture",
                source,
                entry_widget="CameraCapturePage",
                object_ids=["content.filter_catalog_release"],
                page_kind="embedded",
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(report.review, [])

    def test_missing_cross_object_public_port_used_from_part_is_reported(self) -> None:
        source = (
            "lib/service/content_service/media/media_upload_session/"
            "presentation/camera_capture_page.dart"
        )
        filter_port = (
            "lib/service/content_service/media/filter_catalog_release/"
            "application/public/image_editor_filter_catalog.dart"
        )
        self.write_dart_text(
            filter_port,
            "abstract interface class ImageEditorFilterCatalog {}\n",
        )
        self.write_dart_text(
            source,
            "import 'package:quwoquan_app/service/content_service/media/"
            "filter_catalog_release/application/public/"
            "image_editor_filter_catalog.dart';\n"
            "part 'camera_capture_page_body.dart';\n"
            "class CameraCapturePage extends StatelessWidget {}\n",
        )
        self.write_dart_text(
            "lib/service/content_service/media/media_upload_session/"
            "presentation/camera_capture_page_body.dart",
            "part of 'camera_capture_page.dart';\n"
            "final class CameraCaptureBody {\n"
            "  CameraCaptureBody(this.catalog);\n"
            "  final ImageEditorFilterCatalog catalog;\n"
            "}\n",
        )
        self.write_contract(
            page_block(
                "media.camera_capture",
                source,
                entry_widget="CameraCapturePage",
                object_ids=[],
                page_kind="embedded",
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(len(report.review), 1)
        self.assertIn("content.filter_catalog_release", report.review[0].detail)
        self.assertIn("image_editor_filter_catalog.dart", report.review[0].detail)
        self.assertIn("ImageEditorFilterCatalog", report.review[0].detail)

    def test_missing_cross_object_public_provider_is_reported(self) -> None:
        source = (
            "lib/service/content_service/media/media_upload_session/"
            "presentation/camera_capture_page.dart"
        )
        filter_provider = (
            "lib/service/content_service/media/filter_catalog_release/"
            "application/public/filter_catalog_provider.dart"
        )
        self.write_dart_text(
            filter_provider,
            "final filterCatalogProvider = Provider<Object>((ref) => Object());\n",
        )
        self.write_dart_text(
            source,
            "import 'package:quwoquan_app/service/content_service/media/"
            "filter_catalog_release/application/public/"
            "filter_catalog_provider.dart';\n"
            "final catalog = ref.watch(filterCatalogProvider);\n"
            "class CameraCapturePage extends StatelessWidget {}\n",
        )
        self.write_contract(
            page_block(
                "media.camera_capture",
                source,
                entry_widget="CameraCapturePage",
                object_ids=[],
                page_kind="embedded",
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(len(report.review), 1)
        self.assertIn("filterCatalogProvider", report.review[0].detail)

    def test_public_typed_value_and_static_resolver_do_not_create_participant(self) -> None:
        source = (
            "lib/service/content_service/media/media_upload_session/"
            "presentation/camera_capture_page.dart"
        )
        route_value = (
            "lib/service/content_service/media/filter_catalog_release/"
            "application/public/filter_catalog_route_extra.dart"
        )
        self.write_dart_text(
            route_value,
            "class FilterCatalogRouteExtra {}\n"
            "abstract final class FilterCatalogResolver {\n"
            "  static FilterCatalogRouteExtra resolve() => FilterCatalogRouteExtra();\n"
            "}\n",
        )
        self.write_dart_text(
            source,
            "import 'package:quwoquan_app/service/content_service/media/"
            "filter_catalog_release/application/public/"
            "filter_catalog_route_extra.dart';\n"
            "final extra = FilterCatalogResolver.resolve();\n"
            "class CameraCapturePage extends StatelessWidget {}\n",
        )
        self.write_contract(
            page_block(
                "media.camera_capture",
                source,
                entry_widget="CameraCapturePage",
                object_ids=[],
                page_kind="embedded",
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(report.review, [])

    def test_typed_intent_consumed_from_instance_coordinator_seam_is_reported(self) -> None:
        source = (
            "lib/service/chat_service/chat/conversation/"
            "presentation/chat_conversation_page.dart"
        )
        rtc_entry = (
            "lib/service/rtc_service/rtc/call_session/application/public/"
            "rtc_call_entry_coordinator.dart"
        )
        self.write_dart_text(
            rtc_entry,
            "enum RtcCallEntryMediaType { audio, video }\n"
            "final class RtcCallEntryIntent {\n"
            "  const RtcCallEntryIntent(this.mediaType);\n"
            "  final RtcCallEntryMediaType mediaType;\n"
            "}\n"
            "final class RtcCallEntryCoordinator {\n"
            "  Future<void> initiate(RtcCallEntryIntent intent) async {}\n"
            "}\n",
        )
        self.write_dart_text(
            source,
            "import 'package:quwoquan_app/service/rtc_service/rtc/call_session/"
            "application/public/rtc_call_entry_coordinator.dart';\n"
            "final intent = RtcCallEntryIntent(RtcCallEntryMediaType.audio);\n"
            "class ChatConversationPage extends StatelessWidget {}\n",
        )
        self.write_contract(
            page_block(
                "chat.detail",
                source,
                entry_widget="ChatConversationPage",
                object_ids=["chat.conversation"],
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(len(report.review), 1)
        self.assertIn("rtc.call_session", report.review[0].detail)
        self.assertIn("RtcCallEntryCoordinator", report.review[0].detail)

    def test_static_coordinator_and_value_with_instance_helper_do_not_create_participant(self) -> None:
        source = (
            "lib/service/content_service/media/media_upload_session/"
            "presentation/camera_capture_page.dart"
        )
        route_value = (
            "lib/service/content_service/media/filter_catalog_release/"
            "application/public/filter_catalog_route_extra.dart"
        )
        self.write_dart_text(
            route_value,
            "final class FilterCatalogRouteExtra {\n"
            "  String normalized() => 'route';\n"
            "}\n"
            "abstract final class FilterCatalogCoordinator {\n"
            "  static FilterCatalogRouteExtra resolve() => FilterCatalogRouteExtra();\n"
            "}\n",
        )
        self.write_dart_text(
            source,
            "import 'package:quwoquan_app/service/content_service/media/"
            "filter_catalog_release/application/public/"
            "filter_catalog_route_extra.dart';\n"
            "final extra = FilterCatalogCoordinator.resolve();\n"
            "class CameraCapturePage extends StatelessWidget {}\n",
        )
        self.write_contract(
            page_block(
                "media.camera_capture",
                source,
                entry_widget="CameraCapturePage",
                object_ids=[],
                page_kind="embedded",
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(report.review, [])

    def test_commented_public_import_does_not_create_participant(self) -> None:
        source = (
            "lib/service/content_service/media/media_upload_session/"
            "presentation/camera_capture_page.dart"
        )
        filter_port = (
            "lib/service/content_service/media/filter_catalog_release/"
            "application/public/image_editor_filter_catalog.dart"
        )
        self.write_dart_text(
            filter_port,
            "abstract interface class ImageEditorFilterCatalog {}\n",
        )
        self.write_dart_text(
            source,
            "/* import 'package:quwoquan_app/service/content_service/media/"
            "filter_catalog_release/application/public/"
            "image_editor_filter_catalog.dart'; */\n"
            "const fakeImport = \"import 'package:quwoquan_app/service/"
            "content_service/media/filter_catalog_release/application/public/"
            "image_editor_filter_catalog.dart'; ImageEditorFilterCatalog\";\n"
            "class CameraCapturePage extends StatelessWidget {}\n",
        )
        self.write_contract(
            page_block(
                "media.camera_capture",
                source,
                entry_widget="CameraCapturePage",
                object_ids=[],
                page_kind="embedded",
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(report.review, [])

    def test_generated_and_runtime_public_imports_do_not_create_participant(self) -> None:
        source = (
            "lib/service/content_service/media/media_upload_session/"
            "presentation/camera_capture_page.dart"
        )
        generated_port = (
            "lib/service/content_service/media/filter_catalog_release/"
            "application/public/generated/filter_catalog_port.g.dart"
        )
        runtime_port = "lib/runtime/application/public/runtime_media_port.dart"
        self.write_dart_text(
            generated_port,
            "abstract interface class GeneratedFilterCatalogPort {}\n",
        )
        self.write_dart_text(
            runtime_port,
            "abstract interface class RuntimeMediaPort {}\n",
        )
        self.write_dart_text(
            source,
            "import 'package:quwoquan_app/service/content_service/media/"
            "filter_catalog_release/application/public/generated/"
            "filter_catalog_port.g.dart';\n"
            "import 'package:quwoquan_app/runtime/application/public/"
            "runtime_media_port.dart';\n"
            "final GeneratedFilterCatalogPort? generatedPort = null;\n"
            "final RuntimeMediaPort? runtimePort = null;\n"
            "class CameraCapturePage extends StatelessWidget {}\n",
        )
        self.write_contract(
            page_block(
                "media.camera_capture",
                source,
                entry_widget="CameraCapturePage",
                object_ids=[],
                page_kind="embedded",
            )
        )

        report = self.run_sync(shape_of=self.service_shape)
        self.assertEqual(report.review, [])

    def test_page_outside_disk_scan_set_is_reported(self) -> None:
        source = "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart"
        self.write_dart(source, "CircleDetailPage")
        self.write_contract(
            page_block(
                "circle.detail",
                source,
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            )
        )
        report = self.run_sync(disk_scan_paths=frozenset())
        self.assertEqual(
            [item.kind for item in report.review], ["outside_page_scan_set"]
        )
        report_in_set = self.run_sync(disk_scan_paths=frozenset({source}))
        self.assertEqual(report_in_set.review, [])


class GateFailureClassificationTest(unittest.TestCase):
    """门禁失败必须按「谁能修」分类，避免每轮人工重读 flat 列表。"""

    def test_each_failure_lands_in_its_owner_bucket(self) -> None:
        output = "\n".join(
            (
                "page_object_contract: FAIL",
                "  - canonical source 不在页面扫描集: lib/service/circle_service/circle_management/circle/presentation/x_page.dart",
                "  - circle.detail: source_path 不存在: lib/ui/circle/pages/x_page.dart",
                "  - rtc.incoming: typed_presentation 在 App/Contract Dart 中不存在: CallSessionDto",
                "  - circle.detail: experience_owner 'circle' 无 UI 路径、父页面或服务领域佐证",
                "  - circle.detail: mount evidence 未消费 entry_widget CircleDetailPage",
                "  - 某条尚未归类的新失败",
            )
        )
        classified = subject.classify_gate_failures(output)
        self.assertEqual(len(classified["page_scan_set_gap"]), 1)
        self.assertEqual(len(classified["contract_path_drift"]), 1)
        self.assertEqual(len(classified["contract_reference_drift"]), 1)
        self.assertEqual(len(classified["owner_or_object_missing"]), 1)
        self.assertEqual(len(classified["assembly_evidence_broken"]), 1)
        self.assertEqual(len(classified["unclassified"]), 1)

    def test_passing_gate_yields_no_failures(self) -> None:
        self.assertEqual(
            subject.classify_gate_failures("page_object_contract: OK (95 pages)"), {}
        )


class RunReportTest(unittest.TestCase):
    def test_report_is_disposable_run_output_not_a_ledger(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name) / "page-object-source-path"
        payload = {
            "schema": "page-object-source-path-sync-run",
            "scanAt": "2026-08-04T12:00:00Z",
            "headCommit": "0" * 40,
            "mode": "write",
            "sync": {
                "totalPages": 95,
                "driftTotal": 0,
                "changed": False,
                "fixes": [],
                "manual": [],
                "review": [],
            },
        }
        subject.write_run_report(target, payload)
        markdown = (target / "report.md").read_text(encoding="utf-8")
        self.assertIn("可删除可重建", markdown)
        self.assertIn("不是台账", markdown)
        self.assertIn("0" * 40, markdown)


class GitRenameEvidenceTest(unittest.TestCase):
    """git 重命名链是最权威证据，必须能压过同名诱饵文件。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / subject.APP_DIR_NAME
        self.contract = self.root / subject.CONTRACT_REL
        self.contract.parent.mkdir(parents=True)
        self.git("init", "-q")
        self.git("config", "user.email", "gate@example.invalid")
        self.git("config", "user.name", "gate")

    def git(self, *arguments: str) -> None:
        subprocess.run(
            ["git", *arguments], cwd=self.root, check=True, capture_output=True
        )

    def write(self, relative: str, body: str) -> None:
        target = self.app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_rename_chain_disambiguates_same_name_candidates(self) -> None:
        old = "lib/ui/circle/pages/circle_detail_page.dart"
        new = "lib/service/circle_service/circle_management/circle/presentation/circle_detail_page.dart"
        decoy = "lib/service/content_service/content/post/presentation/circle_detail_page.dart"
        body = "class CircleDetailPage {}\n" + "// padding\n" * 40
        self.write(old, body)
        self.write(decoy, body)
        self.contract.write_text(
            CONTRACT_HEADER
            + page_block(
                "circle.detail",
                old,
                entry_widget="CircleDetailPage",
                object_ids=["circle.circle"],
            ),
            encoding="utf-8",
        )
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")

        moved = self.app / new
        moved.parent.mkdir(parents=True, exist_ok=True)
        (self.app / old).rename(moved)
        self.git("add", "-A")
        self.git("commit", "-qm", "move page into object tree")

        report = subject.sync(self.root, write=True)
        self.assertEqual(report.manual, [])
        self.assertEqual(len(report.fixes), 1)
        self.assertEqual(report.fixes[0].method, "git_rename")
        self.assertEqual(report.fixes[0].new_path, new)


if __name__ == "__main__":
    unittest.main()
