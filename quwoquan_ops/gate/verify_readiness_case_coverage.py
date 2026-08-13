#!/usr/bin/env python3
"""让 UAT 与 ops 层的测试义务缺口可见且只减不增。

ContractGraph 的 readiness_cases 长期偏科：`layer: user_acceptance` 与
`producer: ops` 的声明远少于磁盘上真实存在的验收测试。测试文件存在而契约
不声明，意味着 readiness 计算永远看不到这层证据，商用准出被静默架空。

本门禁做三件事：

* 反向派生缺失清单 —— App `test/user_acceptance/service/<svc>/<ctx>/<obj>/`
  下存在 `*_test.dart` 的对象，其 `operations.yaml` 必须声明至少一条
  `layer: user_acceptance` 的 readiness case；Ops
  `tests/acceptance/user_acceptance/service_ops/<service>/` 下存在验收测试的
  服务，必须有至少一条 `producer: ops` 的 case。缺失进入棘轮：新增缺失
  BLOCK，缺失减少时基线必须同步收紧（stale 条目 BLOCK）。
* 声明真实性 strict-zero —— 已声明的 `layer: user_acceptance` case 的
  `runner_source_path` 必须存在于磁盘；指向不存在文件的声明立即 BLOCK，
  不进入棘轮。
* 空扫描 fail-closed —— 扫不到对象契约或测试根缺失时 FAIL，绝不空集 PASS。

棘轮基线：`quwoquan_ops/policies/gates/readiness_case_coverage_baseline.json`。
基线只允许收紧；补齐声明后必须同批删除对应基线条目。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_RELATIVE = "quwoquan_ops/policies/gates/readiness_case_coverage_baseline.json"
APP_UAT_ROOT = "quwoquan_app/test/user_acceptance/service"
OPS_UAT_ROOT = "quwoquan_ops/tests/acceptance/user_acceptance/service_ops"


class ScanError(Exception):
    """Raised when the scan itself cannot be trusted, never for a policy failure."""


def app_service_to_cloud(name: str) -> str:
    """App 目录用下划线（chat_service），云侧服务目录用 kebab（chat-service）。"""
    return name.replace("_", "-")


def app_uat_objects(repo_root: Path) -> dict[tuple[str, str, str], list[str]]:
    root = repo_root / APP_UAT_ROOT
    if not root.is_dir():
        raise ScanError(f"App user_acceptance root does not exist: {root}")
    found: dict[tuple[str, str, str], list[str]] = {}
    for path in sorted(root.glob("*/*/*/*_test.dart")):
        relative = path.relative_to(root)
        service, context, obj = relative.parts[0], relative.parts[1], relative.parts[2]
        found.setdefault((service, context, obj), []).append(
            path.relative_to(repo_root).as_posix()
        )
    if not found:
        raise ScanError(f"scanned 0 user_acceptance tests under {root}")
    return found


def ops_uat_services(repo_root: Path) -> list[str]:
    root = repo_root / OPS_UAT_ROOT
    if not root.is_dir():
        raise ScanError(f"Ops user_acceptance root does not exist: {root}")
    services = sorted(entry.name for entry in root.iterdir() if entry.is_dir())
    if not services:
        raise ScanError(f"scanned 0 service_ops acceptance directories under {root}")
    return services


def operations_documents(repo_root: Path) -> dict[tuple[str, str, str], tuple[Path, dict]]:
    service_root = repo_root / "quwoquan_service"
    if not service_root.is_dir():
        raise ScanError(f"service root does not exist: {service_root}")
    documents: dict[tuple[str, str, str], tuple[Path, dict]] = {}
    for path in sorted(service_root.glob("services/*/contracts/*/*/operations.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise ScanError(f"{path}: {error}") from error
        if not isinstance(document, dict):
            continue
        relative = path.relative_to(service_root)
        # ('services', '<service>', 'contracts', '<context>', '<object>', 'operations.yaml')
        service, context, obj = relative.parts[1], relative.parts[3], relative.parts[4]
        documents[(service, context, obj)] = (path, document)
    if not documents:
        raise ScanError(f"scanned 0 operations.yaml under {service_root}")
    return documents


def declared_layers(
    documents: dict[tuple[str, str, str], tuple[Path, dict]],
) -> tuple[set[tuple[str, str, str]], set[str], list[str]]:
    """Return (objects with UA cases, services with ops cases, strict failures)."""
    ua_objects: set[tuple[str, str, str]] = set()
    ops_services: set[str] = set()
    failures: list[str] = []
    for key, (path, document) in sorted(documents.items()):
        cases = document.get("readiness_cases") or []
        if not isinstance(cases, list):
            continue
        for case in cases:
            if not isinstance(case, dict):
                continue
            if case.get("producer") == "ops":
                ops_services.add(key[0])
            if case.get("layer") != "user_acceptance":
                continue
            ua_objects.add(key)
            runner = str(case.get("runner_source_path", "")).strip()
            if not runner:
                failures.append(
                    f"{path}: user_acceptance case "
                    f"{case.get('case_id')!r} declares no runner_source_path; "
                    "a UA declaration without a runner is unfalsifiable"
                )
                continue
            if not (DEFAULT_REPO_ROOT / runner).is_file() and not (
                path.parents[5] / runner
            ).is_file():
                failures.append(
                    f"{path}: user_acceptance case {case.get('case_id')!r} "
                    f"runner_source_path {runner!r} does not exist on disk; "
                    "a declaration pointing at nothing is worse than no declaration"
                )
    return ua_objects, ops_services, failures


def load_baseline(repo_root: Path) -> tuple[set[str], set[str], list[str]]:
    path = repo_root / BASELINE_RELATIVE
    if not path.is_file():
        return set(), set(), []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return set(), set(), [f"baseline 解析失败: {error}"]
    problems: list[str] = []
    governance = document.get("_governance")
    if not isinstance(governance, dict):
        problems.append("baseline 缺少 _governance 段")
        governance = {}
    for required in ("owner", "reason", "expires_when"):
        if not str(governance.get(required, "")).strip():
            problems.append(f"baseline governance 缺少 {required}")
    ua = {str(item) for item in document.get("missing_user_acceptance_objects") or []}
    ops = {str(item) for item in document.get("missing_ops_producer_services") or []}
    return ua, ops, problems


def run(repo_root: Path, print_current: bool) -> int:
    uat_tests = app_uat_objects(repo_root)
    ops_services_on_disk = ops_uat_services(repo_root)
    documents = operations_documents(repo_root)
    ua_declared, ops_declared, strict_failures = declared_layers(documents)

    missing_ua: list[str] = []
    for (service, context, obj), _tests in sorted(uat_tests.items()):
        cloud_key = (app_service_to_cloud(service), context, obj)
        if cloud_key not in documents:
            strict_failures.append(
                f"App UAT tests exist for {service}/{context}/{obj} but no "
                "operations.yaml owns that object; the test tree and the contract "
                "tree disagree about the object existing"
            )
            continue
        if cloud_key not in ua_declared:
            missing_ua.append(f"{cloud_key[0]}/{context}/{obj}")

    missing_ops = [
        service for service in ops_services_on_disk if service not in ops_declared
    ]

    if print_current:
        print(
            json.dumps(
                {
                    "missing_user_acceptance_objects": missing_ua,
                    "missing_ops_producer_services": missing_ops,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    baseline_ua, baseline_ops, baseline_problems = load_baseline(repo_root)
    failures = list(strict_failures)
    failures.extend(baseline_problems)

    new_ua = sorted(set(missing_ua) - baseline_ua)
    stale_ua = sorted(baseline_ua - set(missing_ua))
    new_ops = sorted(set(missing_ops) - baseline_ops)
    stale_ops = sorted(baseline_ops - set(missing_ops))

    for item in new_ua:
        failures.append(
            f"object {item} has user_acceptance tests on disk but declares no "
            "layer=user_acceptance readiness case; new gaps are blocked, declare "
            "the case instead of relying on the file existing"
        )
    for item in new_ops:
        failures.append(
            f"service {item} has service_ops acceptance tests but declares no "
            "producer=ops readiness case; new gaps are blocked"
        )
    for item in stale_ua + stale_ops:
        failures.append(
            f"baseline entry {item!r} is no longer a real gap; tighten "
            f"{BASELINE_RELATIVE} in the same change (ratchet only shrinks)"
        )

    print(
        "[readiness-case-coverage] "
        f"uat_test_objects={len(uat_tests)} ua_declared={len(ua_declared)} "
        f"missing_ua={len(missing_ua)} missing_ops={len(missing_ops)} "
        f"baseline_ua={len(baseline_ua)} baseline_ops={len(baseline_ops)}"
    )
    if failures:
        for failure in failures:
            print(f"[readiness-case-coverage] FAIL: {failure}", file=sys.stderr)
        print(
            f"[readiness-case-coverage] GATE_BLOCK: {len(failures)} failure(s)",
            file=sys.stderr,
        )
        return 1
    print("[readiness-case-coverage] OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument(
        "--print-current",
        action="store_true",
        help="打印当前实际缺口，用于生成或收紧基线",
    )
    arguments = parser.parse_args(argv)
    repo_root = Path(arguments.repo_root).resolve()
    try:
        return run(repo_root, arguments.print_current)
    except ScanError as error:
        print(f"[readiness-case-coverage] FAIL: {error}", file=sys.stderr)
        return 1
    except (OSError, yaml.YAMLError) as error:
        print(f"[readiness-case-coverage] FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
