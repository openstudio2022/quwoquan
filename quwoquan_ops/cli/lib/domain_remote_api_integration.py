"""Derive and validate object-level App Remote API integration evidence.

The committed ContractGraph is the only coverage map. This module never keeps
an object or test-path inventory; it selects the five governed domains from
``readinessEvidence`` and validates the physical App tests and their harnesses.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
SPEC_REF = re.compile(
    r"spec_ref:\s*specs/feature-tree/[^\s#]+/spec\.md#"
    r"(?:uat|dom|sit|gwt)-\d+",
    re.IGNORECASE,
)
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


@dataclass(frozen=True)
class DomainRemoteApiCase:
    domain: str
    object_id: str
    test_path: str
    test_sha256: str
    service_test_paths: tuple[str, ...]
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
            "harnessPath": self.harness_path,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    document = _graph_document(root)
    cases: list[DomainRemoteApiCase] = []
    issues: list[str] = []
    seen_paths: set[str] = set()
    for item in document["readinessEvidence"]:
        if not isinstance(item, dict):
            continue
        object_id = str(item.get("objectId") or "")
        domain = object_id.partition(".")[0]
        if domain not in GOVERNED_DOMAINS:
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
        if SPEC_REF.search(source) is None:
            issues.append(f"{case.domain}: test lacks stable spec_ref: {case.test_path}")
        for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
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
        required_tokens = (
            "buildGeneratedCloudOperationClient",
            "API_CONTRACT_BASE_URL",
            "CloudRuntimeEnvironment(",
            "defaultValue: 'gamma'",
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
                harness_path=harness_relative,
            )
        )

    for domain in GOVERNED_DOMAINS:
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
