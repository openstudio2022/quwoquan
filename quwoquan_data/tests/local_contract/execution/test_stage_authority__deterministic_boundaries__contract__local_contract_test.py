"""spec_ref: multi-carrier-release GWT-020/GWT-030/GWT-034。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from content.execution import stage_authority, stage_semantic_recorder, task_init
from content.execution import stage_gate_registry
from core import paths
from core.source_digest import current_execution_bundle_identity, current_source_definition_snapshot

EXECUTION_ID = "20260901--travel-article-stage-authority--china--pilot-001"


def _write_inputs(root: Path) -> tuple[Path, Path]:
    demand = {
        "schema": "quwoquan_data.carrier_demand", "status": "confirmed",
        "executionId": EXECUTION_ID, "carrier": "article",
        "familyRef": "content/travel/article/article", "quota": 1,
        "workRequestRef": "data/local/workspace/work-requests/wr.json",
        "workRequestDigest": "sha256:" + "1" * 64,
        "sourceDigest": current_source_definition_snapshot().to_document(),
        "executionBundle": current_execution_bundle_identity().to_document(),
        "entityCatalogDigest": "sha256:" + "2" * 64, "retryOf": None,
    }
    candidates = {
        "schema": "quwoquan_data.immutable_candidate_bindings",
        "executionId": EXECUTION_ID, "carrier": "article",
        "sourceRef": "data/local/workspace/source-pools/article.json",
        "entityCatalogDigest": demand["entityCatalogDigest"], "candidateCount": 1,
        "targets": [{"name": "西湖", "entityType": "地点/景区", "publishAngle": "攻略", "publishTitle": "西湖攻略", "publishSeq": 1}],
    }
    demand_path = root / "inputs/demand.json"
    candidate_path = root / "inputs/candidates.json"
    demand_path.parent.mkdir(parents=True)
    demand_path.write_text(json.dumps(demand, ensure_ascii=False), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
    return demand_path, candidate_path


@pytest.fixture
def work_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    release = output / "data/releases"
    for module in (paths, task_init.paths, stage_authority.paths, stage_semantic_recorder.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
        monkeypatch.setattr(module, "RELEASE_ROOT", release)
    demand, candidates = _write_inputs(output)
    task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=candidates)
    return tasks / EXECUTION_ID


def _runner(exit_code: int = 0):
    def run(argv: tuple[str, ...]) -> SimpleNamespace:
        return SimpleNamespace(returncode=exit_code, stdout="real stdout", stderr="real stderr")
    return run


def _semantic_context(stage: str, *, actor_family: str = "gpt") -> dict:
    request_path = stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, stage)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result_refs = _write_semantic_outputs(stage, actor_family=actor_family)
    result_input = {
        "schema": "quwoquan_data.stage_semantic_result_input",
        "requestRef": request_path.relative_to(paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID).as_posix(),
        "requestDigest": request["requestDigest"],
        "actor": {
            "host": "cursor", "modelFamily": actor_family, "sessionId": f"{stage}-session",
            "invocation": {"provider": "cursor", "model": actor_family, "runId": f"{stage}-run"},
        },
        "resultRefs": sorted(result_refs),
    }
    result_path = stage_semantic_recorder.record_stage_semantic_result(
        EXECUTION_ID, stage, result_input
    )
    return {
        "semanticResultRef": result_path.relative_to(paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID).as_posix(),
        "semanticResultDigest": stage_authority._sha256(result_path.read_bytes()),
    }


def _write_json(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    return path.relative_to(paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID).as_posix()


def _write_semantic_outputs(stage: str, *, actor_family: str) -> list[str]:
    root = paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID
    object_root = root / "posts/article/攻略/西湖攻略/1"
    if stage == "sources":
        unit = root / "sources/source-001"
        values = {
            "meta.json": {
                "schema": "quwoquan_data.source_unit", "stage": "1.download",
                "executionId": EXECUTION_ID, "executionBinding": "frozen",
                "sourceUnitId": "source-001", "entityName": "西湖", "title": "西湖",
                "sourceKind": "wikipedia", "extractor": "wikipedia_api",
                "canonicalUrl": "https://zh.wikipedia.org/wiki/西湖",
                "finalUrl": "https://zh.wikipedia.org/wiki/西湖", "fetchedAt": "2026-09-01T00:00:00Z",
                "rawSha256": "sha256:" + "1" * 64, "cleanSha256": "sha256:" + "2" * 64,
                "policyRevision": "encyclopedia-primary", "sourceUseMode": "factual_reference_only",
                "rightsMode": "factual_reference_only",
            },
            "source.md": "source", "source.clean.md": "source", "source.layout.json": {},
            "source.quality.json": {}, "assets/index.json": {},
        }
        refs = []
        for name, value in values.items():
            path = unit / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text((json.dumps(value) if isinstance(value, dict) else value) + "\n", encoding="utf-8")
            refs.append(path.relative_to(root).as_posix())
        return refs
    if stage == "2.quality":
        path = object_root / "2.quality/quality_analysis.json"
        return [_write_json(path, {
            "schema": "quwoquan_data.quality_analysis", "stage": "2.quality",
            "executionId": EXECUTION_ID, "executionBinding": "frozen",
            "sourcePolicyRevision": "encyclopedia-primary", "sourceRevision": "sha256:" + "1" * 64,
            "recommendation": "proceed", "sourcePaths": ["sources/source-001/source.clean.md"],
            "sourceAdmissions": [{"sourceRef": "sources/source-001", "decision": "selected", "evidenceHash": "sha256:" + "2" * 64}],
            "rejectionReasons": [], "evidenceHashes": ["sha256:" + "2" * 64],
        })]
    if stage == "3.compose":
        path = object_root / "3.compose/writing_pack.json"
        return [_write_json(path, {
            "schema": "quwoquan_data.writing_pack", "stage": "3.compose",
            "executionId": EXECUTION_ID, "executionBinding": "frozen",
            "sourcePolicyRevision": "encyclopedia-primary", "sourceRevision": "sha256:" + "1" * 64,
            "promptBundleRevision": "sha256:" + "2" * 64,
            "selectedSourceUrls": ["https://zh.wikipedia.org/wiki/西湖"],
            "ref": "article-object", "kind": "article", "title": "西湖攻略", "carrier": "article",
        })]
    if stage == "4.draft":
        draft = object_root / "4.draft/draft.article.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("draft\n", encoding="utf-8")
        path = object_root / "4.draft/agent_result_envelope.json"
        digest = stage_authority._sha256(draft.read_bytes())
        return [_write_json(path, {
            "schema": "quwoquan.agent_result_envelope", "executionId": EXECUTION_ID,
            "jobId": "author-job", "ref": "article-object", "stage": "4.draft",
            "agent": {"provider": "cursor", "model": actor_family, "runId": "4.draft-run", "promptSha256": "sha256:" + "3" * 64},
            "files": [{"path": "draft.article.md", "sha256": digest}],
            "gates": [{"schema": "quwoquan.gate_verdict", "gateId": "draft", "decision": "passed", "final": True, "inputHash": "sha256:" + "4" * 64, "outputHash": digest}],
        })]
    reviewer = object_root / "5.review/reviewer_result.json"
    rubric = object_root / "5.review/rubric_review.json"
    return [
        _write_json(reviewer, {
            "schema": "quwoquan_data.reviewer_result", "stage": "5.review",
            "executionId": EXECUTION_ID, "executionBinding": "frozen", "objectRef": "article-object",
            "provider": "cursor", "model": actor_family, "modelFamily": actor_family,
            "runId": "5.review-run", "verdict": "passed", "issues": [],
            "resultHash": "sha256:" + "5" * 64,
        }),
        _write_json(rubric, {
            "schema": "quwoquan_data.rubric_review", "ref": "article-object",
            "generationModelFamily": "gpt",
            "judges": [{"modelId": actor_family, "modelFamily": actor_family, "promptHash": "sha256:" + "6" * 64, "temperature": 0}],
            "biasControls": {"positionSwapApplied": True, "lengthControlApplied": True},
            "dimensions": [{"name": "professionalism", "scores": [9, 9], "verdict": "pass", "rationale": "pass"}],
            "decision": "approved",
        }),
    ]


def _open_gate_close(stage: str, *, runner=None, issues=None, actor_family="gpt") -> Path:
    stage_authority.open_stage(EXECUTION_ID, stage)
    if stage == "4.draft":
        draft_dir = paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID / "posts/article/攻略/西湖攻略/1/4.draft"
        draft_dir.mkdir(parents=True, exist_ok=True)
        (draft_dir / "prompt.md").write_text("prompt\n", encoding="utf-8")
        for name in ("prompt_snapshot.json", "author_job_packet.json", "draft_meta.json", "author_self_check.json"):
            (draft_dir / name).write_text("{}\n", encoding="utf-8")
    if stage == "1.download":
        _write_json(
            paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID / "posts/article/攻略/西湖攻略/1/1.download/source_refs.json",
            {"sources": []},
        )
    context = _semantic_context(stage, actor_family=actor_family) if stage in stage_semantic_recorder.SEMANTIC_STAGES else None
    if stage == "5.review":
        review_dir = paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID / "posts/article/攻略/西湖攻略/1/5.review"
        for name in ("deterministic_gate.json", "media_ref_review.json", "finalization_report.json", "attestation.json", "evidence_index.json"):
            (review_dir / name).write_text("{}\n", encoding="utf-8")
    if stage in {"1.download", "2.quality", "3.compose", "4.draft", "5.review"}:
        from core.stage_artifact_contract import required_stage_artifacts
        lane = "article"
        root = paths.DATA_EXECUTIONS_ROOT / EXECUTION_ID
        refs = []
        for name in required_stage_artifacts(lane)[stage]:
            candidates = list(root.glob(f"**/{stage}/{name}"))
            if candidates:
                refs.append({"scope": "execution", "ref": candidates[0].relative_to(root).as_posix()})
        context = {**(context or {}), "artifactRefs": refs}
    stage_authority.run_stage_gate(EXECUTION_ID, stage, close_context=context, runner=runner or _runner())
    return stage_authority.close_stage(EXECUTION_ID, stage, close_context={"typedIssues": issues or []})


def test_open_rejects_jump_and_blocked_predecessor(work_package: Path) -> None:
    with pytest.raises(stage_authority.StageAuthorityError, match="illegal stage jump"):
        stage_authority.open_stage(EXECUTION_ID, "sources")
    issue = {"code": "DATA.TEST.BLOCKED", "message": "blocked", "recoveryStage": "0.plan"}
    _open_gate_close("0.plan", issues=[issue])
    with pytest.raises(stage_authority.StageAuthorityError, match="latest predecessor is blocked"):
        stage_authority.open_stage(EXECUTION_ID, "sources")


def test_open_create_once_replay_conflict_and_init_drift(work_package: Path) -> None:
    first = stage_authority.open_stage(EXECUTION_ID, "0.plan")
    before = first.read_bytes()
    assert stage_authority.open_stage(EXECUTION_ID, "0.plan") == first
    assert first.read_bytes() == before
    payload = json.loads(first.read_text())
    payload["workflowContract"]["digest"] = "sha256:" + "0" * 64
    first.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(stage_authority.StageAuthorityConflict):
        stage_authority.open_stage(EXECUTION_ID, "0.plan")


def test_artifact_missing_and_digest_drift_are_rejected(work_package: Path) -> None:
    stage_authority.open_stage(EXECUTION_ID, "0.plan")
    artifact = work_package / "0.plan/artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    gate = stage_authority.run_stage_gate(
        EXECUTION_ID, "0.plan",
        close_context={"artifactRefs": [{"scope": "execution", "ref": "0.plan/artifact.json"}]},
        runner=_runner(),
    )
    artifact.write_text('{"drift":true}\n', encoding="utf-8")
    with pytest.raises(stage_authority.StageAuthorityError, match="digest drift"):
        stage_authority.close_stage(EXECUTION_ID, "0.plan")
    assert gate.is_file()


def test_gate_exit_one_can_never_close_pass(work_package: Path) -> None:
    receipt = _open_gate_close("0.plan", runner=_runner(1))
    value = json.loads(receipt.read_text())
    assert value["verdict"] == "blocked"
    assert value["next"] == "0.plan"
    assert value["typedIssues"][0]["code"] == "DATA.STAGE.GATE_COMMAND_FAILED"


def test_regular_and_review_pass_have_fixed_successors(work_package: Path) -> None:
    plan = _open_gate_close("0.plan")
    assert json.loads(plan.read_text())["next"] == "sources"
    for stage in ("sources", "1.download", "2.quality", "3.compose", "4.draft"):
        # 4.draft actor evidence 单独由专门测试覆盖；此处只推进到它之前。
        if stage == "4.draft":
            break
        receipt = _open_gate_close(stage)
        expected = stage_authority.RECEIPT_STAGES[stage_authority._STAGE_INDEX[stage] + 1]
        assert json.loads(receipt.read_text())["next"] == expected


def test_public_close_context_cannot_input_next_actor_or_verdict(work_package: Path) -> None:
    stage_authority.open_stage(EXECUTION_ID, "0.plan")
    stage_authority.run_stage_gate(EXECUTION_ID, "0.plan", runner=_runner())
    with pytest.raises(stage_authority.StageAuthorityError, match="only accepts typedIssues"):
        stage_authority.close_stage(EXECUTION_ID, "0.plan", close_context={"next": "ship"})



def test_blocked_recovery_must_be_completed_or_current(work_package: Path) -> None:
    stage_authority.open_stage(EXECUTION_ID, "0.plan")
    stage_authority.run_stage_gate(EXECUTION_ID, "0.plan", runner=_runner())
    issue = {"code": "DATA.TEST.FUTURE", "message": "future jump", "recoveryStage": "ship"}
    with pytest.raises(stage_authority.StageAuthorityError, match="not completed/current"):
        stage_authority.close_stage(
            EXECUTION_ID, "0.plan", close_context={"typedIssues": [issue]}
        )


@pytest.mark.parametrize(
    ("carrier", "expected_command_ids"),
    [
        ("homepage", ["stage-artifacts", "homepage-media-decision"]),
        ("image", ["stage-artifacts", "homepage-media-decision"]),
        ("article", ["stage-artifacts"]),
        ("video", ["stage-artifacts"]),
    ],
)
def test_download_gate_registry_commands_are_carrier_specific(
    work_package: Path, carrier: str, expected_command_ids: list[str]
) -> None:
    request_path = work_package / "0.plan/request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["carrier"] = carrier
    request_path.write_text(json.dumps(request, ensure_ascii=False) + "\n", encoding="utf-8")

    command_ids = [
        command_id
        for command_id, _argv in stage_gate_registry.registry_argv(
            EXECUTION_ID, "1.download", {}
        )
    ]

    assert command_ids == expected_command_ids


def test_gate_context_cannot_input_command_or_exit_code(work_package: Path) -> None:
    stage_authority.open_stage(EXECUTION_ID, "0.plan")
    with pytest.raises(stage_authority.StageAuthorityError, match="unknown fields"):
        stage_authority.run_stage_gate(
            EXECUTION_ID, "0.plan",
            close_context={"command": "false", "exitCode": 0}, runner=_runner(),
        )


def test_workflow_input_drift_rejects_open_replay(work_package: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stage_authority.open_stage(EXECUTION_ID, "0.plan")
    monkeypatch.setattr(stage_authority, "operational_fingerprint", lambda **_kwargs: "sha256:" + "9" * 64)
    with pytest.raises(stage_authority.StageAuthorityConflict, match="conflict"):
        stage_authority.open_stage(EXECUTION_ID, "0.plan")


def test_historical_semantic_receipt_skips_only_current_workflow_equality(
    work_package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for stage in ("0.plan", "sources", "1.download", "2.quality", "3.compose"):
        _open_gate_close(stage)
    receipt_path = _open_gate_close("4.draft", actor_family="gpt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    authority = receipt["authority"]
    open_request = json.loads(
        (work_package / authority["openRequest"]["ref"]).read_text(encoding="utf-8")
    )
    result = json.loads(
        (work_package / authority["semanticResult"]["ref"]).read_text(encoding="utf-8")
    )
    request = json.loads((work_package / result["requestRef"]).read_text(encoding="utf-8"))
    assert open_request["workflowContract"] == request["workflowContract"] == result["workflowContract"]
    request_stable = {key: value for key, value in request.items() if key not in {"requestDigest", "preparedAt"}}
    result_stable = {key: value for key, value in result.items() if key not in {"resultDigest", "recordedAt"}}
    assert request["requestDigest"] == stage_semantic_recorder._sha256(
        stage_semantic_recorder._canonical_bytes(request_stable)
    )
    assert result["resultDigest"] == stage_semantic_recorder._sha256(
        stage_semantic_recorder._canonical_bytes(result_stable)
    )

    drift = "sha256:" + "9" * 64
    monkeypatch.setattr(stage_authority, "operational_fingerprint", lambda **_kwargs: drift)
    monkeypatch.setattr(stage_semantic_recorder, "operational_fingerprint", lambda **_kwargs: drift)

    with pytest.raises(stage_authority.StageAuthorityError, match="workflow contract digest drift"):
        stage_authority.validate_stage_receipt_authority(EXECUTION_ID, receipt_path)
    assert stage_authority.validate_stage_receipt_authority(
        EXECUTION_ID, receipt_path, verify_current_workflow=False
    )["verdict"] == "pass"

    request["workflowContract"]["digest"] = "sha256:" + "8" * 64
    (work_package / result["requestRef"]).write_text(
        json.dumps(request, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with pytest.raises(stage_authority.StageAuthorityError, match="semantic closure rejected"):
        stage_authority.validate_stage_receipt_authority(
            EXECUTION_ID, receipt_path, verify_current_workflow=False
        )


def test_gate_create_once_exact_replay_and_context_conflict(work_package: Path) -> None:
    stage_authority.open_stage(EXECUTION_ID, "0.plan")
    first = stage_authority.run_stage_gate(EXECUTION_ID, "0.plan", runner=_runner())
    before = first.read_bytes()
    assert stage_authority.run_stage_gate(EXECUTION_ID, "0.plan", runner=_runner(1)) == first
    assert first.read_bytes() == before
    receipt = stage_authority.close_stage(EXECUTION_ID, "0.plan")
    receipt_before = receipt.read_bytes()
    assert stage_authority.close_stage(EXECUTION_ID, "0.plan") == receipt
    assert receipt.read_bytes() == receipt_before
    assert stage_authority.open_stage(EXECUTION_ID, "0.plan").is_file()
    with pytest.raises(stage_authority.StageAuthorityConflict):
        stage_authority.run_stage_gate(
            EXECUTION_ID, "0.plan", close_context={"artifactRefs": [{"scope": "execution", "ref": "execution_manifest.json"}]}, runner=_runner(),
        )


def test_five_review_pass_has_fixed_publish_successor(work_package: Path) -> None:
    for stage in ("0.plan", "sources", "1.download", "2.quality", "3.compose"):
        _open_gate_close(stage)
    draft = _open_gate_close("4.draft", actor_family="gpt")
    assert json.loads(draft.read_text())["actor"]["modelFamily"] == "gpt"
    receipt = _open_gate_close("5.review", actor_family="claude")
    value = json.loads(receipt.read_text())
    assert value["verdict"] == "pass" and value["next"] == "publish"
    assert value["actor"] == {"host": "cursor", "modelFamily": "claude", "sessionId": "5.review-session", "invocation": {"provider": "cursor", "model": "claude", "runId": "5.review-run"}}


def test_review_same_family_rejected_different_family_passes(work_package: Path) -> None:
    for stage in ("0.plan", "sources", "1.download", "2.quality", "3.compose", "4.draft"):
        _open_gate_close(stage, actor_family="gpt")
    stage_authority.open_stage(EXECUTION_ID, "5.review")
    request = stage_semantic_recorder.prepare_stage_semantic_request(EXECUTION_ID, "5.review")
    request_value = json.loads(request.read_text())
    refs = _write_semantic_outputs("5.review", actor_family="gpt")
    same_family = {
        "schema": "quwoquan_data.stage_semantic_result_input",
        "requestRef": request.relative_to(work_package).as_posix(),
        "requestDigest": request_value["requestDigest"],
        "actor": {
            "host": "cursor", "modelFamily": "gpt", "sessionId": "5.review-session",
            "invocation": {"provider": "cursor", "model": "gpt", "runId": "5.review-run"},
        },
        "resultRefs": sorted(refs),
    }
    with pytest.raises(stage_semantic_recorder.StageSemanticError, match="must differ"):
        stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "5.review", same_family)
    refs = _write_semantic_outputs("5.review", actor_family="claude")
    different = {**same_family, "actor": {"host": "cursor", "modelFamily": "claude", "sessionId": "5.review-session", "invocation": {"provider": "cursor", "model": "claude", "runId": "5.review-run"}}, "resultRefs": sorted(refs)}
    assert stage_semantic_recorder.record_stage_semantic_result(EXECUTION_ID, "5.review", different).is_file()


def test_ship_release_binding_must_equal_predecessor_authority(
    work_package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_a = {"releaseId": "release-a", "releaseDigest": "sha256:" + "1" * 64}
    release_b = {"releaseId": "release-b", "releaseDigest": "sha256:" + "2" * 64}
    monkeypatch.setattr(
        stage_authority, "_validate_receipt_chain",
        lambda _execution_id: [(9, "release", Path("release.json"), {
            "verdict": "pass", "authority": {"releaseBinding": release_a},
        })],
    )
    with pytest.raises(stage_authority.StageAuthorityError, match="differs from release predecessor"):
        stage_authority._validate_ship_predecessor_release(EXECUTION_ID, release_b)
    stage_authority._validate_ship_predecessor_release(EXECUTION_ID, release_a)


def test_ship_requires_acceptance_and_rejects_cross_release(
    work_package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="requires environmentAcceptanceFactRef"):
        __import__("content.execution.stage_gate_registry", fromlist=["normalize_context"]).normalize_context(
            "ship", {
                "releaseId": "release-a", "releaseDigest": "sha256:" + "1" * 64,
                "environment": "gamma", "importRunId": "import-1", "verifyRunId": "verify-1",
                "readinessPhase": "research", "acceptanceProfile": "environment_promotion",
            },
        )

    fact_ref = "env/gamma/acceptance.json"
    fact_path = paths.OUTPUT_ROOT / fact_ref
    fact_path.parent.mkdir(parents=True, exist_ok=True)
    fact_path.write_text("{}\n", encoding="utf-8")
    digest = stage_authority._sha256(fact_path.read_bytes())
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.environment_acceptance_fact.load_environment_acceptance_fact",
        lambda *_args, **_kwargs: ({
            "releaseId": "release-b", "releaseDigest": "sha256:" + "1" * 64,
            "acceptanceProfile": "environment_promotion",
            "environment": "gamma", "target": "gamma-local",
            "importRunId": "import-1", "verifyRunId": "verify-1",
        }, digest),
    )
    context = {
        "releaseId": "release-a", "releaseDigest": "sha256:" + "1" * 64,
        "environment": "gamma", "importRunId": "import-1", "verifyRunId": "verify-1",
        "readinessPhase": "research", "target": "gamma-local",
        "acceptanceProfile": "environment_promotion",
        "requiredTargetProfiles": [{"platform": "ios", "deviceProfile": "promotable"}],
        "environmentAcceptanceFactRef": fact_ref,
        "environmentAcceptanceFactDigest": digest, "artifactRefs": [],
    }
    with pytest.raises(stage_authority.StageAuthorityError, match="identity drifted"):
        stage_authority._validate_acceptance(__import__("content.execution.stage_gate_registry", fromlist=["normalize_context"]).normalize_context("ship", context))


def test_ship_profiles_are_explicit_and_select_distinct_managed_commands() -> None:
    registry = __import__(
        "content.execution.stage_gate_registry", fromlist=["normalize_context", "registry_argv"]
    )
    base = {
        "releaseId": "release-a", "releaseDigest": "sha256:" + "1" * 64,
        "importRunId": "import-1", "verifyRunId": "verify-1",
        "readinessPhase": "research",
        "environmentAcceptanceFactRef": "env/alpha/fact.json",
        "environmentAcceptanceFactDigest": "sha256:" + "2" * 64,
    }
    with pytest.raises(ValueError, match="requires acceptanceProfile"):
        registry.normalize_context(
            "ship",
            {**base, "environment": "alpha", "target": "alpha-local", "requiredTargetProfiles": []},
        )
    with pytest.raises(ValueError, match="non-empty"):
        registry.normalize_context(
            "ship",
            {
                **base, "acceptanceProfile": "environment_promotion",
                "environment": "alpha", "target": "alpha-local", "requiredTargetProfiles": [],
            },
        )
    with pytest.raises(ValueError, match=r"requiredTargetProfiles=\[\]"):
        registry.normalize_context(
            "ship",
            {
                **base, "acceptanceProfile": "m1_api_consumer",
                "environment": "alpha", "target": "alpha-local",
                "requiredTargetProfiles": [{"platform": "ios", "deviceProfile": "promotable"}],
            },
        )
    with pytest.raises(ValueError, match="readinessPhase"):
        registry.normalize_context(
            "ship",
            {
                **base, "acceptanceProfile": "m1_api_consumer",
                "readinessPhase": "commercial", "environment": "alpha",
                "target": "alpha-local", "requiredTargetProfiles": [],
            },
        )
    m1 = registry.normalize_context(
        "ship",
        {
            **base, "acceptanceProfile": "m1_api_consumer",
            "environment": "alpha", "target": "alpha-local", "requiredTargetProfiles": [],
        },
    )
    m1_commands = registry.registry_argv(EXECUTION_ID, "ship", m1)
    assert [command_id for command_id, _argv in m1_commands] == [
        "ship-apply", "ship-verify", "release-lifecycle", "stackctl-health-content-consumer",
    ]
    assert m1_commands[-1][1][-5:] == (
        "health", "--target", "alpha-local", "--scope", "content-consumer",
    )

    promotion = registry.normalize_context(
        "ship",
        {
            **base, "acceptanceProfile": "environment_promotion",
            "environment": "gamma", "target": "gamma-local",
            "requiredTargetProfiles": [{"platform": "ios", "deviceProfile": "promotable"}],
        },
    )
    promotion_commands = registry.registry_argv(EXECUTION_ID, "ship", promotion)
    assert promotion_commands[-1][0] == "stackctl-verify"
    assert "release" in promotion_commands[-1][1]


def test_ship_acceptance_profile_must_match_exact_fact(
    work_package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fact_ref = "env/alpha/acceptance.json"
    fact_path = paths.OUTPUT_ROOT / fact_ref
    fact_path.parent.mkdir(parents=True, exist_ok=True)
    fact_path.write_text("{}\n", encoding="utf-8")
    digest = stage_authority._sha256(fact_path.read_bytes())
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.environment_acceptance_fact.load_environment_acceptance_fact",
        lambda *_args, **_kwargs: ({
            "acceptanceProfile": "environment_promotion",
            "releaseId": "release-a", "releaseDigest": "sha256:" + "1" * 64,
            "environment": "alpha", "target": "alpha-local",
            "importRunId": "import-1", "verifyRunId": "verify-1",
        }, digest),
    )
    context = {
        "releaseId": "release-a", "releaseDigest": "sha256:" + "1" * 64,
        "acceptanceProfile": "m1_api_consumer",
        "environment": "alpha", "target": "alpha-local",
        "importRunId": "import-1", "verifyRunId": "verify-1",
        "readinessPhase": "research", "requiredTargetProfiles": [],
        "environmentAcceptanceFactRef": fact_ref,
        "environmentAcceptanceFactDigest": digest, "artifactRefs": [],
    }
    with pytest.raises(stage_authority.StageAuthorityError, match="identity drifted"):
        stage_authority._validate_acceptance(
            __import__("content.execution.stage_gate_registry", fromlist=["normalize_context"])
            .normalize_context("ship", context)
        )


def test_ship_acceptance_validator_failure_is_protocol_rejection(
    work_package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quwoquan_ops.cli.lib.environment_acceptance_fact import EnvironmentAcceptanceFactError

    def reject(*_args, **_kwargs):
        raise EnvironmentAcceptanceFactError("OPS.TEST", "required raw UAT missing")
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.environment_acceptance_fact.load_environment_acceptance_fact", reject
    )
    context = {
        "releaseId": "release-a", "releaseDigest": "sha256:" + "1" * 64,
        "environment": "gamma", "importRunId": "import-1", "verifyRunId": "verify-1",
        "readinessPhase": "research", "target": "gamma-local",
        "acceptanceProfile": "environment_promotion",
        "requiredTargetProfiles": [{"platform": "ios", "deviceProfile": "promotable"}],
        "environmentAcceptanceFactRef": "env/gamma/fact.json",
        "environmentAcceptanceFactDigest": "sha256:" + "2" * 64, "artifactRefs": [],
    }
    with pytest.raises(stage_authority.StageAuthorityError, match="required raw UAT missing"):
        stage_authority._validate_acceptance(__import__("content.execution.stage_gate_registry", fromlist=["normalize_context"]).normalize_context("ship", context))


def test_ship_pass_is_only_succeeded_writer(work_package: Path) -> None:
    from content.execution.stage_receipt import receipt_state_status
    from core.control_types import ExecutionStateStatus

    regular = {"stage": "5.review", "verdict": "pass"}
    blocked_ship = {"stage": "ship", "verdict": "blocked"}
    passed_ship = {"stage": "ship", "verdict": "pass"}
    assert receipt_state_status(regular) is ExecutionStateStatus.RUNNING
    assert receipt_state_status(blocked_ship) is ExecutionStateStatus.MANUAL_REQUIRED
    assert receipt_state_status(passed_ship) is ExecutionStateStatus.SUCCEEDED


def test_deep_validator_rejects_deleted_gate_and_artifact_drift(work_package: Path) -> None:
    receipt = _open_gate_close("0.plan")
    assert stage_authority.validate_stage_receipt_authority(EXECUTION_ID, receipt)["verdict"] == "pass"
    gate_path = work_package / "_shared/stage-authority/001-0.plan/gate.json"
    gate_path.unlink()
    with pytest.raises(stage_authority.StageAuthorityError, match="binding|authority|readable"):
        stage_authority.validate_stage_receipt_authority(EXECUTION_ID, receipt)

    # New isolated work package is supplied by a separate test invocation; exact artifact drift
    # remains covered by test_artifact_missing_and_digest_drift_are_rejected.


def test_current_receipt_writer_requires_private_admission() -> None:
    from content.execution import stage_receipt

    assert not hasattr(stage_receipt, "write_receipt_create_once")
    with pytest.raises(PermissionError, match="admission denied"):
        stage_receipt._write_current_receipt_create_once(
            EXECUTION_ID, {"executionId": EXECUTION_ID, "sequence": 1, "stage": "0.plan"},
            writer_token=object(),
        )
