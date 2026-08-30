"""verify_local_env_port_manifest 的 Compose→manifest 反向闭包判据固化。

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#req-005

正向校验只能证明「声明过的 role 有对应模块」，证明不了「Compose 里没有 manifest 不认识
的发布口」。本文件固化反向闭包的每条判否路径与真实仓库的 PASS 正例：门禁实现日后被回退
或放宽时，必须在这里报红，而不是靠一次会话内的手工变异验证。
"""

from __future__ import annotations

import copy
import importlib.util
import inspect as inspect_module
import pathlib as pathlib_module
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GATE = ROOT / "quwoquan_ops" / "gate" / "verify_local_env_port_manifest.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_local_env_port_manifest", GATE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalEnvPortManifestReverseClosureGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = _load_gate()
        cls.manifest = cls.gate.load_port_manifest()

    def _issues(self, manifest: dict) -> list[str]:
        return self.gate._compose_reverse_closure_issues(manifest)

    def test_real_repository_closes_both_directions(self) -> None:
        """PASS 正例：真实仓库的 Compose 闭包与 manifest 双向闭合。"""
        self.assertEqual(self.gate.validate_port_manifest(self.manifest), [])
        self.assertEqual(self._issues(self.manifest), [])

    def test_closure_covers_every_first_party_service_and_environment_compose(
        self,
    ) -> None:
        """闭包不得漏掉本地 target runtime 会合并的 authoring source。"""
        issues: list[str] = []
        sources = {
            str(path.relative_to(ROOT))
            for path in self.gate._local_compose_sources(
                issues,
                unowned_sources=self.manifest[self.gate.UNOWNED_COMPOSE_SOURCES_KEY],
            )
        }
        self.assertEqual(issues, [])
        for path in ROOT.glob("quwoquan_service/services/*/deploy/compose.yaml"):
            self.assertIn(str(path.relative_to(ROOT)), sources)
        for name in self.gate.LOCAL_ENVIRONMENT_COMPOSE:
            self.assertIn(
                f"quwoquan_ops/environments/compose/{name}",
                sources,
            )

    def test_undeclared_environment_compose_file_fails_closed(self) -> None:
        """`environments/compose/` 下新增文件必须被裁决归属，不能靠没人注意逃出闭包。"""
        adjudicated = set(self.gate.LOCAL_ENVIRONMENT_COMPOSE) | set(
            self.manifest[self.gate.UNOWNED_COMPOSE_SOURCES_KEY]
        )
        present = {
            path.name
            for path in (
                ROOT / "quwoquan_ops" / "environments" / "compose"
            ).glob("docker-compose*.y*ml")
            if path.is_file()
        }
        self.assertEqual(sorted(present - adjudicated), [])
        self.assertTrue(present)

    def test_unowned_compose_exemption_lives_in_the_manifest_not_the_gate(self) -> None:
        """豁免声明位在 manifest：门禁不能同时是判据和自己的豁免出处。"""
        self.assertFalse(hasattr(self.gate, "DEV_CONVENIENCE_COMPOSE"))
        declared = self.manifest[self.gate.UNOWNED_COMPOSE_SOURCES_KEY]
        self.assertTrue(declared)
        for name, reason in declared.items():
            self.assertTrue(str(reason).strip(), msg=f"{name} 缺豁免理由")

        missing = copy.deepcopy(self.manifest)
        missing.pop(self.gate.UNOWNED_COMPOSE_SOURCES_KEY)
        self.assertTrue(
            [
                item
                for item in self.gate.validate_port_manifest(missing)
                if "must be declared" in item
            ],
            msg="豁免声明段缺失未判否",
        )

        blank = copy.deepcopy(self.manifest)
        blank[self.gate.UNOWNED_COMPOSE_SOURCES_KEY]["docker-compose.yaml"] = ""
        self.assertTrue(
            [
                item
                for item in self.gate.validate_port_manifest(blank)
                if "reason is required" in item
            ],
            msg="豁免缺理由未判否",
        )

    def test_compose_source_globs_are_symmetric(self) -> None:
        """每个来源目录都用 `*compose.yaml`：只放宽一部分会留下静默逃逸口。"""
        for pattern in self.gate.LOCAL_COMPOSE_GLOBS:
            self.assertTrue(
                pattern.endswith("*compose.yaml"),
                msg=f"闭包 glob 不对称: {pattern}",
            )
        self.assertEqual(
            len(self.gate.LOCAL_COMPOSE_GLOBS),
            len(self.gate.COMPOSE_SOURCE_ROOTS),
        )

    def test_host_port_variable_declaration_is_required_and_role_bound(self) -> None:
        """`composeHostPortVariables` 是主机端口变量的唯一声明位，缺失或 role 不存在即判否。"""
        declared = self.manifest[self.gate.HOST_PORT_VARIABLES_KEY]
        self.assertTrue(declared)
        for name, role in declared.items():
            self.assertIn(role, self.manifest["roles"], msg=f"{name} 绑到未声明 role")

        missing = copy.deepcopy(self.manifest)
        missing.pop(self.gate.HOST_PORT_VARIABLES_KEY)
        self.assertTrue(
            [
                item
                for item in self.gate.validate_port_manifest(missing)
                if "must be declared" in item
            ],
            msg="变量声明段缺失未判否",
        )

        unknown_role = copy.deepcopy(self.manifest)
        unknown_role[self.gate.HOST_PORT_VARIABLES_KEY]["BETA_MONGO_PORT"] = "no-such"
        self.assertTrue(
            [
                item
                for item in self.gate.validate_port_manifest(unknown_role)
                if "role is not declared" in item
            ],
            msg="变量绑到未声明 role 未判否",
        )

    def test_host_port_variable_used_but_undeclared_is_rejected(self) -> None:
        """compose 里用作主机端口的变量必须已声明，否则该发布口整条逃出 canonical 断言。"""
        stripped = copy.deepcopy(self.manifest)
        stripped[self.gate.HOST_PORT_VARIABLES_KEY].pop("QWQ_DATA_FLEET_MONGO_PORT")

        issues = self._issues(stripped)

        self.assertTrue(
            [
                item
                for item in issues
                if "published host port variable is not declared" in item
            ],
            msg=f"未声明的主机端口变量未判否: {issues}",
        )

    def test_env_exports_and_manifest_declaration_must_agree(self) -> None:
        """两个声明位对同一变量的 role 说法分叉时判否；只比对交集,不要求任一侧全覆盖。"""
        drifted = copy.deepcopy(self.manifest)
        drifted[self.gate.HOST_PORT_VARIABLES_KEY]["LOCAL_GAMMA_ADMIN_PORT"] = "api-edge"

        issues = self._issues(drifted)

        self.assertTrue(
            [item for item in issues if "disagrees between ENV_EXPORTS" in item],
            msg=f"两声明位分叉未判否: {issues}",
        )
        # 交集之外不判否：ENV_EXPORTS 里多数变量并不出现在 compose 的主机端口位。
        self.assertEqual(
            self.gate._injection_declaration_agreement_issues(
                self.manifest[self.gate.HOST_PORT_VARIABLES_KEY]
            ),
            [],
        )

    def test_data_fleet_publisher_resolves_to_its_own_roles(self) -> None:
        """fleet 的发布口必须归 fleet 自有 role，不能被目标 runtime 的同名 service 抢走。"""
        roles = self.gate.compose_published_endpoint_roles(self.manifest, "beta-local")
        closure = self.gate.compose_publisher_container_role_closure(roles)

        self.assertEqual(
            closure[("data-execution-mongodb", 27017, "tcp")],
            frozenset({"data-execution-mongodb"}),
        )
        self.assertEqual(
            closure[("mongodb", 27017, "tcp")], frozenset({"mongodb"})
        )
        self.assertEqual(
            closure[("data-execution-redis", 6379, "tcp")],
            frozenset({"data-execution-redis"}),
        )
        self.assertEqual(closure[("redis", 6379, "tcp")], frozenset({"redis"}))

    def test_published_endpoint_without_any_owning_role_is_rejected(self) -> None:
        """撤掉某容器发布口的全部认领方后，Compose 那条发布口必须判否。"""
        stripped = copy.deepcopy(self.manifest)
        for role in ("user-service", "chat-service"):
            stripped["roles"][role].pop("composePublishedEndpoints")

        issues = self._issues(stripped)

        self.assertTrue(
            [item for item in issues if "no canonical role: 18081/tcp" in item],
            msg=f"未判否未认领的发布口: {issues}",
        )

    def test_non_canonical_declared_host_port_is_rejected(self) -> None:
        """字面/`:-` 缺省主机端口与 canonical 分叉时必须判否。"""
        drift = copy.deepcopy(self.manifest)
        # 19210 是 user-service 的 canonical 主机端口，slot 改掉后 Compose 里的
        # `${QWQ_COMPOSE_USER_PORT:-19210}` 缺省值不再 canonical。
        drift["roles"]["user-service"]["slotOffset"] = 390

        issues = self._issues(drift)

        self.assertTrue(
            [
                item
                for item in issues
                if "host port is not canonical for 18081/tcp: 19210" in item
            ],
            msg=f"未判否非 canonical 主机端口: {issues}",
        )

    def test_host_ip_prefixed_default_port_is_parsed_not_skipped(self) -> None:
        """`127.0.0.1:${VAR:-19210}` 必须解析出主机端口，而不是落进不判定区。

        按最后一个冒号切分会切在 `${...}` 内部，得到 `-19210}` 两不匹配而返回 `None`；
        `None` 会跳过 canonical 断言，让一条声称支持的形态变成假通过入口。
        """
        self.assertEqual(
            self.gate._declared_host_port("127.0.0.1:${QWQ_COMPOSE_USER_PORT:-19210}"),
            19210,
        )
        self.assertEqual(self.gate._declared_host_port("127.0.0.1:19210"), 19210)
        self.assertEqual(
            self.gate._declared_host_port("${QWQ_COMPOSE_USER_PORT:-19210}"), 19210
        )
        # `:?` 没有缺省值，字面上确实不可判定；它由注入反查承担，不在这里猜。
        self.assertIsNone(self.gate._declared_host_port("${VAR:?required}"))

    def test_required_form_host_port_resolves_to_its_declared_role(self) -> None:
        """`:?` 形态反查出的是 role，不是折算的 canonical 端口。

        声明段是 profile 无关的（`QWQ_COMPOSE_*` 一族按当前 target 注入，同一变量服务全部
        profile），折算只能任取一个 profile；且折算值派生自同一份 manifest，比对它等于自证。
        返回 role 才能让调用方断言一件独立的事：注入变量的 role 就是该容器端点的归属 role。
        """
        variables = self.manifest[self.gate.HOST_PORT_VARIABLES_KEY]

        self.assertEqual(
            self.gate._injected_host_port_role(
                "${LOCAL_GAMMA_ADMIN_PORT:?LOCAL_GAMMA_ADMIN_PORT is required}",
                host_port_variables=variables,
            ),
            "caddy-admin",
        )
        self.assertEqual(
            self.gate._injected_host_port_role(
                "127.0.0.1:${QWQ_DATA_FLEET_MONGO_PORT:?required}",
                host_port_variables=variables,
            ),
            "data-execution-mongodb",
        )
        self.assertIsNone(
            self.gate._injected_host_port_role(
                "${NOT_DECLARED_PORT:?required}",
                host_port_variables=variables,
            )
        )

    def test_unrecognized_host_port_form_is_rejected_not_skipped(self) -> None:
        """形态没被识别时必须判否——读不出来不能塌陷成「不可判定」而跳过断言。

        「不可判定」有两种成因：已识别形态但变量不在任何注入声明位（有界且登记在案），
        与形态本身未被识别。后者说明 gate 连该声明是什么都不知道，静默跳过会让新形态
        一出现就逃出闭包。
        """
        for recognized in (
            "19210",
            "${QWQ_COMPOSE_USER_PORT:-19210}",
            "${QWQ_DATA_FLEET_MONGO_PORT:?required}",
            "127.0.0.1:${QWQ_COMPOSE_USER_PORT:-19210}",
        ):
            self.assertTrue(
                self.gate._host_segment_is_recognized(recognized),
                msg=f"已识别形态被误判为未知: {recognized}",
            )
        for unrecognized in ("$PORT", "abc", "${A}${B}", "", "0.0.0.0:$PORT"):
            self.assertFalse(
                self.gate._host_segment_is_recognized(unrecognized),
                msg=f"未知形态被误判为已识别: {unrecognized}",
            )

        issues: list[str] = []
        parsed = self.gate._published_endpoint(
            "$PORT:18081",
            source="fixture/compose.yaml",
            service="service-core",
            issues=issues,
            host_port_variables=self.manifest[self.gate.HOST_PORT_VARIABLES_KEY],
        )

        self.assertIsNone(parsed)
        self.assertTrue(
            [item for item in issues if "host port form is unrecognized" in item],
            msg=f"未知 host 形态未判否: {issues}",
        )

    def test_required_form_yields_injected_role_instead_of_host_port(self) -> None:
        """`:?` 形态给出 injectedRole；hostPort 与 injectedRole 恰好一个有值。"""
        issues: list[str] = []
        parsed = self.gate._published_endpoint(
            "127.0.0.1:${QWQ_DATA_FLEET_MONGO_PORT:?required}:27017",
            source="fixture/compose.yaml",
            service="data-execution-mongodb",
            issues=issues,
            host_port_variables=self.manifest[self.gate.HOST_PORT_VARIABLES_KEY],
        )

        self.assertEqual(issues, [])
        self.assertIsNotNone(parsed)
        container_port, protocol, host_port, injected_role = parsed
        self.assertEqual((container_port, protocol), (27017, "tcp"))
        self.assertIsNone(host_port)
        self.assertEqual(injected_role, "data-execution-mongodb")

    def test_injected_variable_role_must_own_the_container_endpoint(self) -> None:
        """注入变量声明的 role 必须就是该容器端点的归属 role，分叉即判否。

        这是 `:?` 形态上唯一非自证的判据：把变量折算成 canonical 端口再比对，折算值与
        publisher 派生自同一份 manifest，同改同变。
        """
        drifted = copy.deepcopy(self.manifest)
        # coturn 的 3478/udp 归 coturn；把注入变量改声明成别的 role 就构成分叉。
        drifted[self.gate.HOST_PORT_VARIABLES_KEY]["LOCAL_GAMMA_TURN_UDP_PORT"] = (
            "livekit-rtc-udp"
        )

        issues = self._issues(drifted)

        self.assertTrue(
            [
                item
                for item in issues
                if "injected host port variable role does not own" in item
            ],
            msg=f"注入 role 与容器端点归属分叉未判否: {issues}",
        )

    def test_injected_variable_role_must_own_profile_canonical_endpoints_too(
        self,
    ) -> None:
        """容器口跟随主机口的形态也要断言注入 role 归属，不能只查 follower 存在。

        这一形态（`${VAR:?}:${VAR:?}`，gamma-local 的 object-storage 就是）主机端口恒非
        字面量，判据只能落在注入变量上。漏掉时把变量换成另一个已声明变量门禁仍放行，
        运行期却会把该服务发布到别的 role 的 canonical 口。
        """
        drifted = copy.deepcopy(self.manifest)
        drifted[self.gate.HOST_PORT_VARIABLES_KEY][
            "LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT"
        ] = "mongodb"

        issues = self._issues(drifted)

        self.assertTrue(
            [
                item
                for item in issues
                if "does not own profile-canonical" in item
            ],
            msg=f"profile-canonical 形态的注入 role 漂移未判否: {issues}",
        )

    def test_non_numeric_default_host_port_is_rejected(self) -> None:
        """`${VAR:-<非数字>}` 是第三类：缺省值静态可读但不是端口，必须判否。

        变量缺席时 Docker 会随机分配主机口，所有权运行期不可判定；把它当「已识别形态」
        降级成只查 role 声明，等于放过一条不可判定的发布口。
        """
        for rejected in ("${VAR:-}", "${VAR:-latest}", "127.0.0.1:${VAR:-abc}"):
            self.assertFalse(
                self.gate._host_segment_is_recognized(rejected),
                msg=f"非端口缺省值被误判为已识别: {rejected}",
            )
        for accepted in ("${VAR:-19210}", "127.0.0.1:${VAR:-19210}", "${VAR:?msg}"):
            self.assertTrue(
                self.gate._host_segment_is_recognized(accepted),
                msg=f"合法形态被误判为未知: {accepted}",
            )

    def test_unowned_exemption_matches_repository_path_not_bare_file_name(
        self,
    ) -> None:
        """豁免按仓库相对路径比对：按文件名会让环境根的豁免在全部来源目录生效。"""
        declared = self.manifest[self.gate.UNOWNED_COMPOSE_SOURCES_KEY]
        source = pathlib_module.Path(
            inspect_module.getsourcefile(self.gate._local_compose_sources)
        ).read_text(encoding="utf-8")
        body = source.split("def _local_compose_sources", 1)[1].split("\ndef ", 1)[0]

        # 第二个循环（其余来源目录）不得再按 `path.name` 放行。
        self.assertIn("if relative in unowned_sources:", body)
        self.assertNotIn("or path.name in unowned_sources", body)
        # 环境根那处仍按文件名裁决，声明键因此是裸文件名。
        for name in declared:
            self.assertNotIn("/", name)

    def test_declared_variable_must_be_used_by_some_compose_host_port(self) -> None:
        """声明段反向闭合：登记了但没人用的变量会长期留存且不可见。"""
        drifted = copy.deepcopy(self.manifest)
        drifted[self.gate.HOST_PORT_VARIABLES_KEY]["QWQ_NEVER_USED_PORT"] = "mongodb"

        issues = self._issues(drifted)

        self.assertTrue(
            [item for item in issues if "no Compose host port uses" in item],
            msg=f"死声明未判否: {issues}",
        )

    def test_environment_compose_adjudication_glob_matches_other_source_roots(
        self,
    ) -> None:
        """环境目录自己的裁决 glob 必须与其余来源目录同宽。

        只收 `docker-compose*` 前缀时，`local-elasticsearch.compose.yaml` 这种命名既不进
        `LOCAL_ENVIRONMENT_COMPOSE`、不匹配闭包 glob、也不被裁决收集 —— 三重漏网，而漏网
        的表现恰好是「门禁通过」。
        """
        source = pathlib_module.Path(
            inspect_module.getsourcefile(self.gate._local_compose_sources)
        ).read_text(encoding="utf-8")
        body = source.split("def _local_compose_sources", 1)[1].split("\ndef ", 1)[0]

        self.assertIn('environment_root.glob("*compose*.y*ml")', body)
        self.assertNotIn('environment_root.glob("docker-compose*.y*ml")', body)

    def test_empty_compose_closure_fails_closed(self) -> None:
        """闭包为空时判否而不是放行——读不出来不能塌陷成通过。"""
        saved = self.gate.LOCAL_COMPOSE_GLOBS
        saved_environment = self.gate.LOCAL_ENVIRONMENT_COMPOSE
        self.gate.LOCAL_COMPOSE_GLOBS = ()
        self.gate.LOCAL_ENVIRONMENT_COMPOSE = ()
        try:
            issues = self._issues(self.manifest)
        finally:
            self.gate.LOCAL_COMPOSE_GLOBS = saved
            self.gate.LOCAL_ENVIRONMENT_COMPOSE = saved_environment

        self.assertTrue(
            [item for item in issues if "closure is empty" in item],
            msg=f"空闭包未判否: {issues}",
        )

    def test_gate_entry_returns_nonzero_on_any_issue(self) -> None:
        """任一 issue 即非零退出，不得包装成 warning 或成功。"""
        gate = _load_gate()
        gate.validate_port_manifest = lambda _manifest: ["injected issue"]

        self.assertEqual(gate.main(), 1)


if __name__ == "__main__":
    unittest.main()
