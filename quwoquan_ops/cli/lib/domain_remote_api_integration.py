"""Derive and validate object-level App Remote API integration evidence.

The committed ContractGraph is the only coverage map. This module never keeps
an object or test-path inventory; it selects the five governed domains from
``readinessEvidence`` and validates the physical App tests and their harnesses.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


from quwoquan_ops.cli.lib.feature_tree.evidence import extract_spec_refs
from quwoquan_ops.cli.lib.feature_tree.patterns import ACCEPTANCE_ANCHOR_RE
from quwoquan_ops.cli.lib.test_data.cases.ids import AcceptanceCaseId

GOVERNED_DOMAINS = (
    "entity",
    "notification",
    "realtime",
    "recommendation",
    "tag",
)
CONTRACT_GRAPH_PATH = Path("quwoquan_service/generated/contract_graph.json")
APP_API_TEST_PREFIX = "quwoquan_app/test/api_integration/service/"
APP_API_TEST_SUFFIX = "__api_integration_test.dart"
# spec_ref 语法解析复用 feature-tree 库唯一 lexical 入口；本处只保留语义过滤：
# 稳定证据必须至少有一个指向验收锚点（`.tN` 子句同样成立）的显式绑定。
# 闭集与位数引用 feature-tree 库唯一定义点。
_ACCEPTANCE_ANCHOR = ACCEPTANCE_ANCHOR_RE
HARNESS_IMPORT = re.compile(
    r"import\s+'([^']*support/runtime/api_contract/"
    r"[a-z0-9_]+_api_contract_harness\.dart)';"
)
FORBIDDEN_SOURCE_PATTERNS = {
    "dynamic skip": re.compile(r"\b(?:skip|skipTest|markTestSkipped)\b"),
    "fixture": re.compile(r"\bfixture\b", re.IGNORECASE),
    "mock": re.compile(r"\bmock\w*\b", re.IGNORECASE),
    "fake": re.compile(r"\bfake\w*\b", re.IGNORECASE),
    "raw dart:io": re.compile(r"import\s+'dart:io'"),
    "raw package:http": re.compile(r"package:http/"),
    "raw HttpClient": re.compile(r"\bHttpClient\b"),
}
FORBIDDEN_TEST_ONLY_PATTERNS = {
    "direct adapter import": re.compile(r"/adapters/[^']+\.dart'"),
    "platform environment": re.compile(r"\bPlatform\.environment\b"),
}
TYPED_ENVIRONMENT_RESOLVER = "api_contract_environment.dart"
MANAGED_GATHERING_PLAN_DEFINE_KEYS = (
    "QWQ_GATHERING_PLAN_ACCESS_TOKEN",
    "QWQ_GATHERING_PLAN_ACCOUNT_ID",
    "QWQ_GATHERING_PLAN_PERSONA_ID",
    "QWQ_GATHERING_PLAN_GATHERING_ID",
    "QWQ_GATHERING_PLAN_PLAN_ID",
    "QWQ_GATHERING_PLAN_VERSION",
    "QWQ_GATHERING_PLAN_CURRENT_REVISION_ID",
    "QWQ_GATHERING_PLAN_CURRENT_REVISION_NUMBER",
    "QWQ_GATHERING_PLAN_CURRENT_REVISION_DIGEST",
)


@dataclass(frozen=True)
class DomainRemoteApiCase:
    domain: str
    object_id: str
    test_path: str
    test_sha256: str
    service_test_paths: tuple[str, ...]
    readiness_case_ids: tuple[str, ...] = ()
    harness_path: str = ""

    @property
    def service_api_test_count(self) -> int:
        return len(self.service_test_paths)

    def document(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "objectId": self.object_id,
            "testPath": self.test_path,
            "testSha256": self.test_sha256,
            "serviceApiTestCount": self.service_api_test_count,
            "readinessCaseIds": list(self.readiness_case_ids),
            "harnessPath": self.harness_path,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def managed_readiness_case_ids(
    cases: list[DomainRemoteApiCase],
) -> tuple[AcceptanceCaseId, ...]:
    managed_case_id = AcceptanceCaseId.CIRCLE_GATHERING_PLAN
    return (
        (managed_case_id,)
        if any(
            case_id == managed_case_id.value
            for case in cases
            for case_id in case.readiness_case_ids
        )
        else ()
    )


def create_private_define_file(definitions: Mapping[str, object]) -> Path:
    missing = [
        key
        for key in MANAGED_GATHERING_PLAN_DEFINE_KEYS
        if not str(definitions.get(key) or "").strip()
    ]
    if missing:
        raise ValueError(
            "managed GatheringPlan definitions are incomplete: " + ", ".join(missing)
        )
    fd, raw_path = tempfile.mkstemp(prefix="qwq-gathering-plan-", suffix=".json")
    path = Path(raw_path)
    try:
        os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "w", encoding="utf-8")
        fd = -1
        with handle:
            json.dump(
                {key: definitions[key] for key in MANAGED_GATHERING_PLAN_DEFINE_KEYS},
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
    except BaseException:
        if fd >= 0:
            os.close(fd)
        path.unlink(missing_ok=True)
        raise
    return path


def sanitized_flutter_argv(argv: list[str]) -> list[str]:
    sanitized: list[str] = []
    for item in argv:
        if item.startswith("--dart-define-from-file="):
            sanitized.append("--dart-define-from-file=<private>")
        else:
            sanitized.append(item)
    return sanitized


def _redact_private_flutter_output(
    output: object,
    *,
    private_path: Path,
    definitions: Mapping[str, object],
) -> str:
    redacted = str(output or "").replace(str(private_path), "<private>")
    private_values = sorted(
        {
            str(definitions[key])
            for key in MANAGED_GATHERING_PLAN_DEFINE_KEYS
            if str(definitions.get(key) or "")
        },
        key=len,
        reverse=True,
    )
    for value in private_values:
        redacted = redacted.replace(value, "<private>")
    return redacted


def run_flutter_with_private_defines(
    definitions: Mapping[str, object],
    *,
    command_prefix: list[str],
    test_paths: list[str],
    runner: Any,
    cwd: Path,
) -> tuple[Any, list[str]]:
    define_path = create_private_define_file(definitions)
    command = [
        *command_prefix,
        f"--dart-define-from-file={define_path}",
        *test_paths,
    ]
    try:
        result = runner(command, cwd=cwd)
        sanitized_result = subprocess.CompletedProcess(
            sanitized_flutter_argv(command),
            result.returncode,
            stdout=_redact_private_flutter_output(
                result.stdout,
                private_path=define_path,
                definitions=definitions,
            ),
            stderr=_redact_private_flutter_output(
                result.stderr,
                private_path=define_path,
                definitions=definitions,
            ),
        )
    finally:
        define_path.unlink(missing_ok=True)
    if define_path.exists():
        raise RuntimeError("managed GatheringPlan private define cleanup failed")
    return sanitized_result, sanitized_flutter_argv(command)


def has_stable_spec_ref(source: str) -> bool:
    """源码是否声明了至少一个指向验收锚点的显式 spec_ref 绑定。"""
    return any(
        _ACCEPTANCE_ANCHOR.match(ref.partition("#")[2])
        for ref in extract_spec_refs(source)
    )


def _graph_document(root: Path) -> dict[str, Any]:
    path = root / CONTRACT_GRAPH_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("ContractGraph root must be an object")
    evidence = document.get("readinessEvidence")
    if not isinstance(evidence, list):
        raise ValueError("ContractGraph readinessEvidence must be an array")
    return document


def discover_cases(root: Path) -> tuple[list[DomainRemoteApiCase], list[str]]:
    """Select governed App API cases from ContractGraph readiness evidence."""

    return _discover_cases(root, required_test_paths=None)


def discover_selected_cases(
    root: Path,
    test_paths: tuple[str, ...],
) -> tuple[list[DomainRemoteApiCase], list[str]]:
    """Select exact ContractGraph-owned App API cases for a focused run."""

    normalized = tuple(sorted({path.strip() for path in test_paths if path.strip()}))
    if not normalized:
        return [], ["focused App API integration requires at least one test path"]
    cases, issues = _discover_cases(root, required_test_paths=set(normalized))
    discovered_paths = {case.test_path for case in cases}
    for missing in sorted(set(normalized) - discovered_paths):
        issues.append(
            f"focused App API integration path is not owned by ContractGraph: {missing}"
        )
    return cases, issues


def _discover_cases(
    root: Path,
    *,
    required_test_paths: set[str] | None,
) -> tuple[list[DomainRemoteApiCase], list[str]]:
    document = _graph_document(root)
    readiness_case_ids_by_path: dict[str, set[str]] = {}
    for item in document.get("readinessCases", []):
        if not isinstance(item, dict):
            continue
        runner_path = str(item.get("runnerSourcePath") or "").strip()
        case_id = str(item.get("caseId") or "").strip()
        executions = item.get("executions")
        executions = executions if isinstance(executions, list) else []
        app_gamma_runner = any(
            isinstance(execution, dict)
            and execution.get("environment") == "gamma"
            and execution.get("platform") == "app"
            and execution.get("deviceClass") == "runner"
            for execution in executions
        )
        if (
            item.get("producer") == "app"
            and item.get("layer") == "api_integration"
            and runner_path.startswith(APP_API_TEST_PREFIX)
            and runner_path.endswith(APP_API_TEST_SUFFIX)
            and case_id
            and app_gamma_runner
        ):
            readiness_case_ids_by_path.setdefault(runner_path, set()).add(case_id)
    cases: list[DomainRemoteApiCase] = []
    issues: list[str] = []
    seen_paths: set[str] = set()
    for item in document["readinessEvidence"]:
        if not isinstance(item, dict):
            continue
        object_id = str(item.get("objectId") or "")
        domain = object_id.partition(".")[0]
        if required_test_paths is None and domain not in GOVERNED_DOMAINS:
            continue
        app = item.get("app") if isinstance(item.get("app"), dict) else {}
        service = item.get("service") if isinstance(item.get("service"), dict) else {}
        app_tests = app.get("apiIntegration")
        service_tests = service.get("apiIntegration")
        app_tests = app_tests if isinstance(app_tests, list) else []
        service_tests = service_tests if isinstance(service_tests, list) else []
        for evidence in app_tests:
            if not isinstance(evidence, dict):
                continue
            test_path = str(evidence.get("path") or "")
            if (
                required_test_paths is not None
                and test_path not in required_test_paths
            ):
                continue
            if not (
                test_path.startswith(APP_API_TEST_PREFIX)
                and test_path.endswith(APP_API_TEST_SUFFIX)
            ):
                continue
            if test_path in seen_paths:
                issues.append(f"{domain}: duplicate ContractGraph test path: {test_path}")
                continue
            seen_paths.add(test_path)
            cases.append(
                DomainRemoteApiCase(
                    domain=domain,
                    object_id=object_id,
                    test_path=test_path,
                    test_sha256=str(evidence.get("sha256") or ""),
                    service_test_paths=tuple(
                        sorted(
                            {
                                str(candidate.get("path") or "")
                                for candidate in service_tests
                                if isinstance(candidate, dict)
                                and str(candidate.get("path") or "").startswith(
                                    "quwoquan_service/services/"
                                )
                                and (
                                    str(candidate.get("path") or "").endswith(
                                        "__api_integration_test.go"
                                    )
                                    or str(candidate.get("path") or "").endswith(
                                        "__api_integration_test.py"
                                    )
                                )
                            }
                        )
                    ),
                    readiness_case_ids=tuple(
                        sorted(readiness_case_ids_by_path.get(test_path, set()))
                    ),
                )
            )
    cases.sort(key=lambda case: (case.domain, case.object_id, case.test_path))
    return cases, issues


def _resolve_harness(test_path: Path, source: str) -> Path | None:
    match = HARNESS_IMPORT.search(source)
    if match is None:
        return None
    return (test_path.parent / match.group(1)).resolve()


def validate_cases(
    root: Path,
    cases: list[DomainRemoteApiCase],
    *,
    required_domains: tuple[str, ...] = GOVERNED_DOMAINS,
) -> tuple[list[DomainRemoteApiCase], list[str]]:
    """Validate generated-client, production-Remote, and no-substitute boundaries."""

    validated: list[DomainRemoteApiCase] = []
    issues: list[str] = []
    for case in cases:
        test_path = root / case.test_path
        if not test_path.is_file() or test_path.is_symlink():
            issues.append(f"{case.domain}: missing physical App API test: {case.test_path}")
            continue
        source = test_path.read_text(encoding="utf-8")
        if _sha256(test_path) != case.test_sha256:
            issues.append(
                f"{case.domain}: ContractGraph digest is stale for {case.test_path}"
            )
        if not has_stable_spec_ref(source):
            issues.append(f"{case.domain}: test lacks stable spec_ref: {case.test_path}")
        for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
            if pattern.search(source):
                issues.append(f"{case.domain}: {label} is forbidden: {case.test_path}")
        for label, pattern in FORBIDDEN_TEST_ONLY_PATTERNS.items():
            if pattern.search(source):
                issues.append(f"{case.domain}: {label} is forbidden: {case.test_path}")
        harness_path = _resolve_harness(test_path, source)
        if harness_path is None:
            issues.append(
                f"{case.domain}: test must import its typed API contract harness: "
                f"{case.test_path}"
            )
            continue
        try:
            harness_relative = harness_path.relative_to(root).as_posix()
        except ValueError:
            issues.append(f"{case.domain}: harness escaped repository: {harness_path}")
            continue
        if not harness_path.is_file() or harness_path.is_symlink():
            issues.append(f"{case.domain}: missing physical harness: {harness_relative}")
            continue
        expected_harness_name = f"{case.domain}_api_contract_harness.dart"
        if harness_path.name != expected_harness_name:
            issues.append(
                f"{case.domain}: expected {expected_harness_name}, got "
                f"{harness_path.name}: {case.test_path}"
            )
        harness_source = harness_path.read_text(encoding="utf-8")
        required_tokens = ["buildGeneratedCloudOperationClient"]
        if TYPED_ENVIRONMENT_RESOLVER in harness_source:
            required_tokens.append("ApiContractEnvironment.resolve()")
        else:
            required_tokens.extend(
                (
                    "API_CONTRACT_BASE_URL",
                    "CloudRuntimeEnvironment(",
                    "defaultValue: 'gamma'",
                )
            )
        for token in required_tokens:
            if token not in harness_source:
                issues.append(
                    f"{case.domain}: harness lacks {token}: {harness_relative}"
                )
        if not (
            "ProductionComposition." in harness_source
            or re.search(r"\bRemote[A-Z]\w*\(", harness_source)
        ):
            issues.append(
                f"{case.domain}: harness lacks production Remote adapter: "
                f"{harness_relative}"
            )
        for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
            if pattern.search(harness_source):
                issues.append(
                    f"{case.domain}: harness {label} is forbidden: {harness_relative}"
                )
        if case.service_api_test_count < 1:
            issues.append(
                f"{case.domain}: {case.object_id} lacks service api_integration evidence"
            )
        validated.append(
            DomainRemoteApiCase(
                domain=case.domain,
                object_id=case.object_id,
                test_path=case.test_path,
                test_sha256=case.test_sha256,
                service_test_paths=case.service_test_paths,
                readiness_case_ids=case.readiness_case_ids,
                harness_path=harness_relative,
            )
        )

    for domain in required_domains:
        domain_cases = [case for case in cases if case.domain == domain]
        if not domain_cases:
            issues.append(
                f"{domain}: ContractGraph has no object-level App api_integration case"
            )
    return validated, issues


def evidence_counts(cases: list[DomainRemoteApiCase]) -> dict[str, dict[str, int]]:
    return {
        domain: {
            "coveredObjectCount": len(
                {case.object_id for case in cases if case.domain == domain}
            ),
            "appTestFileCount": len(
                {case.test_path for case in cases if case.domain == domain}
            ),
            "serviceTestFileCount": len(
                {
                    path
                    for case in cases
                    if case.domain == domain
                    for path in case.service_test_paths
                }
            ),
        }
        for domain in GOVERNED_DOMAINS
    }
