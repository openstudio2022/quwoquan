# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t2
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from content.execution import stage_receipt, stage_receipt_cli, task_init
from core import paths

EXECUTION_ID = "20260903--travel-article-minimal-kernel--china--pilot-001"
DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
CLI = DATA_ROOT / "scripts/cli.py"


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _inputs(output: Path) -> tuple[Path, Path]:
    demand = {
        "schema": "quwoquan_data.carrier_demand",
        "status": "confirmed",
        "executionId": EXECUTION_ID,
        "carrier": "article",
        "familyRef": "content/travel/article/article",
        "quota": 1,
        "retryOf": None,
    }
    bindings = {
        "schema": "quwoquan_data.immutable_candidate_bindings",
        "executionId": EXECUTION_ID,
        "carrier": "article",
        "entityCatalogDigest": "sha256:" + "2" * 64,
        "candidateCount": 1,
        "targets": [{
            "name": "西湖", "entityType": "地点/景区", "publishAngle": "攻略",
            "publishTitle": "西湖一日游", "publishSeq": 1,
        }],
    }
    return (
        _write(output / "inputs/demand.json", demand),
        _write(output / "inputs/bindings.json", bindings),
    )


@pytest.fixture
def kernel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    for module in (paths, task_init.paths, stage_receipt.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    demand, bindings = _inputs(output)
    task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)
    return output, tasks / EXECUTION_ID


def _open_input(tmp_path: Path, refs: list[dict[str, str]]) -> Path:
    return _write(tmp_path / "open.json", {"inputRefs": refs})


def test_producer_receipt_sequence_ends_at_release_and_rejects_ship(
    kernel: tuple[Path, Path], tmp_path: Path
) -> None:
    assert stage_receipt.RECEIPT_STAGES == (
        "0.plan",
        "sources",
        "1.download",
        "2.quality",
        "3.compose",
        "4.draft",
        "5.review",
        "publish",
        "release",
    )
    with pytest.raises(stage_receipt.StageProtocolError, match="未知 stage"):
        stage_receipt.open_stage(
            EXECUTION_ID, "ship", _open_input(tmp_path / "ship", [])
        )


def _close_input(
    tmp_path: Path,
    *,
    verdict: str = "pass",
    issues: list[dict] | None = None,
    result_refs: list[dict[str, str]] | None = None,
    evidence_ref: dict[str, str] | None = None,
    evidence_digest: str | None = None,
    facts: list[dict] | None = None,
    actor: dict | None = None,
) -> Path:
    verifier_facts = facts
    if verifier_facts is None:
        verifier_facts = [{
            "name": "fixture",
            "status": "passed",
            "command": "pytest fixture",
            "exitCode": 0,
            "observedAt": "2026-09-03T00:00:00Z",
            **({"evidenceRef": evidence_ref, "evidenceDigest": evidence_digest} if evidence_ref is not None else {}),
        }]
    return _write(tmp_path / "close.json", {
        "actor": actor or {"host": "cursor", "modelFamily": "gpt", "sessionId": "s-1", "invocation": None},
        "verdict": verdict,
        "typedIssues": issues or [],
        "resultRefs": result_refs or [],
        "verifierFacts": verifier_facts,
    })




def _pass_close(tmp_path: Path, root: Path, stage: str) -> Path:
    result = _write(root / stage / "result.json", {"stage": stage})
    ref = {"scope": "execution", "ref": result.relative_to(root).as_posix()}
    digest = "sha256:" + hashlib.sha256(result.read_bytes()).hexdigest()
    return _close_input(
        tmp_path / stage,
        result_refs=[ref],
        evidence_ref=ref,
        evidence_digest=digest,
    )


def _open_and_pass(
    root: Path,
    tmp_path: Path,
    stage: str,
    refs: list[dict[str, str]] | None = None,
) -> Path:
    stage_receipt.open_stage(EXECUTION_ID, stage, _open_input(tmp_path / stage, refs or []))
    return stage_receipt.close_stage(
        EXECUTION_ID, stage, _pass_close(tmp_path, root, stage)
    )


def test_init_has_only_new_bindings_and_replays_same_bytes(kernel: tuple[Path, Path]) -> None:
    output, root = kernel
    demand, bindings = _inputs(output)
    replay = task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)
    assert replay["status"] == "replayed"
    files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    assert files == ["0.plan/request.json", "0.plan/target_set.json", "execution_manifest.json"]
    joined = " ".join(path.read_text(encoding="utf-8") for path in root.rglob("*.json"))
    retired = ("workRequest", "sourceDigest", "executionBundle", "operationalFingerprint")
    for name in retired:
        assert name not in joined
    init_source = Path(task_init.__file__).read_text(encoding="utf-8")
    for name in (*retired, "WorkRequest", "task_init_projection", "materialize"):
        assert name not in init_source
    request = json.loads((root / "0.plan/request.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "execution_manifest.json").read_text(encoding="utf-8"))
    assert request["carrierDemand"]["digest"].startswith("sha256:")
    assert manifest["initInputs"]["immutableCandidateBindings"]["digest"].startswith("sha256:")


def test_homepage_target_ref_matches_execution_object_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    execution_id = "20260903--travel-homepage-minimal-kernel--china--pilot-001"
    for module in (paths, task_init.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    demand, bindings = _inputs(output)
    demand_doc = json.loads(demand.read_text(encoding="utf-8"))
    demand_doc.update(
        {
            "executionId": execution_id,
            "carrier": "homepage",
            "familyRef": "content/travel/homepage/homepage",
        }
    )
    bindings_doc = json.loads(bindings.read_text(encoding="utf-8"))
    bindings_doc.update({"executionId": execution_id, "carrier": "homepage"})
    bindings_doc["targets"][0].pop("publishAngle")
    bindings_doc["targets"][0].pop("publishTitle")
    bindings_doc["targets"][0].pop("publishSeq")
    _write(demand, demand_doc)
    _write(bindings, bindings_doc)

    task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)
    root = tasks / execution_id
    target_set = json.loads((root / "0.plan/target_set.json").read_text(encoding="utf-8"))
    assert target_set["targetRefs"] == ["entities/地点/景区/西湖"]
    assert root / target_set["targetRefs"][0] == root / "entities/地点/景区/西湖"


def test_init_rejects_non_homepage_target_without_publish_seq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    for module in (paths, task_init.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    demand, bindings = _inputs(output)
    bindings_doc = json.loads(bindings.read_text(encoding="utf-8"))
    bindings_doc["targets"][0].pop("publishSeq")
    _write(bindings, bindings_doc)

    with pytest.raises((task_init.TaskInitError, ValueError), match="publishSeq|发布坐标"):
        task_init.initialize_task(
            carrier_demand_path=demand,
            candidate_bindings_path=bindings,
        )


def test_open_freezes_exact_refs_and_enforces_order(kernel: tuple[Path, Path], tmp_path: Path) -> None:
    _output, root = kernel
    open_input = _open_input(tmp_path, [{"scope": "execution", "ref": "execution_manifest.json"}])
    opened = stage_receipt.open_stage(EXECUTION_ID, "0.plan", open_input)
    first = opened.read_bytes()
    assert stage_receipt.open_stage(EXECUTION_ID, "0.plan", open_input) == opened
    assert opened.read_bytes() == first
    frozen = json.loads(first)
    expected = "sha256:" + hashlib.sha256((root / "execution_manifest.json").read_bytes()).hexdigest()
    assert frozen["inputRefs"][0]["digest"] == expected
    _write(open_input, {"inputRefs": [{"scope": "execution", "ref": "0.plan/request.json"}]})
    with pytest.raises(stage_receipt.StageConflict):
        stage_receipt.open_stage(EXECUTION_ID, "0.plan", open_input)
    with pytest.raises(stage_receipt.StageProtocolError, match="连续前缀"):
        stage_receipt.open_stage(EXECUTION_ID, "sources", open_input)


def test_close_pass_rechecks_open_bytes_and_writes_no_state(kernel: tuple[Path, Path], tmp_path: Path) -> None:
    _output, root = kernel
    open_input = _open_input(tmp_path, [{"scope": "execution", "ref": "0.plan/request.json"}])
    stage_receipt.open_stage(EXECUTION_ID, "0.plan", open_input)
    result = _write(root / "0.plan/result.json", {"ok": True})
    result_ref = {"scope": "execution", "ref": result.relative_to(root).as_posix()}
    evidence_digest = "sha256:" + hashlib.sha256(result.read_bytes()).hexdigest()
    close_input = _close_input(
        tmp_path,
        result_refs=[result_ref],
        evidence_ref=result_ref,
        evidence_digest=evidence_digest,
    )
    receipt = stage_receipt.close_stage(EXECUTION_ID, "0.plan", close_input)
    value = json.loads(receipt.read_text(encoding="utf-8"))
    assert value["verdict"] == "pass" and value["resultRefs"][0]["digest"].startswith("sha256:")
    assert stage_receipt.close_stage(EXECUTION_ID, "0.plan", close_input) == receipt
    drifted_close = json.loads(close_input.read_text(encoding="utf-8"))
    drifted_close["actor"]["sessionId"] = "s-2"
    _write(close_input, drifted_close)
    with pytest.raises(stage_receipt.StageConflict):
        stage_receipt.close_stage(EXECUTION_ID, "0.plan", close_input)
    assert "next" not in value and "authority" not in value and "machineGate" not in value
    assert not (root / "_shared/execution_state.json").exists()
    assert not (root / "_shared/journal").exists()
    sources_open = _open_input(tmp_path / "sources", [{"scope": "execution", "ref": "0.plan/request.json"}])
    stage_receipt.open_stage(EXECUTION_ID, "sources", sources_open)
    request = json.loads((root / "0.plan/request.json").read_text(encoding="utf-8"))
    request["quota"] = 2
    _write(root / "0.plan/request.json", request)
    with pytest.raises(stage_receipt.StageProtocolError, match="exact bytes"):
        stage_receipt.close_stage(EXECUTION_ID, "sources", close_input)


def test_blocked_close_stops_following_stages(kernel: tuple[Path, Path], tmp_path: Path) -> None:
    _output, root = kernel
    open_input = _open_input(tmp_path, [])
    stage_receipt.open_stage(EXECUTION_ID, "0.plan", open_input)
    issue = {"code": "DATA.TEST", "message": "等待人工"}
    close_input = _close_input(
        tmp_path,
        verdict="blocked",
        issues=[issue],
        facts=[{
            "name": "fixture",
            "status": "failed",
            "command": "pytest fixture",
            "exitCode": 1,
            "observedAt": "2026-09-03T00:00:00Z",
        }],
    )
    receipt = stage_receipt.close_stage(EXECUTION_ID, "0.plan", close_input)
    assert json.loads(receipt.read_text(encoding="utf-8"))["typedIssues"] == [issue]
    with pytest.raises(stage_receipt.StageProtocolError, match="blocked"):
        stage_receipt.open_stage(EXECUTION_ID, "sources", open_input)
    assert not (root / "_shared/execution_state.json").exists()


def test_task_cli_exposes_only_kernel_and_atomic_media_commands(tmp_path: Path) -> None:
    environment = {**os.environ, "QWQ_OUTPUT_ROOT": str(tmp_path / "output"), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", str(CLI), "task", "--help"], capture_output=True, text=True, env=environment, cwd=DATA_ROOT.parent)
    assert result.returncode == 0, result.stderr
    for current in ("init", "stage-open", "stage-close", "acquire-images", "acquire-videos"):
        assert current in result.stdout
    for retired in ("compile-intent", "project-init-inputs", "materialize-sources", "stage-gate", "semantic-prepare", "lane-claim", "fleet-status", "supersede-execution", "terminal-evidence-precheck"):
        assert retired not in result.stdout


def test_stage_cli_maps_protocol_and_conflict_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Args:
        execution_id = EXECUTION_ID
        stage = "0.plan"
        input = str(tmp_path / "input.json")

    def protocol(*_args: object) -> Path:
        raise stage_receipt.StageProtocolError("协议错误")

    monkeypatch.setattr(stage_receipt_cli, "open_stage", protocol)
    with pytest.raises(SystemExit) as protocol_exit:
        stage_receipt_cli._handle_stage_open(Args())
    assert protocol_exit.value.code == 2
    assert "协议错误" in capsys.readouterr().err

    def conflict(*_args: object) -> Path:
        raise stage_receipt.StageConflict("字节冲突")

    monkeypatch.setattr(stage_receipt_cli, "close_stage", conflict)
    with pytest.raises(SystemExit) as conflict_exit:
        stage_receipt_cli._handle_stage_close(Args())
    assert conflict_exit.value.code == 3
    assert "字节冲突" in capsys.readouterr().err


def test_nofollow_rejects_execution_root_and_ref_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    for module in (paths, task_init.paths, stage_receipt.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    demand, bindings = _inputs(output)
    task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)
    root = tasks / EXECUTION_ID
    moved = tasks / "real-execution"
    root.rename(moved)
    root.symlink_to(moved, target_is_directory=True)
    with pytest.raises(stage_receipt.StageProtocolError, match="symlink|不可信"):
        stage_receipt.open_stage(EXECUTION_ID, "0.plan", _open_input(tmp_path, []))

    root.unlink()
    moved.rename(root)
    actual = _write(root / "evidence/actual.json", {"ok": True})
    (root / "evidence/leaf.json").symlink_to(actual)
    with pytest.raises(stage_receipt.StageProtocolError, match="不可读取"):
        stage_receipt.open_stage(
            EXECUTION_ID,
            "0.plan",
            _open_input(tmp_path / "leaf", [{"scope": "execution", "ref": "evidence/leaf.json"}]),
        )
    (root / "linked-parent").symlink_to(root / "evidence", target_is_directory=True)
    with pytest.raises(stage_receipt.StageProtocolError, match="父目录"):
        stage_receipt.open_stage(
            EXECUTION_ID,
            "0.plan",
            _open_input(tmp_path / "parent", [{"scope": "execution", "ref": "linked-parent/actual.json"}]),
        )


def test_pass_requires_exit_evidence_and_rfc3339_timezone(
    kernel: tuple[Path, Path], tmp_path: Path
) -> None:
    _output, root = kernel
    stage_receipt.open_stage(EXECUTION_ID, "0.plan", _open_input(tmp_path, []))
    result = _write(root / "0.plan/result.json", {"ok": True})
    result_ref = {"scope": "execution", "ref": result.relative_to(root).as_posix()}
    base = {
        "name": "fixture",
        "status": "passed",
        "command": "pytest fixture",
        "observedAt": "2026-09-03T00:00:00Z",
    }
    for bad_fact in (
        base,
        {**base, "exitCode": 0},
        {**base, "exitCode": 1, "evidenceRef": result_ref, "evidenceDigest": "sha256:" + "0" * 64},
    ):
        with pytest.raises(stage_receipt.StageProtocolError):
            stage_receipt.close_stage(
                EXECUTION_ID,
                "0.plan",
                _close_input(tmp_path / f"bad-{bad_fact.get('exitCode', 'missing')}", result_refs=[result_ref], facts=[bad_fact]),
            )
    digest = "sha256:" + hashlib.sha256(result.read_bytes()).hexdigest()
    malformed = {**base, "exitCode": 0, "evidenceRef": result_ref, "evidenceDigest": digest, "observedAt": "2026-09-03 00:00:00"}
    with pytest.raises(stage_receipt.StageProtocolError, match="RFC3339"):
        stage_receipt.close_stage(
            EXECUTION_ID,
            "0.plan",
            _close_input(tmp_path / "bad-time", result_refs=[result_ref], facts=[malformed]),
        )


def test_progress_rejects_missing_future_and_illegal_artifacts(
    kernel: tuple[Path, Path], tmp_path: Path
) -> None:
    _output, root = kernel
    receipt_dir = root / "_shared/receipts"
    receipt_dir.mkdir(parents=True)
    _write(receipt_dir / "002-sources.json", {})
    with pytest.raises(stage_receipt.StageProtocolError, match="extra"):
        stage_receipt.open_stage(EXECUTION_ID, "0.plan", _open_input(tmp_path, []))
    (receipt_dir / "002-sources.json").unlink()
    stage_receipt.open_stage(EXECUTION_ID, "0.plan", _open_input(tmp_path / "plan", []))
    receipt_dir.joinpath("001-0.plan.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(stage_receipt.StageProtocolError):
        stage_receipt.open_stage(EXECUTION_ID, "1.download", _open_input(tmp_path / "missing", []))
    (receipt_dir / "001-0.plan.json").unlink()
    (root / "_shared/stage-open/001-0.plan.json").unlink()
    open_dir = root / "_shared/stage-open"
    open_dir.mkdir(parents=True, exist_ok=True)
    _write(open_dir / "002-sources.json", {})
    with pytest.raises(stage_receipt.StageProtocolError, match="extra"):
        stage_receipt.open_stage(EXECUTION_ID, "0.plan", _open_input(tmp_path / "future", []))
    (open_dir / "002-sources.json").unlink()
    _write(receipt_dir / "junk.json", {})
    with pytest.raises(stage_receipt.StageProtocolError, match="非法命名"):
        stage_receipt.open_stage(EXECUTION_ID, "0.plan", _open_input(tmp_path / "junk", []))


def test_closed_reopen_and_blocked_execution_are_terminal(
    kernel: tuple[Path, Path], tmp_path: Path
) -> None:
    _output, root = kernel
    open_input = _open_input(tmp_path, [])
    stage_receipt.open_stage(EXECUTION_ID, "0.plan", open_input)
    stage_receipt.close_stage(EXECUTION_ID, "0.plan", _pass_close(tmp_path, root, "0.plan"))
    with pytest.raises(stage_receipt.StageProtocolError, match="已关闭"):
        stage_receipt.open_stage(EXECUTION_ID, "0.plan", open_input)
    stage_receipt.open_stage(EXECUTION_ID, "sources", _open_input(tmp_path / "sources", []))
    issue = {"code": "DATA.TEST", "message": "stop"}
    blocked = _close_input(
        tmp_path / "blocked",
        verdict="blocked",
        issues=[issue],
        facts=[{"name":"fixture","status":"failed","command":"false","exitCode":1,"observedAt":"2026-09-03T00:00:00Z"}],
    )
    stage_receipt.close_stage(EXECUTION_ID, "sources", blocked)
    with pytest.raises(stage_receipt.StageProtocolError, match="blocked"):
        stage_receipt.close_stage(EXECUTION_ID, "sources", blocked)
    with pytest.raises(stage_receipt.StageProtocolError, match="blocked"):
        stage_receipt.open_stage(EXECUTION_ID, "1.download", _open_input(tmp_path / "download", []))
    with pytest.raises(stage_receipt.StageProtocolError, match="blocked"):
        stage_receipt.open_stage(EXECUTION_ID, "0.plan", open_input)
    with pytest.raises(stage_receipt.StageProtocolError, match="blocked"):
        stage_receipt.close_stage(EXECUTION_ID, "0.plan", _pass_close(tmp_path / "again", root, "0.plan"))


def test_same_open_document_rechecks_ref_bytes(
    kernel: tuple[Path, Path], tmp_path: Path
) -> None:
    _output, root = kernel
    ref_path = _write(root / "evidence/input.json", {"v": 1})
    input_doc = _open_input(tmp_path, [{"scope":"execution","ref":ref_path.relative_to(root).as_posix()}])
    stage_receipt.open_stage(EXECUTION_ID, "0.plan", input_doc)
    _write(ref_path, {"v": 2})
    with pytest.raises(stage_receipt.StageConflict, match="引用字节冲突"):
        stage_receipt.open_stage(EXECUTION_ID, "0.plan", input_doc)


def test_receipts_bind_direct_predecessor_hash_chain(
    kernel: tuple[Path, Path], tmp_path: Path
) -> None:
    _output, root = kernel
    first_path = _open_and_pass(root, tmp_path, "0.plan")
    first = json.loads(first_path.read_text(encoding="utf-8"))
    assert first["predecessor"] is None
    second_path = _open_and_pass(root, tmp_path, "sources")
    second = json.loads(second_path.read_text(encoding="utf-8"))
    assert second["predecessor"] == {
        "scope":"execution",
        "ref":"_shared/receipts/001-0.plan.json",
        "digest":"sha256:" + hashlib.sha256(first_path.read_bytes()).hexdigest(),
    }
    first["actor"]["sessionId"] = "tampered"
    first_path.write_text(
        json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(stage_receipt.StageProtocolError, match="predecessor 链漂移"):
        stage_receipt.open_stage(EXECUTION_ID, "1.download", _open_input(tmp_path / "download", []))


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t10
def test_review_close_allows_same_family_but_rejects_author_session(
    kernel: tuple[Path, Path], tmp_path: Path
) -> None:
    _output, root = kernel
    for stage in ("0.plan", "sources", "1.download", "2.quality", "3.compose"):
        _open_and_pass(root, tmp_path, stage)

    author_actor = {
        "host": "cursor",
        "modelFamily": "gpt",
        "sessionId": "author-session",
        "invocation": {"provider": "host", "model": "gpt-5.6", "runId": "author-run"},
    }
    stage_receipt.open_stage(EXECUTION_ID, "4.draft", _open_input(tmp_path / "draft", []))
    draft_result = _write(root / "4.draft/result.json", {"stage": "4.draft"})
    draft_ref = {"scope": "execution", "ref": "4.draft/result.json"}
    draft_digest = "sha256:" + hashlib.sha256(draft_result.read_bytes()).hexdigest()
    stage_receipt.close_stage(
        EXECUTION_ID,
        "4.draft",
        _close_input(
            tmp_path / "draft-close",
            result_refs=[draft_ref],
            evidence_ref=draft_ref,
            evidence_digest=draft_digest,
            actor=author_actor,
        ),
    )

    reviewer_actor = {
        "host": "cursor",
        "modelFamily": "gpt",
        "sessionId": "review-session",
        "invocation": {"provider": "host", "model": "gpt-5.6", "runId": "review-run"},
    }
    reviewer_result = _write(root / "posts/article/攻略/西湖一日游/1/5.review/reviewer_result.json", {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "executionBinding": "frozen",
        "objectRef": "posts/article/攻略/西湖一日游/1",
        "actor": reviewer_actor,
        "verdict": "passed",
        "issues": [],
        "resultHash": "sha256:" + "a" * 64,
    })
    reviewer_ref = {"scope": "execution", "ref": reviewer_result.relative_to(root).as_posix()}
    reviewer_digest = "sha256:" + hashlib.sha256(reviewer_result.read_bytes()).hexdigest()
    stage_receipt.open_stage(EXECUTION_ID, "5.review", _open_input(tmp_path / "review", []))
    stage_receipt.close_stage(
        EXECUTION_ID,
        "5.review",
        _close_input(
            tmp_path / "review-close",
            result_refs=[reviewer_ref],
            evidence_ref=reviewer_ref,
            evidence_digest=reviewer_digest,
            actor=reviewer_actor,
        ),
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t11
def test_review_close_rejects_author_self_review(
    kernel: tuple[Path, Path], tmp_path: Path
) -> None:
    _output, root = kernel
    for stage in ("0.plan", "sources", "1.download", "2.quality", "3.compose"):
        _open_and_pass(root, tmp_path, stage)
    author_actor = {
        "host": "cursor",
        "modelFamily": "gpt",
        "sessionId": "same-session",
        "invocation": {"provider": "host", "model": "gpt-5.6", "runId": "author-run"},
    }
    stage_receipt.open_stage(EXECUTION_ID, "4.draft", _open_input(tmp_path / "draft", []))
    draft_result = _write(root / "4.draft/result.json", {"stage": "4.draft"})
    draft_ref = {"scope": "execution", "ref": "4.draft/result.json"}
    draft_digest = "sha256:" + hashlib.sha256(draft_result.read_bytes()).hexdigest()
    stage_receipt.close_stage(
        EXECUTION_ID,
        "4.draft",
        _close_input(
            tmp_path / "draft-close",
            result_refs=[draft_ref],
            evidence_ref=draft_ref,
            evidence_digest=draft_digest,
            actor=author_actor,
        ),
    )
    self_actor = {**author_actor, "invocation": {**author_actor["invocation"], "runId": "review-run"}}
    reviewer_result = _write(root / "posts/article/攻略/西湖一日游/1/5.review/reviewer_result.json", {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "executionBinding": "frozen",
        "objectRef": "posts/article/攻略/西湖一日游/1",
        "actor": self_actor,
        "verdict": "passed",
        "issues": [],
        "resultHash": "sha256:" + "a" * 64,
    })
    reviewer_ref = {"scope": "execution", "ref": reviewer_result.relative_to(root).as_posix()}
    reviewer_digest = "sha256:" + hashlib.sha256(reviewer_result.read_bytes()).hexdigest()
    stage_receipt.open_stage(EXECUTION_ID, "5.review", _open_input(tmp_path / "review", []))
    with pytest.raises(stage_receipt.StageProtocolError, match="同一 host/sessionId"):
        stage_receipt.close_stage(
            EXECUTION_ID,
            "5.review",
            _close_input(
                tmp_path / "review-close",
                result_refs=[reviewer_ref],
                evidence_ref=reviewer_ref,
                evidence_digest=reviewer_digest,
                actor=self_actor,
            ),
        )


def test_init_reads_each_source_once_and_embeds_canonical_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    for module in (paths, task_init.paths, stage_receipt.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    demand, bindings = _inputs(output)
    real_read = task_init._read_regular_at
    counts = {"carrier_demand": 0, "immutable_candidate_bindings": 0}

    def counted(root_fd: int, ref: str, *, label: str) -> bytes:
        if label in counts:
            counts[label] += 1
        return real_read(root_fd, ref, label=label)

    monkeypatch.setattr(task_init, "_read_regular_at", counted)
    task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)
    assert counts == {"carrier_demand": 1, "immutable_candidate_bindings": 1}
    root = tasks / EXECUTION_ID
    request = json.loads((root / "0.plan/request.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "execution_manifest.json").read_text(encoding="utf-8"))
    assert request["submittedInputs"] == manifest["submittedInputs"]
    assert request["submittedInputs"]["carrierDemand"]["quota"] == 1



def _canonical_write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


def _blocked_retry_execution(output: Path, execution_id: str, *, verdict: str = "blocked") -> Path:
    root = output / "data/tasks" / execution_id
    manifest = {
        "schema": "quwoquan_data.content_execution_manifest",
        "executionId": execution_id,
        "carrier": "article",
        "familyRef": {"ref": "content/travel/article/article", "digest": "sha256:" + "1" * 64},
        "initInputs": {
            "carrierDemand": {"scope": "output", "ref": "inputs/previous-demand.json", "digest": "sha256:" + "2" * 64},
            "immutableCandidateBindings": {"scope": "output", "ref": "inputs/previous-bindings.json", "digest": "sha256:" + "3" * 64},
        },
        "submittedInputs": {
            "carrierDemand": {
                "schema": "quwoquan_data.carrier_demand", "status": "confirmed",
                "executionId": execution_id, "carrier": "article",
                "familyRef": "content/travel/article/article", "quota": 1, "retryOf": None,
            },
            "immutableCandidateBindings": {
                "schema": "quwoquan_data.immutable_candidate_bindings", "executionId": execution_id,
                "carrier": "article", "entityCatalogDigest": "sha256:" + "4" * 64,
                "candidateCount": 1,
                "targets": [{"name": "西湖", "entityType": "地点/景区", "publishAngle": "攻略", "publishTitle": "西湖一日游", "publishSeq": 1}],
            },
        },
        "request": {"ref": "0.plan/request.json", "digest": "sha256:" + "5" * 64},
        "targetSet": {"ref": "0.plan/target_set.json", "digest": "sha256:" + "6" * 64},
        "retryOf": None,
    }
    _canonical_write(root / "execution_manifest.json", manifest)
    submitted_input = {"inputRefs": []}
    open_doc = {
        "schema": "quwoquan_data.stage_open_request", "executionId": execution_id,
        "stage": "0.plan", "sequence": 1, "predecessor": None,
        "input": {"digest": "sha256:" + hashlib.sha256((json.dumps(submitted_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()},
        "submittedInput": submitted_input, "inputRefs": [],
    }
    open_path = _canonical_write(root / "_shared/stage-open/001-0.plan.json", open_doc)
    result_refs: list[dict[str, str]] = []
    frozen_results: list[dict[str, str]] = []
    facts = [{"name": "fixture", "status": "failed", "command": "false", "exitCode": 1, "observedAt": "2026-09-02T00:00:00Z"}]
    if verdict == "pass":
        result = _canonical_write(root / "0.plan/result.json", {"ok": True})
        result_refs = [{"scope": "execution", "ref": "0.plan/result.json"}]
        frozen_results = [{**result_refs[0], "digest": "sha256:" + hashlib.sha256(result.read_bytes()).hexdigest()}]
        facts = [{"name": "fixture", "status": "passed", "command": "true", "exitCode": 0, "observedAt": "2026-09-02T00:00:00Z", "evidenceRef": result_refs[0], "evidenceDigest": "sha256:" + hashlib.sha256(result.read_bytes()).hexdigest()}]
    typed_issues = [] if verdict == "pass" else [{"code": "DATA.RETRY", "message": "blocked"}]
    submitted_close = {
        "actor": {"host": "cursor", "modelFamily": "gpt", "sessionId": "previous", "invocation": None},
        "verdict": verdict, "typedIssues": typed_issues,
        "resultRefs": result_refs, "verifierFacts": facts,
    }
    receipt = {
        "schema": "quwoquan_data.stage_receipt", "executionId": execution_id,
        "stage": "0.plan", "sequence": 1, "predecessor": None,
        "openRequest": {"scope": "execution", "ref": "_shared/stage-open/001-0.plan.json", "digest": "sha256:" + hashlib.sha256(open_path.read_bytes()).hexdigest()},
        "closeInput": {"digest": "sha256:" + hashlib.sha256((json.dumps(submitted_close, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()},
        "submittedClose": submitted_close,
        "actor": submitted_close["actor"], "verdict": verdict,
        "typedIssues": typed_issues, "inputRefs": [],
        "resultRefs": frozen_results, "verifierFacts": facts,
    }
    return _canonical_write(root / "_shared/receipts/001-0.plan.json", receipt)


def test_init_retry_accepts_cross_day_blocked_execution_and_freezes_terminal_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    for module in (paths, task_init.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    previous_id = "20260902--travel-article-previous--other-scope--scale-999"
    terminal = _blocked_retry_execution(output, previous_id)
    demand, bindings = _inputs(output)
    demand_doc = json.loads(demand.read_text(encoding="utf-8"))
    demand_doc["retryOf"] = previous_id
    _write(demand, demand_doc)

    task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)
    request = json.loads((tasks / EXECUTION_ID / "0.plan/request.json").read_text(encoding="utf-8"))
    manifest = json.loads((tasks / EXECUTION_ID / "execution_manifest.json").read_text(encoding="utf-8"))
    expected = {
        "executionId": previous_id,
        "terminalReceipt": {
            "scope": "output",
            "ref": f"data/tasks/{previous_id}/_shared/receipts/001-0.plan.json",
            "digest": "sha256:" + hashlib.sha256(terminal.read_bytes()).hexdigest(),
        },
    }
    assert request["retryOf"] == expected
    assert manifest["retryOf"] == expected


def test_init_retry_rejects_non_blocked_terminal_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    for module in (paths, task_init.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    previous_id = "20260901--travel-article-previous--other-scope--full-123"
    root = output / "data/tasks" / previous_id
    _canonical_write(root / "0.plan/result.json", {"ok": True})
    _blocked_retry_execution(output, previous_id, verdict="pass")
    demand, bindings = _inputs(output)
    demand_doc = json.loads(demand.read_text(encoding="utf-8"))
    demand_doc["retryOf"] = previous_id
    _write(demand, demand_doc)
    with pytest.raises(task_init.TaskInitError, match="terminal receipt 必须为 blocked|receipt 链不可信"):
        task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)


@pytest.mark.parametrize(
    "target,mutation",
    [
        ("_shared/stage-open/001-0.plan.json", lambda value: value["input"].update({"digest": "sha256:" + "0" * 64})),
        ("_shared/receipts/001-0.plan.json", lambda value: value["closeInput"].update({"digest": "sha256:" + "0" * 64})),
        ("_shared/receipts/001-0.plan.json", lambda value: value["submittedClose"].update({"verdict": "pass", "typedIssues": [], "resultRefs": [], "verifierFacts": []})),
    ],
)
def test_init_retry_rejects_open_close_and_submitted_close_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, mutation
) -> None:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    for module in (paths, task_init.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    previous_id = "20260902--travel-article-previous--tamper--scale-999"
    _blocked_retry_execution(output, previous_id)
    target_path = tasks / previous_id / target
    value = json.loads(target_path.read_text(encoding="utf-8"))
    mutation(value)
    _canonical_write(target_path, value)
    demand, bindings = _inputs(output)
    demand_doc = json.loads(demand.read_text(encoding="utf-8"))
    demand_doc["retryOf"] = previous_id
    _write(demand, demand_doc)
    with pytest.raises(task_init.TaskInitError, match="receipt 链不可信"):
        task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)


@pytest.mark.parametrize("tamper_kind", ("result", "evidence"))
def test_init_retry_rejects_result_and_evidence_exact_byte_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper_kind: str
) -> None:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    for module in (paths, task_init.paths):
        monkeypatch.setattr(module, "OUTPUT_ROOT", output)
        monkeypatch.setattr(module, "DATA_EXECUTIONS_ROOT", tasks)
        monkeypatch.setattr(module, "DATA_LOCAL_ROOT", local)
    previous_id = "20260902--travel-article-previous--result-tamper--scale-999"
    root = tasks / previous_id
    _blocked_retry_execution(output, previous_id, verdict="pass")
    receipt_path = root / "_shared/receipts/001-0.plan.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["submittedClose"]["verdict"] = "blocked"
    receipt["submittedClose"]["typedIssues"] = [{"code": "DATA.RETRY", "message": "blocked"}]
    receipt["verdict"] = "blocked"
    receipt["typedIssues"] = receipt["submittedClose"]["typedIssues"]
    receipt["closeInput"]["digest"] = "sha256:" + hashlib.sha256((json.dumps(receipt["submittedClose"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    _canonical_write(receipt_path, receipt)
    if tamper_kind == "result":
        (root / "0.plan/result.json").write_bytes(b'{"tampered":true}\n')
    else:
        evidence = _canonical_write(root / "0.plan/evidence.json", {"ok": True})
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        evidence_ref = {"scope": "execution", "ref": "0.plan/evidence.json"}
        evidence_digest = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
        receipt["submittedClose"]["verifierFacts"][0]["evidenceRef"] = evidence_ref
        receipt["submittedClose"]["verifierFacts"][0]["evidenceDigest"] = evidence_digest
        receipt["verifierFacts"] = receipt["submittedClose"]["verifierFacts"]
        receipt["closeInput"]["digest"] = "sha256:" + hashlib.sha256((json.dumps(receipt["submittedClose"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
        _canonical_write(receipt_path, receipt)
        evidence.write_bytes(b'{"tampered":true}\n')
    demand, bindings = _inputs(output)
    demand_doc = json.loads(demand.read_text(encoding="utf-8"))
    demand_doc["retryOf"] = previous_id
    _write(demand, demand_doc)
    with pytest.raises(task_init.TaskInitError, match="receipt 链不可信"):
        task_init.initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)
