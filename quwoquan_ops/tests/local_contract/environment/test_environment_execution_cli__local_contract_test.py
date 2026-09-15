# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-001
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

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
from quwoquan_ops.cli.lib.evidence_signing import (  # noqa: E402
    ENVIRONMENT_OPS_IDENTITY,
    INTEGRATION_SCHEDULER_IDENTITY,
)
from quwoquan_ops.tests.support.evidence_signing_test_support import (  # noqa: E402
    TemporarySigning,
    create_temporary_signing,
)

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "quwoquan_ops/cli/environment_execution.py"
CANDIDATE_CLI = ROOT / "quwoquan_ops/cli/integration_candidate.py"
IMPACT = "sha256:" + "9" * 64
NOW = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)


def _signing(store: Path, **kwargs: object) -> TemporarySigning:
    """每个测试的 store 旁边放一套临时私钥根 + keyring；重复调用幂等。"""

    return create_temporary_signing(store.parent / "signing", **kwargs)  # type: ignore[arg-type]


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
    # 只使用临时 bare origin；不访问真实远端、不移动工程 refs。
    origin = tmp_path / "origin.git"
    _git(repository, "init", "--bare", str(origin))
    _git(repository, "remote", "add", "origin", str(origin))
    _git(repository, "push", "origin", "dev1.0")
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
    environment = _signing(store).environment(
        {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(bytecode_root),
        }
    )
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
    assert "PRIVATE KEY" not in completed.stdout
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
        ENVIRONMENT_OPS_IDENTITY,
        "--signing-keyring",
        str(_signing(store).keyring_path),
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
        INTEGRATION_SCHEDULER_IDENTITY,
        "--signing-keyring",
        str(_signing(store).keyring_path),
        "--expected-alpha-signer-identity",
        ENVIRONMENT_OPS_IDENTITY,
        "--expected-beta-signer-identity",
        ENVIRONMENT_OPS_IDENTITY,
        "--expected-gamma-signer-identity",
        ENVIRONMENT_OPS_IDENTITY,
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
    _git(repository, "push", "origin", "dev1.0")
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
    _git(repository, "push", "origin", "dev1.0")

    completed, payload = _qualify(repository, store, publish_result, gamma)

    assert completed.returncode != 0
    assert payload["terminal"] == "GATE_BLOCK"
    assert payload["code"] == "ENVIRONMENT_EXECUTION.GAMMA_IDENTITY_DRIFT"


def test_cli_qualify_blocks_missing_environment_verification_key(
    tmp_path: Path,
) -> None:
    """keyring 里没有 environment-ops 的 active 公钥时，Gamma 链验签器不可构造，fail closed。"""

    repository, store, publish_result, gamma, _ = _qualification_inputs(tmp_path)
    head, tree = _dev_identity(repository)
    scheduler_only = create_temporary_signing(
        tmp_path / "scheduler-only", identities=(INTEGRATION_SCHEDULER_IDENTITY,),
    )
    environment = scheduler_only.environment(
        {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(store.parent / "python-cache"),
        }
    )
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
            INTEGRATION_SCHEDULER_IDENTITY,
            "--signing-keyring",
            str(scheduler_only.keyring_path),
            "--expected-alpha-signer-identity",
            ENVIRONMENT_OPS_IDENTITY,
            "--expected-beta-signer-identity",
            ENVIRONMENT_OPS_IDENTITY,
            "--expected-gamma-signer-identity",
            ENVIRONMENT_OPS_IDENTITY,
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
    assert "PRIVATE KEY" not in completed.stdout


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
        ENVIRONMENT_OPS_IDENTITY,
        "--signing-keyring",
        str(_signing(store).keyring_path),
        "--expected-alpha-signer-identity",
        ENVIRONMENT_OPS_IDENTITY,
        "--expected-beta-signer-identity",
        ENVIRONMENT_OPS_IDENTITY,
        "--expected-gamma-signer-identity",
        ENVIRONMENT_OPS_IDENTITY,
        "--issued-at",
        NOW.isoformat(),
        "--expires-at",
        (NOW + timedelta(hours=1)).isoformat(),
    )
    assert completed.returncode == 2
    assert payload["terminal"] == "GATE_BLOCK"
    assert payload["code"] == "ENVIRONMENT_EXECUTION.KEY_PURPOSE_CONFLICT"


def test_integration_candidate_qualify_blocks_missing_environment_key(tmp_path: Path) -> None:
    scheduler_only = create_temporary_signing(
        tmp_path / "scheduler-only", identities=(INTEGRATION_SCHEDULER_IDENTITY,),
    )
    environment = scheduler_only.environment({**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CANDIDATE_CLI),
            "qualify",
            "--publish-result",
            "publish/result.json=sha256:" + "1" * 64,
            "--gamma-fact",
            "acceptance/gamma.json=sha256:" + "2" * 64,
            "--qualification-signer-identity",
            INTEGRATION_SCHEDULER_IDENTITY,
            "--signing-keyring",
            str(scheduler_only.keyring_path),
            "--expected-alpha-signer-identity",
            ENVIRONMENT_OPS_IDENTITY,
            "--expected-beta-signer-identity",
            ENVIRONMENT_OPS_IDENTITY,
            "--expected-gamma-signer-identity",
            ENVIRONMENT_OPS_IDENTITY,
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
    assert "PRIVATE KEY" not in completed.stdout


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
    assert fact["publishResult"] == publish_result


def _store_snapshot(store: Path) -> dict[str, bytes]:
    return {path.relative_to(store).as_posix(): path.read_bytes()
            for path in store.rglob("*") if path.is_file()}


def test_published_head_still_requires_exact_publish_predecessor(tmp_path: Path) -> None:
    repository, store, publish_result, gamma, _ = _qualification_inputs(tmp_path)
    payload = json.loads((store / publish_result["ref"]).read_bytes())
    payload["readbackOid"] = "0" * 40
    wrong_publish = _write(store, "publish/wrong-readback.json", payload)
    before = _store_snapshot(store)
    completed, result = _qualify(repository, store, wrong_publish, gamma)
    assert completed.returncode == 2
    assert result["code"] == "INTEGRATION_QUALIFICATION.DEV_HEAD_DRIFT"
    assert _store_snapshot(store) == before


def test_local_unpublished_head_cannot_qualify(tmp_path: Path) -> None:
    repository, store, publish_result, gamma, _ = _qualification_inputs(tmp_path)
    _git(repository, "commit", "--allow-empty", "-m", "unpublished candidate")
    before = _store_snapshot(store)
    completed, payload = _qualify(repository, store, publish_result, gamma)
    assert completed.returncode == 2
    assert payload["code"] == "ENVIRONMENT_EXECUTION.DEV_HEAD_DRIFT"
    assert _store_snapshot(store) == before


def test_remote_move_without_local_tracking_update_blocks_qualification(tmp_path: Path) -> None:
    repository, store, publish_result, gamma, candidate = _qualification_inputs(tmp_path)
    moved = _git(repository, "commit-tree", candidate["tree"], "-p", candidate["commit"], "-m", "published next")
    _git(repository, "push", str(tmp_path / "origin.git"), f"{moved}:refs/heads/dev1.0")
    before = _store_snapshot(store)
    completed, payload = _qualify(repository, store, publish_result, gamma)
    assert completed.returncode == 2
    assert payload["code"] == "ENVIRONMENT_EXECUTION.DEV_HEAD_DRIFT"
    assert _git(repository, "rev-parse", "origin/dev1.0") == candidate["commit"]
    assert _store_snapshot(store) == before


@pytest.mark.parametrize("failure", ["local-ahead", "remote-moved", "unavailable", "candidate-drift", "expected-tree"])
def test_gamma_request_rejects_unpublished_identity_without_mutation(tmp_path: Path, failure: str) -> None:
    repository, store = _initialize_repository(tmp_path)
    head, tree = _dev_identity(repository)
    if failure == "local-ahead":
        _git(repository, "commit", "--allow-empty", "-m", "local only")
        head, tree = _dev_identity(repository)
    candidate, _ = _candidate(store, repository)
    if failure == "remote-moved":
        moved = _git(repository, "commit-tree", tree, "-p", head, "-m", "remote only")
        _git(repository, "push", str(tmp_path / "origin.git"), f"{moved}:refs/heads/dev1.0")
    elif failure == "unavailable":
        _git(repository, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    elif failure == "candidate-drift":
        _git(repository, "commit", "--allow-empty", "-m", "published successor")
        _git(repository, "push", "origin", "dev1.0")
        head, tree = _dev_identity(repository)
    elif failure == "expected-tree":
        tree = "0" * 40
    before = _store_snapshot(store)
    refs = _git(repository, "show-ref")
    index = (repository / ".git/index").read_bytes()
    completed, payload = _run_cli(
        repository, store, "request", "--candidate", _exact_arg(candidate),
        "--environment", "gamma", "--impact-plan-digest", IMPACT, "--priority", "1",
        "--expected-dev-head", head, "--expected-dev-tree", tree,
    )
    code = {"unavailable": "DEV_AUTHORITY_UNAVAILABLE", "candidate-drift": "GAMMA_IDENTITY_DRIFT"}.get(failure, "DEV_HEAD_DRIFT")
    assert completed.returncode == 2
    assert payload["code"] == f"ENVIRONMENT_EXECUTION.{code}"
    assert _store_snapshot(store) == before
    assert _git(repository, "show-ref") == refs
    assert (repository / ".git/index").read_bytes() == index


@pytest.mark.parametrize("stage", ["before-sign", "after-sign"])
@pytest.mark.parametrize("failure", ["moved", "unavailable"])
@pytest.mark.parametrize("command", ["issue", "qualify"])
def test_signing_stage_drift_leaves_no_usable_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, failure: str, command: str,
) -> None:
    from quwoquan_ops.cli import environment_execution as execution

    original_cli = _run_cli
    original_guard = execution._published_dev_signer
    observed = []

    def intercepted(repository: Path, store: Path, *arguments: str):
        if arguments[0] != command or (command == "issue" and "evidence/gamma-case.json" not in " ".join(arguments)):
            return original_cli(repository, store, *arguments)
        for key, value in _signing(store).environment({}).items():
            monkeypatch.setenv(key, value)
        args = execution._build_parser().parse_args([
            "--repository", str(repository), "--store-root", str(store), *arguments,
        ])
        before = _store_snapshot(store)
        expected = "DEV_HEAD_DRIFT" if failure == "moved" else "DEV_AUTHORITY_UNAVAILABLE"
        with pytest.raises(execution.EnvironmentExecutionError, match=expected):
            execution._dispatch(args)
        assert _store_snapshot(store) == before
        observed.append(command)
        # 提前终止 fixture，不合成 acceptance 或 qualification 成功。
        raise StopIteration("observed signing fence")

    def guard(repository, current, signer):
        def drift():
            if failure == "unavailable":
                _git(repository, "remote", "set-url", "origin", str(tmp_path / "absent.git"))
            else:
                moved = _git(repository, "commit-tree", current["tree"], "-p", current["head"], "-m", "concurrent publish")
                _git(repository, "push", str(tmp_path / "origin.git"), f"{moved}:refs/heads/dev1.0")

        def real_sign(payload):
            signature = signer(payload)
            if stage == "after-sign":
                drift()
            return signature

        if stage == "before-sign":
            drift()
        return original_guard(repository, current, real_sign)

    monkeypatch.setattr(execution, "_published_dev_signer", guard)
    monkeypatch.setattr(sys.modules[__name__], "_run_cli", intercepted)
    with pytest.raises(StopIteration, match="observed signing fence"):
        repository, store, publish_result, gamma, _ = _qualification_inputs(tmp_path)
        _qualify(repository, store, publish_result, gamma)
    assert observed == [command]


def test_unreadable_origin_cannot_fall_back_to_local_dev(tmp_path: Path) -> None:
    repository, store, publish_result, gamma, _ = _qualification_inputs(tmp_path)
    _git(repository, "remote", "set-url", "origin", str(tmp_path / "missing-origin.git"))
    before = _store_snapshot(store)
    completed, payload = _qualify(repository, store, publish_result, gamma)
    assert completed.returncode == 2
    assert payload["code"] == "ENVIRONMENT_EXECUTION.DEV_AUTHORITY_UNAVAILABLE"
    assert _store_snapshot(store) == before
