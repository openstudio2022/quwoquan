# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from quwoquan_ops.ci.system_backsync import (
    SystemBacksyncError,
    _canonical_bytes,
    _digest,
    backsync_main_to_dev,
)

REPOSITORY = "owner/quwoquan"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=check, text=True, capture_output=True,
    ).stdout.strip()


def repos(tmp_path: Path) -> tuple[Path, str, str, str, str]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.name", "system")
    git(repo, "config", "user.email", "system@example.com")
    git(repo, "checkout", "-b", "main")
    (repo / "base").write_text("base", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-b", "dev1.0")
    (repo / "source").write_text("source", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "source")
    source = git(repo, "rev-parse", "HEAD")
    source_tree = git(repo, "show", "-s", "--format=%T", source)
    git(repo, "push", "origin", "dev1.0")
    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "dev1.0", "-m", "promotion")
    main = git(repo, "rev-parse", "HEAD")
    main_tree = git(repo, "show", "-s", "--format=%T", main)
    git(repo, "push", "origin", "main")
    return repo, base, source, source_tree, main, main_tree


def write_canonical(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")
    return path


def evidence(
    tmp_path: Path, *, base: str, source: str, source_tree: str,
    main: str, main_tree: str, hosted: bool = True,
) -> dict[str, Any]:
    admission: dict[str, Any] = {
        "schema": "quwoquan_ops.promotion_admission_receipt.v1",
        "decision": "admitted",
        "headRef": "refs/heads/dev1.0",
        "baseRef": "refs/heads/main",
        "headSha": source,
        "headTree": source_tree,
        "baseSha": base,
        "syntheticMergeSha": "e" * 40,
        "syntheticMergeTree": main_tree,
        "qualification": {"ref": "integration/qualification.json", "digest": DIGEST_A},
        "authority": {
            name: {"ref": f"promotion/{name}.json", "digest": DIGEST_A}
            for name in ("approval", "threads", "ruleset", "changedBoundary")
        },
        "requiredEvidence": [{"ref": "promotion/required.json", "digest": DIGEST_B}],
        "changedPaths": ["a.txt"],
        "promotionReadyAt": "2026-09-06T10:00:00Z",
    }
    admission["admissionId"] = _digest(admission)
    admission_path = write_canonical(
        tmp_path / "promotion-admission/fact.json", admission
    )
    seal: dict[str, Any] = {
        "schema": "quwoquan_ops.main_source_seal.v1",
        "sourceStatus": "source-admitted",
        "releaseStatus": "not_selected",
        "mainRef": "refs/heads/main",
        "mainSha": main,
        "mainTree": main_tree,
        "promotionAdmission": {
            "ref": "promotion-admission/fact.json",
            "digest": _digest(admission_path),
        },
        "sourceHeadSha": source,
        "promotionReadyAt": "2026-09-06T10:00:00Z",
        "mainReadbackAt": "2026-09-06T10:01:00Z",
        "durationSeconds": 60,
    }
    hosted_path = None
    if hosted:
        admission_oci = f"ghcr.io/{REPOSITORY}/promotion-admission@{DIGEST_A}"
        handoff_identity: dict[str, Any] = {
            "schema": "quwoquan_ops.promotion_admission_handoff.v1",
            "repository": REPOSITORY,
            "pullRequestNumber": 42,
            "headSha": source,
            "baseSha": base,
            "syntheticMergeSha": admission["syntheticMergeSha"],
            "syntheticMergeTree": main_tree,
            "workflowRunId": 100,
            "workflowRunAttempt": 1,
            "workflowRepository": REPOSITORY,
            "workflowHeadSha": source,
            "workflowActor": {"login": "merge-owner", "id": 456},
            "handoffContext": "quwoquan/promotion-admission-handoff/v1",
            "promotionAdmissionRef": admission_oci,
            "admissionBytesDigest": _digest(admission_path),
            "createdAt": "2026-09-06T10:00:00Z",
        }
        record = {
            **{
                key: value for key, value in handoff_identity.items()
                if key != "handoffContext"
            },
            "recordId": _digest(handoff_identity),
            "checkRunId": 123,
            "checkRunNodeId": "CR_kwDOtrusted",
            "context": "quwoquan/promotion-admission-handoff/v1",
            "app": {"slug": "quwoquan-promotion-recorder", "id": 789},
        }
        hosted_path = write_canonical(
            tmp_path / "promotion-handoff/record.json", record
        )
        seal["promotionAdmissionOciRef"] = admission_oci
        seal["hostedPromotionHandoff"] = {
            "ref": "promotion-handoff/record.json",
            "digest": _digest(hosted_path),
        }
    seal["sealId"] = _digest(seal)
    seal_path = write_canonical(tmp_path / "main-source-seal.json", seal)
    seal_digest = "sha256:" + "c" * 64
    return {
        "github_repository": REPOSITORY,
        "main_source_seal_path": seal_path,
        "main_source_seal_ref": (
            f"ghcr.io/{REPOSITORY}/main-source-seal@{seal_digest}"
        ),
        "main_source_seal_digest": seal_digest,
        "promotion_admission_path": admission_path,
        "hosted_handoff_path": hosted_path,
        "source_sha": source,
    }


def _rebind_hosted_record(facts: dict[str, Any], hosted_path: Path) -> None:
    seal_path = facts["main_source_seal_path"]
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["hostedPromotionHandoff"]["digest"] = _digest(hosted_path)
    seal["sealId"] = _digest(
        {key: value for key, value in seal.items() if key != "sealId"}
    )
    write_canonical(seal_path, seal)


def execute(
    repo: Path, before: str, facts: dict[str, Any], path: Path,
    *, environment_overrides: dict[str, str] | None = None,
) -> Path:
    environment = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_REF_NAME": "main",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_SHA": git(repo, "rev-parse", "main"),
        "GITHUB_EVENT_BEFORE": git(repo, "show", "-s", "--format=%P", "main").split()[0],
        "GITHUB_EVENT_AFTER": git(repo, "rev-parse", "main"),
        "GITHUB_WORKFLOW_REF": (
            f"{REPOSITORY}/.github/workflows/delivery-gate.yml@refs/heads/main"
        ),
        "QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF": (
            f"{REPOSITORY}/.github/workflows/system-backsync.yml@refs/heads/main"
        ),
        "QWQ_MANAGED_SYSTEM_BACKSYNC": "system-fast-forward-cas-v1",
        "QWQ_PROMOTION_RECORDER_APP_SLUG": "quwoquan-promotion-recorder",
        "QWQ_PROMOTION_RECORDER_APP_ID": "789",
    }
    environment.update(environment_overrides or {})
    return backsync_main_to_dev(
        repository=repo,
        remote="origin",
        expected_dev_before=before,
        environment=environment,
        evidence_path=path,
        recorded_at="2026-09-06T10:02:00Z",
        **facts,
    )


def test_fast_forward_cas_backsync_consumes_only_source_authority(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )

    result = execute(repo, source, facts, tmp_path / "first.json")
    payload = json.loads(result.read_text(encoding="utf-8"))

    assert payload["terminal"] == "success"
    assert payload["sourceOid"] == source
    assert payload["requestedAfterOid"] == main
    assert payload["sourceEvidence"]["promotionAdmission"]["headSha"] == source
    assert payload["sourceEvidence"]["hostedPromotionHandoff"]["ref"] == (
        "promotion-handoff/record.json"
    )
    assert git(repo, "ls-remote", "--refs", "origin", "refs/heads/dev1.0").split()[0] == main
    serialized = json.dumps(payload, sort_keys=True)
    assert "releasedFact" not in serialized
    assert "postReleaseSoakFact" not in serialized


def test_equal_backsync_is_idempotent(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    git(repo, "push", "origin", "main:dev1.0")
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )

    result = execute(repo, source, facts, tmp_path / "idempotent.json")

    assert json.loads(result.read_text(encoding="utf-8"))["terminal"] == "idempotent"


@pytest.mark.parametrize(
    ("mutate", "match"),
    (
        (lambda facts: facts.update(main_source_seal_ref="refs/heads/main"), "AUTHORITY_UNAVAILABLE"),
        (lambda facts: facts.update(main_source_seal_digest=DIGEST_A), "AUTHORITY_UNAVAILABLE"),
        (lambda facts: facts.update(source_sha="d" * 40), "SOURCE_NOT_MAIN_REACHABLE"),
    ),
)
def test_backsync_rejects_wrong_seal_or_source_before_mutation(
    tmp_path: Path, mutate, match: str,
) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    mutate(facts)

    with pytest.raises(SystemBacksyncError, match=match):
        execute(repo, source, facts, tmp_path / "blocked.json")

    assert git(repo, "ls-remote", "--refs", "origin", "refs/heads/dev1.0").split()[0] == source


def test_backsync_rejects_invalid_hosted_record_in_seal(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    seal_path = facts["main_source_seal_path"]
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["hostedPromotionHandoff"] = {
        "ref": "promotion-handoff/latest",
        "digest": DIGEST_B,
    }
    seal["sealId"] = _digest(
        {key: value for key, value in seal.items() if key != "sealId"}
    )
    write_canonical(seal_path, seal)

    with pytest.raises(SystemBacksyncError, match="AUTHORITY_UNAVAILABLE"):
        execute(repo, source, facts, tmp_path / "blocked.json")


def test_backsync_rejects_hosted_record_bytes_drift(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    hosted_path = facts["hosted_handoff_path"]
    record = json.loads(hosted_path.read_text(encoding="utf-8"))
    record["workflowHeadSha"] = "d" * 40
    write_canonical(hosted_path, record)

    with pytest.raises(SystemBacksyncError, match="AUTHORITY_UNAVAILABLE"):
        execute(repo, source, facts, tmp_path / "blocked.json")


def test_backsync_rejects_legacy_status_hosted_shape(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    hosted_path = facts["hosted_handoff_path"]
    record = json.loads(hosted_path.read_text(encoding="utf-8"))
    record["statusId"] = record.pop("checkRunId")
    record["statusNodeId"] = record.pop("checkRunNodeId")
    record["creator"] = record.pop("workflowActor")
    record["app"] = {"id": record["app"]["id"]}
    write_canonical(hosted_path, record)
    _rebind_hosted_record(facts, hosted_path)

    with pytest.raises(SystemBacksyncError, match="AUTHORITY_UNAVAILABLE"):
        execute(repo, source, facts, tmp_path / "blocked.json")


@pytest.mark.parametrize(
    ("mutate", "field"),
    (
        (lambda record: record["app"].update(slug="untrusted-app"), "app"),
        (lambda record: record["workflowActor"].update(id=999), "actor"),
        (lambda record: record.update(workflowRunId=999), "run"),
        (lambda record: record.update(promotionAdmissionRef="ghcr.io/owner/quwoquan/promotion-admission@" + DIGEST_B), "ref"),
        (lambda record: record.update(admissionBytesDigest=DIGEST_B), "digest"),
    ),
)
def test_backsync_rejects_wrong_check_run_authority_binding(
    tmp_path: Path, mutate, field: str,
) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / f"evidence-{field}", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    hosted_path = facts["hosted_handoff_path"]
    record = json.loads(hosted_path.read_text(encoding="utf-8"))
    mutate(record)
    write_canonical(hosted_path, record)
    _rebind_hosted_record(facts, hosted_path)

    with pytest.raises(SystemBacksyncError, match="AUTHORITY_UNAVAILABLE"):
        execute(repo, source, facts, tmp_path / f"blocked-{field}.json")


def test_backsync_rejects_missing_trusted_app_identity(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )

    with pytest.raises(SystemBacksyncError, match="AUTHORITY_UNAVAILABLE"):
        execute(
            repo, source, facts, tmp_path / "blocked.json",
            environment_overrides={"QWQ_PROMOTION_RECORDER_APP_ID": ""},
        )


def test_backsync_rejects_admission_synthetic_merge_tree_drift(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    admission_path = facts["promotion_admission_path"]
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    admission["syntheticMergeTree"] = "d" * 40
    admission["admissionId"] = _digest(
        {key: value for key, value in admission.items() if key != "admissionId"}
    )
    write_canonical(admission_path, admission)
    seal_path = facts["main_source_seal_path"]
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["promotionAdmission"]["digest"] = _digest(admission_path)
    seal["sealId"] = _digest(
        {key: value for key, value in seal.items() if key != "sealId"}
    )
    write_canonical(seal_path, seal)

    with pytest.raises(SystemBacksyncError, match="SOURCE_NOT_MAIN_REACHABLE"):
        execute(repo, source, facts, tmp_path / "blocked.json")


def test_backsync_rejects_wrong_merge_and_predecessor_bytes(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    admission_path = facts["promotion_admission_path"]
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    admission["syntheticMergeTree"] = "d" * 40
    admission["admissionId"] = _digest(
        {key: value for key, value in admission.items() if key != "admissionId"}
    )
    write_canonical(admission_path, admission)

    with pytest.raises(SystemBacksyncError, match="AUTHORITY_UNAVAILABLE"):
        execute(repo, source, facts, tmp_path / "blocked.json")


def test_backsync_rejects_push_before_or_after_drift(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    for override in (
        {"GITHUB_EVENT_BEFORE": "d" * 40},
        {"GITHUB_EVENT_AFTER": "d" * 40},
    ):
        with pytest.raises(SystemBacksyncError):
            execute(
                repo, source, facts, tmp_path / f"blocked-{next(iter(override))}.json",
                environment_overrides=override,
            )
        assert git(repo, "ls-remote", "--refs", "origin", "refs/heads/dev1.0").split()[0] == source


def test_backsync_rejects_stale_expected_source_and_divergence(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )
    with pytest.raises(SystemBacksyncError, match="BACKSYNC_CAS_CONFLICT"):
        execute(repo, "c" * 40, facts, tmp_path / "blocked.json")

    git(repo, "checkout", "--orphan", "unrelated")
    git(repo, "rm", "-rf", ".")
    (repo / "unrelated").write_text("unrelated", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "unrelated")
    unrelated = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "--force", "origin", f"{unrelated}:dev1.0")
    git(repo, "checkout", "main")
    with pytest.raises(SystemBacksyncError, match="BACKSYNC_CAS_CONFLICT"):
        execute(repo, source, facts, tmp_path / "diverged.json")


def test_backsync_accepts_sha_pinned_reusable_workflow_identity(tmp_path: Path) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )

    result = execute(
        repo, source, facts, tmp_path / "sha-pinned.json",
        environment_overrides={
            "QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF": (
                f"{REPOSITORY}/.github/workflows/system-backsync.yml@{main}"
            )
        },
    )

    assert json.loads(result.read_text(encoding="utf-8"))["terminal"] == "success"


@pytest.mark.parametrize(
    "environment_overrides",
    (
        {"GITHUB_EVENT_NAME": "workflow_dispatch"},
        {"GITHUB_REF_NAME": "dev1.0"},
        {"GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/raw.yml@refs/heads/main"},
        {"QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/raw.yml@refs/heads/main"},
        {"QWQ_MANAGED_SYSTEM_BACKSYNC": ""},
    ),
)
def test_backsync_rejects_manual_or_unmanaged_runtime_before_mutation(
    tmp_path: Path, environment_overrides: dict[str, str],
) -> None:
    repo, base, source, source_tree, main, main_tree = repos(tmp_path)
    facts = evidence(
        tmp_path / "evidence", base=base, source=source,
        source_tree=source_tree, main=main, main_tree=main_tree,
    )

    with pytest.raises(SystemBacksyncError, match="DIRECT_PUSH_NOT_ALLOWED"):
        execute(
            repo, source, facts, tmp_path / "blocked.json",
            environment_overrides=environment_overrides,
        )
