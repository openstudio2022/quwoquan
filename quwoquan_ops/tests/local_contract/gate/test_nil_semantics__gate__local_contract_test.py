#!/usr/bin/env python3
"""`verify_nil_semantics.py` 的行为级 companion。

门禁本身是全仓扫描，全绿只说明"当前仓库恰好没有违规"，不说明判据还成立。这里改为
喂构造好的 Go 源，逐条断言判定行为，这样判据一旦退化（比如 wire 判定退回目录名、
`return nil, nil, err` 又被计入、`*bool` 被误伤）就会在这里先红。

每个用例都给出正例与反例：只断言"违规能被抓到"会漏掉误报，只断言"合规能通过"会漏
掉漏报。
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_service/scripts/verify/structure/verify_nil_semantics.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_nil_semantics", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


class GoTree:
    """临时 Go 源树。`SERVICE_ROOT` 指到这里，门禁就只看得见这些文件。"""

    def __init__(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self._original = gate.SERVICE_ROOT
        gate.SERVICE_ROOT = self.root

    def write(self, relative: str, body: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def wire_findings(self):
        sources = [gate.GoFile(path) for path in sorted(gate._go_sources())]
        return gate._wire_findings(sources)

    def close(self) -> None:
        gate.SERVICE_ROOT = self._original
        self._temp.cleanup()


class WireBoundaryByDataFlowTest(unittest.TestCase):
    """出站边界必须按数据流判定。这是 replayed 缺陷溜过去的那条判据。"""

    def setUp(self) -> None:
        self.tree = GoTree()
        self.addCleanup(self.tree.close)

    def _handler(self, call: str) -> str:
        return (
            "package http\n\n"
            "import (\n"
            '\t"quwoquan_service/services/demo/internal/demo/application"\n'
            ")\n\n"
            "func handle(w http.ResponseWriter, r *http.Request) {\n"
            f"\t{call}\n"
            "}\n"
        )

    def test_bool_omitempty_on_dto_defined_outside_http_dir_blocks(self) -> None:
        # DTO 在 application，writeJSON 在 adapters/inbound/http。按目录名判定时这里
        # 什么都看不见——replayed 就是这样进入现网的。
        self.tree.write(
            "services/demo/internal/demo/application/contracts.go",
            "package application\n\n"
            "type CommandResult struct {\n"
            '\tReplayed bool `json:"replayed,omitempty"`\n'
            "}\n\n"
            "func (s *Service) Run() (CommandResult, error) {\n"
            "\treturn CommandResult{}, nil\n"
            "}\n",
        )
        self.tree.write(
            "services/demo/internal/demo/adapters/inbound/http/handler.go",
            self._handler("writeJSON(w, 200, result)").replace(
                "\twriteJSON(w, 200, result)",
                "\tresult, _ := s.Run()\n\twriteJSON(w, 200, result)",
            ),
        )
        bool_violations, _, _ = self.tree.wire_findings()
        self.assertTrue(
            any("replayed" in item for item in bool_violations),
            f"bool+omitempty 必须硬 BLOCK，实际={bool_violations}",
        )

    def test_pointer_bool_omitempty_passes(self) -> None:
        # nil 省略、&false 输出 false，指针恰好把三态表达对了。
        self.tree.write(
            "services/demo/internal/demo/application/contracts.go",
            "package application\n\n"
            "type CommandResult struct {\n"
            '\tReplayed *bool `json:"replayed,omitempty"`\n'
            "}\n\n"
            "func (s *Service) Run() (CommandResult, error) {\n"
            "\treturn CommandResult{}, nil\n"
            "}\n",
        )
        self.tree.write(
            "services/demo/internal/demo/adapters/inbound/http/handler.go",
            "package http\n\n"
            "func handle(w http.ResponseWriter) {\n"
            "\tresult, _ := s.Run()\n"
            "\twriteJSON(w, 200, result)\n"
            "}\n",
        )
        bool_violations, _, _ = self.tree.wire_findings()
        self.assertEqual([], bool_violations)

    def test_bool_omitempty_never_serialized_passes(self) -> None:
        # 同样的字段，只要没有任何出站 writer 触达，就不在本门禁的判据范围内。
        self.tree.write(
            "services/demo/internal/demo/application/contracts.go",
            "package application\n\n"
            "type InternalFlagBag struct {\n"
            '\tReplayed bool `json:"replayed,omitempty"`\n'
            "}\n",
        )
        bool_violations, _, _ = self.tree.wire_findings()
        self.assertEqual([], bool_violations)

    def test_nested_struct_and_slice_element_are_reachable(self) -> None:
        # 根类型只是入口，判定必须沿字段类型递归展开，否则嵌套一层就漏。
        self.tree.write(
            "services/demo/internal/demo/application/contracts.go",
            "package application\n\n"
            "type Envelope struct {\n"
            '\tItems []Item `json:"items"`\n'
            "}\n\n"
            "type Item struct {\n"
            '\tFastStart bool `json:"fastStart,omitempty"`\n'
            "}\n\n"
            "func (s *Service) Load() (Envelope, error) {\n"
            "\treturn Envelope{}, nil\n"
            "}\n",
        )
        self.tree.write(
            "services/demo/internal/demo/adapters/inbound/http/handler.go",
            "package http\n\n"
            "func handle(w http.ResponseWriter) {\n"
            "\tenvelope, _ := s.Load()\n"
            "\twriteJSON(w, 200, envelope)\n"
            "}\n",
        )
        bool_violations, _, _ = self.tree.wire_findings()
        self.assertTrue(
            any("fastStart" in item for item in bool_violations),
            f"嵌套列表元素里的字段必须可达，实际={bool_violations}",
        )

    def test_multi_line_method_signature_is_indexed(self) -> None:
        # `CommentService.CreateComment` 的签名就是换行写的。返回类型索引只认单行时，
        # 这个 DTO 根本进不了可达图——replayed 第一次被漏掉正是这个原因。
        self.tree.write(
            "services/demo/internal/demo/application/contracts.go",
            "package application\n\n"
            "type CommandResult struct {\n"
            '\tReplayed bool `json:"replayed,omitempty"`\n'
            "}\n\n"
            "func (s *Service) CreateComment(\n"
            "\tctx context.Context,\n"
            "\tinput CreateCommentInput,\n"
            ") (CommandResult, error) {\n"
            "\treturn CommandResult{}, nil\n"
            "}\n",
        )
        self.tree.write(
            "services/demo/internal/demo/adapters/inbound/http/handler.go",
            "package http\n\n"
            "func handle(w http.ResponseWriter) {\n"
            "\tresult, _ := s.CreateComment(ctx, input)\n"
            "\twriteJSON(w, 200, result)\n"
            "}\n",
        )
        bool_violations, _, _ = self.tree.wire_findings()
        self.assertTrue(
            any("replayed" in item for item in bool_violations),
            f"多行签名的返回类型必须能被索引，实际={bool_violations}",
        )

    def test_list_omitempty_goes_to_ratchet_not_hard_block(self) -> None:
        # 删掉列表的 omitempty 之后 nil slice 会序列化成 null，同样违反 REQ-003，
        # 所以它必须连着构造期归一化一起改，走棘轮而不是硬 BLOCK。
        self.tree.write(
            "services/demo/internal/demo/application/contracts.go",
            "package application\n\n"
            "type Envelope struct {\n"
            '\tTags []string `json:"tags,omitempty"`\n'
            "}\n\n"
            "func (s *Service) Load() (Envelope, error) {\n"
            "\treturn Envelope{}, nil\n"
            "}\n",
        )
        self.tree.write(
            "services/demo/internal/demo/adapters/inbound/http/handler.go",
            "package http\n\n"
            "func handle(w http.ResponseWriter) {\n"
            "\tenvelope, _ := s.Load()\n"
            "\twriteJSON(w, 200, envelope)\n"
            "}\n",
        )
        bool_violations, list_ratchet, _ = self.tree.wire_findings()
        self.assertEqual([], bool_violations)
        identities = [
            identity
            for entries in list_ratchet.values()
            for identity in entries
        ]
        self.assertTrue(
            any("Envelope.Tags" in identity for identity in identities),
            f"列表 omitempty 必须进棘轮，实际={list_ratchet}",
        )

    def test_map_literal_argument_is_not_a_violation(self) -> None:
        # 键逐个写死，不会因取值而消失，也没有 struct 定义可查。
        self.tree.write(
            "services/demo/internal/demo/adapters/inbound/http/handler.go",
            "package http\n\n"
            "func handle(w http.ResponseWriter) {\n"
            '\twriteJSON(w, 200, map[string]any{"replayed": false})\n'
            "}\n",
        )
        bool_violations, list_ratchet, unresolved = self.tree.wire_findings()
        self.assertEqual([], bool_violations)
        self.assertEqual({}, list_ratchet)
        self.assertEqual([], unresolved)

    def test_unresolvable_call_site_is_reported_not_silently_passed(self) -> None:
        # 门禁只对能证明的部分下断言，剩下的必须可见——静默当成合规才是真正的风险。
        self.tree.write(
            "services/demo/internal/demo/adapters/inbound/http/handler.go",
            "package http\n\n"
            "func handle(w http.ResponseWriter) {\n"
            "\twriteJSON(w, 200, somethingUntraceable(r))\n"
            "}\n",
        )
        bool_violations, _, unresolved = self.tree.wire_findings()
        self.assertEqual([], bool_violations)
        self.assertEqual(1, len(unresolved), f"实际={unresolved}")


class NilNilRatchetTest(unittest.TestCase):
    """`return nil, nil` 只计二元，且身份是函数而不是文件。"""

    def test_binary_nil_nil_is_counted(self) -> None:
        counts = gate._nil_nil_identities(
            "func Find() (*T, error) {\n\treturn nil, nil\n}\n"
        )
        self.assertEqual({"Find": 1}, counts)

    def test_ternary_nil_nil_err_is_not_counted(self) -> None:
        # 第三个返回值已经在表达失败，它不属于"空返回值兼作未命中信号"这条判据。
        counts = gate._nil_nil_identities(
            "func Find() (*T, []byte, error) {\n\treturn nil, nil, err\n}\n"
        )
        self.assertEqual({}, counts)

    def test_identity_is_function_so_moving_a_hit_is_visible(self) -> None:
        # 配额挂在文件上时，删一处、在另一个函数里添一处，总数不变，门禁看不见。
        before = gate._nil_nil_identities(
            "func A() (*T, error) {\n\treturn nil, nil\n}\n"
            "func B() (*T, error) {\n\treturn found, nil\n}\n"
        )
        after = gate._nil_nil_identities(
            "func A() (*T, error) {\n\treturn found, nil\n}\n"
            "func B() (*T, error) {\n\treturn nil, nil\n}\n"
        )
        self.assertEqual({"A": 1}, before)
        self.assertEqual({"B": 1}, after)
        self.assertNotEqual(before, after)

    def test_method_receiver_declaration_is_recognized(self) -> None:
        counts = gate._nil_nil_identities(
            "func (r *repo) Find() (*T, error) {\n\treturn nil, nil\n}\n"
        )
        self.assertEqual({"Find": 1}, counts)


class PortLayerScopeTest(unittest.TestCase):
    """`return nil, nil` 的计入范围：领域端口计入，infrastructure 与非端口层不计。"""

    def setUp(self) -> None:
        self.tree = GoTree()
        self.addCleanup(self.tree.close)

    def test_application_counts_and_infrastructure_and_cmd_do_not(self) -> None:
        finder = "func Find() (*T, error) {\n\treturn nil, nil\n}\n"
        self.tree.write(
            "services/demo/internal/demo/application/port.go",
            f"package application\n\n{finder}",
        )
        # store 未命中有其合理性，收敛它需要先统一显式约定。
        self.tree.write(
            "services/demo/internal/demo/infrastructure/mongo.go",
            f"package infrastructure\n\n{finder}",
        )
        self.tree.write(
            "services/demo/cmd/main.go", f"package main\n\n{finder}"
        )
        _, _, ratchet = gate.scan()
        self.assertEqual(
            {"services/demo/internal/demo/application/port.go": {"Find": 1}},
            ratchet,
        )

    def test_layer_lookup_covers_all_three_port_layers(self) -> None:
        for layer in ("application", "domain", "adapters"):
            self.assertEqual(
                layer,
                gate._port_layer(f"services/demo/internal/demo/{layer}/port.go"),
            )
        self.assertIsNone(gate._port_layer("services/demo/cmd/main.go"))


class BaselineMonotonicityTest(unittest.TestCase):
    """基线是身份指纹，任何增加都必须 BLOCK。"""

    def test_shipped_baseline_is_identity_keyed_with_governance(self) -> None:
        import json

        document = json.loads(
            gate.BASELINE_PATH.read_text(encoding="utf-8")
        )
        governance = document.get("_governance")
        self.assertIsInstance(governance, dict, "基线必须带 _governance 块")
        for required in ("owner", "reason", "expires_when", "measure"):
            self.assertTrue(
                str(governance.get(required, "")).strip(),
                f"_governance 缺少 {required}",
            )
        entries = {
            key: value for key, value in document.items() if key != "_governance"
        }
        self.assertTrue(entries, "基线不能为空——那说明口径已经失真")
        for path, identities in entries.items():
            self.assertIsInstance(
                identities,
                dict,
                f"{path} 必须是 身份->计数 而不是单个数字：按文件计数时"
                f"同文件替换看不见",
            )


if __name__ == "__main__":
    unittest.main()
