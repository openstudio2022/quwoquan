"""代次写围栏的本地并发契约。

spec_ref: 用户冻结的有限提交临界区契约（2026-09-13）
"""
from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.coordination import ConflictError, CoordinationStore, ROLE_NAMES  # noqa: E402
from content.coordination.fence import WriteFenceToken  # noqa: E402
from content.coordination.runtime import fenced_call  # noqa: E402


@pytest.mark.parametrize("entry", ["init", "acquire", "seal", "publish", "finalize"])
def test_real_cli_handlers_reject_missing_fence_before_business_io(tmp_path, monkeypatch, capsys, entry):
    """spec_ref: multi-carrier-release/spec.md#gwt-054。不是模拟 callable 的自证。"""
    import argparse
    from content.execution.handler import _handle_acquire, _handle_seal
    from content.execution.task_init_cli import handle_task_init
    from content.release.canonical.handler import handle_publish_object, handle_release_finalize
    for name in ("QWQ_CONTENT_WRITE_FENCE", "QWQ_CONTENT_COORDINATION_DB"):
        monkeypatch.delenv(name, raising=False)
    handlers = {"init": handle_task_init, "acquire": _handle_acquire, "seal": _handle_seal,
                "publish": handle_publish_object, "finalize": handle_release_finalize}
    args = argparse.Namespace(round=str(tmp_path / "absent.json"), input=str(tmp_path / "absent.json"),
                              execution_id="absent", stage="4.draft", target_ref="posts/image/example/1")
    with pytest.raises(SystemExit) as blocked:
        handlers[entry](args)
    assert blocked.value.code == 2
    assert "WRITE_FENCE_CONFIGURATION_INCOMPLETE" in capsys.readouterr().err
    # 必须首先拒绝围栏，不能让业务内核先读工作包/正式根。
    assert not list(tmp_path.iterdir())


def _claimed_store(tmp_path: Path) -> tuple[CoordinationStore, dict[str, object]]:
    store = CoordinationStore(tmp_path / "coordination.sqlite", timeout=10)
    store.register_iteration("i1", "approval://iteration/i1")
    store.register_deployment("i1", "d1", {role: [__import__("json").dumps(["cursor", f"actor-{role}", f"run-{role}"])] for role in ROLE_NAMES}, instance_id="instance-1", account_identity_ref="account://1", resource_reservation_ref="budget://1")
    store.register_deployment("i1", "d2", {role: [__import__("json").dumps(["cursor", f"other-{role}", f"other-run-{role}"])] for role in ROLE_NAMES}, instance_id="instance-2", account_identity_ref="account://2", resource_reservation_ref="budget://2")
    store.register_shard(
        "i1", "s1", "分片一", "scope://s1", 0,
        ["target://existing", "target://other"],
    )
    store.register_shard("i1", "s2", "分片二", "scope://s2", 1, ["target://foreign"])
    claim = store.claim("i1", "team-a", "claim-1", shard_id="s1", deployment_id="d1")
    return store, claim


def _token(claim: dict[str, object], **changes: object) -> WriteFenceToken:
    values: dict[str, object] = {
        "iteration_id": "i1",
        "shard_id": "s1",
        "deployment_id": "d1",
        "team": "team-a",
        "generation": claim["generation"],
        "target_ref": "target://existing",
    }
    values.update(changes)
    return WriteFenceToken(**values)  # type: ignore[arg-type]


def test_fenced_write_holds_release_until_external_write_finishes_then_old_generation_is_rejected(
    tmp_path: Path,
) -> None:
    store, first = _claimed_store(tmp_path)
    token = _token(first)
    entered = threading.Event()
    allow_finish = threading.Event()
    release_started = threading.Event()
    release_finished = threading.Event()

    def finite_write() -> str:
        entered.set()
        assert allow_finish.wait(timeout=5)
        return "committed"

    def release() -> dict[str, object]:
        release_started.set()
        result = store.release(
            "i1", "s1", "team-a", int(first["generation"]), "release-1",
            handoff_ref="handoff://1", remaining=True,
        )
        release_finished.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        write_future = pool.submit(store.fenced_write, token, finite_write)
        assert entered.wait(timeout=5)
        release_future = pool.submit(release)
        assert release_started.wait(timeout=5)
        assert not release_finished.wait(timeout=0.2), "release 不得越过在飞有限提交"
        allow_finish.set()
        assert write_future.result(timeout=5) == "committed"
        assert release_future.result(timeout=5)["state"] == "available"

    second = store.claim("i1", "team-b", "claim-2", shard_id="s1", deployment_id="d1")
    assert second["generation"] == int(first["generation"]) + 1
    with pytest.raises(ConflictError) as stale:
        store.fenced_write(token, lambda: pytest.fail("旧代 callable 不得执行"))
    assert stale.value.code == "COORDINATION.WRITE_FENCE_STALE_CLAIM"


def test_fenced_write_rejects_cross_shard_wrong_deployment_and_blocked_claim(tmp_path: Path) -> None:
    store, claim = _claimed_store(tmp_path)
    calls: list[str] = []

    with pytest.raises(ConflictError) as cross_shard:
        store.fenced_write(
            _token(claim, target_ref="target://foreign"),
            lambda: calls.append("cross-shard"),
        )
    assert cross_shard.value.code == "COORDINATION.WRITE_FENCE_TARGET_OUTSIDE_SHARD"

    with pytest.raises(ConflictError) as deployment:
        store.fenced_write(
            _token(claim, deployment_id="d2"),
            lambda: calls.append("deployment"),
        )
    assert deployment.value.code == "COORDINATION.WRITE_FENCE_DEPLOYMENT_MISMATCH"

    store.block(
        "i1", "s1", "team-a", int(claim["generation"]), "block-1",
        fact_ref="incident://blocked",
    )
    with pytest.raises(ConflictError) as blocked:
        store.fenced_write(_token(claim), lambda: calls.append("blocked"))
    assert blocked.value.code == "COORDINATION.WRITE_FENCE_STATE_FORBIDDEN"
    assert calls == []


def test_fenced_write_rejects_target_whose_occupancy_no_longer_belongs_to_claim(tmp_path: Path) -> None:
    store, claim = _claimed_store(tmp_path)
    with store._transaction() as connection:
        connection.execute(
            "DELETE FROM target_occupancy WHERE iteration_id=? AND target_ref=?",
            ("i1", "target://existing"),
        )

    with pytest.raises(ConflictError) as unoccupied:
        store.fenced_write(
            _token(claim),
            lambda: pytest.fail("occupancy 不属于 claim 时不得执行 callable"),
        )
    assert unoccupied.value.code == "COORDINATION.WRITE_FENCE_TARGET_NOT_OCCUPIED"


def test_callable_failure_rolls_back_coordination_transaction_without_changing_claim(tmp_path: Path) -> None:
    store, claim = _claimed_store(tmp_path)
    before = store.status("i1")["shards"][0]["claim"]

    class ExternalWriteFailed(RuntimeError):
        pass

    with pytest.raises(ExternalWriteFailed):
        store.fenced_write(
            _token(claim),
            lambda: (_ for _ in ()).throw(ExternalWriteFailed("external atomic write failed")),
        )

    after = store.status("i1")["shards"][0]["claim"]
    assert after == before
    assert after["state"] == "claimed"


def test_draining_allows_only_targets_already_frozen_in_claim_occupancy(tmp_path: Path) -> None:
    store, claim = _claimed_store(tmp_path)
    store.begin_drain("i1", "s1", "team-a", int(claim["generation"]), "drain-1")

    assert store.fenced_write(_token(claim), lambda: "drained") == "drained"
    with pytest.raises(ConflictError) as new_target:
        store.fenced_write(
            _token(claim, target_ref="target://not-frozen"),
            lambda: pytest.fail("draining 不得扩展新 target"),
        )
    assert new_target.value.code == "COORDINATION.WRITE_FENCE_TARGET_OUTSIDE_SHARD"


def test_assert_write_authorized_is_side_effect_free_preflight_not_a_toctou_fence(tmp_path: Path) -> None:
    store, claim = _claimed_store(tmp_path)
    token = _token(claim)

    assert store.assert_write_authorized(token) is None
    store.release(
        "i1", "s1", "team-a", int(claim["generation"]), "release-after-preflight",
        handoff_ref="handoff://preflight", remaining=True,
    )
    with pytest.raises(ConflictError) as stale_snapshot:
        store.fenced_write(token, lambda: pytest.fail("预检结果不得充当写围栏"))
    assert stale_snapshot.value.code == "COORDINATION.WRITE_FENCE_STALE_CLAIM"


def test_fenced_write_many_requires_one_claim_and_unique_targets(tmp_path: Path) -> None:
    store, claim = _claimed_store(tmp_path)
    first = _token(claim, target_ref="target://existing")
    second = _token(claim, target_ref="target://other")
    assert store.fenced_write_many((first, second), lambda: "ok") == "ok"
    with pytest.raises(Exception, match="TOKEN_SET_INVALID"):
        store.fenced_write_many((first, first), lambda: pytest.fail("duplicate target must not write"))


def test_runtime_fence_blocks_real_entry_callable_before_business_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, claim = _claimed_store(tmp_path)
    token = _token(claim)
    monkeypatch.setenv("QWQ_CONTENT_COORDINATION_DB", str(store.path))
    monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE", __import__("json").dumps({
        "iteration_id": token.iteration_id, "shard_id": token.shard_id,
        "deployment_id": token.deployment_id, "team": token.team,
        "generation": token.generation, "target_ref": token.target_ref,
    }))
    business = tmp_path / "business-byte"
    assert fenced_call(lambda: business.write_text("ok") or "ok", target_ref=token.target_ref)
    store.release("i1", "s1", "team-a", int(claim["generation"]), "release-runtime", handoff_ref="handoff://runtime", remaining=True)
    business.unlink()
    with pytest.raises(ConflictError, match="WRITE_FENCE_STALE_CLAIM"):
        fenced_call(lambda: business.write_text("stale"), target_ref=token.target_ref)
    assert not business.exists()


def test_runtime_finalize_requires_explicit_global_closer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, claim = _claimed_store(tmp_path)
    token = _token(claim)
    monkeypatch.setenv("QWQ_CONTENT_COORDINATION_DB", str(store.path))
    monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE", __import__("json").dumps(token.__dict__ if hasattr(token, "__dict__") else {
        "iteration_id": token.iteration_id, "shard_id": token.shard_id,
        "deployment_id": token.deployment_id, "team": token.team,
        "generation": token.generation, "target_ref": token.target_ref,
    }))
    called: list[str] = []
    with pytest.raises(Exception, match="GLOBAL_CLOSER_REQUIRED"):
        fenced_call(lambda: called.append("bad"), require_global_closer=True)
    monkeypatch.setenv("QWQ_CONTENT_GLOBAL_CLOSER_DEPLOYMENT", "d1")
    fenced_call(lambda: called.append("ok"), require_global_closer=True)
    assert called == ["ok"]


def test_slow_batch_does_not_hold_sqlite_or_block_other_batch(tmp_path, monkeypatch):
    from content.coordination.runtime import actor_key
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    _claim_author(context, 0)
    _claim_author(context, 1, actor="author-b")
    entered, finish, other_done = threading.Event(), threading.Event(), threading.Event()
    def write(index, actor, callback):
        return store.fenced_producer_write(_tokens(claim, [targets[index]]), callback,
            actor=actor_key(_actor(actor)), task_digest=digest, roots=roots, operation="init",
            batches={_execution(index): [targets[index]]}, nonces={_execution(index): f"author-{index}"})
    def slow():
        entered.set()
        assert finish.wait(5)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write, 0, "article_creator", slow)
        assert entered.wait(2)
        second = pool.submit(write, 1, "author-b", other_done.set)
        try:
            assert other_done.wait(1), "不同batch不能被慢业务的SQLite事务阻塞"
        finally:
            finish.set()
        first.result(3); second.result(3)


@pytest.mark.parametrize("operation", ["block", "release", "revoke"])
def test_control_change_waits_for_inflight_business_without_holding_db(tmp_path, monkeypatch, operation):
    from content.coordination.runtime import actor_key
    import hashlib
    import json
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    _claim_author(context, 0)
    entered, finish, control_started, control_done = (threading.Event() for _ in range(4))
    def slow():
        entered.set()
        assert finish.wait(5)
    def control():
        control_started.set()
        try:
            if operation == "block":
                store.block("i1", "s1", "team-a", 1, "blocked", fact_ref="incident://1")
            elif operation == "release":
                with pytest.raises(ConflictError, match="BATCHES_UNCLOSED"):
                    store.release("i1", "s1", "team-a", 1, "release", handoff_ref="no-proof", remaining=False)
            else:
                document = json.loads(task.read_bytes())
                document["coordination"]["revokedActors"] = [roles["article_creator"][0]]
                replacement = task.with_name("task-next.json")
                replacement.write_text(json.dumps(document))
                next_digest = "sha256:" + hashlib.sha256(replacement.read_bytes()).hexdigest()
                store.bind_context("i1", "d1", task_ref=str(replacement), task_digest=next_digest,
                                   roots=roots, actor=roles["director"][0], expected_digest=digest)
        finally:
            control_done.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(store.fenced_producer_write, _tokens(claim, [targets[0]]), slow,
            actor=actor_key(_actor("article_creator")), task_digest=digest, roots=roots, operation="init",
            batches={_execution(0): [targets[0]]}, nonces={_execution(0): "author-0"})
        assert entered.wait(2)
        changing = pool.submit(control)
        assert control_started.wait(2)
        try:
            assert not control_done.wait(.15)
            import sqlite3
            connection = sqlite3.connect(store.path, timeout=.2, isolation_level=None)
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.rollback()
            finally:
                connection.close()
        finally:
            finish.set()
        future.result(3); changing.result(3)
    if operation != "release":
        with pytest.raises(Exception, match="STATE_FORBIDDEN|TASK_VERSION_STALE"):
            store.fenced_producer_write(_tokens(claim, [targets[0]]), lambda: pytest.fail("撤权后不得写"),
                actor=actor_key(_actor("article_creator")), task_digest=digest, roots=roots, operation="init",
                batches={_execution(0): [targets[0]]}, nonces={_execution(0): "author-0"})


@pytest.mark.parametrize("operation", ["init", "acquire", "4.draft"])
def test_handler_consumes_checked_input_bytes_even_if_file_changes(tmp_path, monkeypatch, operation):
    from content.execution import handler, task_init_cli
    context = _autonomy(tmp_path, monkeypatch)
    _claim_author(context, 0)
    module = task_init_cli if operation == "init" else handler
    original = module.producer_call
    changed = []
    def replace_after_preflight(callback, **kwargs):
        if kwargs["operation"] == operation:
            name = {"init": "round.json", "acquire": "ingest.json", "4.draft": "seal.json"}[operation]
            path = tmp_path / "inputs-0" / name
            path.write_text("{}")
            changed.append(name)
        return original(callback, **kwargs)
    monkeypatch.setattr(module, "producer_call", replace_after_preflight)
    root, inputs = _produce(context, monkeypatch, 0)
    assert changed
    assert (root / "_shared/receipts/002-4.draft.json").is_file()


def _actor(name):
    return {"host": "cursor", "sessionId": name, "modelFamily": "gpt",
            "invocation": {"provider": "openai", "model": "gpt", "runId": "run-" + name}}


def _autonomy(tmp_path, monkeypatch):
    import json
    from core import paths
    from content.coordination.runtime import actor_key, actual_roots
    root = tmp_path.resolve() / "output"
    root.mkdir()
    monkeypatch.setattr(paths, "OUTPUT_ROOT", root)
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", root / "data/tasks")
    monkeypatch.setattr(paths, "DATA_LOCAL_ROOT", root / "data/local")
    monkeypatch.setattr(paths, "PUBLISH_ROOT", tmp_path / "publish")
    monkeypatch.setattr(paths, "LIBRARY_ROOT", tmp_path / "library")
    monkeypatch.setenv("QWQ_CARRIED_MEDIA_ROOT", str(tmp_path / "carried"))
    store = CoordinationStore(tmp_path / "team.sqlite")
    store.register_iteration("i1", "human://authorized")
    roles = {role: [actor_key(_actor(role))] for role in ROLE_NAMES}
    roles["article_creator"].append(actor_key(_actor("author-b")))
    roles["qa"].append(actor_key(_actor("qa-b")))
    store.register_deployment("i1", "d1", roles, instance_id="native", account_identity_ref="account://one", resource_reservation_ref="budget://bounded")
    targets = [f"posts/article/导览/作品{index}/1" for index in range(6)]
    store.register_shard("i1", "s1", "批次", "scope://bounded", 1, targets)
    claim = store.claim("i1", "team-a", "team-claim", deployment_id="d1")
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"coordination": {"version": 1, "confirmationRef": "human://authorized/director-confirmed",
        "confirmedBy": roles["director"][0], "allowedActions": ["init", "acquire", "1.download", "4.draft", "5.review", "publish", "finalize"]}}))
    digest = "sha256:" + __import__("hashlib").sha256(task.read_bytes()).hexdigest()
    roots = actual_roots()
    store.bind_context("i1", "d1", task_ref=str(task), task_digest=digest, roots=roots, actor=roles["director"][0])
    return store, claim, roles, roots, task, digest, targets


def _execution(index):
    return f"20260913--travel-article-autonomy--batch-{index}--pilot-001"


def _tokens(claim, refs):
    return [_token(claim, target_ref=ref) for ref in refs]


def _claim_author(context, index, actor="article_creator", refs=None):
    from content.coordination.runtime import actor_key
    store, claim, roles, roots, task, digest, targets = context
    return store.claim_batch(_tokens(claim, refs or [targets[index]]), execution_id=_execution(index),
                             actor=actor_key(_actor(actor)), nonce=f"author-{index}", task_digest=digest)


def _env(context, monkeypatch, index, actor="article_creator", refs=None, review=False):
    import json
    from dataclasses import asdict
    store, claim, roles, roots, task, digest, targets = context
    monkeypatch.setenv("QWQ_CONTENT_COORDINATION_DB", str(store.path))
    monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE", json.dumps([asdict(token) for token in _tokens(claim, refs or [targets[index]])]))
    monkeypatch.setenv("QWQ_CONTENT_ACTOR", json.dumps(_actor(actor)))
    monkeypatch.setenv("QWQ_CONTENT_TASK_DIGEST", digest)
    monkeypatch.setenv("QWQ_CONTENT_BATCH_NONCES", json.dumps({_execution(index): f"{'review' if review else 'author'}-{index}"}))


def _produce(context, monkeypatch, index, *, seal_author=True, actor_document=None):
    """通过真实 init/acquire/seal 生成证据，不手写 receipt 或替换事实校验器。"""
    import argparse
    import json
    from core import paths
    from content.execution.task_init_cli import handle_task_init
    from content.execution.handler import _handle_acquire, _handle_seal
    store, claim, roles, roots, task, digest, targets = context
    _env(context, monkeypatch, index)
    if actor_document is not None:
        monkeypatch.setenv("QWQ_CONTENT_ACTOR", json.dumps(actor_document))
    inputs = task.parent / f"inputs-{index}"
    inputs.mkdir()
    round_path = inputs / "round.json"
    round_path.write_text(json.dumps({"schema": "quwoquan_data.round_spec", "executions": {"article": _execution(index)}, "targets": [
        {"carrier": "article", "name": f"作品{index}", "entityType": "地点/景区", "entityRef": f"/entity/test-{index}",
         "entityId": f"entity:test-{index}", "publishAngle": "导览", "publishTitle": f"作品{index}", "publishSeq": 1}]}))
    handle_task_init(argparse.Namespace(round=str(round_path)))
    source = inputs / "source.md"
    source.write_text("# 示例景区\n\n示例景区位于测试地区，正文用于本地机械契约测试。\n" * 5)
    ingest = inputs / "ingest.json"
    ingest.write_text(json.dumps({"schema": "quwoquan_data.ingest_manifest", "executionId": _execution(index), "targets": [{"targetRef": targets[index], "sources": [
        {"kind": "page", "sourceUrl": "https://zh.wikipedia.org/wiki/Test", "title": "示例景区", "sourceMarkdownPath": str(source),
         "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "Wikipedia", "relevance": "本地测试"}]}]}))
    _handle_acquire(argparse.Namespace(execution_id=_execution(index), input=str(ingest)))
    payload = inputs / "seal.json"
    payload.write_text(json.dumps({"actor": actor_document or _actor("article_creator"), "verdict": "pass"}))
    _handle_seal(argparse.Namespace(execution_id=_execution(index), input=str(payload), stage="1.download"))
    root = paths.DATA_EXECUTIONS_ROOT / _execution(index)
    draft = root / targets[index] / "4.draft/draft.article.md"
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(f"---\ntitle: 作品{index}\ntagRefs: [Entity/地点/景区]\n---\n# 示例景区\n\n本地契约测试正文。\n")
    if seal_author:
        _handle_seal(argparse.Namespace(execution_id=_execution(index), input=str(payload), stage="4.draft"))
    return root, inputs


def _review_semantics(
    root: Path, target_ref: str, *, reviewer: dict[str, object], decision: str, blocking_issues: list[str]
) -> dict[str, object]:
    import json
    from content.execution import seal

    protocol = {"schemaVersion": "1.0.0", "dialectVersion": "1.0.0", "canonicalizationVersion": "1.0.0"}
    revision = {"contentRevision": 1, "sourceRevision": 1, "layoutRevision": 1}
    refs_document = json.loads((root / target_ref / "1.download/source_refs.json").read_bytes())
    counts = {"title": 0, "heading": 0, "paragraph": 1, "list": 0, "tableLogicalCell": 0, "footnote": 0, "media": 0}
    report_rows = []
    for row in refs_document["sources"]:
        source_ref = row["sourceRef"]
        source_digest = seal.sha256((root / source_ref).read_bytes())
        sequence_digest = seal.sha256(seal.canonical_bytes({
            "objectRef": target_ref, "sourceRef": source_ref,
            "sourceDigest": source_digest, "objectRevision": revision,
        }))
        report_rows.append({
            "sourceRef": source_ref, "sourceDigest": source_digest, "parseStatus": "complete",
            "dialect": "markdown", "dialectVersion": "1", "capabilities": ["paragraph"],
            "sourceCounts": counts, "draftCounts": counts,
            "sourceSequenceDigest": sequence_digest, "draftSequenceDigest": sequence_digest,
        })
    carrier = "homepage" if target_ref.startswith("entities/") else "article"
    semantic_report: dict[str, object] = {
        "reviewedCarrier": carrier, "carrierCompatible": True, "sources": report_rows,
        "issues": [] if decision == "approved" else [{
            "code": "SEMANTIC_COVERAGE_GAP",
            "message": blocking_issues[0],
            "ref": target_ref,
        }],
    }
    if carrier == "homepage":
        semantic_report["homepageFidelity"] = {
            "title": True, "headingTree": True, "paragraphOrder": True, "links": True,
            "nestedLists": True, "tableLogicalGrid": True, "footnotes": True, "mediaCaptionOrder": True,
        }
        draft_name = "page.md"
    else:
        semantic_report["articleIntent"] = {
            "independent": True, "intent": "景区导览",
            "rationale": "测试草稿对采用来源作独立导览表达，而非百科原文复制",
        }
        draft_name = "draft.article.md"
    draft_digest = seal.sha256((root / target_ref / "4.draft" / draft_name).read_bytes())
    source_set_digest = seal.sha256(seal.canonical_bytes([row["sourceDigest"] for row in report_rows]))
    approved = decision == "approved"
    disposition = {
        "issueId": f"{carrier}-{'semantic-exact' if approved else 'coverage-gap'}-r1",
        "objectRef": target_ref,
        "sourceAnchor": {"origin": "source-set", "start": 0, "end": len(report_rows), "selector": target_ref},
        "sourceDigest": source_set_digest, "targetDigest": draft_digest,
        "detectedType": "SEMANTIC_EXACT" if approved else "SEMANTIC_COVERAGE_GAP",
        "proposedMapping": None, "lossFields": [] if approved else ["sourceEvidence"],
        "severity": "info" if approved else "error",
        "actor": {"actorId": reviewer["sessionId"], "actorType": "independent_reviewer"},
        "reason": (
            f"reviewed {carrier} draft revision 1 against every acquired source revision"
            if approved else blocking_issues[0]
        ),
        "policyVersion": "1.0.0",
        "reviewStatus": "reviewed_confirmed" if approved else "reviewed_rejected",
        "outcome": "auto_continue" if approved else "definitive_reject",
        "processingDisposition": "preserved" if approved else "blocked_unsafe",
        "protocol": protocol, "objectRevision": revision,
    }
    return {
        "semanticReport": semantic_report, "protocol": protocol,
        "objectRevision": revision, "dispositions": [disposition],
    }


def test_atomic_batch_winner_and_other_author_remains_independent(tmp_path, monkeypatch):
    """spec_ref: multi-carrier-release/spec.md#gwt-054"""
    context = _autonomy(tmp_path, monkeypatch)
    from content.coordination.runtime import actor_key
    store, claim, roles, roots, task, digest, targets = context
    def compete(index):
        try:
            return store.claim_batch(_tokens(claim, [targets[0]]), execution_id=_execution(0),
                actor=actor_key(_actor("article_creator" if index % 2 else "author-b")), nonce=f"nonce-{index}", task_digest=digest)
        except Exception as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(compete, range(8)))
    assert sum(isinstance(value, dict) for value in results) == 1
    winner = next(value for value in results if isinstance(value, dict))
    other = "author-b" if winner["author"] == roles["article_creator"][0] else "article_creator"
    assert _claim_author(context, 1, actor=other)["execution_id"] == _execution(1)
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM batch_scopes").fetchone()[0] == 2


def test_real_seals_allow_second_batch_but_review_does_not_release_end_to_end_capacity(tmp_path, monkeypatch):
    """spec_ref: multi-carrier-release/spec.md#gwt-054"""
    import argparse
    import json
    from content.coordination.runtime import actor_key, batch_facts
    from content.execution.handler import _handle_seal
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    batch = _claim_author(context, 0)
    with pytest.raises(ConflictError, match="AUTHOR_CAPACITY_EXCEEDED"):
        _claim_author(context, 1)
    root, inputs = _produce(context, monkeypatch, 0)
    _claim_author(context, 1)
    with pytest.raises(ConflictError, match="AUTHOR_CAPACITY_EXCEEDED"):
        _claim_author(context, 2)
    review_batch = store.claim_batch(_tokens(claim, [targets[0]]), execution_id=_execution(0), actor=actor_key(_actor("qa")), nonce="review-0", task_digest=digest, review=True)
    _produce(context, monkeypatch, 1)
    with pytest.raises(ConflictError, match="REVIEW_CAPACITY_EXCEEDED"):
        store.claim_batch(_tokens(claim, [targets[1]]), execution_id=_execution(1), actor=actor_key(_actor("qa")), nonce="review-1", task_digest=digest, review=True)
    assert store.claim_batch(_tokens(claim, [targets[1]]), execution_id=_execution(1), actor=actor_key(_actor("qa-b")), nonce="review-1", task_digest=digest, review=True)["reviewer"] == actor_key(_actor("qa-b"))
    with pytest.raises(ConflictError, match="REVIEW_OCCUPIED"):
        store.claim_batch(_tokens(claim, [targets[0]]), execution_id=_execution(0), actor=actor_key(_actor("qa-b")), nonce="steal", task_digest=digest, review=True)
    _env(context, monkeypatch, 0, actor="qa", review=True)
    review = inputs / "review.json"
    reviewer = _actor("qa")
    judgement = {"decision": "approved", "blockingIssues": [], "advisories": []}
    judgement.update(_review_semantics(
        root, targets[0], reviewer=reviewer, decision="approved", blocking_issues=[]
    ))
    review.write_text(json.dumps({"actor": reviewer, "verdict": "pass", "reviews": {targets[0]: judgement}}))
    _handle_seal(argparse.Namespace(execution_id=_execution(0), input=str(review), stage="5.review"))
    assert batch_facts(review_batch, roots)["review_sealed"]
    assert not batch_facts(review_batch, roots)["closed"]
    with pytest.raises(ConflictError, match="AUTHOR_CAPACITY_EXCEEDED"):
        _claim_author(context, 2)
    with pytest.raises(ConflictError, match="BATCHES_UNCLOSED"):
        store.release("i1", "s1", "team-a", 1, "close-lie", handoff_ref="claims-all-done", remaining=False)


def test_real_init_requires_exact_batch_target_coverage_before_creating_execution(tmp_path, monkeypatch):
    import argparse
    import json
    from core import paths
    from content.execution.task_init_cli import handle_task_init
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    _claim_author(context, 0, refs=targets[:2])
    _env(context, monkeypatch, 0, refs=[targets[0]])
    round_path = tmp_path / "two.json"
    round_path.write_text(json.dumps({"schema": "quwoquan_data.round_spec", "executions": {"article": _execution(0)}, "targets": [
        {"carrier": "article", "name": f"作品{i}", "entityType": "地点/景区", "entityRef": f"/entity/test-{i}", "entityId": f"entity:test-{i}", "publishAngle": "导览", "publishTitle": f"作品{i}", "publishSeq": 1} for i in range(2)]}))
    with pytest.raises(SystemExit) as blocked:
        handle_task_init(argparse.Namespace(round=str(round_path)))
    assert blocked.value.code == 2
    assert not (paths.DATA_EXECUTIONS_ROOT / _execution(0)).exists()


@pytest.mark.parametrize("failure", ["actor", "version", "root", "publish", "confirmation", "generation"])
def test_producer_context_rejects_drift_without_writing(tmp_path, monkeypatch, failure):
    """spec_ref: multi-carrier-release/spec.md#gwt-055"""
    import json
    from content.coordination.runtime import producer_call
    from content.coordination.store import CoordinationError
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    _claim_author(context, 0)
    _env(context, monkeypatch, 0)
    operation = "init"
    if failure == "actor":
        monkeypatch.setenv("QWQ_CONTENT_ACTOR", json.dumps(_actor("author-b")))
    elif failure == "version":
        monkeypatch.setenv("QWQ_CONTENT_TASK_DIGEST", "old")
    elif failure == "root":
        monkeypatch.setenv("QWQ_CARRIED_MEDIA_ROOT", str(tmp_path / "wrong"))
    elif failure == "publish":
        operation = "publish"
    elif failure == "confirmation":
        task.write_text("{}")
    elif failure == "generation":
        value = json.loads(__import__("os").environ["QWQ_CONTENT_WRITE_FENCE"])
        value[0]["generation"] += 1
        monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE", json.dumps(value))
    with pytest.raises(CoordinationError):
        producer_call(lambda: pytest.fail("越权不能写"), operation=operation, batches={_execution(0): [targets[0]]})


def test_cli_legacy_roles_and_missing_fence_have_typed_nonzero_exit(tmp_path, capsys):
    import json
    from content.coordination.cli import main
    db = tmp_path / "cli.sqlite"
    assert main(["--db", str(db), "register-iteration", "i", "human://1"]) == 0
    assert main(["--db", str(db), "register-deployment", "i", "legacy", "--roles", json.dumps({role: "actor-" + role for role in ROLE_NAMES})]) == 2
    assert "INVALID_ROLE_BINDINGS" in capsys.readouterr().out
    assert main(["--db", str(db), "claim-batch", "--tokens", "[]", "--execution-id", _execution(0), "--actor", json.dumps(_actor("article_creator")), "--nonce", "n", "--task-digest", "old"]) == 2
    assert "TOKEN_SET_INVALID" in capsys.readouterr().out


def test_context_update_revokes_only_affected_actor_and_rejects_old_digest(tmp_path, monkeypatch):
    import hashlib
    import json
    from content.coordination.runtime import actor_key, producer_call
    from content.coordination.store import CoordinationError
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    _claim_author(context, 0)
    _claim_author(context, 1, actor="author-b")
    document = json.loads(task.read_bytes())
    document["coordination"].update(version=2, revokedActors=[roles["article_creator"][0]])
    task.write_text(json.dumps(document))
    next_digest = "sha256:" + hashlib.sha256(task.read_bytes()).hexdigest()
    store.bind_context("i1", "d1", task_ref=str(task), task_digest=next_digest, roots=roots,
                       actor=roles["director"][0], expected_digest=digest)
    _env(context, monkeypatch, 0)
    with pytest.raises(CoordinationError, match="TASK_VERSION_STALE"):
        producer_call(lambda: pytest.fail("旧版本"), operation="init", batches={_execution(0): [targets[0]]})
    monkeypatch.setenv("QWQ_CONTENT_TASK_DIGEST", next_digest)
    with pytest.raises(CoordinationError, match="ACTOR_FORBIDDEN"):
        producer_call(lambda: pytest.fail("撤权"), operation="init", batches={_execution(0): [targets[0]]})
    _env(context, monkeypatch, 1, actor="author-b")
    monkeypatch.setenv("QWQ_CONTENT_TASK_DIGEST", next_digest)
    assert producer_call(lambda: "healthy", operation="init", batches={_execution(1): [targets[1]]}) == "healthy"


def test_author_cannot_use_real_publish_handler_even_with_same_deployment(tmp_path, monkeypatch, capsys):
    import argparse
    from content.release.canonical.handler import handle_publish_object
    context = _autonomy(tmp_path, monkeypatch)
    _claim_author(context, 0)
    _env(context, monkeypatch, 0)
    with pytest.raises(SystemExit) as blocked:
        handle_publish_object(argparse.Namespace(execution_id=_execution(0), target_ref=context[-1][0]))
    assert blocked.value.code == 2
    assert "DIRECTOR_REQUIRED" in capsys.readouterr().err
    assert not Path(context[3]["publish"]).exists()


def test_explicit_root_binding_rejects_drift_and_existing_execution_is_not_adopted(tmp_path, monkeypatch):
    from content.coordination.store import CoordinationError
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    with pytest.raises(CoordinationError, match="ROOT_REBIND_FORBIDDEN"):
        store.bind_context("i1", "d1", task_ref=str(task), task_digest=digest,
                           roots={**roots, "publish": str(tmp_path / "another-publish")}, actor=roles["director"][0], expected_digest=digest)
    previous = Path(roots["output"]) / "data/tasks" / _execution(0)
    previous.mkdir(parents=True)
    original = previous / "old-receipt.json"
    original.write_text("preserved")
    with pytest.raises(CoordinationError, match="EXISTING_EXECUTION_REBIND_FORBIDDEN"):
        _claim_author(context, 0)
    assert original.read_text() == "preserved"


@pytest.mark.parametrize("mixed", [False, True, "all-rejected"])
def test_actual_homepage_publish_proof_frees_capacity_and_drift_retains_it(tmp_path, monkeypatch, mixed):
    """spec_ref: multi-carrier-release/spec.md#gwt-054；真实 canonical 事务，不自填 published。"""
    import argparse
    import json
    from content.coordination.runtime import actor_key, batch_facts
    from content.execution.task_init import execution_target_ref
    from content.execution.handler import _handle_seal
    from content.release.canonical import handler, object_transaction, publish_object
    from content.release.canonical.creator_projection import project_creator_object
    from local_contract.release import test_homepage_revision__identity_preserving__local_contract_test as fixture
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    output, publish = Path(roots["output"]), Path(roots["publish"])
    (publish / ".git").mkdir(parents=True)
    (publish / "repository.json").write_text(json.dumps({"schema": "quwoquan_data.publish_repository.v2", "repositoryId": "autonomy-test", "layoutVersion": 2}))
    for module in (object_transaction, publish_object, handler):
        monkeypatch.setattr(module, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(publish_object, "OUTPUT_ROOT", output)
    monkeypatch.setattr(handler, "OUTPUT_ROOT", output)
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", roots["library"])
    # text-only creator 是 schema 允许的最小测试对象；不使用伪摘要头像 holding。
    import yaml
    from content.release.canonical import creator_projection
    pool = tmp_path / "creator-pool"
    (pool / "profiles").mkdir(parents=True)
    profile_path = creator_projection._creator_profile_path(fixture.CREATOR, creator_pool_root=creator_projection.CONTROL_PLANE_CREATOR_POOL_ROOT)
    profile = yaml.safe_load(profile_path.read_text())
    profile.pop("avatarAsset", None)
    (pool / "profiles/test.creator.yaml").write_text(yaml.safe_dump(profile, allow_unicode=True))
    monkeypatch.setattr(creator_projection, "CONTROL_PLANE_CREATOR_POOL_ROOT", pool)
    project_creator_object(fixture.CREATOR, publish / "creators" / fixture.CREATOR)
    # 使用已有真实对象 fixture，只替换测试 actor；生产 receipt 仍由 seal 内核生成。
    monkeypatch.setattr(fixture, "AUTHOR", _actor("homepage_creator"))
    monkeypatch.setattr(fixture, "REVIEWER", _actor("qa"))
    def reviewed_homepage_ref(target):
        process_ref = execution_target_ref(target, carrier="homepage")
        return process_ref.replace("entities/地点/景区/", "entities/地点/", 1) + "/1"

    ref = reviewed_homepage_ref({"name": "西湖", "entityType": "地点/景区", "entityId": "entity:xihu", "entityRef": "/entity/travel/stable/xihu"})
    execution_id = "20260912--travel-homepage-correction--local--pilot-001"
    store.release("i1", "s1", "team-a", 1, "unused-shard", handoff_ref="scope-not-started", remaining=False)
    candidate = {"carrier": "homepage", "name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市",
                 "entityId": "entity:xihu", "entityRef": "/entity/travel/stable/xihu"}
    candidates = [candidate]
    if mixed:
        candidates.append({**candidate, "name": "未核实景区", "entityId": "entity:rejected", "entityRef": "/entity/travel/stable/rejected"})
    refs = [reviewed_homepage_ref(value) for value in candidates]
    store.register_shard("i1", "homepage", "主页小批", "scope://homepage", 2, refs)
    homepage_claim = store.claim("i1", "team-a", "homepage-claim", deployment_id="d1", shard_id="homepage")
    tokens = [WriteFenceToken("i1", "homepage", "d1", "team-a", homepage_claim["generation"], value) for value in refs]
    store.claim_batch(tokens, execution_id=execution_id, actor=roles["homepage_creator"][0], nonce="home-author", task_digest=digest)
    from content.execution import task_init, seal
    from content.source.acquire import acquire
    monkeypatch.setattr(
        task_init, "execution_target_ref",
        lambda target, *, carrier: reviewed_homepage_ref(target),
    )
    round_path = output / "round.json"
    round_path.write_text(json.dumps({"schema": "quwoquan_data.round_spec", "executions": {"homepage": execution_id}, "targets": candidates}))
    task_init.initialize_round(round_spec_path=round_path)
    root = output / "data/tasks" / execution_id
    source = output / "source.md"
    source.write_text("# 西湖\n\n用于本地测试的独立取得正文。\n")
    ingest = output / "ingest.json"
    ingest.write_text(json.dumps({"schema": "quwoquan_data.ingest_manifest", "executionId": execution_id, "targets": [
        {"targetRef": value, "sources": [{"kind": "page", "sourceUrl": "https://zh.wikipedia.org/wiki/西湖", "title": "西湖", "sourceMarkdownPath": str(source),
         "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "词条编辑", "relevance": "实体事实", "extractor": "html_text"}]} for value in refs]}))
    assert acquire(execution_id=execution_id, request_path=ingest)["failed"] == 0
    seal_path = output / "author.json"
    seal_path.write_text(json.dumps({"actor": _actor("homepage_creator"), "verdict": "pass"}))
    seal.seal_stage(execution_id=execution_id, stage="1.download", input_path=seal_path)
    for value in refs:
        draft = root / value / "4.draft/page.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(f"---\ntitle: 西湖\ntagRefs: [Entity/地点/景区]\ncreatorProfileId: {fixture.CREATOR}\n---\n# 西湖\n\n测试事实。\n")
    seal.seal_stage(execution_id=execution_id, stage="4.draft", input_path=seal_path)
    batch = store.claim_batch(tokens, execution_id=execution_id, actor=roles["qa"][0], nonce="home-review", task_digest=digest, review=True)
    from dataclasses import asdict
    monkeypatch.setenv("QWQ_CONTENT_COORDINATION_DB", str(store.path))
    monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE", json.dumps([asdict(token) for token in tokens]))
    monkeypatch.setenv("QWQ_CONTENT_TASK_DIGEST", digest)
    monkeypatch.setenv("QWQ_CONTENT_ACTOR", json.dumps(_actor("qa")))
    monkeypatch.setenv("QWQ_CONTENT_BATCH_NONCES", json.dumps({execution_id: "home-review"}))
    review = tmp_path / "home-review.json"
    reviewer = _actor("qa")
    judgements = {ref: {"decision": "approved", "blockingIssues": [], "advisories": []}}
    if mixed:
        judgements[refs[1]] = {"decision": "rejected", "blockingIssues": ["关键事实缺少来源证据"], "advisories": []}
    payload = {"actor": reviewer, "verdict": "pass", "reviews": judgements}
    if mixed == "all-rejected":
        judgements[ref] = {"decision": "rejected", "blockingIssues": ["关键事实缺证"], "advisories": []}
        payload.update(verdict="blocked", typedIssues=[{"code": "DATA.SEAL.REVIEW_REJECTED", "message": "本批无批准对象"}])
    for target_ref, judgement in judgements.items():
        judgement.update(_review_semantics(
            root, target_ref, reviewer=reviewer, decision=judgement["decision"],
            blocking_issues=judgement["blockingIssues"],
        ))
    review.write_text(json.dumps(payload))
    _handle_seal(argparse.Namespace(execution_id=execution_id, stage="5.review", input=str(review)))
    assert not batch_facts(batch, roots)["closed"]
    if mixed == "all-rejected":
        with pytest.raises(ConflictError, match="BATCHES_UNCLOSED"):
            store.release("i1", "homepage", "team-a", homepage_claim["generation"], "no-native-proof", handoff_ref="rejected-is-not-native-terminal", remaining=False)
        return
    monkeypatch.setenv("QWQ_CONTENT_WRITE_FENCE", json.dumps([asdict(tokens[0])]))
    monkeypatch.setenv("QWQ_CONTENT_ACTOR", json.dumps(_actor("director")))
    handler.handle_publish_object(argparse.Namespace(execution_id=execution_id, target_ref=ref))
    assert batch_facts(batch, roots)["closed"]
    if mixed:
        rejected = root / refs[1] / "5.review/content_review.json"
        original = rejected.read_bytes()
        rejected.write_text("{}")
        with pytest.raises(ValueError, match="digest 漂移"):
            batch_facts(batch, roots)
        rejected.write_bytes(original)
        assert batch_facts(batch, roots)["closed"]
    canonical = next(publish.glob("entities/**/page.md"))
    canonical.write_text("tampered")
    assert not batch_facts(batch, roots)["closed"]


@pytest.mark.parametrize("failure", ["acquire-target", "review-as-author", "seal-actor"])
def test_real_stage_handlers_reject_bad_scope_and_input_before_new_receipt(tmp_path, monkeypatch, capsys, failure):
    import argparse
    import json
    from content.execution.handler import _handle_acquire, _handle_seal
    context = _autonomy(tmp_path, monkeypatch)
    _claim_author(context, 0)
    root, inputs = _produce(context, monkeypatch, 0)
    before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    capsys.readouterr()
    args = argparse.Namespace(execution_id=_execution(0), input=str(inputs / "ingest.json"))
    if failure == "acquire-target":
        document = json.loads((inputs / "ingest.json").read_bytes())
        document["targets"][0]["targetRef"] = context[-1][1]
        (inputs / "ingest.json").write_text(json.dumps(document))
        call = _handle_acquire
    else:
        args.stage = "5.review" if failure == "review-as-author" else "4.draft"
        args.input = str(inputs / "bad-seal.json")
        (inputs / "bad-seal.json").write_text(json.dumps({"actor": _actor("author-b" if failure == "seal-actor" else "article_creator"), "verdict": "pass"}))
        call = _handle_seal
    with pytest.raises(SystemExit) as blocked:
        call(args)
    assert blocked.value.code == 2
    code = {"acquire-target": "INGEST_TARGET_COVERAGE_INVALID", "review-as-author": "BATCH_ACTOR_MISMATCH", "seal-actor": "SUBMITTED_ACTOR_MISMATCH"}[failure]
    assert code in capsys.readouterr().err
    assert before == {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_acquire_mixed_empty_source_preserves_good_target(tmp_path, monkeypatch, capsys):
    """spec_ref: multi-carrier-release/spec.md#gwt-054；真实CLI一好一坏不整批中止。"""
    import argparse
    import json
    from content.execution.task_init_cli import handle_task_init
    from content.execution.handler import _handle_acquire
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    _claim_author(context, 0, refs=targets[:2])
    _env(context, monkeypatch, 0, refs=targets[:2])
    round_path = tmp_path / "mixed-round.json"
    round_path.write_text(json.dumps({"schema": "quwoquan_data.round_spec", "executions": {"article": _execution(0)}, "targets": [
        {"carrier": "article", "name": f"作品{i}", "entityType": "地点/景区", "entityRef": f"/entity/test-{i}", "entityId": f"entity:test-{i}", "publishAngle": "导览", "publishTitle": f"作品{i}", "publishSeq": 1} for i in range(2)]}))
    handle_task_init(argparse.Namespace(round=str(round_path)))
    sources = [tmp_path / "good.md", tmp_path / "empty.md"]
    sources[0].write_text("# 合法来源\n\n独立目标的测试正文。\n")
    sources[1].write_text(" \n")
    ingest = tmp_path / "mixed-ingest.json"
    ingest.write_text(json.dumps({"schema": "quwoquan_data.ingest_manifest", "executionId": _execution(0), "targets": [
        {"targetRef": targets[i], "sources": [{"kind": "page", "sourceUrl": f"https://zh.wikipedia.org/wiki/Test{i}", "title": f"作品{i}", "sourceMarkdownPath": str(sources[i]),
         "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "Wikipedia", "relevance": "测试"}]} for i in range(2)]}))
    capsys.readouterr()
    with pytest.raises(SystemExit) as outcome:
        _handle_acquire(argparse.Namespace(execution_id=_execution(0), input=str(ingest)))
    assert outcome.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert (report["ingested"], report["failed"]) == (1, 1)
    assert report["targets"][1]["issue"]["code"] == "DATA.ACQUIRE.PAGE_EMPTY"
    root = Path(roots["output"]) / "data/tasks" / _execution(0)
    assert (root / targets[0] / "1.download/source_refs.json").is_file()
    assert not (root / targets[1] / "1.download/source_refs.json").exists()


def test_same_session_new_run_cannot_bypass_author_capacity(tmp_path, monkeypatch):
    import json
    from content.coordination.runtime import actor_key
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    _claim_author(context, 0)
    second_actor = _actor("article_creator")
    second_actor["invocation"]["runId"] = "new-run"
    # 显式部署同一session的下一调用仍须计入原作者；不是凭空授予新成员。
    roles["article_creator"].append(actor_key(second_actor))
    with store._transaction() as connection:
        connection.execute("UPDATE deployments SET roles=? WHERE deployment_id='d1'", (json.dumps(roles),))
    with pytest.raises(Exception, match="AUTHOR_CAPACITY_EXCEEDED|INVALID_ROLE_BINDINGS"):
        store.claim_batch(_tokens(claim, [targets[1]]), execution_id=_execution(1), actor=actor_key(second_actor), nonce="new-run-claim", task_digest=digest)


def test_member_capacity_aggregates_new_runs_but_sealed_writer_stays_exact(tmp_path, monkeypatch):
    from content.coordination.runtime import actor_key, producer_call
    context = _autonomy(tmp_path, monkeypatch)
    store, claim, roles, roots, task, digest, targets = context
    _claim_author(context, 0)
    next_actor = _actor("article_creator")
    next_actor["invocation"]["runId"] = "next-run"
    with pytest.raises(ConflictError, match="AUTHOR_CAPACITY_EXCEEDED"):
        store.claim_batch(_tokens(claim, [targets[1]]), execution_id=_execution(1), actor=actor_key(next_actor), nonce="author-1", task_digest=digest)
    _produce(context, monkeypatch, 0)
    second = store.claim_batch(_tokens(claim, [targets[1]]), execution_id=_execution(1), actor=actor_key(next_actor), nonce="author-1", task_digest=digest)
    assert second["author"] == actor_key(next_actor)
    _produce(context, monkeypatch, 1, actor_document=next_actor)
    third_actor = _actor("article_creator")
    third_actor["invocation"]["runId"] = "third-run"
    with pytest.raises(ConflictError, match="AUTHOR_CAPACITY_EXCEEDED"):
        store.claim_batch(_tokens(claim, [targets[2]]), execution_id=_execution(2), actor=actor_key(third_actor), nonce="author-2", task_digest=digest)
    _env(context, monkeypatch, 1)  # 同成员旧run不能接管新run冻结的execution。
    with pytest.raises(ConflictError, match="BATCH_ACTOR_MISMATCH"):
        producer_call(lambda: pytest.fail("旧run改写新run"), operation="4.draft", batches={_execution(1): [targets[1]]})
    qa = _actor("qa")
    store.claim_batch(_tokens(claim, [targets[0]]), execution_id=_execution(0), actor=actor_key(qa), nonce="review-0", task_digest=digest, review=True)
    qa["invocation"]["runId"] = "qa-next-run"
    with pytest.raises(ConflictError, match="REVIEW_CAPACITY_EXCEEDED"):
        store.claim_batch(_tokens(claim, [targets[1]]), execution_id=_execution(1), actor=actor_key(qa), nonce="review-1", task_digest=digest, review=True)
