#!/usr/bin/env python3
"""Accept only complete, handoff-bound nonproduction test-data results.

Trigger: explicit release-evidence review after Alpha/Beta/Gamma runs.
Block: mixed candidate/request identities, incomplete lifecycle receipts, skipped
business cases, or a Prod mutation-boundary receipt that could have reached a
Provider.
Repair: rerun the exact handoff through ``stackctl verify``; never patch a
CaseResult or reuse a result from a different candidate.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-002
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.test_data.model import canonical_digest


HANDOFF_SCHEMA = "qwq.test_data_handoff.v1"
CASE_RESULT_SCHEMA = "qwq.case_result"
RECEIPT_SCHEMA = "qwq.test_data_receipt.v1"
ENVIRONMENTS = ("alpha", "beta", "gamma")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--handoff",
        action="append",
        default=[],
        metavar="ENV=PATH",
        help="One exact Alpha/Beta/Gamma handoff per environment.",
    )
    parser.add_argument(
        "--case-result",
        action="append",
        default=[],
        metavar="ENV=PATH",
        help="One exact Alpha/Beta/Gamma CaseResult per environment.",
    )
    parser.add_argument("--prod-rejection", required=True, type=Path)
    return parser


def _load(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"evidence must be a JSON object: {path}")
    return payload


def _parse_environment_paths(
    values: list[str],
    *,
    option: str,
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        environment, separator, raw_path = value.partition("=")
        if not separator or environment not in ENVIRONMENTS or not raw_path:
            raise ValueError(f"{option} must use alpha|beta|gamma=PATH")
        if environment in result:
            raise ValueError(f"duplicate {option} environment: {environment}")
        result[environment] = Path(raw_path)
    if set(result) != set(ENVIRONMENTS):
        raise ValueError(f"one {option} is required for alpha, beta and gamma")
    return result


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def _receipt_digest_issues(
    *,
    environment: str,
    case_id: object,
    digest: object,
    embedded: object = None,
    path: object = None,
    base_dir: Path,
    expected_kind: str,
    expected_candidate_binding_digest: object,
    expected_test_data_instance_id: object,
) -> list[str]:
    if not _is_digest(digest):
        return [f"{environment}: {case_id!r} receipt digest is not canonical sha256"]
    documents: list[Mapping[str, Any]] = []
    if embedded is not None:
        if not isinstance(embedded, Mapping):
            return [f"{environment}: {case_id!r} embedded receipt is invalid"]
        documents.append(embedded)
    if path is not None:
        if not isinstance(path, str) or not path.strip():
            return [f"{environment}: {case_id!r} receipt path is invalid"]
        receipt_path = Path(path)
        if receipt_path.is_absolute():
            return [
                f"{environment}: {case_id!r} receipt path must be relative to CaseResult"
            ]
        try:
            receipt_path = (base_dir / receipt_path).resolve()
            receipt_path.relative_to(base_dir.resolve())
            documents.append(_load(receipt_path))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return [f"{environment}: {case_id!r} receipt cannot be loaded: {exc}"]
    if not documents:
        return [
            f"{environment}: {case_id!r} {expected_kind} receipt has no document or path"
        ]
    issues: list[str] = []
    for document in documents:
        unsigned = {
            key: value for key, value in document.items() if key != "receiptDigest"
        }
        recomputed = canonical_digest(unsigned)
        if (
            document.get("schema") != RECEIPT_SCHEMA
            or document.get("kind") != expected_kind
            or document.get("caseId") != case_id
            or document.get("candidateBindingDigest")
            != expected_candidate_binding_digest
            or document.get("testDataInstanceId")
            != expected_test_data_instance_id
            or isinstance(document.get("sequence"), bool)
            or not isinstance(document.get("sequence"), int)
            or int(document.get("sequence") or 0) <= 0
            or not str(document.get("recordedAt") or "").strip()
            or not isinstance(document.get("payload"), Mapping)
        ):
            issues.append(
                f"{environment}: {case_id!r} receipt document is not bound to "
                f"{expected_kind}"
            )
        if document.get("receiptDigest") != recomputed or digest != recomputed:
            issues.append(
                f"{environment}: {case_id!r} receipt digest does not match its document"
            )
    return issues


def _validate_handoff(
    handoff: Mapping[str, Any],
    *,
    environment: str,
) -> list[str]:
    issues: list[str] = []
    unsigned = {key: value for key, value in handoff.items() if key != "handoffDigest"}
    if handoff.get("schema") != HANDOFF_SCHEMA:
        issues.append("handoff schema mismatch")
    if not _is_digest(handoff.get("handoffDigest")):
        issues.append("handoff handoffDigest is not a canonical digest")
    if handoff.get("handoffDigest") != canonical_digest(unsigned):
        issues.append("handoff digest mismatch")
    if (
        handoff.get("environment") != environment
        or handoff.get("target") != f"{environment}-local"
    ):
        issues.append(f"{environment}: handoff environment/target mismatch")
    for field in (
        "baselineId",
        "packageDigest",
        "runtimeConfigDigest",
        "manifestDigest",
        "readinessReceiptDigest",
        "requestDigest",
        "evidenceDigest",
        "candidateBindingDigest",
    ):
        if not _is_digest(handoff.get(field)):
            issues.append(f"handoff {field} is not a canonical digest")
    source_revision = str(handoff.get("sourceRevision") or "").strip()
    if len(source_revision) != 40 or any(
        character not in "0123456789abcdef" for character in source_revision
    ):
        issues.append("handoff sourceRevision is not a canonical Git revision")
    if not str(handoff.get("releaseId") or "").strip():
        issues.append("handoff releaseId is missing")
    if not str(handoff.get("importRunId") or "").strip():
        issues.append("handoff importRunId is missing")
    if handoff.get("readinessPhase") not in {"research", "commercial"}:
        issues.append("handoff readinessPhase is invalid")
    for field in (
        "expectedCases",
        "expectedProviderOwners",
        "expectedProviderCapabilities",
        "requiredOperations",
        "allowedOperations",
    ):
        values = handoff.get(field)
        if not isinstance(values, list) or not values or any(
            not isinstance(value, str) or not value for value in values
        ):
            issues.append(f"handoff {field} is missing or invalid")
        elif len(values) != len(set(values)):
            issues.append(f"handoff {field} contains duplicate identities")
    return issues


def _validate_case_result(
    *,
    environment: str,
    result: Mapping[str, Any],
    handoff: Mapping[str, Any],
    result_path: Path,
) -> list[str]:
    issues: list[str] = []
    if result.get("schema") != CASE_RESULT_SCHEMA:
        issues.append(f"{environment}: CaseResult schema mismatch")
    expected_cases = handoff.get("expectedCases")
    expected_providers = handoff.get("expectedProviderOwners")
    expected_provider_capabilities = handoff.get("expectedProviderCapabilities")
    if (
        result.get("status") != "passed"
        or result.get("preparationStatus") != "passed"
        or result.get("baselineEligible") is not True
        or result.get("benchmarkPolicy") != "normal"
        or result.get("benchmarkOnly") is not False
        or result.get("executed") != len(expected_cases or ())
        or result.get("skipped") != 0
    ):
        issues.append(f"{environment}: CaseResult is not a full green release run")
    if (
        result.get("environment") != environment
        or result.get("target") != f"{environment}-local"
        or result.get("candidateBindingDigest")
        != handoff.get("candidateBindingDigest")
        or result.get("requestDigest") != handoff.get("requestDigest")
        or result.get("evidenceDigest") != handoff.get("evidenceDigest")
        or result.get("handoffDigest") != handoff.get("handoffDigest")
    ):
        issues.append(f"{environment}: CaseResult identity drifts from handoff")
    for result_field, handoff_field in (
        ("sourceRevision", "sourceRevision"),
        ("packageDigest", "packageDigest"),
        ("runtimeConfigDigest", "runtimeConfigDigest"),
        ("releaseId", "releaseId"),
        ("manifestDigest", "manifestDigest"),
        ("importRunId", "importRunId"),
        ("readinessReceiptDigest", "readinessReceiptDigest"),
    ):
        if result.get(result_field) != handoff.get(handoff_field):
            issues.append(
                f"{environment}: CaseResult {result_field} drifts from handoff"
            )
    if sorted(result.get("loadedProviders") or []) != sorted(expected_providers or []):
        issues.append(f"{environment}: loaded Provider closure drifts from handoff")
    if sorted(result.get("requiredProviders") or []) != sorted(expected_providers or []):
        issues.append(f"{environment}: required Provider closure drifts from handoff")
    if sorted(result.get("requiredProviderCapabilities") or []) != sorted(
        expected_provider_capabilities or []
    ):
        issues.append(
            f"{environment}: required Provider capability closure drifts from handoff"
        )
    executed_operations = result.get("executedOperationIds")
    allowed_operations = set(handoff.get("allowedOperations") or [])
    required_operations = set(handoff.get("requiredOperations") or [])
    if (
        not isinstance(executed_operations, list)
        or not executed_operations
        or any(not isinstance(item, str) or not item for item in executed_operations)
        or len(executed_operations) != len(set(executed_operations))
        or not required_operations.issubset(set(executed_operations))
        or not set(executed_operations).issubset(allowed_operations)
        or not required_operations.issubset(allowed_operations)
    ):
        issues.append(
            f"{environment}: executed operations exceed or miss the handoff closure"
        )
    operation_count = result.get("operationCount")
    if (
        isinstance(operation_count, bool)
        or not isinstance(operation_count, int)
        or operation_count < len(result.get("executedOperationIds") or [])
    ):
        issues.append(f"{environment}: operation receipt count is incomplete")
    case_results = result.get("caseResults")
    if not isinstance(case_results, list) or len(case_results) != len(expected_cases or ()):
        return [*issues, f"{environment}: CaseResult case rows are incomplete"]
    actual_case_ids = {str(item.get("caseId") or "") for item in case_results if isinstance(item, Mapping)}
    if actual_case_ids != set(expected_cases or ()):
        issues.append(f"{environment}: CaseResult cases drift from handoff")
    instance_ids: list[str] = []
    request_ids: list[str] = []
    for item in case_results:
        if not isinstance(item, Mapping):
            issues.append(f"{environment}: CaseResult row is invalid")
            continue
        execution = item.get("testExecution")
        case_id = item.get("caseId")
        instance_ids.append(str(item.get("testDataInstanceId") or ""))
        request_ids.append(str(item.get("requestId") or ""))
        readback_receipts = item.get("readbackReceiptDigests")
        cleanup_receipts = item.get("cleanupReceiptDigests")
        if (
            item.get("status") != "passed"
            or item.get("candidateBindingDigest")
            != handoff.get("candidateBindingDigest")
            or not str(item.get("testDataInstanceId") or "").strip()
            or not str(item.get("requestId") or "").strip()
            or not isinstance(readback_receipts, list)
            or not readback_receipts
            or any(not isinstance(digest, str) for digest in readback_receipts)
            or len(readback_receipts) != len(set(readback_receipts))
            or not isinstance(cleanup_receipts, list)
            or not cleanup_receipts
            or any(not isinstance(digest, str) for digest in cleanup_receipts)
            or len(cleanup_receipts) != len(set(cleanup_receipts))
            or not isinstance(execution, Mapping)
            or execution.get("executed") != 1
            or execution.get("failed") != 0
            or execution.get("skipped") != 0
        ):
            issues.append(
                f"{environment}: {item.get('caseId')!r} lifecycle receipt closure is incomplete"
            )
            continue
        issues.extend(
            _receipt_digest_issues(
                environment=environment,
                case_id=case_id,
                digest=item.get("provisionReceiptDigest"),
                embedded=item.get("provisionReceipt"),
                path=item.get("provisionReceiptPath"),
                base_dir=result_path.parent,
                expected_kind="provision",
                expected_candidate_binding_digest=handoff.get(
                    "candidateBindingDigest"
                ),
                expected_test_data_instance_id=item.get("testDataInstanceId"),
            )
        )
        issues.extend(
            _receipt_digest_issues(
                environment=environment,
                case_id=case_id,
                digest=item.get("testBodyReceiptDigest"),
                embedded=item.get("testBodyReceipt"),
                path=item.get("testBodyReceiptPath"),
                base_dir=result_path.parent,
                expected_kind="test-body",
                expected_candidate_binding_digest=handoff.get(
                    "candidateBindingDigest"
                ),
                expected_test_data_instance_id=item.get("testDataInstanceId"),
            )
        )
        for label, digests, embedded_rows, paths in (
            (
                "readback",
                readback_receipts,
                item.get("readbackReceipts"),
                item.get("readbackReceiptPaths"),
            ),
            (
                "cleanup",
                cleanup_receipts,
                item.get("cleanupReceipts"),
                item.get("cleanupReceiptPaths"),
            ),
        ):
            if embedded_rows is not None and (
                not isinstance(embedded_rows, list)
                or len(embedded_rows) != len(digests)
            ):
                issues.append(
                    f"{environment}: {case_id!r} embedded {label} receipt closure is invalid"
                )
                continue
            if paths is not None and (
                not isinstance(paths, list) or len(paths) != len(digests)
            ):
                issues.append(
                    f"{environment}: {case_id!r} {label} receipt path closure is invalid"
                )
                continue
            for index, digest in enumerate(digests):
                issues.extend(
                    _receipt_digest_issues(
                        environment=environment,
                        case_id=case_id,
                        digest=digest,
                        embedded=(
                            embedded_rows[index]
                            if isinstance(embedded_rows, list)
                            else None
                        ),
                        path=paths[index] if isinstance(paths, list) else None,
                        base_dir=result_path.parent,
                        expected_kind=label,
                        expected_candidate_binding_digest=handoff.get(
                            "candidateBindingDigest"
                        ),
                        expected_test_data_instance_id=item.get(
                            "testDataInstanceId"
                        ),
                    )
                )
    if len(instance_ids) != len(set(instance_ids)):
        issues.append(f"{environment}: CaseResults reuse a testDataInstanceId")
    if len(request_ids) != len(set(request_ids)):
        issues.append(f"{environment}: CaseResults reuse a root requestId")
    return issues


def _validate_prod_rejection(
    result: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> list[str]:
    if (
        result.get("schema") == CASE_RESULT_SCHEMA
        and result.get("caseId") == "prod-test-data-mutation-boundary"
        and result.get("status") == "GATE_BLOCK"
        and result.get("preparationStatus") == "GATE_BLOCK"
        and result.get("environment") == "prod"
        and result.get("target") == "prod-hosted"
        and result.get("executed") == 0
        and result.get("skipped") == 0
        and result.get("operationCount") == 0
        and result.get("executedOperationIds") == []
        and result.get("loadedProviders") == []
        and result.get("requiredProviders") == []
        and result.get("baselineEligible") is False
        and result.get("requestDigest") == handoff.get("requestDigest")
        and any(
            "before Provider discovery" in str(item)
            for item in (result.get("issues") or [])
        )
    ):
        return []
    return ["Prod mutation-boundary rejection receipt is incomplete or unbound"]


def verify(
    *,
    handoff_paths: Mapping[str, Path],
    case_result_paths: Mapping[str, Path],
    prod_rejection_path: Path,
) -> list[str]:
    expected_environments = set(ENVIRONMENTS)
    if set(handoff_paths) != expected_environments:
        raise ValueError("one handoff is required for alpha, beta and gamma")
    if set(case_result_paths) != expected_environments:
        raise ValueError("one CaseResult is required for alpha, beta and gamma")
    handoffs = {
        environment: _load(path)
        for environment, path in sorted(handoff_paths.items())
    }
    issues: list[str] = []
    for environment, handoff in handoffs.items():
        issues.extend(_validate_handoff(handoff, environment=environment))
    shared_fields = (
        "sourceRevision",
        "packageDigest",
        "releaseId",
        "manifestDigest",
        "readinessPhase",
        "requestDigest",
        "expectedCases",
        "expectedProviderOwners",
        "expectedProviderCapabilities",
        "requiredOperations",
        "allowedOperations",
    )
    for field in shared_fields:
        values = {
            json.dumps(handoff.get(field), ensure_ascii=False, sort_keys=True)
            for handoff in handoffs.values()
        }
        if len(values) != 1:
            issues.append(f"environment handoffs disagree on shared {field}")
    results = {
        environment: _load(path)
        for environment, path in sorted(case_result_paths.items())
    }
    for environment, result in results.items():
        issues.extend(
            _validate_case_result(
                environment=environment,
                result=result,
                handoff=handoffs[environment],
                result_path=case_result_paths[environment],
            )
        )
    operation_sets = {
        tuple(sorted(str(item) for item in (result.get("executedOperationIds") or [])))
        for result in results.values()
    }
    if len(operation_sets) != 1:
        issues.append("environment CaseResults disagree on executed operations")
    issues.extend(
        _validate_prod_rejection(
            _load(prod_rejection_path),
            handoffs["alpha"],
        )
    )
    return issues


def main() -> int:
    args = _parser().parse_args()
    try:
        issues = verify(
            handoff_paths=_parse_environment_paths(
                args.handoff,
                option="--handoff",
            ),
            case_result_paths=_parse_environment_paths(
                args.case_result,
                option="--case-result",
            ),
            prod_rejection_path=args.prod_rejection,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        issues = [str(exc)]
    if issues:
        print("GATE_BLOCK: test-data environment result bundle is unacceptable")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("PASS: Alpha/Beta/Gamma CaseResults and Prod rejection match the exact handoff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
