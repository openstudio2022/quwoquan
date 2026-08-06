#!/usr/bin/env python3
"""垂类架构防回退门。

本门禁只读取物理源码、canonical domain owner metadata 与现存债务基线：

* 禁止新增按内容垂类拆分的 ``services/<vertical>-service``；
* 禁止业务代码新增垂类 ``switch/case`` 或 ``contentVertical ==`` 分叉；
* ``contentVertical`` 使用、``domain_taxonomy.yaml`` 运行时消费者只减不增；
* 已退役 travel-service 目录与 App、Assistant、api-edge 依赖永久保持为零。

基线不是服务/字段/消费者注册表，只保存允许现存命中的路径、计数摘要与退役责任。
删除命中会自动通过；新路径、计数增加或等量替换会阻断。travel-service 已完成日落，
其目录和三类调用方依赖不再接受任何 allowance、正计数或迁移期开关。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = (
    ROOT
    / "quwoquan_ops"
    / "policies"
    / "gates"
    / "vertical_architecture_ratchet_baseline.yaml"
)
DOMAIN_TAXONOMY = Path(
    "quwoquan_service/contracts/metadata/_shared/domain_taxonomy.yaml"
)
CONTRACT_GRAPH = Path("quwoquan_service/generated/contract_graph.json")
SERVICE_ROOT = Path("quwoquan_service/services")
RETIRED_TRAVEL_SERVICE = Path("quwoquan_service/services/travel-service")
TRAVEL_DOMAIN = "travel"

BASELINE_SCHEMA = "vertical-architecture-ratchet"
REQUIRED_BUCKETS = (
    "platform_vertical_branches",
    "content_vertical_usage",
    "domain_taxonomy_runtime_consumers",
)
TRAVEL_DEPENDENCY_AREAS = ("app", "assistant", "api_edge")

CODE_SUFFIXES = {
    ".dart",
    ".go",
    ".java",
    ".js",
    ".kt",
    ".kts",
    ".py",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
TEXT_SUFFIXES = CODE_SUFFIXES | {".json", ".toml", ".yaml", ".yml"}
SKIP_PARTS = {
    ".dart_tool",
    ".git",
    ".qwq_output",
    "__pycache__",
    "build",
    "fixtures",
    "generated",
    "migrations",
    "mock",
    "node_modules",
    "test",
    "testdata",
    "tests",
    "testsupport",
    "vendor",
}
COPY_PARTS = {"l10n"}

CONTENT_VERTICAL_RE = re.compile(r"\b(?:contentVertical|ContentVertical|content_vertical)\b")
TAXONOMY_FILENAME_RE = re.compile(r"\bdomain_taxonomy\.yaml\b")
CASE_RE = re.compile(
    r"(?m)^[ \t]*case[ \t]+(?P<quote>['\"])(?P<value>[a-z][a-z0-9_-]*)"
    r"(?P=quote)[ \t]*(?:,|:|=>)"
)
CONTENT_VERTICAL_COMPARE_RE = re.compile(
    r"(?P<left>\b(?:contentVertical|ContentVertical|content_vertical)\b)"
    r"\s*(?:==|!=)\s*(?P<right>['\"][^'\"]+['\"])"
    r"|(?P<reverse>['\"][^'\"]+['\"])\s*(?:==|!=)\s*"
    r"(?P<identifier>\b(?:contentVertical|ContentVertical|content_vertical)\b)"
)
APP_TRAVEL_DEPENDENCY_RE = re.compile(
    r"package:quwoquan_app/travel/"
    r"|runtime/transport/generated/travel/"
    r"|\btravel-service\b"
    r"|\btravel_service\b"
    r"|\bTravelService\b"
    r"|\bTRAVEL_SERVICE\b"
)
SERVICE_TRAVEL_DEPENDENCY_RE = re.compile(
    r"\btravel-service\b"
    r"|\btravel_service\b"
    r"|\bTravelService\b"
    r"|\bTRAVEL_SERVICE\b"
    r"|\btravel_client\b"
    r"|\bTravelClient\b"
)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PATH_RE = re.compile(r"^[a-zA-Z0-9_.@+-]+(?:/[a-zA-Z0-9_.@+-]+)*$")

VERTICAL_WORD_STOPLIST = {
    "and",
    "companion",
    "decision",
    "general",
    "planning",
    "the",
    "transport",
    "wellness",
}


@dataclass(frozen=True)
class HitSummary:
    count: int
    digest: str
    samples: tuple[str, ...]


@dataclass(frozen=True)
class Snapshot:
    vertical_terms: frozenset[str]
    service_domains: Mapping[str, str]
    platform_vertical_branches: Mapping[str, HitSummary]
    content_vertical_usage: Mapping[str, HitSummary]
    domain_taxonomy_runtime_consumers: Mapping[str, HitSummary]
    travel_service_dependencies: Mapping[str, Mapping[str, HitSummary]]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_skipped(relative: Path, *, exclude_copy: bool = False) -> bool:
    parts = set(relative.parts)
    return bool(parts & SKIP_PARTS) or (exclude_copy and bool(parts & COPY_PARTS))


def _iter_files(
    root: Path,
    relative_roots: Sequence[Path],
    *,
    suffixes: set[str],
    exclude_copy: bool = False,
) -> Iterable[Path]:
    seen: set[Path] = set()
    for relative_root in relative_roots:
        scan_root = root / relative_root
        if not scan_root.is_dir():
            continue
        for directory, child_directories, filenames in os.walk(scan_root):
            relative_directory = Path(directory).relative_to(root)
            child_directories[:] = sorted(
                name
                for name in child_directories
                if not _is_skipped(
                    relative_directory / name,
                    exclude_copy=exclude_copy,
                )
            )
            for filename in sorted(filenames):
                path = Path(directory) / filename
                if path.suffix.lower() not in suffixes:
                    continue
                if (
                    "_test." in path.name
                    or path.name.startswith("test_")
                    or path.name.endswith("_test.dart")
                ):
                    continue
                relative = path.relative_to(root)
                if _is_skipped(relative, exclude_copy=exclude_copy):
                    continue
                if path in seen:
                    continue
                seen.add(path)
                yield path


def _code_without_comment_lines(text: str) -> str:
    """移除纯注释行，避免文案/说明中的示例被当作控制流。"""

    lines: list[str] = []
    in_block_comment = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            lines.append("")
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped[2:]:
                in_block_comment = True
            lines.append("")
            continue
        if stripped.startswith(("//", "#", "*")):
            lines.append("")
            continue
        lines.append(line)
    return "\n".join(lines)


def _normalized_line(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    return re.sub(r"\s+", " ", text[start:end].strip())


def _digest(path: str, fingerprints: Sequence[str]) -> str:
    payload = json.dumps(
        {"path": path, "fingerprints": sorted(fingerprints)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _summary(path: str, fingerprints: Sequence[str], samples: Sequence[str]) -> HitSummary:
    return HitSummary(
        count=len(fingerprints),
        digest=_digest(path, fingerprints),
        samples=tuple(samples[:5]),
    )


def _load_yaml_mapping(path: Path, *, label: str) -> dict:
    try:
        document = yaml.safe_load(_read_text(path))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{label} 无法读取或解析: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} 必须是 mapping: {path}")
    return document


def _vertical_tokens_from_text(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        return set()
    tokens = {normalized}
    tokens.update(
        token
        for token in normalized.split("_")
        if len(token) >= 4 and token not in VERTICAL_WORD_STOPLIST
    )
    return tokens


def load_vertical_terms(root: Path) -> frozenset[str]:
    path = root / DOMAIN_TAXONOMY
    document = _load_yaml_mapping(path, label="domain taxonomy")
    domains = document.get("domains")
    if not isinstance(domains, list):
        raise ValueError(f"domain taxonomy 缺少 domains 列表: {path}")
    terms: set[str] = set()
    for entry in domains:
        if not isinstance(entry, dict) or entry.get("mode") != "content":
            continue
        terms.update(_vertical_tokens_from_text(entry.get("id")))
        label = entry.get("label")
        if isinstance(label, dict):
            terms.update(_vertical_tokens_from_text(label.get("en")))
        for assistant_id in entry.get("assistant_domain_ids") or []:
            terms.update(_vertical_tokens_from_text(assistant_id))
        for category in entry.get("sub_categories") or []:
            terms.update(_vertical_tokens_from_text(category))
    if not terms:
        raise ValueError("domain taxonomy 没有可派生的 content vertical 标识")
    return frozenset(terms)


def _load_contract_graph_domains(root: Path) -> set[str]:
    path = root / CONTRACT_GRAPH
    if not path.is_file():
        return set()
    try:
        document = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"ContractGraph 无法读取或解析: {path}: {exc}") from exc
    objects = document.get("objects") if isinstance(document, dict) else None
    if not isinstance(objects, list):
        return set()
    return {
        str(item.get("domain") or "").strip()
        for item in objects
        if isinstance(item, dict) and str(item.get("domain") or "").strip()
    }


def _service_has_files(path: Path) -> bool:
    return any(
        candidate.is_file() and candidate.name != ".DS_Store"
        for candidate in path.rglob("*")
    )


def scan_service_domains(root: Path) -> tuple[dict[str, str], list[str]]:
    services_root = root / SERVICE_ROOT
    if not services_root.is_dir():
        return {}, []
    graph_domains = _load_contract_graph_domains(root)
    service_domains: dict[str, str] = {}
    issues: list[str] = []
    domain_owners: dict[str, list[str]] = {}
    for service_dir in sorted(path for path in services_root.iterdir() if path.is_dir()):
        if not _service_has_files(service_dir):
            continue
        relative = _relative(root, service_dir)
        domain_path = service_dir / "contracts" / "domain.yaml"
        if not domain_path.is_file():
            issues.append(
                f"{relative}: 新服务边界缺少 contracts/domain.yaml owner metadata；"
                "不得以垂类目录绕过 canonical domain owner"
            )
            continue
        document = _load_yaml_mapping(domain_path, label=f"{relative} domain owner")
        domain = str(document.get("domain") or "").strip()
        if not domain:
            issues.append(f"{relative}: contracts/domain.yaml.domain 不能为空")
            continue
        service_domains[relative] = domain
        domain_owners.setdefault(domain, []).append(relative)
        if graph_domains and domain not in graph_domains:
            issues.append(
                f"{relative}: domain={domain!r} 未被 canonical ContractGraph 对象拥有；"
                "禁止新建无对象 owner 的垂类服务"
            )
    for domain, owners in sorted(domain_owners.items()):
        if len(owners) > 1:
            issues.append(
                f"domain={domain!r} 同时由多个服务拥有: {', '.join(sorted(owners))}"
            )
    return service_domains, issues


def _matches_vertical_service(
    service_path: str,
    domain: str,
    vertical_terms: frozenset[str],
) -> bool:
    name = Path(service_path).name
    stem = name.removesuffix("-service").removesuffix("-gateway")
    candidates = {
        stem.lower().replace("-", "_"),
        domain.lower().replace("-", "_"),
    }
    for candidate in candidates:
        if candidate in vertical_terms:
            return True
        if any(
            candidate.startswith(f"{term}_") or candidate.endswith(f"_{term}")
            for term in vertical_terms
        ):
            return True
    return False


def _scan_identifier_hits(
    root: Path,
    paths: Iterable[Path],
    pattern: re.Pattern[str],
) -> dict[str, HitSummary]:
    results: dict[str, HitSummary] = {}
    for path in paths:
        relative = _relative(root, path)
        text = _code_without_comment_lines(_read_text(path))
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        fingerprints = [
            f"{match.group(0)}|{_normalized_line(text, match.start())}"
            for match in matches
        ]
        samples = [f"{relative}: {_normalized_line(text, match.start())}" for match in matches]
        results[relative] = _summary(relative, fingerprints, samples)
    return dict(sorted(results.items()))


def scan_content_vertical_usage(root: Path) -> dict[str, HitSummary]:
    roots = (
        Path("quwoquan_app/lib"),
        Path("quwoquan_data/scripts"),
        Path("quwoquan_service/runtime"),
        Path("quwoquan_service/services"),
    )
    return _scan_identifier_hits(
        root,
        _iter_files(root, roots, suffixes=TEXT_SUFFIXES, exclude_copy=True),
        CONTENT_VERTICAL_RE,
    )


def _is_vertical_label(value: str, vertical_terms: frozenset[str]) -> bool:
    normalized = value.lower().replace("-", "_")
    return normalized in vertical_terms or any(
        normalized.startswith(f"{term}_") for term in vertical_terms
    )


def scan_platform_vertical_branches(
    root: Path,
    vertical_terms: frozenset[str],
) -> dict[str, HitSummary]:
    roots = (
        Path("quwoquan_app/lib"),
        Path("quwoquan_data/scripts"),
        Path("quwoquan_service/runtime"),
        Path("quwoquan_service/services"),
    )
    results: dict[str, HitSummary] = {}
    for path in _iter_files(
        root,
        roots,
        suffixes=CODE_SUFFIXES,
        exclude_copy=True,
    ):
        relative = _relative(root, path)
        text = _code_without_comment_lines(_read_text(path))
        found: list[tuple[int, str]] = []
        for match in CASE_RE.finditer(text):
            value = match.group("value")
            if _is_vertical_label(value, vertical_terms):
                found.append((match.start(), f"case:{value}"))
        for match in CONTENT_VERTICAL_COMPARE_RE.finditer(text):
            found.append((match.start(), f"comparison:{match.group(0)}"))
        if not found:
            continue
        fingerprints = [
            f"{kind}|{_normalized_line(text, offset)}" for offset, kind in found
        ]
        samples = [
            f"{relative}: {_normalized_line(text, offset)}" for offset, _ in found
        ]
        results[relative] = _summary(relative, fingerprints, samples)
    return dict(sorted(results.items()))


def scan_taxonomy_runtime_consumers(root: Path) -> dict[str, HitSummary]:
    """只扫可执行业务树；canonical contract、生成体、测试、迁移和 gate 不算消费者。"""

    roots = (
        Path("quwoquan_app/lib"),
        Path("quwoquan_data/scripts"),
        Path("quwoquan_service/runtime"),
        Path("quwoquan_service/services"),
    )
    paths = (
        path
        for path in _iter_files(
            root,
            roots,
            suffixes=TEXT_SUFFIXES,
            exclude_copy=True,
        )
        if "contracts" not in path.relative_to(root).parts
        and path.relative_to(root) != DOMAIN_TAXONOMY
    )
    return _scan_identifier_hits(root, paths, TAXONOMY_FILENAME_RE)


def scan_travel_dependencies(root: Path) -> dict[str, dict[str, HitSummary]]:
    app = _scan_identifier_hits(
        root,
        _iter_files(
            root,
            (Path("quwoquan_app/lib"),),
            suffixes=CODE_SUFFIXES,
            exclude_copy=True,
        ),
        APP_TRAVEL_DEPENDENCY_RE,
    )
    assistant = _scan_identifier_hits(
        root,
        _iter_files(
            root,
            (Path("quwoquan_service/services/assistant-service"),),
            suffixes=TEXT_SUFFIXES,
        ),
        SERVICE_TRAVEL_DEPENDENCY_RE,
    )
    api_edge = _scan_identifier_hits(
        root,
        _iter_files(
            root,
            (Path("quwoquan_service/services/api-edge"),),
            suffixes=TEXT_SUFFIXES,
        ),
        SERVICE_TRAVEL_DEPENDENCY_RE,
    )
    return {"app": app, "assistant": assistant, "api_edge": api_edge}


def build_snapshot(root: Path) -> tuple[Snapshot, list[str]]:
    vertical_terms = load_vertical_terms(root)
    service_domains, service_issues = scan_service_domains(root)
    return (
        Snapshot(
            vertical_terms=vertical_terms,
            service_domains=service_domains,
            platform_vertical_branches=scan_platform_vertical_branches(
                root, vertical_terms
            ),
            content_vertical_usage=scan_content_vertical_usage(root),
            domain_taxonomy_runtime_consumers=scan_taxonomy_runtime_consumers(root),
            travel_service_dependencies=scan_travel_dependencies(root),
        ),
        service_issues,
    )


def _parse_entries(value: object, *, label: str) -> dict[str, HitSummary]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是 mapping")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"{label}.entries 必须是 list")
    parsed: dict[str, HitSummary] = {}
    seen_order: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{label}.entries 条目必须是 mapping")
        path = str(entry.get("path") or "").strip()
        count = entry.get("count")
        digest = str(entry.get("digest") or "").strip()
        if not PATH_RE.fullmatch(path) or "*" in path:
            raise ValueError(f"{label}: 基线只接受精确相对路径，不接受通配符: {path!r}")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError(f"{label}: {path} count 必须是正整数")
        if DIGEST_RE.fullmatch(digest) is None:
            raise ValueError(f"{label}: {path} digest 必须是 canonical sha256")
        if path in parsed:
            raise ValueError(f"{label}: 重复路径 {path}")
        parsed[path] = HitSummary(count=count, digest=digest, samples=())
        seen_order.append(path)
    if seen_order != sorted(seen_order):
        raise ValueError(f"{label}.entries 必须按 path 升序")
    for required in ("owner", "retirement_condition"):
        if not str(value.get(required) or "").strip():
            raise ValueError(f"{label}.{required} 必填")
    return parsed


def load_baseline(path: Path) -> tuple[dict[str, dict[str, HitSummary]], dict]:
    document = _load_yaml_mapping(path, label="vertical architecture baseline")
    if document.get("schema") != BASELINE_SCHEMA:
        raise ValueError(f"baseline schema 必须是 {BASELINE_SCHEMA}")
    allowed_sections = {"schema", "governance", *REQUIRED_BUCKETS}
    unsupported_sections = sorted(set(document) - allowed_sections)
    if unsupported_sections:
        raise ValueError(
            "baseline 不再接受 travel-service allowance/dependency 或其他迁移期 section: "
            + ", ".join(unsupported_sections)
        )
    governance = document.get("governance")
    if not isinstance(governance, dict):
        raise ValueError("baseline.governance 必须是 mapping")
    for required in ("owner", "reason", "retirement_condition"):
        if not str(governance.get(required) or "").strip():
            raise ValueError(f"baseline.governance.{required} 必填")

    buckets: dict[str, dict[str, HitSummary]] = {}
    for name in REQUIRED_BUCKETS:
        buckets[name] = _parse_entries(document.get(name), label=name)
    return buckets, document


def _path_in_scope(path: str, scope: str) -> bool:
    is_app = path.startswith("quwoquan_app/")
    if scope == "all":
        return True
    if scope == "app":
        return is_app
    return not is_app


def _compare_bucket(
    name: str,
    current: Mapping[str, HitSummary],
    baseline: Mapping[str, HitSummary],
    *,
    scope: str,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    reductions: list[str] = []
    for path, actual in sorted(current.items()):
        if not _path_in_scope(path, scope):
            continue
        allowed = baseline.get(path)
        if allowed is None:
            failures.append(
                f"{name}: 新增命中 {path} count={actual.count}\n      "
                + "\n      ".join(actual.samples)
            )
            continue
        if actual.count > allowed.count:
            failures.append(
                f"{name}: {path} 命中增加 baseline={allowed.count} "
                f"current={actual.count}\n      "
                + "\n      ".join(actual.samples)
            )
            continue
        if actual.count == allowed.count and actual.digest != allowed.digest:
            failures.append(
                f"{name}: {path} 等量命中摘要改变，疑似以新命中替换旧命中；"
                "不得横向搬运债务"
            )
            continue
        if actual.count < allowed.count:
            reductions.append(
                f"{name}: {path} {allowed.count}->{actual.count}"
            )
    for path, allowed in sorted(baseline.items()):
        if not _path_in_scope(path, scope) or path in current:
            continue
        reductions.append(f"{name}: {path} {allowed.count}->0")
    return failures, reductions


def _bucket_debt(bucket: Mapping[str, HitSummary], *, scope: str) -> dict[str, int]:
    filtered = {
        path: summary
        for path, summary in bucket.items()
        if _path_in_scope(path, scope)
    }
    return {
        "paths": len(filtered),
        "hits": sum(summary.count for summary in filtered.values()),
    }


def evaluate(
    root: Path,
    baseline_path: Path,
    *,
    scope: str = "all",
) -> tuple[list[str], dict]:
    snapshot, discovery_issues = build_snapshot(root)
    baseline, _document = load_baseline(baseline_path)
    failures = list(discovery_issues) if scope in {"all", "service"} else []
    reductions: list[str] = []

    retired_path = RETIRED_TRAVEL_SERVICE.as_posix()
    if scope in {"all", "service"} and (root / RETIRED_TRAVEL_SERVICE).is_dir():
        failures.append(
            f"retired_travel_service: {retired_path} 目录已退役且必须永久不存在；"
            "不得通过恢复旧 owner、源码或 digest 重新启用"
        )
    for service_path, domain in sorted(snapshot.service_domains.items()):
        if not _matches_vertical_service(
            service_path, domain, snapshot.vertical_terms
        ):
            continue
        failures.append(
            f"vertical_service: 禁止新增/恢复垂类服务 {service_path} "
            f"(domain owner={domain!r})；垂类必须由 Topic/Distribution/Skill/"
            "Presentation/ExperiencePackage 数据组合承载"
        )

    current_buckets = {
        "platform_vertical_branches": snapshot.platform_vertical_branches,
        "content_vertical_usage": snapshot.content_vertical_usage,
        "domain_taxonomy_runtime_consumers": (
            snapshot.domain_taxonomy_runtime_consumers
        ),
    }
    for name, current in current_buckets.items():
        bucket_failures, bucket_reductions = _compare_bucket(
            name,
            current,
            baseline[name],
            scope=scope,
        )
        failures.extend(bucket_failures)
        reductions.extend(bucket_reductions)

    for area, current in snapshot.travel_service_dependencies.items():
        if scope == "app" and area != "app":
            continue
        if scope == "service" and area == "app":
            continue
        for path, summary in sorted(current.items()):
            failures.append(
                f"travel_service_dependencies.{area}: 已退役依赖必须永久为零，"
                f"发现 {path} count={summary.count}\n      "
                + "\n      ".join(summary.samples)
            )

    report_buckets = {
        **current_buckets,
        **{
            f"travel_service_dependencies.{area}": dependencies
            for area, dependencies in snapshot.travel_service_dependencies.items()
        },
    }
    debt = {
        name: _bucket_debt(current, scope=scope)
        for name, current in report_buckets.items()
    }
    report = {
        "scope": scope,
        "vertical_term_count": len(snapshot.vertical_terms),
        "service_boundaries": len(snapshot.service_domains),
        "retired_travel_service_present": (root / RETIRED_TRAVEL_SERVICE).is_dir(),
        "debt": debt,
        "reductions": reductions,
    }
    return failures, report


def _print_report(report: Mapping[str, object]) -> None:
    print(f"[vertical-architecture-ratchet] scope={report['scope']}")
    print(
        "  owner metadata: "
        f"services={report['service_boundaries']} "
        f"vertical_terms_derived={report['vertical_term_count']} "
        "retired_travel_present="
        f"{str(report['retired_travel_service_present']).lower()}"
    )
    debt = report["debt"]
    assert isinstance(debt, dict)
    for name, value in debt.items():
        assert isinstance(value, dict)
        print(f"  debt {name}: paths={value['paths']} hits={value['hits']}")
    reductions = report["reductions"]
    assert isinstance(reductions, list)
    if reductions:
        print(f"  ratchet reductions accepted automatically: {len(reductions)}")
        for reduction in reductions:
            print(f"    - {reduction}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--scope", choices=("all", "app", "service"), default="all")
    parser.add_argument("--json", action="store_true", help="输出机器可读报告")
    args = parser.parse_args()
    try:
        failures, report = evaluate(
            Path(args.root).resolve(),
            Path(args.baseline).resolve(),
            scope=args.scope,
        )
    except ValueError as exc:
        print(f"[vertical-architecture-ratchet] FAIL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({**report, "failures": failures}, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    if failures:
        if not args.json:
            print("[vertical-architecture-ratchet] GATE_BLOCK")
            for index, failure in enumerate(failures, start=1):
                print(f"  {index}. {failure}")
        return 1
    if not args.json:
        print("[vertical-architecture-ratchet] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
