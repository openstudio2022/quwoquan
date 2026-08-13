"""端云 metric 语义同源门禁的判定契约。

被测对象是 `quwoquan_ops/gate/verify_metric_identity_homology.py`：三处 metric 标识
（云侧 `telemetry.metric`、Prometheus `contract_metric` label、App `operationId`）
必须同源。这里锁住三组判定各自「什么必须过、什么必须拦」，避免判定被悄悄放宽成恒真。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
GATE_PATH = REPO_ROOT / "quwoquan_ops/gate/verify_metric_identity_homology.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_metric_identity_homology", GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()
coverage = gate.coverage


def _operation(operation_id: str, metric: str) -> "coverage.OperationContract":
    domain, object_name, _ = operation_id.split(".")
    return coverage.OperationContract(
        operation_id=operation_id,
        domain=domain,
        service=f"{domain}-service",
        object_name=object_name,
        method="POST",
        path_template=f"/{object_name}",
        commercial_status="ready",
        block_reason="",
        metric=metric,
        latency_p95_ms=200,
        availability_percent=99.9,
    )


def test_rules_file_is_loadable_and_declares_three_groups():
    rules = gate.load_rules()
    assert rules["schema"] == gate.RULES_SCHEMA
    for section in ("identity_join", "family_projection", "naming_structure"):
        assert isinstance(rules[section], dict), section


def test_rules_file_rejects_wrong_schema(tmp_path: Path):
    bad = tmp_path / "rules.yaml"
    bad.write_text(yaml.safe_dump({"schema": "metric_identity.v0"}), encoding="utf-8")
    with pytest.raises(gate.RuleInputError):
        gate.load_rules(bad)


def test_naming_structure_requires_domain_prefix():
    rules = gate.load_rules()
    good = _operation("circle.gathering.CancelGathering", "circle_gathering_cancel")
    bad = _operation("circle.gathering.CancelGathering", "gathering_cancel")
    assert gate.check_naming_structure(rules, [good]) == []
    findings = gate.check_naming_structure(rules, [bad])
    assert len(findings) == 1
    assert "域前缀" in findings[0].message


def test_naming_structure_requires_token_anchor():
    rules = gate.load_rules()
    # 前缀合规但与 domain / object / localId 无任何共享 token：族名与契约脱锚。
    drifted = _operation("circle.gathering.CancelGathering", "circle_zzz_qqq")
    findings = gate.check_naming_structure(rules, [drifted])
    assert [f for f in findings if "锚点" in f.message]


def test_naming_structure_accepts_pascal_to_snake_transform():
    rules = gate.load_rules()
    # localId `CancelGathering` 折成 snake 后与族名共享 token，属于允许的形态转换。
    operation = _operation("circle.gathering.CancelGathering", "circle_cancel_flow")
    assert gate.check_naming_structure(rules, [operation]) == []


def test_only_morphological_transforms_are_declared():
    """允许的转换必须是纯形态的；一旦掺入同义词/缩写映射即为语义漂移。"""
    rules = gate.load_rules()
    assert set(rules["naming_structure"]["case_transforms"]) <= {
        "pascal_to_snake",
        "singular_plural",
    }
    assert gate.pascal_to_snake("CancelGathering") == "cancel_gathering"
    assert gate.pascal_to_snake("GetPublicGathering") == "get_public_gathering"
    assert gate._singularize("metrics") == "metric"
    assert gate._singularize("intersections") == "intersection"
    # 不做词干还原：`access` / `status` 这类以 ss 结尾或过短的 token 保持原样。
    assert gate._singularize("access") == "access"
    assert gate._singularize("ops") == "ops"


def test_family_projection_blocks_undeclared_contract_metric(tmp_path: Path):
    rules = gate.load_rules()
    alerts = tmp_path / "alerts"
    alerts.mkdir()
    (alerts / "rules.yaml").write_text(
        yaml.safe_dump(
            {
                "groups": [
                    {
                        "name": "g",
                        "rules": [
                            {
                                "alert": "A",
                                "expr": 'sum(quwoquan_circle_contract_operation_requests_total'
                                '{contract_metric="circle_ghost_metric"})',
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rules["family_projection"]["promql_roots"] = [
        str(alerts.relative_to(REPO_ROOT)) if alerts.is_relative_to(REPO_ROOT) else str(alerts)
    ]
    # tmp_path 在仓库外，用绝对根消费。
    rules["family_projection"]["promql_roots"] = [str(alerts)]
    operations = [_operation("circle.gathering.CancelGathering", "circle_gathering_cancel")]
    findings = gate.check_family_projection(rules, operations)
    assert [f for f in findings if "circle_ghost_metric" in f.message]


def test_family_projection_blocks_jointly_unsatisfiable_selector(tmp_path: Path):
    rules = gate.load_rules()
    alerts = tmp_path / "alerts"
    alerts.mkdir()
    # operation 与 contract_metric 各自都存在，但不属于同一个 operation：永远不会有样本。
    (alerts / "rules.yaml").write_text(
        yaml.safe_dump(
            {
                "groups": [
                    {
                        "name": "g",
                        "rules": [
                            {
                                "alert": "A",
                                "expr": "sum(quwoquan_circle_contract_operation_requests_total"
                                '{operation="circle.gathering.CancelGathering",'
                                'contract_metric="circle_gathering_publish"})',
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rules["family_projection"]["promql_roots"] = [str(alerts)]
    operations = [
        _operation("circle.gathering.CancelGathering", "circle_gathering_cancel"),
        _operation("circle.gathering.PublishGathering", "circle_gathering_publish"),
    ]
    findings = gate.check_family_projection(rules, operations)
    assert [f for f in findings if "无法被任何 operation 同时满足" in f.message]


def test_family_projection_accepts_matching_pair(tmp_path: Path):
    rules = gate.load_rules()
    alerts = tmp_path / "alerts"
    alerts.mkdir()
    (alerts / "rules.yaml").write_text(
        yaml.safe_dump(
            {
                "groups": [
                    {
                        "name": "g",
                        "rules": [
                            {
                                "alert": "A",
                                "expr": "sum(quwoquan_circle_contract_operation_requests_total"
                                '{operation="circle.gathering.CancelGathering",'
                                'contract_metric="circle_gathering_cancel"})',
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rules["family_projection"]["promql_roots"] = [str(alerts)]
    operations = [_operation("circle.gathering.CancelGathering", "circle_gathering_cancel")]
    assert gate.check_family_projection(rules, operations) == []


def test_identity_join_blocks_app_operation_id_outside_graph(tmp_path: Path):
    rules = gate.load_rules()
    generated = tmp_path / "operation_contracts.g.dart"
    generated.write_text(
        'const canonicalOperationId: "circle.gathering.GhostOperation";\n', encoding="utf-8"
    )
    rules["identity_join"]["app_generated_operation_sources"] = [
        str(generated.relative_to(tmp_path))
    ]
    rules["identity_join"]["app_local_operation_scan_roots"] = []
    # 用绝对路径喂给判定：REPO_ROOT / 绝对路径 仍是该绝对路径。
    rules["identity_join"]["app_generated_operation_sources"] = [str(generated)]
    operations = [_operation("circle.gathering.CancelGathering", "circle_gathering_cancel")]
    findings = gate.check_identity_join(rules, operations)
    assert [f for f in findings if "GhostOperation" in f.message]


def test_identity_join_accepts_registered_and_namespaced_local_ids(tmp_path: Path):
    rules = gate.load_rules()
    root = tmp_path / "lib"
    root.mkdir()
    registry = tmp_path / "telemetry_metrics.go"
    registry.write_text(
        "func boundedLoginOperation(value string) string {\n"
        "\tswitch value {\n"
        '\tcase "send_otp":\n'
        "\t\treturn value\n"
        "\tdefault:\n"
        '\t\treturn "other"\n'
        "\t}\n"
        "}\n",
        encoding="utf-8",
    )
    (root / "page.dart").write_text(
        "void x() {\n"
        "  track(operationId: 'send_otp');\n"
        "  track(operationId: 'app.runtime.anr_watchdog');\n"
        "}\n",
        encoding="utf-8",
    )
    rules["identity_join"]["app_generated_operation_sources"] = []
    rules["identity_join"]["app_local_operation_scan_roots"] = [str(root)]
    rules["identity_join"]["app_local_operation_registries"] = [
        {"path": str(registry), "func": "boundedLoginOperation"}
    ]
    operations = [_operation("circle.gathering.CancelGathering", "circle_gathering_cancel")]
    assert gate.check_identity_join(rules, operations) == []


def test_identity_join_blocks_unregistered_local_id(tmp_path: Path):
    rules = gate.load_rules()
    root = tmp_path / "lib"
    root.mkdir()
    (root / "page.dart").write_text(
        "void x() { track(operationId: 'drifted_local_action'); }\n", encoding="utf-8"
    )
    rules["identity_join"]["app_generated_operation_sources"] = []
    rules["identity_join"]["app_local_operation_scan_roots"] = [str(root)]
    rules["identity_join"]["app_local_operation_registries"] = []
    operations = [_operation("circle.gathering.CancelGathering", "circle_gathering_cancel")]
    findings = gate.check_identity_join(rules, operations)
    assert [f for f in findings if "drifted_local_action" in f.message]


def test_identity_join_blocks_local_id_colliding_with_cloud_operation(tmp_path: Path):
    rules = gate.load_rules()
    root = tmp_path / "lib"
    root.mkdir()
    (root / "page.dart").write_text(
        "void x() { track(operationId: 'circle.gathering.CancelGathering'); }\n", encoding="utf-8"
    )
    rules["identity_join"]["app_generated_operation_sources"] = []
    rules["identity_join"]["app_local_operation_scan_roots"] = [str(root)]
    rules["identity_join"]["app_local_operation_registries"] = []
    operations = [_operation("circle.gathering.CancelGathering", "circle_gathering_cancel")]
    findings = gate.check_identity_join(rules, operations)
    assert [f for f in findings if "与云侧 operation id 相同" in f.message]


def test_local_operation_registry_reads_declared_go_vocabulary():
    rules = gate.load_rules()
    entries = rules["identity_join"]["app_local_operation_registries"]
    assert entries, "必须显式声明云侧 bounded 词表来源"
    registered, findings = gate.load_local_operation_registry(entries)
    assert findings == []
    assert "send_otp" in registered
    assert "other" not in registered


def test_declared_app_generated_source_is_parsable_and_shaped():
    """真实产物断言：声明的 App 生成侧来源必须存在，且每个 operationId 都符合约定形状。

    这里不断言「App id ⊆ ContractGraph id」本身：ContractGraph 是周期性重建的产物，
    契约先落地、graph 后重建的窗口期内该子集关系本就会短暂不成立。子集判定交给门禁
    （下一个用例锁住「门禁必须报出差集」），测试只锁住形状与可解析性。
    """
    rules = gate.load_rules()
    pattern = gate.re.compile(rules["identity_join"]["operation_id_pattern"])
    for relative in rules["identity_join"]["app_generated_operation_sources"]:
        path = REPO_ROOT / relative
        assert path.is_file(), relative
        app_ids = set(gate._APP_GENERATED_OPERATION_RE.findall(path.read_text(encoding="utf-8")))
        assert app_ids, f"{relative} 未解析出任何 canonicalOperationId"
        malformed = sorted(value for value in app_ids if not pattern.fullmatch(value))
        assert malformed == [], malformed


def test_identity_join_reports_every_app_id_missing_from_graph(tmp_path: Path):
    """门禁必须逐条报出 App 生成侧领先 / 偏离 ContractGraph 的 operationId，不得聚合吞掉。"""
    rules = gate.load_rules()
    generated = tmp_path / "operation_contracts.g.dart"
    generated.write_text(
        'canonicalOperationId: "circle.gathering.CancelGathering",\n'
        'canonicalOperationId: "content.outbound_share_fact.CreateOutboundShare",\n'
        'canonicalOperationId: "content.media_original_access_fact.RequestOriginalImageAccess",\n',
        encoding="utf-8",
    )
    rules["identity_join"]["app_generated_operation_sources"] = [str(generated)]
    rules["identity_join"]["app_local_operation_scan_roots"] = []
    operations = [_operation("circle.gathering.CancelGathering", "circle_gathering_cancel")]
    findings = gate.check_identity_join(rules, operations)
    reported = {
        message.split("canonicalOperationId ")[1].split(" 不是")[0].strip("'")
        for message in (finding.message for finding in findings)
        if "canonicalOperationId" in message
    }
    assert reported == {
        "content.outbound_share_fact.CreateOutboundShare",
        "content.media_original_access_fact.RequestOriginalImageAccess",
    }


def test_contract_graph_operation_ids_match_declared_shape():
    rules = gate.load_rules()
    services = coverage.load_domain_services()
    operations = coverage.load_operations(domain_services=services)
    findings = [f for f in gate.check_identity_join(rules, operations) if "不符合约定形状" in f.message]
    assert findings == [], [f.message for f in findings]


def test_survey_reports_family_fanout(capsys):
    rules = gate.load_rules()
    services = coverage.load_domain_services()
    runtime = coverage.runtime_domain_services(services)
    operations = [
        op
        for op in coverage.load_operations(domain_services=services)
        if op.service in runtime.values()
    ]
    gate.survey(operations, rules)
    output = capsys.readouterr().out
    assert "多对一族名" in output
    assert "App 生成侧 canonicalOperationId" in output


def test_rules_document_is_valid_json_serializable():
    # 规则文件必须是纯数据（可被其他工具消费），不得依赖 YAML 自定义标签。
    rules = gate.load_rules()
    json.dumps(rules)
