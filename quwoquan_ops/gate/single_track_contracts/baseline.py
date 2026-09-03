"""Single-track exact-fingerprint baseline schema, comparison, and writer."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .scanner import Finding, Inventory

BASELINE_SCHEMA = "single-track-exact-fingerprint-baseline"
BASELINE_REVISION = "b227730d2a43eefe3a676e9cec0473e4b7537869"
FINGERPRINT_ALGORITHM = "sha256(category\0path\0normalized-detail)-v1"
DEFAULT_BASELINE = (
    Path(__file__).resolve().parents[2]
    / "policies/gates/single_track_exact_fingerprint_baseline.json"
)
BASELINE_PATH = DEFAULT_BASELINE
GOVERNANCE = {
    "owner": "cloud-contract-governance",
    "reason": (
        "canonical dev1.0 already contains single-track findings; exact identities "
        "may only be removed while the historical debt is retired"
    ),
    "expires_when": (
        "findings is empty; delete this baseline and restore the zero-only gate"
    ),
    "measure": (
        "verify_single_track_contracts.py scans constants.py:SCAN_ROOTS and compares "
        "the exact multiset sha256(category NUL repo-relative-path NUL semantic-detail) "
        "after removing only a leading L<line>:; every identity count may only decrease"
    ),
}
_LINE_PREFIX = re.compile(r"^L[1-9][0-9]*:\s*")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_WILDCARD_CHARS = frozenset("*?[]{}")


class BaselineError(ValueError):
    """The exact-fingerprint baseline is malformed or non-canonical."""


@dataclass(frozen=True, order=True)
class Fingerprint:
    category: str
    path: str
    detail: str

    @property
    def sha256(self) -> str:
        return semantic_fingerprint(self.category, self.path, self.detail)


@dataclass(frozen=True)
class RatchetResult:
    baseline_count: int
    baseline_identity_count: int
    current_count: int
    current_identity_count: int
    reductions: int
    removed_identities: int
    additions: tuple[tuple[Fingerprint, int, int], ...]

    @property
    def passed(self) -> bool:
        return not self.additions


@dataclass(frozen=True)
class RatchetEvaluation:
    failures: tuple[str, ...]
    reductions: tuple[str, ...]
    baseline_total: int
    baseline_identity_count: int
    current_total: int
    current_identity_count: int


def normalize_detail(detail: str) -> str:
    """Remove only scanner-added leading line metadata; preserve semantic values."""
    return _LINE_PREFIX.sub("", detail, count=1)


def semantic_fingerprint(category: str, path: str, detail: str) -> str:
    material = "\0".join((category, path, normalize_detail(detail))).encode("utf-8")
    return "sha256:" + hashlib.sha256(material).hexdigest()


def fingerprint_of(finding: Finding) -> Fingerprint:
    return Fingerprint(
        finding.category,
        finding.path,
        normalize_detail(finding.detail),
    )


def fingerprint_for_finding(finding: Finding) -> str:
    return fingerprint_of(finding).sha256


def inventory_counts(inv: Inventory) -> Counter[Fingerprint]:
    return Counter(fingerprint_of(finding) for finding in inv.findings)


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BaselineError(f"{field} must be one non-empty canonical string")
    return value


def _validate_repo_path(value: object, *, field: str) -> str:
    path = _required_text(value, field=field)
    candidate = PurePosixPath(path)
    if (
        candidate.is_absolute()
        or path.startswith("./")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or any(character in path for character in _WILDCARD_CHARS)
    ):
        raise BaselineError(f"{field} must be an exact repo-relative POSIX path")
    return path


def _entry(fingerprint: Fingerprint, count: int) -> dict[str, object]:
    return {
        "fingerprint": fingerprint.sha256,
        "category": fingerprint.category,
        "path": fingerprint.path,
        "detail": fingerprint.detail,
        "count": count,
    }


def baseline_document(
    counts: Counter[Fingerprint], *, baseline_revision: str
) -> dict[str, object]:
    if _REVISION.fullmatch(baseline_revision) is None:
        raise BaselineError("baselineRevision must be a lowercase 40-hex commit SHA")
    return {
        "_governance": dict(GOVERNANCE),
        "schema": BASELINE_SCHEMA,
        "fingerprintAlgorithm": FINGERPRINT_ALGORITHM,
        "baselineRevision": baseline_revision,
        "findings": [
            _entry(fingerprint, counts[fingerprint])
            for fingerprint in sorted(counts)
        ],
    }


def canonical_json(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def parse_baseline_document(document: object) -> Counter[Fingerprint]:
    expected_fields = {
        "_governance",
        "schema",
        "fingerprintAlgorithm",
        "baselineRevision",
        "findings",
    }
    if not isinstance(document, dict) or set(document) != expected_fields:
        raise BaselineError(f"baseline fields must be exactly {sorted(expected_fields)}")
    if document.get("schema") != BASELINE_SCHEMA:
        raise BaselineError(f"schema must be {BASELINE_SCHEMA}")
    if document.get("fingerprintAlgorithm") != FINGERPRINT_ALGORITHM:
        raise BaselineError("fingerprintAlgorithm 已过期或不受支持")
    revision = document.get("baselineRevision")
    if not isinstance(revision, str) or _REVISION.fullmatch(revision) is None:
        raise BaselineError("baselineRevision must be a lowercase 40-hex commit SHA")
    if not isinstance(document.get("_governance"), dict):
        raise BaselineError("_governance must be an object")
    findings = document.get("findings")
    if not isinstance(findings, list):
        raise BaselineError("findings must be a list")
    counts: Counter[Fingerprint] = Counter()
    previous: Fingerprint | None = None
    for index, raw in enumerate(findings):
        field = f"findings[{index}]"
        if not isinstance(raw, dict) or set(raw) != {
            "fingerprint", "category", "path", "detail", "count"
        }:
            raise BaselineError(f"{field} has invalid fields")
        fingerprint = Fingerprint(
            _required_text(raw.get("category"), field=f"{field}.category"),
            _validate_repo_path(raw.get("path"), field=f"{field}.path"),
            _required_text(raw.get("detail"), field=f"{field}.detail"),
        )
        if _LINE_PREFIX.match(fingerprint.detail):
            raise BaselineError(f"{field}.detail must not retain leading line metadata")
        raw_fingerprint = raw.get("fingerprint")
        if not isinstance(raw_fingerprint, str) or _DIGEST.fullmatch(raw_fingerprint) is None:
            raise BaselineError(f"{field}.fingerprint must be canonical sha256")
        if raw_fingerprint != fingerprint.sha256:
            raise BaselineError(f"{field} has a stale fingerprint")
        count = raw.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise BaselineError(f"{field}.count must be a positive integer")
        if previous is not None and fingerprint <= previous:
            if fingerprint == previous:
                raise BaselineError(f"{field} has 重复 fingerprint")
            raise BaselineError(f"{field} is not sorted")
        counts[fingerprint] = count
        previous = fingerprint
    return counts



def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise BaselineError(f"baseline JSON contains duplicate key: {key}")
        document[key] = value
    return document


def load_baseline(path: Path = DEFAULT_BASELINE) -> Counter[Fingerprint]:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        return parse_baseline_document(document)
    except BaselineError:
        raise
    except FileNotFoundError as error:
        raise BaselineError(f"无法读取 baseline: missing {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BaselineError(f"无法读取 baseline: {error}") from error


def compare_counts(
    baseline: Counter[Fingerprint], current: Counter[Fingerprint]
) -> RatchetResult:
    additions = tuple(
        (fingerprint, baseline.get(fingerprint, 0), current_count)
        for fingerprint, current_count in sorted(current.items())
        if current_count > baseline.get(fingerprint, 0)
    )
    inherited_current = sum(
        min(count, baseline.get(fingerprint, 0))
        for fingerprint, count in current.items()
    )
    return RatchetResult(
        baseline_count=sum(baseline.values()),
        baseline_identity_count=len(baseline),
        current_count=sum(current.values()),
        current_identity_count=len(current),
        reductions=sum(baseline.values()) - inherited_current,
        removed_identities=sum(1 for fingerprint in baseline if fingerprint not in current),
        additions=additions,
    )


def compare_inventory(
    inv: Inventory, baseline: Counter[Fingerprint]
) -> RatchetResult:
    return compare_counts(baseline, inventory_counts(inv))


def evaluate_ratchet(
    inv: Inventory, baseline_path: Path = DEFAULT_BASELINE
) -> RatchetEvaluation:
    baseline = load_baseline(baseline_path)
    current = inventory_counts(inv)
    result = compare_counts(baseline, current)
    failures = tuple(
        (
            f"新增语义 fingerprint: {fingerprint.category} {fingerprint.path} "
            f"{fingerprint.detail} count={before}->{after}"
            if before == 0
            else f"语义 fingerprint 计数增长: {fingerprint.category} "
            f"{fingerprint.path} {fingerprint.detail} count={before}->{after}"
        )
        for fingerprint, before, after in result.additions
    )
    reductions = tuple(
        f"{fingerprint.category} {fingerprint.path} {fingerprint.detail} "
        f"count={before}->{current.get(fingerprint, 0)}"
        for fingerprint, before in sorted(baseline.items())
        if current.get(fingerprint, 0) < before
    )
    return RatchetEvaluation(
        failures=failures,
        reductions=reductions,
        baseline_total=result.baseline_count,
        baseline_identity_count=result.baseline_identity_count,
        current_total=result.current_count,
        current_identity_count=result.current_identity_count,
    )


def repository_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip()
    if result.returncode != 0 or _REVISION.fullmatch(revision) is None:
        raise BaselineError(f"cannot resolve canonical baseline revision under {root}")
    return revision


def write_baseline(
    inv: Inventory,
    path: Path = DEFAULT_BASELINE,
    *,
    baseline_revision: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        canonical_json(
            baseline_document(
                inventory_counts(inv),
                baseline_revision=baseline_revision,
            )
        ),
        encoding="utf-8",
    )
