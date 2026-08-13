# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
# Python 1000 行硬顶治理：原单文件按场景拆分为本文件与同目录
# test_single_track_contracts__*__local_contract_test.py 兄弟文件；共享 harness
# 下沉 quwoquan_ops/tests/support/single_track_contracts_test_support.py。
# 本文件保留「contract 字段单轨与退役 domain identity 归属」场景，测试逐字搬移。

from __future__ import annotations

import sys
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.single_track_contracts_test_support import (
    ROOT,
    VERIFIER_PATH,
    _load_verifier,
    _scan_fixture,
)

class SingleTrackContractsContractTest(unittest.TestCase):
    def test_verifier_module_loads(self) -> None:
        module = _load_verifier()
        self.assertTrue(hasattr(module, "scan_file"))
        self.assertTrue(hasattr(module, "Inventory"))

    def test_contract_source_keys_fallback_is_blocked(self) -> None:
        module = _load_verifier()
        inventory = _scan_fixture(
            module,
            "quwoquan_service/services/circle-service/contracts/"
            "circle_management/circle/projections/member_row.yaml",
            "fields:\n"
            "- name: membershipId\n"
            "  source: membershipId\n"
            "  source_keys: [membershipId, id, _id]\n"
            "  type: string\n",
        )
        self.assertEqual(
            inventory.counts.get("T1_contract_source_keys_alias", 0),
            1,
        )

    def test_contract_single_source_is_canonical(self) -> None:
        module = _load_verifier()
        inventory = _scan_fixture(
            module,
            "quwoquan_service/services/circle-service/contracts/"
            "circle_management/circle/projections/member_row.yaml",
            "fields:\n"
            "- name: membershipId\n"
            "  source: membershipId\n"
            "  type: string\n",
        )
        self.assertEqual(
            inventory.counts.get("T1_contract_source_keys_alias", 0),
            0,
        )

    def test_declared_app_paths_still_exist_on_disk(self) -> None:
        """按路径生效的扫描一旦指向已搬走的对象就静默失效，必须在测试层拦住。

        端侧对象化搬迁会整体挪动 `quwoquan_app/lib/**`；这里只覆盖端侧路径，云侧契约
        由所属服务的门禁自己盯。
        """
        module = _load_verifier()
        declared_files = (
            set(module.APP_REMOTE_CONFIG_SINGLE_IDENTITY_PATHS)
            | set(module.RUNTIME_ERROR_SINGLE_TRACK_PATHS)
            | {module.APP_ROUTER_SINGLE_TRACK_PATH}
        )
        # 入口已拆为薄入口 + 包，字面量声明散布在包内模块，源码扫描需覆盖两者。
        verifier_sources = [
            VERIFIER_PATH,
            *sorted(
                (ROOT / "quwoquan_ops/gate/single_track_contracts").glob("*.py")
            ),
        ]
        for source_path in verifier_sources:
            declared_files.update(
                path
                for path in module.re.findall(
                    r"['\"](quwoquan_app/lib/[A-Za-z0-9_./-]+\.dart)['\"]",
                    source_path.read_text(encoding="utf-8"),
                )
            )
        app_files = sorted(
            path
            for path in declared_files
            if path.startswith("quwoquan_app/")
        )
        app_roots = [module.PUBLIC_USER_MODEL_SINGLE_TRACK_ROOT]
        self.assertTrue(app_files)
        self.assertTrue(app_roots)

        missing_files = [
            path for path in app_files if not (ROOT / path).is_file()
        ]
        missing_roots = [
            path for path in app_roots if not (ROOT / path).is_dir()
        ]
        self.assertEqual(missing_files, [])
        self.assertEqual(missing_roots, [])

    def test_retired_domain_identity_fields_are_blocked_in_owner_contexts(
        self,
    ) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/services/assistant-service/contracts/assistant/"
                "assistant_policy_release/fields.yaml",
                "fields:\n  - name: releaseVersion\n"
                "  - name: canonicalDigest\n",
                2,
            ),
            (
                "quwoquan_service/services/product-ops-service/contracts/"
                "product_ops/experiment_assignment_fact/fields.yaml",
                "fields:\n  - name: policyVersion\n",
                1,
            ),
            (
                "quwoquan_service/services/recommendation-service/contracts/"
                "recommendation/recommendation_model_release/fields.yaml",
                "fields:\n  - name: modelVersion\n"
                "  - name: featureVersion\n"
                "  - name: featureContractVersion\n",
                3,
            ),
            (
                "quwoquan_service/services/assistant-service/contracts/assistant/"
                "assistant_learning_fact/fields.yaml",
                "fields:\n  - name: eventVersion\n",
                1,
            ),
        )
        for relative_path, text, expected in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(
                    inventory.counts.get(
                        "T1_retired_domain_identity_field",
                        0,
                    ),
                    expected,
                )

    def test_retired_domain_identity_scope_is_object_ownership_not_nearby_text(
        self,
    ) -> None:
        """归属只认 ContractGraph 对象领地，不认命中行附近提到了对象名。

        两个方向都必须成立，否则 ±16 行上下文判据的双向产错会复活：

        * 正例：文件落在 `product_ops/experiment_assignment_fact/` 领地内，但既不在
          product-ops-service 前缀下、附近也没有任何一行提到对象名——上下文判据会漏判。
        * 负例：文件属于 content.post，只是注释里提到了 assistant_policy_release，
          其 `releaseVersion` 是另一个概念——上下文判据会误伤。
        """
        module = _load_verifier()

        caught = _scan_fixture(
            module,
            "quwoquan_app/lib/service/product_ops_service/product_ops/experiment_assignment_fact/"
            "domain/assignment.dart",
            "class Assignment {\n  final String policyVersion;\n}\n",
        )
        self.assertEqual(
            caught.counts.get("T1_retired_domain_identity_field", 0),
            1,
            "对象自己领地内的退役字段必须命中，即使附近无人提到对象名",
        )

        clean = _scan_fixture(
            module,
            "quwoquan_service/services/content-service/internal/content/post/"
            "domain/post.go",
            "package post\n\n"
            "// 本对象的发布版本与 assistant_policy_release 无关，\n"
            "// 也不参与 AssistantPolicyRelease 的身份收敛。\n"
            "type Post struct {\n\treleaseVersion string\n}\n",
        )
        self.assertEqual(
            clean.counts.get("T1_retired_domain_identity_field", 0),
            0,
            "他人领地内的同名字段不得因附近注释提到对象名而被判违规",
        )

    def test_recommendation_identity_scope_is_derived_from_canonical_contracts(
        self,
    ) -> None:
        """recommendation 单轨范围由「谁声明 canonical 身份」派生，不由邻近文本判定。

        ±16 行上下文窗口判据双向产错：目标词在窗口外就漏判，窗口内任何注释或
        字符串字面量提到它就误判。这里把归属换成两个结构事实的合成——ContractGraph
        的对象布局，加上对象自己 contracts YAML 解析后是否声明 canonical 身份字段。
        """
        module = _load_verifier()
        segments = module._recommendation_identity_object_segments()

        self.assertIn(("recommendation", "recommendation_model_release"), segments)
        self.assertIn(("recommendation", "recommendation_exposure_fact"), segments)
        self.assertIn(("recommendation", "ranked_recommendation_window"), segments)
        # 跨服务消费者也承载 canonical modelReleaseId，因此同样在单轨范围内。
        # 上下文窗口判据永远够不到它——它的文件里不会逐行复述推荐对象名。
        self.assertIn(("content", "feed_delivery_page"), segments)

        for context, object_name in segments:
            with self.subTest(object=f"{context}/{object_name}"):
                directory = module._contract_object_source_dirs()[
                    (context, object_name)
                ]
                self.assertTrue(
                    module._object_declares_identifiers(
                        directory,
                        module.RECOMMENDATION_CANONICAL_IDENTITY_FIELDS,
                    )
                )

        self.assertFalse(
            hasattr(module, "_nearby_context"),
            "±16 行上下文窗口判据不得复活",
        )

    def test_recommendation_retired_fields_are_blocked_inside_identity_territory(
        self,
    ) -> None:
        """正例：canonical 身份承载者的领地内，第二轨版本字段必须被挡住。"""
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/services/recommendation-service/internal/"
                "recommendation/ranked_recommendation_window/domain/model.py",
                "class Window:\n    modelVersion: str\n",
                1,
            ),
            # content-service 的 feed_delivery_page 只在路径前缀判据之外，
            # 附近也没有一行提到推荐对象名——旧窗口判据在这里完全漏判。
            (
                "quwoquan_service/services/content-service/internal/content/"
                "feed_delivery_page/application/delivery.go",
                "package feed_delivery_page\n\n"
                "type Page struct {\n"
                "\tmodelVersion string\n"
                "\tfeatureContractVersion string\n"
                "}\n",
                2,
            ),
            (
                "quwoquan_service/services/content-service/contracts/content/"
                "feed_delivery_page/projections/delivery_row.yaml",
                "fields:\n  - name: featureVersion\n",
                1,
            ),
        )
        for relative_path, text, expected in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(
                    inventory.counts.get("T1_retired_domain_identity_field", 0),
                    expected,
                )

    def test_recommendation_retired_fields_stay_scoped_outside_identity_territory(
        self,
    ) -> None:
        """负例：不承载 canonical 身份的对象领地里，同名字段不得被误伤。"""
        module = _load_verifier()
        fixtures = (
            # 旧窗口判据的假阳形态：注释提到推荐对象名，字段其实属于别的概念。
            (
                "quwoquan_service/services/content-service/internal/content/"
                "post/domain/post.go",
                "package post\n\n"
                "// 本对象的特征快照与 recommendation_model_release 无关，\n"
                "// 也不参与 RecommendationModelRelease 的身份收敛。\n"
                "type Post struct {\n\tfeatureVersion string\n}\n",
                0,
            ),
            # 旧窗口判据的另一种假阳形态：字符串字面量里出现对象名。
            (
                "quwoquan_service/services/search-service/internal/search/"
                "search_index/application/indexer.py",
                'TOPIC = "recommendation_model_release"\n'
                "def build(modelVersion: str) -> None:\n    ...\n",
                0,
            ),
            # 第三方 provider 的外部 wire 版本仍属对方演进语义。
            (
                "quwoquan_service/services/content-service/internal/content/"
                "feed_delivery_page/infrastructure/providers/vendor_client.py",
                "payload = {'modelVersion': external_model_version}\n",
                0,
            ),
        )
        for relative_path, text, expected in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(
                    inventory.counts.get("T1_retired_domain_identity_field", 0),
                    expected,
                )

    def test_generated_aggregate_documents_are_not_any_single_object_territory(
        self,
    ) -> None:
        """聚合生成文档按对象归属判定，不按「附近提到了谁」判定。

        `contract_graph.json` 同时承载由当前 contracts 源派生的全部对象，其中
        content.filter_catalog_release
        合法拥有 `canonicalDigest`。上下文窗口判据下，它与 AssistantPolicyRelease 的
        距离完全取决于生成器的行序（今日 2891 行，纯属排版运气），行序一变就误伤。
        退役字段的权威拦截点是对象自己的 contracts 源文件（见上面的正例），生成产物
        由漂移校验保证同源，不存在绕过路径。
        """
        module = _load_verifier()
        inventory = _scan_fixture(
            module,
            "quwoquan_service/generated/contract_graph.json",
            '{\n  "objects": [\n'
            '    { "id": "assistant.assistant_policy_release",\n'
            '      "name": "AssistantPolicyRelease" },\n'
            '    { "id": "content.filter_catalog_release",\n'
            '      "name": "FilterCatalogRelease",\n'
            '      "fieldNames": ["canonicalDigest", "categories"] }\n'
            "  ]\n}\n",
        )
        self.assertEqual(
            inventory.counts.get("T1_retired_domain_identity_field", 0),
            0,
        )

    def test_retired_domain_identity_scopes_resolve_to_contract_graph_objects(
        self,
    ) -> None:
        """每个已收口 scope 必须绑定一个真实存在的 ContractGraph 对象。"""
        module = _load_verifier()
        for scope in module.RETIRED_DOMAIN_IDENTITY_OBJECTS:
            with self.subTest(scope=scope):
                context, object_name = module._scope_object_segments(scope)
                self.assertTrue(context)
                self.assertTrue(object_name)

    def test_retired_domain_identity_gate_preserves_legal_version_semantics(
        self,
    ) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/services/content-service/contracts/content/"
                "post/fields.yaml",
                "fields:\n  - name: aggregateVersion\n",
            ),
            (
                "quwoquan_service/services/integration-service/internal/"
                "providers/vendor/client.py",
                "payload = {'modelVersion': external_model_version}\n",
            ),
            (
                "quwoquan_service/contracts/metadata/_shared/"
                "runtime_observability.yaml",
                "forbidden_fields:\n  - eventVersion\n  - releaseVersion\n",
            ),
            (
                "quwoquan_service/services/assistant-service/contracts/assistant/"
                "assistant_policy_rollout/fields.yaml",
                "fields:\n  - name: revision\n  - name: aggregateVersion\n",
            ),
            (
                "quwoquan_service/services/product-ops-service/contracts/"
                "product_ops/experiment_assignment_fact/fields.yaml",
                "fields:\n  - name: experimentRevision\n",
            ),
            (
                "quwoquan_service/services/recommendation-service/contracts/"
                "recommendation/recommendation_model_release/fields.yaml",
                "fields:\n  - name: modelReleaseId\n"
                "  - name: featureContractDigest\n"
                "  - name: featureSnapshotAt\n",
            ),
        )
        for relative_path, text in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(
                    inventory.counts.get(
                        "T1_retired_domain_identity_field",
                        0,
                    ),
                    0,
                )


if __name__ == "__main__":
    unittest.main()
