# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-001
"""显式 cutover：真实 init/acquire/seal/对象事务及原子激活/进程故障回归。

只有输入根隔离与故障注入使用 monkeypatch，不 mock schema/query/review/事务 validator。
"""
from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest

from content.execution import seal, task_init
from content.release.canonical import pool_cutover as subject
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import canonical_inventory_path, load_or_bootstrap_inventory
from content.release.canonical.content_pool_record import build_canonical_pool_record
from content.release.canonical.final_surface_projection import project_publish_final_surface
from content.release.canonical.object_transaction import build_entity_object_transaction_package
from content.release.canonical.post_transaction import build_post_object_transaction_package
from content.release.canonical.object_transaction_audit import audit_object_transaction
from content.release.canonical.object_transaction_contract import (
    _closure_digest, _digest_file, _json_bytes, _read_json, _review_binding, _tree_digest,
    canonical_transaction_id,
)
from content.source import acquire
from core import paths
from core.schema import assert_valid
from support.media_fixture import seed_system_creator_avatar_holding

HOME = "entities/地点/景区/西湖"
POST = "posts/article/导览/西湖速览/1"
CREATOR = "qwq_creator_geo_editor_001"
AUTHOR = {"host": "cursor", "modelFamily": "gpt", "sessionId": "cutover-author", "invocation": {"provider": "openai", "model": "test-model", "runId": "author-run"}}
REVIEWER = {**AUTHOR, "sessionId": "cutover-reviewer", "invocation": {**AUTHOR["invocation"], "runId": "review-run"}}


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode() if isinstance(value, str) else _json_bytes(value))
    return path


def _binding(path: Path, *, role: str | None = None) -> dict:
    row = {"ref": str(path), "digest": _tree_digest(path) if path.is_dir() else _digest_file(path)}
    if role:
        row.update(role=role, kind="tree" if path.is_dir() else "file")
    return row


def _isolate_library(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    from core import content_library
    # library 模块在收集期导入常量；只改 env 不会移动实际 holder。
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", str(root))
    for module in (paths, content_library):
        monkeypatch.setattr(module, "LIBRARY_ROOT", root)
        monkeypatch.setattr(module, "LIBRARY_CAS_ROOT_BY_KIND", {"media": root / "_media_cas", "source": root / "_source_cas"})
    monkeypatch.setattr(paths, "LIBRARY_MEDIA_CAS_ROOT", root / "_media_cas")
    monkeypatch.setattr(paths, "LIBRARY_SOURCE_CAS_ROOT", root / "_source_cas")


def _execution(tmp: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _isolate_library(monkeypatch, tmp / "library")
    monkeypatch.setattr(paths, "OUTPUT_ROOT", tmp / "output")
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tmp / "output/data/tasks")
    monkeypatch.setattr(paths, "DATA_LOCAL_ROOT", tmp / "output/data/local")
    monkeypatch.setattr(paths, "CANONICAL_PUBLISH_SIDECAR_ROOT", tmp / "output/data/local/cache/canonical")
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", str(tmp / "library"))
    monkeypatch.setenv("QWQ_CARRIED_MEDIA_ROOT", str(tmp / "golden_media"))
    execution_id = "20260909--travel-homepage-cutover--local--pilot-001"
    target = {"name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市"}
    task_init.initialize_execution(
        submitted_demand={"schema": "quwoquan_data.carrier_demand", "executionId": execution_id, "carrier": "homepage", "familyRef": "content/travel/homepage/homepage"},
        submitted_bindings={"schema": "quwoquan_data.immutable_candidate_bindings", "executionId": execution_id, "carrier": "homepage", "targets": [target]},
    )
    root = paths.execution_root(execution_id)
    page = _write(tmp / "source.md", "# 西湖\n\n西湖位于杭州，本地合成来源事实。\n")
    request = _write(tmp / "ingest.json", {"schema": "quwoquan_data.ingest_manifest", "executionId": execution_id, "targets": [{"targetRef": HOME, "sources": [{"kind": "page", "sourceUrl": "https://zh.wikipedia.org/wiki/西湖", "title": "西湖", "sourceMarkdownPath": str(page), "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "测试编辑", "relevance": "主页事实"}]}]})
    result = acquire.acquire(execution_id=execution_id, request_path=request)
    assert result["failed"] == 0, result
    _write(root / HOME / "4.draft/page.md", f"---\ntitle: 西湖\ntagRefs: [Entity/地点/景区]\ncreatorProfileId: {CREATOR}\n---\n# 西湖\n\n本地独立审核的主页正文。\n")
    for stage in ("1.download", "4.draft", "5.review"):
        payload = {"actor": REVIEWER if stage == "5.review" else AUTHOR, "verdict": "pass"}
        if stage == "5.review":
            payload["reviews"] = {HOME: {"decision": "approved", "blockingIssues": [], "advisories": []}}
        seal.seal_stage(execution_id=execution_id, stage=stage, input_path=_write(tmp / f"{stage}.json", payload))
    project_publish_final_surface(execution_root=root, object_dir=root / HOME, target_ref=HOME, target=target, carrier="homepage")
    return root


def _publish(tmp: Path, execution: Path) -> tuple[Path, Path]:
    seed_system_creator_avatar_holding(CREATOR)
    transaction_id = canonical_transaction_id(execution_id=execution.name, object_kind="entities", object_ref=HOME.removeprefix("entities/"))
    package = tmp / "package"
    build_entity_object_transaction_package(execution_root=execution, object_ref="/entity/" + HOME.removeprefix("entities/"), transaction_id=transaction_id, package_root=package)
    active = tmp / "active"
    active.mkdir()
    package_doc = _read_json(package / "object_transaction_package.json")
    for row in package_doc["closure"]["creatorObjects"]:
        shutil.copytree(package / row["packageRef"], active / "creators" / row["creatorRef"])
    audit = audit_object_transaction(publish_root=active, output_root=tmp / "transaction-output", package_root=package, transaction_id=transaction_id, expected_canonical_merkle=load_or_bootstrap_inventory(active)["stats"]["merkleRoot"])
    applied = apply_object_transaction(publish_root=active, output_root=tmp / "transaction-output", package_root=package, transaction_id=transaction_id, dry_run_attestation_sha256=audit["dryRunAttestationSha256"])
    assert applied
    return active, package


def _dependent_post(case: dict) -> Path:
    tmp, active = case["tmp"], case["active"]
    execution_id = "20260909--travel-article-cutover--local--pilot-002"
    target = {"name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市", "publishAngle": "导览", "publishTitle": "西湖速览", "publishSeq": 1}
    task_init.initialize_execution(submitted_demand={"schema": "quwoquan_data.carrier_demand", "executionId": execution_id, "carrier": "article", "familyRef": "content/travel/article/article"}, submitted_bindings={"schema": "quwoquan_data.immutable_candidate_bindings", "executionId": execution_id, "carrier": "article", "targets": [target]})
    execution = paths.execution_root(execution_id)
    request = _write(tmp / "article-ingest.json", {"schema": "quwoquan_data.ingest_manifest", "executionId": execution_id, "targets": [{"targetRef": POST, "sources": [{"kind": "page", "sourceUrl": "https://zh.wikipedia.org/wiki/西湖", "title": "西湖", "sourceMarkdownPath": str(tmp / "source.md"), "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "测试编辑", "relevance": "正文事实"}]}]})
    assert acquire.acquire(execution_id=execution_id, request_path=request)["failed"] == 0
    _write(execution / POST / "4.draft/draft.article.md", f"---\ntitle: 西湖速览\ncreatorProfileId: {CREATOR}\ntagRefs: [Entity/地点/景区]\n---\n# 西湖速览\n\n绑定主页的合成文章。\n")
    for stage in ("1.download", "4.draft", "5.review"):
        payload = {"actor": REVIEWER if stage == "5.review" else AUTHOR, "verdict": "pass"}
        if stage == "5.review":
            payload["reviews"] = {POST: {"decision": "approved", "blockingIssues": [], "advisories": []}}
        seal.seal_stage(execution_id=execution_id, stage=stage, input_path=_write(tmp / f"article-{stage}.json", payload))
    project_publish_final_surface(execution_root=execution, object_dir=execution / POST, target_ref=POST, target=target, carrier="article")
    package = tmp / "post-package"
    transaction_id = canonical_transaction_id(execution_id=execution_id, object_kind="posts", object_ref=POST.removeprefix("posts/"))
    build_post_object_transaction_package(execution_root=execution, object_ref=POST.removeprefix("posts/"), transaction_id=transaction_id, package_root=package)
    audit = audit_object_transaction(publish_root=active, output_root=tmp / "post-output", package_root=package, transaction_id=transaction_id, expected_canonical_merkle=load_or_bootstrap_inventory(active)["stats"]["merkleRoot"])
    apply_object_transaction(publish_root=active, output_root=tmp / "post-output", package_root=package, transaction_id=transaction_id, dry_run_attestation_sha256=audit["dryRunAttestationSha256"])
    assert subject.query_pool(active)["counts"]["article"] == 1
    return package


def _prepared_successor(active: Path, package: Path, tmp: Path) -> tuple[Path, Path]:
    # 存储边界构造显式新版本 staging；cutover 只消费它，不代替 author/reviewer。
    stage = tmp / "staging"
    shutil.copytree(active, stage)
    successor = tmp / "successor-package"
    shutil.copytree(package, successor)
    for root in (stage / HOME, successor / "object"):
        document = _read_json(root / "manifest.json")
        document["version"] = 2
        _write(root / "manifest.json", document)
        record_path = root / "_pool/versions/1.json"
        record_path.unlink()
        record = build_canonical_pool_record(object_root=root, object_type="homepage", object_ref=HOME.removeprefix("entities/"))
        assert_valid(record, "release", "pool_object_record")
        _write(record_path, record)
    for root in (stage / "creators" / CREATOR, successor / "creator_objects" / CREATOR):
        profile = _read_json(root / "profile.json")
        profile["version"] = 2
        _write(root / "profile.json", profile)
    document = _read_json(successor / "object_transaction_package.json")
    for row in document["closure"]["creatorObjects"]:
        row["treeDigest"] = _tree_digest(successor / row["packageRef"])
    document["objectClosureDigest"] = _closure_digest(
        object_root=successor / "object", object_kind="entities", object_ref=HOME.removeprefix("entities/"), target_schema="quwoquan_data.entity_object", source_policy_revision=document["sourcePolicyRevision"], closure=document["closure"], cas_rows=document["closure"]["casRefs"], review=_review_binding(successor / "object", document),
    )
    _write(successor / "object_transaction_package.json", document)
    return stage, successor


def _authorize(case: dict) -> dict:
    _write(case["plan_path"], case["plan"])
    digest = _digest_file(case["plan_path"])
    authorization = _write(case["tmp"] / "authorization.json", {"schema": "quwoquan_data.pool_cutover_authorization.v1", "planDigest": digest, "operations": ["dry_run", "activate"], "deleteObjectRefs": sorted(row["before"]["objectRef"] for row in case["plan"]["objects"] if row["action"] == "delete")})
    case["kwargs"] = {"plan_path": case["plan_path"], "expected_plan_digest": digest, "authorization": _binding(authorization), "evidence_path": case["tmp"] / "dry-run.json"}
    return case


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    tmp = tmp_path.resolve()
    execution = _execution(tmp, monkeypatch)
    active, package = _publish(tmp, execution)
    stage, successor = _prepared_successor(active, package, tmp)
    before = subject.snapshot_pool(active)
    after = {row["objectRef"]: row for row in subject.snapshot_pool(stage)["objects"]}
    authority = paths.CONTROL_PLANE_CREATOR_POOL_ROOT / "evidence/system_builtin_author_admission.json"
    rows = []
    for row in before["objects"]:
        evidence = [_binding(authority, role="author_authority")] if row["objectRef"].startswith("creators/") else [_binding(execution, role="execution"), _binding(successor, role="package")]
        rows.append({"before": row, "action": "migrate", "after": after[row["objectRef"]], "evidence": evidence})
    protected = _write(tmp / "old-release.json", {"historical": "unaltered bytes"})
    plan = {"schema": "quwoquan_data.pool_cutover.v1", "cutoverId": "test-cutover", "publishRoot": str(active), "stagingRoot": str(stage), "beforeDigest": before["treeDigest"], "afterDigest": _tree_digest(stage), "objects": rows, "protected": [{**_binding(protected), "kind": "file", "category": "release"}]}
    return _authorize({"tmp": tmp, "active": active, "stage": stage, "execution": execution, "package": successor, "plan": plan, "plan_path": tmp / "plan.json"})


def test_dry_run_validates_real_transaction_and_never_activates(case: dict) -> None:
    before = _tree_digest(case["active"])
    stage = _tree_digest(case["stage"])
    inventory = canonical_inventory_path(case["active"])
    cache_digest = _digest_file(inventory)
    result = subject.dry_run_pool_cutover(**case["kwargs"])
    assert result["report"]["status"] == "validated_not_activated"
    assert result["report"]["stagingQuery"]["counts"]["homepage"] == 1
    assert _tree_digest(case["active"]) == before
    assert _tree_digest(case["stage"]) == stage
    assert _digest_file(inventory) == cache_digest
    assert not canonical_inventory_path(case["stage"]).exists()
    activation = {key: value for key, value in case["kwargs"].items() if key != "evidence_path"}
    with pytest.raises(subject.PoolCutoverError, match="PROTECTION_AUTHORITY_REQUIRED"):
        subject.activate_pool_cutover(**activation, dry_run_evidence=result["evidence"])
    assert _tree_digest(case["active"]) == before
    assert _tree_digest(case["stage"]) == stage


@pytest.mark.parametrize("root,code", [("active", "BEFORE_CAS_MISMATCH"), ("stage", "STAGING_CAS_MISMATCH")])
def test_cas_drift_has_no_partial_tree(case: dict, root: str, code: str) -> None:
    _write(case[root] / HOME / "page.md", "故障注入：实际字节漂移")
    before, after = _tree_digest(case["active"]), _tree_digest(case["stage"])
    with pytest.raises(subject.PoolCutoverError, match=code):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert (_tree_digest(case["active"]), _tree_digest(case["stage"])) == (before, after)
    assert not case["kwargs"]["evidence_path"].exists()


def _activation_case(case: dict, monkeypatch: pytest.MonkeyPatch) -> dict:
    from content.release.canonical.object_transaction_contract import _digest_bytes
    tmp = case["tmp"]
    monkeypatch.setattr(paths, "RELEASE_ROOT", tmp / "releases")
    monkeypatch.setattr(paths, "REFERENCE_RELEASES_ROOT", tmp / "release-references")
    for root in (tmp / "library", tmp / "golden_media", paths.RELEASE_ROOT, paths.REFERENCE_RELEASES_ROOT):
        root.mkdir(exist_ok=True)
    protected = []
    for category, root in (("media_library", tmp / "library"), ("golden_media", tmp / "golden_media"), ("release", paths.RELEASE_ROOT), ("release", paths.REFERENCE_RELEASES_ROOT)):
        protected.append({**_binding(root), "kind": "tree", "category": category})
    for category in ("receipt", "rollback", "environment_binding"):
        protected.append({**_binding(_write(tmp / f"{category}.json", {"fixture": category})), "kind": "file", "category": category})
    case["plan"]["protected"] = protected
    authority = _write(tmp / "protection.json", {"schema": "quwoquan_data.pool_cutover_protection.v1", "cutoverId": case["plan"]["cutoverId"], "beforeDigest": case["plan"]["beforeDigest"], "afterDigest": case["plan"]["afterDigest"], "protectedDigest": _digest_bytes(_json_bytes(protected)), "scope": "complete_release_rollback_environment_media_closure", "issuer": "local-fixture-owner"})
    audit = tmp / "audit"
    audit.mkdir()
    case["plan"]["activation"] = {"auditRoot": str(audit), "protectionAuthority": _binding(authority)}
    _authorize(case)
    dry_run = subject.dry_run_pool_cutover(**case["kwargs"])
    case["activate"] = {**{key: value for key, value in case["kwargs"].items() if key != "evidence_path"}, "dry_run_evidence": dry_run["evidence"]}
    case["audit"] = audit
    return case


def _inspect(case: dict) -> dict:
    return subject.inspect_pool_cutover(plan_path=case["plan_path"], expected_plan_digest=case["kwargs"]["expected_plan_digest"], intent=_binding(case["audit"] / "intent.json"))


def test_atomic_activation_retires_original_bytes_and_invalidates_inventory(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    case = _activation_case(case, monkeypatch)
    protected = {row["ref"]: row["digest"] for row in case["plan"]["protected"]}
    result = subject.activate_pool_cutover(**case["activate"])
    assert result["report"]["status"] == "activated"
    assert _tree_digest(case["active"]) == case["plan"]["afterDigest"]
    assert not case["stage"].exists()
    assert _tree_digest(case["audit"] / "retired") == case["plan"]["beforeDigest"]
    assert not canonical_inventory_path(case["active"]).exists()
    assert _inspect(case)["status"] == "activated"
    assert {row["ref"]: _binding(Path(row["ref"]))["digest"] for row in case["plan"]["protected"]} == protected
    # 下一次 canonical writer 只能从新完整树 bootstrap，而不能消费旧缓存。
    index = load_or_bootstrap_inventory(case["active"])
    assert index


def _activation_child(arguments: dict, path_values: dict, checkpoint: str | None) -> None:
    import os
    from content.release.canonical import pool_cutover_activation as activation
    # fresh spawn 不继承父进程的锁/线程；只传 fixture 的明确路径配置。
    with pytest.MonkeyPatch.context() as patch:
        _isolate_library(patch, path_values["LIBRARY_ROOT"])
        for name, value in path_values.items():
            patch.setattr(paths, name, value)
        def crash(name):
            if name == checkpoint:
                os._exit(73)
        patch.setattr(activation, "_checkpoint", crash)
        try:
            subject.activate_pool_cutover(**arguments)
        except (subject.PoolCutoverError, OSError):
            import traceback
            traceback.print_exc()
            os._exit(75)
        except BaseException:
            import traceback
            traceback.print_exc()
            os._exit(76)


def _start_activation(case: dict, checkpoint: str | None = None):
    import multiprocessing
    names = ("OUTPUT_ROOT", "DATA_EXECUTIONS_ROOT", "DATA_LOCAL_ROOT", "CANONICAL_PUBLISH_SIDECAR_ROOT",
             "RELEASE_ROOT", "REFERENCE_RELEASES_ROOT", "LIBRARY_ROOT")
    process = multiprocessing.get_context("spawn").Process(
        target=_activation_child, args=(case["activate"], {name: getattr(paths, name) for name in names}, checkpoint),
    )
    process.start()
    return process


def _exit_code(process):
    process.join(timeout=45)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail("隔离迁移子进程未在边界内结束")
    return process.exitcode


@pytest.mark.parametrize("checkpoint,expected", [("after_intent", "not_activated"), ("before_exchange", "not_activated"), ("after_exchange", "activated"), ("after_retire", "activated")])
def test_process_crash_has_one_complete_tree_and_readonly_recovery(case: dict, monkeypatch: pytest.MonkeyPatch, checkpoint: str, expected: str) -> None:
    case = _activation_case(case, monkeypatch)
    assert _exit_code(_start_activation(case, checkpoint)) == 73
    before = _tree_digest(case["tmp"])
    assert _inspect(case)["status"] == expected
    assert _tree_digest(case["tmp"]) == before  # 无 lock 创建/receipt/cache 写入。
    assert _tree_digest(case["active"]) == case["plan"]["beforeDigest" if expected == "not_activated" else "afterDigest"]


def test_concurrent_activation_has_exactly_one_winner(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    case = _activation_case(case, monkeypatch)
    children = [_start_activation(case) for _ in range(2)]
    assert sorted(_exit_code(child) for child in children) == [0, 75]
    assert _inspect(case)["status"] == "activated"
    assert _tree_digest(case["active"]) == case["plan"]["afterDigest"]


def test_precommit_cas_drift_preserves_both_trees(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from content.release.canonical import pool_cutover_activation as activation
    case = _activation_case(case, monkeypatch)
    def drift(name):
        if name == "before_exchange":
            _write(case["active"] / HOME / "page.md", "concurrent canonical drift")
    monkeypatch.setattr(activation, "_checkpoint", drift)
    with pytest.raises(subject.PoolCutoverError, match="BEFORE_CAS_MISMATCH"):
        subject.activate_pool_cutover(**case["activate"])
    assert _tree_digest(case["stage"]) == case["plan"]["afterDigest"]
    assert not (case["audit"] / "activated.json").exists()
    assert _inspect(case)["status"] == "conflict"


def test_exact_cleanup_preserves_archive_and_all_media(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    case = _activation_case(case, monkeypatch)
    subject.activate_pool_cutover(**case["activate"])
    intent = _binding(case["audit"] / "intent.json")
    archive = _binding(case["audit"] / "before.tar")
    authorization = _write(case["tmp"] / "cleanup-authority.json", {"schema": "quwoquan_data.pool_cutover_cleanup.v1", "operation": "remove_exact_retired_tree", "planDigest": case["kwargs"]["expected_plan_digest"], "intentDigest": intent["digest"], "archiveDigest": archive["digest"], "beforeDigest": case["plan"]["beforeDigest"]})
    result = subject.cleanup_pool_cutover(plan_path=case["plan_path"], expected_plan_digest=case["kwargs"]["expected_plan_digest"], intent=intent, authorization=_binding(authorization))
    assert result and not (case["audit"] / "retired").exists()
    assert _binding(case["audit"] / "before.tar") == archive
    assert _inspect(case)["status"] == "activated"
    for row in case["plan"]["protected"]:
        assert _binding(Path(row["ref"]))["digest"] == row["digest"]


def test_unsupported_exchange_never_falls_back(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from content.release.canonical import pool_cutover_storage as storage
    case = _activation_case(case, monkeypatch)
    monkeypatch.setattr(storage.sys, "platform", "unsupported-platform")
    with pytest.raises(subject.PoolCutoverError, match="ATOMIC_EXCHANGE_UNSUPPORTED"):
        subject.activate_pool_cutover(**case["activate"])
    assert not list(case["audit"].iterdir())
    assert _tree_digest(case["active"]) == case["plan"]["beforeDigest"]


@pytest.mark.parametrize("fault", ["authorization", "protection", "stage", "archive"])
def test_activation_faults_fail_before_exchange(case: dict, monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    from content.release.canonical import pool_cutover_activation as activation
    case = _activation_case(case, monkeypatch)
    original = _tree_digest(case["active"])
    def mutate(name):
        if name != "before_exchange":
            return
        target = {"authorization": Path(case["activate"]["authorization"]["ref"]), "protection": case["tmp"] / "environment_binding.json", "stage": case["stage"] / HOME / "page.md", "archive": case["audit"] / "before.tar"}[fault]
        target.write_bytes(b"drift")
    monkeypatch.setattr(activation, "_checkpoint", mutate)
    with pytest.raises(subject.PoolCutoverError):
        subject.activate_pool_cutover(**case["activate"])
    assert _tree_digest(case["active"]) == original
    assert not (case["audit"] / "activated.json").exists()


def test_postcommit_failure_reports_outcome_without_reverse_swap(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from content.release.canonical import pool_cutover_activation as activation
    case = _activation_case(case, monkeypatch)
    def fail(name):
        if name == "after_exchange":
            raise OSError("injected after commit fsync failure")
    monkeypatch.setattr(activation, "_checkpoint", fail)
    with pytest.raises(subject.PoolCutoverError, match="COMMIT_OUTCOME_REQUIRES_INSPECTION"):
        subject.activate_pool_cutover(**case["activate"])
    assert _inspect(case)["status"] == "activated"
    assert _tree_digest(case["stage"]) == case["plan"]["beforeDigest"]
    assert not canonical_inventory_path(case["active"]).exists()


@pytest.mark.parametrize("fault", ["wrong_archive_authorization", "retired_symlink", "archive_drift"])
def test_cleanup_rejects_wrong_authority_or_changed_bytes(case: dict, monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    case = _activation_case(case, monkeypatch)
    subject.activate_pool_cutover(**case["activate"])
    intent = _binding(case["audit"] / "intent.json")
    archive = _binding(case["audit"] / "before.tar")
    authorization = _write(case["tmp"] / "cleanup-authority.json", {"schema": "quwoquan_data.pool_cutover_cleanup.v1", "operation": "remove_exact_retired_tree", "planDigest": case["kwargs"]["expected_plan_digest"], "intentDigest": intent["digest"], "archiveDigest": "sha256:" + "0" * 64 if fault == "wrong_archive_authorization" else archive["digest"], "beforeDigest": case["plan"]["beforeDigest"]})
    if fault == "retired_symlink":
        (case["audit"] / "retired/forbidden").symlink_to(case["tmp"] / "library", target_is_directory=True)
    if fault == "archive_drift":
        (case["audit"] / "before.tar").write_bytes(b"corrupt")
    with pytest.raises(subject.PoolCutoverError):
        subject.cleanup_pool_cutover(plan_path=case["plan_path"], expected_plan_digest=case["kwargs"]["expected_plan_digest"], intent=intent, authorization=_binding(authorization))
    assert (case["audit"] / "retired" / HOME / "page.md").exists()
    assert _tree_digest(case["active"]) == case["plan"]["afterDigest"]


def _media_package(case: dict, carrier: str) -> tuple[Path, str, Path]:
    from PIL import Image
    import subprocess
    from content.release.canonical.post_transaction_assets import source_assets
    tmp = case["tmp"]
    execution_id = f"20260909--travel-{carrier}-cutover--local--pilot-003"
    target = {"name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市", "publishAngle": "风光", "publishTitle": "西湖作品", "publishSeq": 1}
    ref = f"posts/{carrier}/风光/西湖作品/1"
    task_init.initialize_execution(submitted_demand={"schema": "quwoquan_data.carrier_demand", "executionId": execution_id, "carrier": carrier, "familyRef": f"content/travel/{carrier}/{carrier}"}, submitted_bindings={"schema": "quwoquan_data.immutable_candidate_bindings", "executionId": execution_id, "carrier": carrier, "targets": [target]})
    execution = paths.execution_root(execution_id)
    media = tmp / ("local.jpg" if carrier == "image" else "local.mp4")
    if carrier == "image":
        Image.new("RGB", (80, 60), (20, 50, 70)).save(media)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(media)], check=True, capture_output=True)
    source = {"kind": carrier, "sourceUrl": "https://commons.wikimedia.org/wiki/File:Local", "directUrl": f"https://upload.wikimedia.org/local/{media.name}", "filePath": str(media), "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "测试摄影师", "description": "本地合成作品", "relevance": "本地来源事实", "watermarkStatus": "absent", "watermarkKind": "none"}
    if carrier == "video":
        source["hasAudio"] = False
    request = _write(tmp / "media-ingest.json", {"schema": "quwoquan_data.ingest_manifest", "executionId": execution_id, "targets": [{"targetRef": ref, "sources": [source]}]})
    acquired = acquire.acquire(execution_id=execution_id, request_path=request)
    assert acquired["failed"] == 0, acquired
    draft = {"title": "西湖作品", "caption": "合成作品说明", "creatorProfileId": CREATOR, "tagRefs": ["Entity/地点/景区"]}
    if carrier == "image":
        draft["assetRefs"] = sorted(source_assets(execution))
    else:
        draft["scriptLines"] = ["合成视频脚本"]
    _write(execution / ref / "4.draft" / ("image_work.json" if carrier == "image" else "video_script.json"), draft)
    for stage in ("1.download", "4.draft", "5.review"):
        payload = {"actor": REVIEWER if stage == "5.review" else AUTHOR, "verdict": "pass"}
        if stage == "5.review":
            payload["reviews"] = {ref: {"decision": "approved", "blockingIssues": [], "advisories": []}}
        seal.seal_stage(execution_id=execution_id, stage=stage, input_path=_write(tmp / f"media-{stage}.json", payload))
    project_publish_final_surface(execution_root=execution, object_dir=execution / ref, target_ref=ref, target=target, carrier=carrier)
    package = tmp / "media-package"
    transaction_id = canonical_transaction_id(execution_id=execution_id, object_kind="posts", object_ref=ref.removeprefix("posts/"))
    build_post_object_transaction_package(execution_root=execution, object_ref=ref.removeprefix("posts/"), transaction_id=transaction_id, package_root=package)
    return execution, ref, package


@pytest.mark.parametrize("carrier", ["image", "video"])
def test_real_json_projection_checks_author_and_canonical_surface(case: dict, carrier: str) -> None:
    execution, ref, package = _media_package(case, carrier)
    manifest = _read_json(package / "object/manifest.json")
    before = _tree_digest(execution)
    subject._verify_json_surface(execution, ref, manifest)
    assert _tree_digest(execution) == before
    import copy
    for key in ("sourceAssetRefs", "acquisitionReceiptRefs", "derivativeBinding", "sha256", "bytes", "caption"):
        changed = copy.deepcopy(manifest)
        changed["assets"][0][key] = ["invented"] if key.endswith("Refs") else "unreviewed"
        with pytest.raises(subject.PoolCutoverError, match="REVIEWED_SURFACE_DRIFT"):
            subject._verify_json_surface(execution, ref, changed)
    manifest["caption"] = "只刷新摘要无法产生这一未经 review 的新说明"
    with pytest.raises(subject.PoolCutoverError, match="REVIEWED_SURFACE_DRIFT"):
        subject._verify_json_surface(execution, ref, manifest)
    assert _tree_digest(execution) == before


@pytest.mark.parametrize("carrier", ["image", "video"])
def test_complete_media_pool_can_activate_new_versions(case: dict, monkeypatch: pytest.MonkeyPatch, carrier: str) -> None:
    execution, ref, package = _media_package(case, carrier)
    transaction_id = _read_json(package / "object_transaction_package.json")["transactionId"]
    audit = audit_object_transaction(publish_root=case["active"], output_root=case["tmp"] / "media-output", package_root=package, transaction_id=transaction_id, expected_canonical_merkle=load_or_bootstrap_inventory(case["active"])["stats"]["merkleRoot"])
    apply_object_transaction(publish_root=case["active"], output_root=case["tmp"] / "media-output", package_root=package, transaction_id=transaction_id, dry_run_attestation_sha256=audit["dryRunAttestationSha256"])
    shutil.copytree(case["active"] / ref, case["stage"] / ref)
    for root in (package / "object", case["stage"] / ref):
        manifest = _read_json(root / "manifest.json")
        manifest["version"] = 2
        _write(root / "manifest.json", manifest)
        (root / "_pool/versions/1.json").unlink()
        _write(root / "_pool/versions/1.json", build_canonical_pool_record(object_root=root, object_type="content", object_ref=ref.removeprefix("posts/")))
    document = _read_json(package / "object_transaction_package.json")
    for row in document["closure"]["creatorObjects"]:
        profile_path = package / row["packageRef"] / "profile.json"
        profile = _read_json(profile_path)
        profile["version"] = 2
        _write(profile_path, profile)
        row["treeDigest"] = _tree_digest(profile_path.parent)
    document["objectClosureDigest"] = _closure_digest(object_root=package / "object", object_kind="posts", object_ref=ref.removeprefix("posts/"), target_schema=document["target"]["objectSchema"], source_policy_revision=document["sourcePolicyRevision"], closure=document["closure"], cas_rows=document["closure"]["casRefs"], review=_review_binding(package / "object", document))
    _write(package / "object_transaction_package.json", document)
    before = subject.snapshot_pool(case["active"])
    after = subject.snapshot_pool(case["stage"])
    case["plan"]["beforeDigest"], case["plan"]["afterDigest"] = before["treeDigest"], after["treeDigest"]
    case["plan"]["objects"].append({"before": next(row for row in before["objects"] if row["objectRef"] == ref), "after": next(row for row in after["objects"] if row["objectRef"] == ref), "action": "migrate", "evidence": [_binding(execution, role="execution"), _binding(package, role="package")]})
    _activation_case(case, monkeypatch)
    subject.activate_pool_cutover(**case["activate"])
    assert subject.query_pool(case["active"])["counts"][carrier] == 1
    assert _read_json(case["active"] / ref / "manifest.json")["version"] == 2
    assert _inspect(case)["status"] == "activated"


def test_pool_placeholders_and_author_are_not_omitted(case: dict) -> None:
    placeholder = case["active"] / "posts/article/缺失/孤儿/1/_pool"
    placeholder.mkdir(parents=True)
    snapshot = subject.snapshot_pool(case["active"])
    assert len(snapshot["objects"]) == 3
    case["plan"]["beforeDigest"] = snapshot["treeDigest"]
    _authorize(case)
    with pytest.raises(subject.PoolCutoverError, match="COVERAGE_MISMATCH"):
        subject.dry_run_pool_cutover(**case["kwargs"])


@pytest.mark.parametrize("mutation,code", [("omit", "COVERAGE_MISMATCH"), ("duplicate", "COVERAGE_MISMATCH"), ("same_version", "AFTER_OBJECT_DRIFT"), ("unknown_field", "SCHEMA_INVALID")])
def test_exact_plan_rejects_ambiguous_actions(case: dict, mutation: str, code: str) -> None:
    rows = case["plan"]["objects"]
    if mutation == "omit":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif mutation == "same_version":
        rows[-1]["after"]["identity"]["contentVersion"] = 1
    else:
        rows[-1]["override"] = True
    _authorize(case)
    before = _tree_digest(case["active"])
    with pytest.raises(subject.PoolCutoverError, match=code):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert _tree_digest(case["active"]) == before


def test_stage_inside_active_and_output_inside_active_fail_before_write(case: dict) -> None:
    case["plan"]["stagingRoot"] = str(case["active"] / HOME)
    _authorize(case)
    with pytest.raises(subject.PoolCutoverError, match="PATH_OVERLAP"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    case["plan"]["stagingRoot"] = str(case["stage"])
    _authorize(case)
    case["kwargs"]["evidence_path"] = case["active"] / "should-not-exist.json"
    with pytest.raises(subject.PoolCutoverError, match="PATH_OVERLAP"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert not case["kwargs"]["evidence_path"].exists()


def test_evidence_digest_and_exact_authorization_are_required(case: dict) -> None:
    case["kwargs"]["expected_plan_digest"] = "sha256:" + "f" * 64
    with pytest.raises(subject.PoolCutoverError, match="EVIDENCE_DIGEST_DRIFT"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    _authorize(case)
    path = Path(case["kwargs"]["authorization"]["ref"])
    document = _read_json(path)
    document["deleteObjectRefs"] = [HOME]
    _write(path, document)
    case["kwargs"]["authorization"] = _binding(path)
    with pytest.raises(subject.PoolCutoverError, match="AUTHORIZATION_MISMATCH"):
        subject.dry_run_pool_cutover(**case["kwargs"])


def test_symlink_in_staging_is_rejected(case: dict) -> None:
    target = case["stage"] / HOME / "symlink.json"
    target.symlink_to(case["tmp"] / "old-release.json")
    with pytest.raises(subject.PoolCutoverError, match="SYMLINK_FORBIDDEN"):
        subject.dry_run_pool_cutover(**case["kwargs"])


def _refresh_stage(case: dict) -> None:
    current = {row["objectRef"]: row for row in subject.snapshot_pool(case["stage"])["objects"]}
    case["plan"]["afterDigest"] = _tree_digest(case["stage"])
    for action in case["plan"]["objects"]:
        if action["action"] == "migrate":
            action["after"] = current[action["after"]["objectRef"]]
    _authorize(case)


@pytest.mark.parametrize("field,value,code", [("usageScope", "research", "RECORD_USAGE_SCOPE_INVALID"), ("rightsResult", "failed", "RECORD_RIGHTS_INVALID"), ("payloadDigest", "sha256:" + "f" * 64, "CANONICAL_DIGEST_DRIFT")])
def test_new_staging_schema_and_rights_reject_old_or_forged_records(case: dict, field: str, value: str, code: str) -> None:
    record_path = case["stage"] / HOME / "_pool/versions/1.json"
    record = _read_json(record_path)
    record[field] = value
    _write(record_path, record)
    _refresh_stage(case)
    before = _tree_digest(case["active"])
    with pytest.raises(subject.PoolCutoverError, match=code):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert _tree_digest(case["active"]) == before


def test_refreshed_payload_cannot_replace_independent_review_evidence(case: dict) -> None:
    root = case["stage"] / HOME
    _write(root / "page.md", "偷偷替换未被 reviewer 看过的正文")
    (root / "_pool/versions/1.json").unlink()
    _write(root / "_pool/versions/1.json", build_canonical_pool_record(object_root=root, object_type="homepage", object_ref=HOME.removeprefix("entities/")))
    _refresh_stage(case)
    with pytest.raises(subject.PoolCutoverError, match="PACKAGE_PAYLOAD_DRIFT"):
        subject.dry_run_pool_cutover(**case["kwargs"])


def test_sources_and_asset_order_cannot_drift_even_when_after_is_exact(case: dict) -> None:
    root = case["stage"] / HOME
    document = _read_json(root / "manifest.json")
    document["sourceAttribution"]["sourcePostUrl"] = "https://zh.wikipedia.org/wiki/其他地点"
    _write(root / "manifest.json", document)
    _refresh_stage(case)
    with pytest.raises(subject.PoolCutoverError, match="SOURCE_IDENTITY_DRIFT"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    # 来源资产顺序单独绑定，即便两张引用都保持原始身份也不可对换。
    assets = [{"assetId": "one", "sha256": "sha256:" + "1" * 64}, {"assetId": "two", "sha256": "sha256:" + "2" * 64}]
    assert subject._source_digest({"assets": assets}) != subject._source_digest({"assets": list(reversed(assets))})


def test_migration_source_digest_normalizes_only_structural_aliases() -> None:
    # manifest 单源转换不应把 singular→plural 机械归一误判为来源漂移。
    original = {"sourceAttribution": {"publicationAdmission": "research_release", "riskAcceptanceId": None},
                "assets": [{"assetId": "stable", "sha256": "sha256:" + "1" * 64,
                            "collectionPageUrl": "https://example.org/work", "sourceAssetRef": "sources/a/assets/a.jpg"}]}
    converted = copy.deepcopy(original)
    converted["sourceAttribution"] = {"publicationAdmission": "production_release"}
    converted["assets"][0]["sourceAssetRefs"] = [converted["assets"][0].pop("sourceAssetRef")]
    assert subject._source_digest(original) == subject._source_digest(converted)
    for field, value in (("sourceAssetRefs", ["sources/other/assets/a.jpg"]),
                         ("collectionPageUrl", "https://example.org/other-work"), ("assetId", "alias")):
        changed = copy.deepcopy(converted)
        changed["assets"][0][field] = value
        assert subject._source_digest(original) != subject._source_digest(changed)
    changed = copy.deepcopy(converted)
    changed["sourceAttribution"]["riskAcceptanceId"] = "non-null-original-fact"
    assert subject._source_digest(original) != subject._source_digest(changed)


def test_exact_deletion_of_missing_manifest_placeholder_is_validated_only(case: dict) -> None:
    ref = "posts/article/缺失/孤儿/1"
    (case["active"] / ref / "_pool").mkdir(parents=True)
    before = subject.snapshot_pool(case["active"])
    row = next(row for row in before["objects"] if row["objectRef"] == ref)
    decision = _write(case["tmp"] / "delete-decision.json", {"objectRef": ref, "decision": "delete", "reason": "缺 manifest 与可核验身份"})
    case["plan"]["objects"].append({"before": row, "action": "delete", "after": None, "evidence": [_binding(decision, role="decision")]})
    case["plan"]["beforeDigest"] = before["treeDigest"]
    _authorize(case)
    result = subject.dry_run_pool_cutover(**case["kwargs"])
    assert result["report"]["objects"][-1]["action"] == "delete"
    assert (case["active"] / ref / "_pool").is_dir()


def test_deleting_homepage_cannot_leave_real_transaction_post_dangling(case: dict) -> None:
    _dependent_post(case)
    before = subject.snapshot_pool(case["active"])
    post_before = next(row for row in before["objects"] if row["objectRef"] == POST)
    assert HOME in post_before["dependencyRefs"]
    destination = case["stage"] / POST
    shutil.copytree(case["active"] / POST, destination)
    document = _read_json(destination / "manifest.json")
    document["version"] = 2
    _write(destination / "manifest.json", document)
    # 只在隔离 staging 注入缺依赖；真实 active 及旧审计完全不删。
    shutil.rmtree(case["stage"] / HOME)
    decision = _write(case["tmp"] / "homepage-delete.json", {"objectRef": HOME, "decision": "delete", "reason": "测试显式退役"})
    for action in case["plan"]["objects"]:
        if action["before"]["objectRef"] == HOME:
            action.update(action="delete", after=None, evidence=[_binding(decision, role="decision")])
    after = next(row for row in subject.snapshot_pool(case["stage"])["objects"] if row["objectRef"] == POST)
    case["plan"]["objects"].append({"before": post_before, "action": "migrate", "after": after, "evidence": [_binding(decision, role="decision")]})
    case["plan"]["beforeDigest"] = before["treeDigest"]
    _refresh_stage(case)
    unchanged = _tree_digest(case["active"])
    with pytest.raises(subject.PoolCutoverError, match="DEPENDENCY_MISSING"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert _tree_digest(case["active"]) == unchanged


def test_all_delete_plan_cannot_empty_pool(case: dict) -> None:
    for action in case["plan"]["objects"]:
        action.update(action="delete", after=None)
    empty = case["tmp"] / "empty-stage"
    empty.mkdir()
    case["plan"].update(stagingRoot=str(empty), afterDigest=_tree_digest(empty))
    _authorize(case)
    with pytest.raises(subject.PoolCutoverError, match="EMPTY_POOL_FORBIDDEN"):
        subject.dry_run_pool_cutover(**case["kwargs"])


def test_protected_exact_bytes_changed_after_plan_fail_closed(case: dict) -> None:
    _write(case["tmp"] / "old-release.json", {"historical": "fault"})
    with pytest.raises(subject.PoolCutoverError, match="EVIDENCE_DIGEST_DRIFT"):
        subject.dry_run_pool_cutover(**case["kwargs"])


def test_staging_hardlink_cannot_alias_active_metadata(case: dict) -> None:
    import os
    path = case["stage"] / HOME / "page.md"
    path.unlink()
    os.link(case["active"] / HOME / "page.md", path)
    with pytest.raises(subject.PoolCutoverError, match="HARDLINK_ALIAS"):
        subject.dry_run_pool_cutover(**case["kwargs"])


def test_dry_run_evidence_never_overwrites_existing_audit(case: dict) -> None:
    path = case["kwargs"]["evidence_path"]
    _write(path, {"old": "receipt exact bytes"})
    digest = _digest_file(path)
    with pytest.raises(subject.PoolCutoverError, match="EVIDENCE_DESTINATION_INVALID"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert _digest_file(path) == digest


def test_shared_lock_rechecks_before_digest(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager
    real_lock = subject.canonical_publish_lock
    @contextmanager
    def concurrent_write(root):
        with real_lock(root):
            _write(case["active"] / HOME / "page.md", "模拟拿锁前发生正常并发写入")
            yield
    monkeypatch.setattr(subject, "canonical_publish_lock", concurrent_write)
    with pytest.raises(subject.PoolCutoverError, match="BEFORE_CAS_MISMATCH"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert not case["kwargs"]["evidence_path"].exists()


def test_cross_device_staging_fails_before_any_output(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    original = Path.stat
    def other_device(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == case["stage"]:
            return SimpleNamespace(st_mode=result.st_mode, st_dev=result.st_dev + 1)
        return result
    monkeypatch.setattr(Path, "stat", other_device)
    with pytest.raises(subject.PoolCutoverError, match="CROSS_DEVICE"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert not case["kwargs"]["evidence_path"].exists()


def test_evidence_destination_never_writes_media_holder(case: dict) -> None:
    (case["tmp"] / "library").mkdir(exist_ok=True)
    case["kwargs"]["evidence_path"] = case["tmp"] / "library" / "forbidden.json"
    with pytest.raises(subject.PoolCutoverError, match="PATH_OVERLAP"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert not case["kwargs"]["evidence_path"].exists()


def test_staging_cached_inventory_is_not_trusted_or_deleted(case: dict) -> None:
    load_or_bootstrap_inventory(case["stage"])
    cache = canonical_inventory_path(case["stage"])
    digest = _digest_file(cache)
    before, after = _tree_digest(case["active"]), _tree_digest(case["stage"])
    with pytest.raises(subject.PoolCutoverError, match="STAGING_INVENTORY_UNVERIFIED"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert _digest_file(cache) == digest
    assert (_tree_digest(case["active"]), _tree_digest(case["stage"])) == (before, after)
    assert not case["kwargs"]["evidence_path"].exists()


def test_creator_profile_must_satisfy_new_schema(case: dict) -> None:
    root = case["stage"] / "creators" / CREATOR
    profile = _read_json(root / "profile.json")
    profile["admission"]["usageScope"] = "research"
    _write(root / "profile.json", profile)
    _refresh_stage(case)
    with pytest.raises(subject.PoolCutoverError, match="AUTHOR_ADMISSION_SCHEMA_INVALID"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert not case["kwargs"]["evidence_path"].exists()


def test_contradictory_delete_decision_is_rejected(case: dict) -> None:
    ref = "posts/article/缺失/孤儿/1"
    (case["active"] / ref / "_pool").mkdir(parents=True)
    before = subject.snapshot_pool(case["active"])
    row = next(row for row in before["objects"] if row["objectRef"] == ref)
    decision = _write(case["tmp"] / "delete-decision.json", {"objectRef": ref, "decision": "retain", "reason": "禁止删除"})
    case["plan"]["objects"].append({"before": row, "action": "delete", "after": None, "evidence": [_binding(decision, role="decision")]})
    case["plan"]["beforeDigest"] = before["treeDigest"]
    _authorize(case)
    with pytest.raises(subject.PoolCutoverError, match="DELETE_DECISION_MISMATCH"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert (case["active"] / ref / "_pool").is_dir()


def test_validation_fault_preserves_both_trees(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    before, after = _tree_digest(case["active"]), _tree_digest(case["stage"])
    def fault(_stage, **_kwargs):
        raise OSError("injected read failure")
    monkeypatch.setattr(subject, "query_pool", fault)
    with pytest.raises(subject.PoolCutoverError, match="injected read failure"):
        subject.dry_run_pool_cutover(**case["kwargs"])
    assert (_tree_digest(case["active"]), _tree_digest(case["stage"])) == (before, after)
    assert not case["kwargs"]["evidence_path"].exists()
