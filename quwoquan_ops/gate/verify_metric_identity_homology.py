#!/usr/bin/env python3
"""端云 metric 语义同源门禁：operationId / contract_metric / telemetry.metric 三处必须同源。

三处标识过去各自为政，没有任何联合校验：

* 云侧 operation 契约的 `telemetry.metric`
* Prometheus 上的 `contract_metric` label
* App 埋点的 `operationId`

现场调研（`--survey`）给出的事实决定了判定形状：`telemetry.metric` 是 operation 之上的
**多对一 SLI 族名**（37 个族名被 2~11 个 operation 共享），不是 operationId 的改名；三者真正的
连接键是 operationId 本身，App 生成侧的 `canonicalOperationId` 与 ContractGraph 的
`operations[].id` 逐字相同。因此规则分三组，配置见
`quwoquan_ops/observability/metric_identity_rules.yaml`：

* identity_join：App 生成侧 operationId ⊆ ContractGraph operation id；App 手写的本地
  operationId 必须落在保留命名空间，且不得与任何云侧 operation id 相等。
* family_projection：PromQL 里出现的 `contract_metric` 字面量必须是已声明族名；同一个
  selector 上的 `operation` 与 `contract_metric` 必须能被至少一个真实 operation 联合满足
  （只查 operation 会漏掉「operation 对、族名错」这类永远不触发的死告警）。
* naming_structure：族名必须以自己的 domain 开头，并与 domain / object / operation localId
  至少共享一个 token。唯一允许的形态转换是 PascalCase → snake_case，不允许语义改写。

没有 allowlist：判定输入每次运行都从 ContractGraph、告警树、仪表盘树和 App 源码现场推导。
"""

from __future__ import annotations

import argparse
import collections
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

import yaml

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_service.scripts.verify.observability import (  # noqa: E402
    verify_object_alert_coverage as coverage,
)

RULES_PATH = REPO_ROOT / "quwoquan_ops/observability/metric_identity_rules.yaml"
RULES_SCHEMA = "metric_identity.v1"

_APP_GENERATED_OPERATION_RE = re.compile(r'canonicalOperationId:\s*"([^"]+)"')
_APP_LOCAL_OPERATION_RE = re.compile(
    r"""operationId:\s*(?:'([^'$]*)'|"([^"$]*)")"""
)
_PASCAL_BOUNDARY_RE = re.compile(r"(?<!^)(?=[A-Z])")
_GO_STRING_RE = re.compile(r'"([^"]*)"')


class RuleInputError(RuntimeError):
    """规则文件或判定输入不可用。"""


@dataclass(frozen=True)
class Finding:
    rule_group: str
    message: str


def load_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise RuleInputError(f"{_display(path)}: 无法解析: {error}") from error
    if not isinstance(document, dict) or document.get("schema") != RULES_SCHEMA:
        raise RuleInputError(f"{_display(path)}: schema 必须是 {RULES_SCHEMA}")
    for section in ("identity_join", "family_projection", "naming_structure"):
        if not isinstance(document.get(section), dict):
            raise RuleInputError(f"{_display(path)}: 缺少 {section} 段")
    return document


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def pascal_to_snake(value: str) -> str:
    return _PASCAL_BOUNDARY_RE.sub("_", value).lower()


def _singularize(token: str) -> str:
    """只做末尾 `s` 归一；不做词干还原，避免把语义改写伪装成形态转换。"""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def load_local_operation_registry(
    entries: Iterable[dict[str, Any]]
) -> tuple[set[str], list[Finding]]:
    """云侧 ingest 的 bounded 词表：Go switch 的 case 字面量即已登记取值。"""
    registered: set[str] = set()
    findings: list[Finding] = []
    for entry in entries or ():
        relative = str(entry.get("path", ""))
        function = str(entry.get("func", ""))
        path = REPO_ROOT / relative
        if not path.is_file():
            findings.append(
                Finding("identity_join", f"{relative}: 云侧 bounded 词表文件缺失")
            )
            continue
        text = path.read_text(encoding="utf-8")
        start = text.find(f"func {function}(")
        if start < 0:
            findings.append(
                Finding("identity_join", f"{relative}: 找不到 bounded 词表函数 {function}")
            )
            continue
        end = text.find("\n}\n", start)
        body = text[start : end if end > 0 else len(text)]
        values = set(_GO_STRING_RE.findall(body))
        if not values:
            findings.append(
                Finding(
                    "identity_join",
                    f"{relative}#{function}: bounded 词表为空，无法作为登记来源",
                )
            )
        registered |= values - {"other"}
    return registered, findings


def _promql_expressions(roots: Iterable[str]) -> list[tuple[str, str, str]]:
    """(来源, 名称, PromQL) 三元组，覆盖告警 YAML 与仪表盘 JSON。"""
    result: list[tuple[str, str, str]] = []
    for relative in roots:
        root = REPO_ROOT / relative
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml")):
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            for group in (document or {}).get("groups") or []:
                if not isinstance(group, dict):
                    continue
                for index, rule in enumerate(group.get("rules") or []):
                    if not isinstance(rule, dict) or not isinstance(rule.get("expr"), str):
                        continue
                    name = str(rule.get("alert") or rule.get("record") or index)
                    result.append((_display(path), f"{group.get('name')}/{name}", rule["expr"]))
        for path in sorted(root.rglob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for name, expression in coverage._walk_dashboard_expressions(document):
                result.append((_display(path), name, expression))
    return result


def _selector_label_sets(expression: str) -> list[dict[str, tuple[str, str]]]:
    sets: list[dict[str, tuple[str, str]]] = []
    for selector in coverage._PROMQL_SELECTOR_RE.finditer(expression):
        labels: dict[str, tuple[str, str]] = {}
        for matcher in coverage._PROMQL_LABEL_RE.finditer(selector.group("labels")):
            labels[matcher.group("name")] = (
                matcher.group("operator"),
                coverage._decode_promql_string(matcher.group("value")),
            )
        if labels:
            sets.append(labels)
    return sets


def _literal_alternatives(operator: str, value: str) -> list[str] | None:
    """把 `=`/简单 `=~` 字面量还原成候选集合；带真正正则量词的返回 None。"""
    if operator == "=":
        return [value]
    if operator != "=~":
        return None
    unescaped = value.replace("\\.", ".")
    if re.search(r"[\[\]+*?^$]", unescaped):
        return None
    body = unescaped
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    if "(" in body or ")" in body:
        return None
    return [part for part in body.split("|") if part]


def check_identity_join(
    rules: dict[str, Any], operations: list[coverage.OperationContract]
) -> list[Finding]:
    section = rules["identity_join"]
    findings: list[Finding] = []
    graph_ids = {operation.operation_id for operation in operations}
    pattern = re.compile(str(section.get("operation_id_pattern", ".*")))

    for operation_id in sorted(graph_ids):
        if not pattern.fullmatch(operation_id):
            findings.append(
                Finding(
                    "identity_join",
                    f"ContractGraph operation id {operation_id!r} 不符合约定形状 {pattern.pattern}",
                )
            )

    for relative in section.get("app_generated_operation_sources") or []:
        path = REPO_ROOT / relative
        if not path.is_file():
            findings.append(
                Finding("identity_join", f"{relative}: App 生成侧 operation 契约文件缺失")
            )
            continue
        text = path.read_text(encoding="utf-8")
        app_ids = set(_APP_GENERATED_OPERATION_RE.findall(text))
        for operation_id in sorted(app_ids - graph_ids):
            findings.append(
                Finding(
                    "identity_join",
                    f"{relative}: canonicalOperationId {operation_id!r} 不是 ContractGraph operation",
                )
            )

    namespaces = tuple(section.get("app_local_operation_namespaces") or ())
    registered, registry_findings = load_local_operation_registry(
        section.get("app_local_operation_registries") or ()
    )
    findings.extend(registry_findings)
    excluded = tuple(section.get("app_local_operation_excluded_path_fragments") or ())
    for relative in section.get("app_local_operation_scan_roots") or []:
        root = REPO_ROOT / relative
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.dart")):
            display = _display(path)
            if any(fragment in f"/{display}" for fragment in excluded):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for single, double in _APP_LOCAL_OPERATION_RE.findall(text):
                value = single or double
                if not value:
                    continue
                if value in graph_ids:
                    findings.append(
                        Finding(
                            "identity_join",
                            f"{display}: 手写 operationId {value!r} 与云侧 operation id 相同，"
                            "本地动作与云 operation 必须分属不同取值域",
                        )
                    )
                    continue
                if value in registered:
                    continue
                if not any(value.startswith(prefix) for prefix in namespaces):
                    findings.append(
                        Finding(
                            "identity_join",
                            f"{display}: 手写 operationId {value!r} 既不在保留命名空间 "
                            f"{list(namespaces)} 内，也未登记到云侧 bounded 词表，"
                            "云侧 ingest 会把它静默折成 other",
                        )
                    )
    return findings


def check_family_projection(
    rules: dict[str, Any], operations: list[coverage.OperationContract]
) -> list[Finding]:
    section = rules["family_projection"]
    findings: list[Finding] = []
    declared = {operation.metric for operation in operations}

    for source, name, expression in _promql_expressions(
        section.get("promql_roots") or []
    ):
        for labels in _selector_label_sets(expression):
            metric_matcher = labels.get("contract_metric")
            if metric_matcher is None:
                continue
            operator, value = metric_matcher
            if operator not in {"=", "=~"}:
                continue
            candidates = _literal_alternatives(operator, value)
            if section.get("require_declared_literal") and candidates is not None:
                for candidate in candidates:
                    if candidate not in declared:
                        findings.append(
                            Finding(
                                "family_projection",
                                f"{source}#{name}: contract_metric {candidate!r} "
                                "不是任何 operation 声明的 telemetry.metric",
                            )
                        )
            if not section.get("require_joint_satisfiability"):
                continue
            operation_matcher = labels.get("operation")
            if operation_matcher is None or operation_matcher[0] not in {"=", "=~"}:
                continue
            satisfied = any(
                coverage._matcher_accepts(
                    operation_matcher[0], operation_matcher[1], operation.operation_id
                )
                and coverage._matcher_accepts(operator, value, operation.metric)
                for operation in operations
            )
            if not satisfied:
                findings.append(
                    Finding(
                        "family_projection",
                        f"{source}#{name}: operation {operation_matcher[0]}{operation_matcher[1]!r} "
                        f"与 contract_metric {operator}{value!r} 无法被任何 operation 同时满足，"
                        "该 selector 永远不会有样本",
                    )
                )
    return findings


def check_naming_structure(
    rules: dict[str, Any], operations: list[coverage.OperationContract]
) -> list[Finding]:
    section = rules["naming_structure"]
    findings: list[Finding] = []
    transforms = set(section.get("case_transforms") or ())
    for operation in sorted(operations, key=lambda item: item.operation_id):
        metric = operation.metric
        if section.get("require_domain_prefix") and not metric.startswith(
            f"{operation.domain}_"
        ):
            findings.append(
                Finding(
                    "naming_structure",
                    f"{operation.operation_id}: telemetry.metric {metric!r} 没有以 "
                    f"{operation.domain!r} 域前缀开头，跨域族名会在 PromQL 里串味",
                )
            )
        if not section.get("require_token_anchor"):
            continue
        local = operation.operation_id.rsplit(".", 1)[-1]
        # domain 前缀已由 require_domain_prefix 单独强制；把它从 token 比对里剔除，
        # 否则 `<domain>_` 本身就构成共享 token，锚点判定会退化成恒真。
        body = metric[len(operation.domain) + 1 :] if metric.startswith(
            f"{operation.domain}_"
        ) else metric
        anchors = set(operation.object_name.split("_"))
        if "pascal_to_snake" in transforms:
            anchors |= set(pascal_to_snake(local).split("_"))
        else:
            anchors.add(local)
        tokens = set(body.split("_"))
        if "singular_plural" in transforms:
            anchors = {_singularize(token) for token in anchors}
            tokens = {_singularize(token) for token in tokens}
        if not anchors & tokens:
            findings.append(
                Finding(
                    "naming_structure",
                    f"{operation.operation_id}: telemetry.metric {metric!r} 与 domain/object/"
                    "operation localId 没有共享任何 token，族名与契约失去锚点",
                )
            )
    return findings


def survey(operations: list[coverage.OperationContract], rules: dict[str, Any]) -> None:
    declared = collections.Counter(operation.metric for operation in operations)
    shared = {name: count for name, count in declared.items() if count > 1}
    print(f"[metric-identity] operations={len(operations)} distinct telemetry.metric={len(declared)}")
    print(
        f"  多对一族名：{len(shared)} 个 telemetry.metric 被多个 operation 共享，"
        f"最大扇出={max(shared.values(), default=0)}"
    )
    for name, count in sorted(shared.items(), key=lambda item: -item[1])[:5]:
        print(f"    {name} x{count}")
    prefix_violations = [
        operation
        for operation in operations
        if not operation.metric.startswith(f"{operation.domain}_")
    ]
    print(f"  缺 <domain>_ 前缀：{len(prefix_violations)}")
    by_domain = collections.Counter(
        operation.domain for operation in prefix_violations
    )
    for domain, count in sorted(by_domain.items()):
        print(f"    {domain}: {count}")

    section = rules["identity_join"]
    graph_ids = {operation.operation_id for operation in operations}
    for relative in section.get("app_generated_operation_sources") or []:
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        app_ids = set(
            _APP_GENERATED_OPERATION_RE.findall(path.read_text(encoding="utf-8"))
        )
        print(
            f"  App 生成侧 canonicalOperationId={len(app_ids)}，"
            f"其中不在 ContractGraph 的={len(app_ids - graph_ids)}，"
            f"ContractGraph 未被 App 消费的={len(graph_ids - app_ids)}"
        )
    namespaces = tuple(section.get("app_local_operation_namespaces") or ())
    local_values: collections.Counter[str] = collections.Counter()
    excluded = tuple(section.get("app_local_operation_excluded_path_fragments") or ())
    for relative in section.get("app_local_operation_scan_roots") or []:
        root = REPO_ROOT / relative
        for path in sorted(root.rglob("*.dart")):
            display = _display(path)
            if any(fragment in f"/{display}" for fragment in excluded):
                continue
            for single, double in _APP_LOCAL_OPERATION_RE.findall(
                path.read_text(encoding="utf-8")
            ):
                value = single or double
                if value:
                    local_values[value] += 1
    registered, _ = load_local_operation_registry(
        section.get("app_local_operation_registries") or ()
    )
    namespaced = sorted(
        value
        for value in local_values
        if any(value.startswith(prefix) for prefix in namespaces)
    )
    by_registry = sorted(set(local_values) & registered)
    unanchored = sorted(set(local_values) - set(namespaced) - registered)
    print(
        f"  App 手写 operationId={len(local_values)} 个取值："
        f"保留命名空间={len(namespaced)}，云侧 bounded 词表登记={len(by_registry)}，"
        f"两者皆无={len(unanchored)}"
    )
    for value in unanchored:
        print(f"    {value}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, default=RULES_PATH)
    parser.add_argument(
        "--survey",
        action="store_true",
        help="只输出三处标识的现场取值分布，不做判定",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        rules = load_rules(args.rules)
        domain_services = coverage.load_domain_services()
        runtime_services = coverage.runtime_domain_services(domain_services)
        operations = [
            operation
            for operation in coverage.load_operations(domain_services=domain_services)
            if operation.service in runtime_services.values()
        ]
    except (RuleInputError, coverage.ContractInputError) as error:
        print(f"[metric-identity] BLOCK: {error}", file=sys.stderr)
        return 1

    if args.survey:
        survey(operations, rules)
        return 0

    findings = (
        check_identity_join(rules, operations)
        + check_family_projection(rules, operations)
        + check_naming_structure(rules, operations)
    )
    grouped = collections.Counter(finding.rule_group for finding in findings)
    print(
        f"[metric-identity] operations={len(operations)} "
        f"telemetry.metric={len({operation.metric for operation in operations})} "
        f"findings={len(findings)}"
    )
    for group in ("identity_join", "family_projection", "naming_structure"):
        print(f"  - {group}: {grouped.get(group, 0)}")
    if findings:
        print(
            f"[metric-identity] FAIL: 端云 metric 语义不同源（{len(findings)} 项）",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - [{finding.rule_group}] {finding.message}", file=sys.stderr)
        return 1
    print("[metric-identity] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
