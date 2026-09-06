# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-001
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True

from quwoquan_ops.ci.environment_scheduler import (  # noqa: E402
    canonical_digest,
    canonical_json_bytes,
    current_task_state,
    exact_file_digest,
    write_create_once,
)

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "quwoquan_ops/cli/environment_execution.py"
CANDIDATE_CLI = ROOT / "quwoquan_ops/cli/integration_candidate.py"
IMPACT = "sha256:" + "9" * 64
NOW = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
ACCEPTANCE_KEY_ENV = "TEST_ENVIRONMENT_ACCEPTANCE_SIGNING_KEY"
QUALIFICATION_KEY_ENV = "TEST_INTEGRATION_QUALIFICATION_SIGNING_KEY"


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _initialize_repository(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    store = tmp_path / "store"
    repository.mkdir()
    _git(repository, "init", "-b", "dev1.0")
    _git(repository, "config", "user.name", "Environment Execution Test")
    _git(repository, "config", "user.email", "environment-execution@example.com")
    (repository / "owned.txt").write_text("current\n", encoding="utf-8")
    _git(repository, "add", "owned.txt")
    _git(repository, "commit", "-m", "current dev head")
    return repository, store


def _dev_identity(repository: Path) -> tuple[str, str]:
    head = _git(repository, "rev-parse", "refs/heads/dev1.0")
    tree = _git(repository, "show", "-s", "--format=%T", head)
    return head, tree


def _write(store: Path, ref: str, value: dict[str, object]) -> dict[str, str]:
    path = store / ref
    write_create_once(path, value)
    return {"ref": ref, "digest": exact_file_digest(path)}


def _exact_arg(value: dict[str, str]) -> str:
    return f"{value['ref']}={value['digest']}"


def _run_cli(
    repository: Path,
    store: Path,
    *args: str,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    bytecode_root = store.parent / "python-cache"
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(bytecode_root),
        ACCEPTANCE_KEY_ENV: "acceptance-secret-never-print",
        QUALIFICATION_KEY_ENV: "qualification-secret-never-print",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CLI),
            "--repository",
            str(repository),
            "--store-root",
            str(store),
            *args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    assert completed.stderr == ""
    assert "acceptance-secret-never-print" not in completed.stdout
    assert "qualification-secret-never-print" not in completed.stdout
    lines = completed.stdout.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert completed.stdout == canonical_json_bytes(payload).decode("utf-8") + "\n"
    return completed, payload


def _candidate(
    store: Path,
    repository: Path,
    *,
    name: str = "current",
) -> tuple[dict[str, str], dict[str, str]]:
    head, tree = _dev_identity(repository)
    body: dict[str, object] = {
        "schema": "quwoquan_ops.exact_integration_candidate.v1",
        "commit": head,
        "tree": tree,
        "expectedParent": head,
        "impactPlanDigest": IMPACT,
        "createdAt": NOW.isoformat(),
    }
    body["candidateId"] = canonical_digest(body)
    return _write(store, f"candidates/{name}.json", body), {
        "candidateId": str(body["candidateId"]),
        "commit": head,
        "tree": tree,
    }


def _request(
    repository: Path,
    store: Path,
    candidate: dict[str, str],
    *,
    environment: str,
    priority: int,
) -> dict[str, str]:
    arguments = [
        "request",
        "--candidate",
        _exact_arg(candidate),
        "--environment",
        environment,
        "--impact-plan-digest",
        IMPACT,
        "--priority",
        str(priority),
        "--created-at",
        NOW.isoformat(),
    ]
    if environment == "gamma":
        head, tree = _dev_identity(repository)
        arguments.extend(["--expected-dev-head", head, "--expected-dev-tree", tree])
    completed, payload = _run_cli(repository, store, *arguments)
    assert completed.returncode == 0
    assert payload["terminal"] == "requested"
    return dict(payload["request"])


def _transition(
    repository: Path,
    store: Path,
    request: dict[str, str],
    state: str,
) -> dict[str, object]:
    completed, payload = _run_cli(
        repository,
        store,
        "transition",
        "--request",
        _exact_arg(request),
        "--state",
        state,
        "--occurred-at",
        NOW.isoformat(),
    )
    assert completed.returncode == 0
    assert payload["state"] == state
    return payload


def _case_result(
    store: Path,
    candidate: dict[str, str],
    environment: str,
) -> dict[str, str]:
    value: dict[str, object] = {
        "objectId": f"{environment}-case",
        "specRef": "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-001",
        "caseId": f"{environment}-case",
        "producer": "ops",
        "layer": "environment_acceptance",
        "status": "passed",
        "target": {"kind": "operation", "id": f"{environment}-case"},
        "commitSha": candidate["commit"],
        "contractGraphSourceHash": "4" * 64,
        "deploymentTarget": f"{environment}-local",
        "baselineId": "environment-execution-cli-v1",
        "packageDigest": "sha256:" + "5" * 64,
        "configurationDigest": "sha256:" + "6" * 64,
        "candidateManifestSha256": "7" * 64,
        "candidateDigest": candidate["candidateId"],
        "environment": environment,
        "provider": "first-party-https",
        "startedAt": NOW.isoformat(),
        "completedAt": (NOW + timedelta(minutes=1)).isoformat(),
        "runnerIdentity": "environment-execution-cli",
        "artifactSha256": "8" * 64,
        "receiptRef": f"environment/{environment}/case.json",
    }
    return _write(store, f"evidence/{environment}-case.json", value)


def _named_evidence(
    store: Path,
    candidate: dict[str, str],
    environment: str,
    role: str,
) -> dict[str, str]:
    statuses = {
        "runtime-identity": "ready",
        "data-lifecycle": "closed",
        "provider-readiness": "ready",
        "observability-readiness": "ready",
        "inspect": "passed",
        "doctor": "passed",
        "cleanup": "closed",
        "lease-closure": "released",
    }
    value: dict[str, object] = {
        "schema": f"quwoquan_ops.environment_{role}.v1",
        "role": role,
        "status": statuses[role],
        "environment": environment,
        "profile": "integration",
        **candidate,
        "impactPlanDigest": IMPACT,
    }
    return _write(store, f"evidence/{environment}-{role}.json", value)


def _issue_acceptance(
    repository: Path,
    store: Path,
    request: dict[str, str],
    candidate: dict[str, str],
    environment: str,
    predecessor: dict[str, str] | None,
) -> dict[str, str]:
    case_result = _case_result(store, candidate, environment)
    roles = {
        role: _named_evidence(store, candidate, environment, role)
        for role in (
            "runtime-identity",
            "data-lifecycle",
            "provider-readiness",
            "observability-readiness",
            "inspect",
            "doctor",
            "cleanup",
            "lease-closure",
        )
    }
    arguments = [
        "issue",
        "--request",
        _exact_arg(request),
        "--profile",
        "integration",
        "--status",
        "passed",
        "--case-result",
        _exact_arg(case_result),
        "--runtime-identity",
        _exact_arg(roles["runtime-identity"]),
        "--data-lifecycle",
        _exact_arg(roles["data-lifecycle"]),
        "--provider-readiness",
        _exact_arg(roles["provider-readiness"]),
        "--observability-readiness",
        _exact_arg(roles["observability-readiness"]),
        "--inspect-evidence",
        _exact_arg(roles["inspect"]),
        "--doctor-evidence",
        _exact_arg(roles["doctor"]),
        "--cleanup-evidence",
        _exact_arg(roles["cleanup"]),
        "--lease-closure-evidence",
        _exact_arg(roles["lease-closure"]),
        "--signer-identity",
        "spiffe://quwoquan.local/environment-ops",
        "--signing-key-env",
        ACCEPTANCE_KEY_ENV,
        "--issued-at",
        NOW.isoformat(),
        "--expires-at",
        (NOW + timedelta(hours=2)).isoformat(),
        "--non-promotable",
        "true",
    ]
    if predecessor is not None:
        arguments.extend(["--predecessor", _exact_arg(predecessor)])
    completed, payload = _run_cli(repository, store, *arguments)
    assert completed.returncode == 0
    assert payload["terminal"] == "acceptance_issued"
    return dict(payload["acceptance"])


def _qualification_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, str], dict[str, str], dict[str, str]]:
    repository, store = _initialize_repository(tmp_path)
    candidate_ref, candidate = _candidate(store, repository)
    predecessor: dict[str, str] | None = None
    facts: dict[str, dict[str, str]] = {}
    for environment in ("alpha", "beta", "gamma"):
        request = _request(
            repository,
            store,
            candidate_ref,
            environment=environment,
            priority=1,
        )
        _transition(repository, store, request, "queued")
        _transition(repository, store, request, "mutation_started")
        facts[environment] = _issue_acceptance(
            repository,
            store,
            request,
            candidate,
            environment,
            predecessor,
        )
        predecessor = facts[environment]
    admission = _write(
        store,
        "publish/admission.json",
        {
            "schema": "quwoquan_ops.integration_publish_admission.v1",
            "decision": "admitted",
            **candidate,
            "environmentFacts": {
                "alpha": facts["alpha"],
                "beta": facts["beta"],
            },
        },
    )
    publish_result = _write(
        store,
        "publish/result.json",
        {
            "schema": "quwoquan_ops.integration_publish_result.v1",
            "terminal": "published",
            "targetRef": "refs/heads/dev1.0",
            "afterOid": candidate["commit"],
            "readbackOid": candidate["commit"],
            "admission": admission,
        },
    )
    return repository, store, publish_result, facts["gamma"], candidate


def _qualify(
    repository: Path,
    store: Path,
    publish_result: dict[str, str],
    gamma: dict[str, str],
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    head, tree = _dev_identity(repository)
    return _run_cli(
        repository,
        store,
        "qualify",
        "--publish-result",
        _exact_arg(publish_result),
        "--gamma-acceptance",
        _exact_arg(gamma),
        "--expected-dev-head",
        head,
        "--expected-dev-tree",
        tree,
        "--qualification-signer-identity",
        "spiffe://quwoquan.local/integration",
        "--qualification-signing-key-env",
        QUALIFICATION_KEY_ENV,
        "--environment-verification-key-env",
        ACCEPTANCE_KEY_ENV,
        "--expected-alpha-signer-identity",
        "spiffe://quwoquan.local/environment-ops",
        "--expected-beta-signer-identity",
        "spiffe://quwoquan.local/environment-ops",
        "--expected-gamma-signer-identity",
        "spiffe://quwoquan.local/environment-ops",
        "--issued-at",
        NOW.isoformat(),
        "--expires-at",
        (NOW + timedelta(hours=1)).isoformat(),
    )


def test_cli_request_next_exposes_gamma_priority_and_deduplicates(
    tmp_path: Path,
) -> None:
    repository, store = _initialize_repository(tmp_path)
    candidate, _ = _candidate(store, repository)
    alpha = _request(repository, store, candidate, environment="alpha", priority=999)
    gamma = _request(repository, store, candidate, environment="gamma", priority=0)
    duplicate = _request(
        repository, store, candidate, environment="gamma", priority=500
    )

    assert duplicate == gamma
    completed, payload = _run_cli(
        repository,
        store,
        "next",
        "--request",
        _exact_arg(alpha),
        "--request",
        _exact_arg(gamma),
        "--request",
        _exact_arg(duplicate),
    )

    assert completed.returncode == 0
    assert payload["terminal"] == "selected"
    assert payload["requestRef"] == gamma
    assert payload["request"]["environment"] == "gamma"
    assert payload["request"]["priority"] == 0


def test_cli_supersede_turns_mutated_stale_gamma_into_safe_teardown(
    tmp_path: Path,
) -> None:
    repository, store = _initialize_repository(tmp_path)
    candidate, _ = _candidate(store, repository)
    gamma = _request(repository, store, candidate, environment="gamma", priority=1)
    _transition(repository, store, gamma, "queued")
    _transition(repository, store, gamma, "mutation_started")

    (repository / "next.txt").write_text("next\n", encoding="utf-8")
    _git(repository, "add", "next.txt")
    _git(repository, "commit", "-m", "advance dev head")
    head, tree = _dev_identity(repository)
    completed, payload = _run_cli(
        repository,
        store,
        "supersede",
        "--request",
        _exact_arg(gamma),
        "--expected-dev-head",
        head,
        "--expected-dev-tree",
        tree,
        "--reason",
        "superseded by current dev head",
        "--occurred-at",
        NOW.isoformat(),
    )

    assert completed.returncode == 0
    assert payload["terminal"] == "superseded"
    assert payload["requests"][0]["state"] == "safe_teardown_required"
    request_payload = json.loads((store / gamma["ref"]).read_text(encoding="utf-8"))
    assert (
        current_task_state(store_root=store, request_id=request_payload["requestId"])
        == "safe_teardown_required"
    )
    event = json.loads(
        (store / payload["requests"][0]["event"]["ref"]).read_text(encoding="utf-8")
    )
    assert event["reason"] == "superseded by current dev head"


def test_cli_qualify_blocks_gamma_for_stale_dev_head(tmp_path: Path) -> None:
    repository, store, publish_result, gamma, _ = _qualification_inputs(tmp_path)
    (repository / "next.txt").write_text("next\n", encoding="utf-8")
    _git(repository, "add", "next.txt")
    _git(repository, "commit", "-m", "replace qualified candidate")

    completed, payload = _qualify(repository, store, publish_result, gamma)

    assert completed.returncode != 0
    assert payload["terminal"] == "GATE_BLOCK"
    assert payload["code"] == "ENVIRONMENT_EXECUTION.GAMMA_IDENTITY_DRIFT"


def test_cli_qualify_blocks_missing_environment_verification_key(
    tmp_path: Path,
) -> None:
    repository, store, publish_result, gamma, _ = _qualification_inputs(tmp_path)
    head, tree = _dev_identity(repository)
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(store.parent / "python-cache"),
            QUALIFICATION_KEY_ENV: "qualification-secret-never-print",
        }
    )
    environment.pop(ACCEPTANCE_KEY_ENV, None)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CLI),
            "--repository",
            str(repository),
            "--store-root",
            str(store),
            "qualify",
            "--publish-result",
            _exact_arg(publish_result),
            "--gamma-acceptance",
            _exact_arg(gamma),
            "--expected-dev-head",
            head,
            "--expected-dev-tree",
            tree,
            "--qualification-signer-identity",
            "spiffe://quwoquan.local/integration",
            "--qualification-signing-key-env",
            QUALIFICATION_KEY_ENV,
            "--environment-verification-key-env",
            ACCEPTANCE_KEY_ENV,
            "--expected-alpha-signer-identity",
            "spiffe://quwoquan.local/environment-ops",
            "--expected-beta-signer-identity",
            "spiffe://quwoquan.local/environment-ops",
            "--expected-gamma-signer-identity",
            "spiffe://quwoquan.local/environment-ops",
            "--issued-at",
            NOW.isoformat(),
            "--expires-at",
            (NOW + timedelta(hours=1)).isoformat(),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    payload = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert completed.stderr == ""
    assert payload["terminal"] == "GATE_BLOCK"
    assert payload["code"] == "ENVIRONMENT_EXECUTION.ENVIRONMENT_VERIFIER_UNAVAILABLE"
    assert "qualification-secret-never-print" not in completed.stdout


def test_cli_qualify_blocks_key_purpose_reuse(tmp_path: Path) -> None:
    repository, store, publish_result, gamma, _ = _qualification_inputs(tmp_path)
    head, tree = _dev_identity(repository)
    completed, payload = _run_cli(
        repository,
        store,
        "qualify",
        "--publish-result",
        _exact_arg(publish_result),
        "--gamma-acceptance",
        _exact_arg(gamma),
        "--expected-dev-head",
        head,
        "--expected-dev-tree",
        tree,
        "--qualification-signer-identity",
        "spiffe://quwoquan.local/integration",
        "--qualification-signing-key-env",
        QUALIFICATION_KEY_ENV,
        "--environment-verification-key-env",
        QUALIFICATION_KEY_ENV,
        "--expected-alpha-signer-identity",
        "spiffe://quwoquan.local/environment-ops",
        "--expected-beta-signer-identity",
        "spiffe://quwoquan.local/environment-ops",
        "--expected-gamma-signer-identity",
        "spiffe://quwoquan.local/environment-ops",
        "--issued-at",
        NOW.isoformat(),
        "--expires-at",
        (NOW + timedelta(hours=1)).isoformat(),
    )
    assert completed.returncode == 2
    assert payload["terminal"] == "GATE_BLOCK"
    assert payload["code"] == "ENVIRONMENT_EXECUTION.KEY_PURPOSE_CONFLICT"


def test_integration_candidate_qualify_blocks_missing_environment_key() -> None:
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        QUALIFICATION_KEY_ENV: "qualification-secret-never-print",
    }
    environment.pop(ACCEPTANCE_KEY_ENV, None)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CANDIDATE_CLI),
            "qualify",
            "--publish-result-ref",
            "publish/result.json",
            "--publish-result-digest",
            "sha256:" + "1" * 64,
            "--gamma-fact-ref",
            "acceptance/gamma.json",
            "--gamma-fact-digest",
            "sha256:" + "2" * 64,
            "--qualification-signer-identity",
            "spiffe://quwoquan.local/integration",
            "--qualification-signing-key-env",
            QUALIFICATION_KEY_ENV,
            "--environment-verification-key-env",
            ACCEPTANCE_KEY_ENV,
            "--expected-alpha-signer-identity",
            "spiffe://quwoquan.local/environment-ops",
            "--expected-beta-signer-identity",
            "spiffe://quwoquan.local/environment-ops",
            "--expected-gamma-signer-identity",
            "spiffe://quwoquan.local/environment-ops",
            "--issued-at",
            NOW.isoformat(),
            "--expires-at",
            (NOW + timedelta(hours=1)).isoformat(),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert completed.stderr == ""
    assert payload["terminal"] == "GATE_BLOCK"
    assert payload["code"] == "SCOPED_CANDIDATE.ENVIRONMENT_VERIFIER_UNAVAILABLE"
    assert "qualification-secret-never-print" not in completed.stdout


def test_cli_issues_gamma_and_qualifies_current_exact_dev_head(
    tmp_path: Path,
) -> None:
    repository, store, publish_result, gamma, candidate = _qualification_inputs(
        tmp_path
    )

    completed, payload = _qualify(repository, store, publish_result, gamma)

    assert completed.returncode == 0
    assert payload["terminal"] == "qualified"
    fact_path = store / payload["qualification"]["ref"]
    assert payload["qualification"]["digest"] == exact_file_digest(fact_path)
    fact = json.loads(fact_path.read_text(encoding="utf-8"))
    assert fact["devHead"] == candidate["commit"]
    assert fact["devTree"] == candidate["tree"]
    assert fact["candidate"] == candidate
    assert fact["environmentChain"]["gamma"] == gamma
