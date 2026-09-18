"""显式根、当前任务与批次围栏；正式 CLI 不存在缺环境变量的无保护分支。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, TypeVar

from .fence import WriteFenceToken
from .store import CoordinationError, CoordinationStore

R = TypeVar("R")
FENCE_ENV = "QWQ_CONTENT_WRITE_FENCE"
DB_ENV = "QWQ_CONTENT_COORDINATION_DB"
CLOSER_ENV = "QWQ_CONTENT_GLOBAL_CLOSER_DEPLOYMENT"


def _document(raw: str) -> object:
    if raw.lstrip().startswith(("{", "[")):
        return json.loads(raw)
    return json.loads(Path(raw).expanduser().read_bytes())


def actor_key(actor: dict) -> str:
    if not isinstance(actor, dict) or not isinstance(actor.get("invocation"), dict):
        raise CoordinationError("COORDINATION.ACTOR_IDENTITY_REQUIRED", "actor/invocation 必须为对象")
    values = (actor.get("host"), actor.get("sessionId"), (actor.get("invocation") or {}).get("runId"))
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise CoordinationError("COORDINATION.ACTOR_IDENTITY_REQUIRED", "host/sessionId/runId 必须完整")
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def member_key(actor_ref: str) -> tuple[str, str]:
    """已部署会话是容量身份；run 只属于本次写者和封存证据，不签发新名额。"""
    try:
        values = json.loads(actor_ref)
        if not isinstance(values, list) or len(values) != 3 or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("actor ref 必须为 host/sessionId/runId")
    except (TypeError, ValueError) as exc:
        raise CoordinationError("COORDINATION.INVALID_ROLE_BINDINGS", "actor ref 必须是完整会话绑定，不接受旧不透明单值") from exc
    return values[0], values[1]


def is_member(actor_ref: str, members) -> bool:
    return member_key(actor_ref) in {member_key(value) for value in members}


def read_task_context(ref, digest, roles):
    """消费现有任务输入内 coordination 字段，不创建第二授权文件。"""
    path = Path(ref)
    try:
        if path.is_symlink():
            raise OSError("任务引用不得为 symlink")
        raw = path.read_bytes()
        document = json.loads(raw)
        context = document["coordination"]
        if not isinstance(context, dict):
            raise TypeError("coordination 必须为对象")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CoordinationError("COORDINATION.TASK_CONTEXT_UNREADABLE", str(path)) from exc
    if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
        raise CoordinationError("COORDINATION.TASK_VERSION_STALE", str(path))
    if (type(context.get("version")) is not int or context["version"] < 1
            or not isinstance(context.get("confirmationRef"), str) or not context["confirmationRef"].strip()
            or context.get("confirmedBy") not in roles["director"]
            or not isinstance(context.get("allowedActions"), list)
            or not set(context["allowedActions"]) <= {"init", "acquire", "1.download", "4.draft", "5.review", "publish", "finalize", "repackage"}
            or not isinstance(context.get("revokedActors", []), list)):
        raise CoordinationError("COORDINATION.TASK_CONFIRMATION_REQUIRED", str(path))
    return context



def read_repackage_task_context(ref, digest, roles, *, authorization_ref: str, authorization_digest: str):
    path=Path(ref)
    try:
        if path.is_symlink(): raise OSError("task symlink")
        raw=path.read_bytes(); document=json.loads(raw)
        from core.schema import assert_valid
        assert_valid(document,"execution","repackage_task_context",label="repackage task context")
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise CoordinationError("COORDINATION.REPACKAGE_TASK_INVALID",str(path)) from exc
    if "sha256:"+hashlib.sha256(raw).hexdigest()!=digest:
        raise CoordinationError("COORDINATION.TASK_VERSION_STALE",str(path))
    context=document["coordination"]
    confirmation=Path(context["confirmationRef"])
    from .authority import verify_authority_artifact
    verify_authority_artifact(str(confirmation),context["confirmationDigest"],purpose="content-repackage-confirmation")
    verify_authority_artifact(authorization_ref,authorization_digest,purpose="content-repackage-user-authorization")
    if (context["confirmedBy"] not in roles["director"] or context["authorizationRef"]!=authorization_ref
            or context["authorizationDigest"]!=authorization_digest):
        raise CoordinationError("COORDINATION.REPACKAGE_AUTHORITY_MISMATCH",str(path))
    return context


def current_tokens() -> tuple[WriteFenceToken, ...]:
    raw = os.environ.get(FENCE_ENV, "").strip()
    db = os.environ.get(DB_ENV, "").strip()
    if not raw or not db:
        raise CoordinationError("COORDINATION.WRITE_FENCE_CONFIGURATION_INCOMPLETE", f"{FENCE_ENV} 与 {DB_ENV} 必须同时提供")
    if not Path(db).is_file():
        raise CoordinationError("COORDINATION.WRITE_FENCE_DATABASE_MISSING", db)
    try:
        value = _document(raw)
        values = value if isinstance(value, list) else [value]
        if not values or any(not isinstance(item, dict) for item in values):
            raise TypeError("fence 必须为非空对象或对象数组")
        return tuple(WriteFenceToken(**item) for item in values)
    except (OSError, TypeError, ValueError) as exc:
        raise CoordinationError("COORDINATION.WRITE_FENCE_INVALID", str(exc)) from exc


def execution_targets(execution_id):
    from content.execution.identity import validate_execution_id
    from core import paths
    from core.schema import assert_valid
    root = paths.DATA_EXECUTIONS_ROOT / validate_execution_id(execution_id)
    manifest = json.loads((root / "execution_manifest.json").read_bytes())
    raw = (root / "0.plan/target_set.json").read_bytes()
    value = json.loads(raw)
    assert_valid(value, "execution", "target_set", label="write fence target_set")
    if (value["executionId"] != execution_id or manifest["executionId"] != execution_id
            or manifest["targetSet"]["digest"] != "sha256:" + hashlib.sha256(raw).hexdigest()):
        raise CoordinationError("COORDINATION.EXECUTION_TARGET_DRIFT", execution_id)
    return value["targetRefs"]


def _receipt_targets(receipt, stage):
    marker = f"/{stage}/"
    return sorted({row["ref"].split(marker)[0] for row in receipt["resultRefs"] if marker in row["ref"]})


def batch_facts(batch, roots):
    """只读 formal chain/proof 核容量；缺失/unknown 保留名额，绝不写阶段或完成表。"""
    from content.execution.receipt_chain import validate_live_receipt_chain, validate_publish_review_chain
    root = Path(roots["output"]) / "data/tasks" / batch["execution_id"]
    result = {"author_sealed": False, "review_sealed": False, "closed": False, "review_targets": []}
    if not (root / "_shared/receipts/002-4.draft.json").is_file():
        return result
    frozen_raw = (root / "0.plan/target_set.json").read_bytes()
    manifest = json.loads((root / "execution_manifest.json").read_bytes())
    frozen = json.loads(frozen_raw)
    if (manifest["targetSet"]["digest"] != "sha256:" + hashlib.sha256(frozen_raw).hexdigest()
            or frozen["executionId"] != batch["execution_id"]
            or sorted(frozen["targetRefs"]) != sorted(batch["targets"])):
        raise CoordinationError("COORDINATION.RECEIPT_TARGET_DRIFT", batch["execution_id"])
    chain = validate_live_receipt_chain(execution_id=batch["execution_id"], execution_root=root)
    author = chain.receipts[1]
    if actor_key(author["actor"]) != batch["author"]:
        raise CoordinationError("COORDINATION.RECEIPT_ACTOR_DRIFT", batch["execution_id"])
    result["author_sealed"] = True
    result["review_targets"] = _receipt_targets(author, "4.draft")
    if not set(result["review_targets"]) <= set(batch["targets"]):
        raise CoordinationError("COORDINATION.RECEIPT_TARGET_DRIFT", batch["execution_id"])
    if len(chain.receipts) < 3:
        return result
    review = chain.receipts[2]
    if not batch["reviewer"] or actor_key(review["actor"]) != batch["reviewer"]:
        raise CoordinationError("COORDINATION.RECEIPT_ACTOR_DRIFT", batch["execution_id"])
    result["review_sealed"] = True
    # 全批 blocked/unknown 不推断原生终止。pass 批中逐对象 rejected 是已封存退轮，
    # 不是需要发布的有效对象；必须 exact 绑定、覆盖整批且有拒绝原因。
    if not result["review_targets"] or review["verdict"] != "pass":
        return result
    from core.schema import assert_valid
    from content.execution.receipt_chain import _independent_actors, digest_bytes
    from content.execution.workspace import target_descriptor_for
    _independent_actors(author["actor"], review["actor"])
    expected_reviews = {f"{ref}/5.review/content_review.json" for ref in result["review_targets"]}
    bindings = review["resultRefs"]
    if len(bindings) != len(expected_reviews) or {row["ref"] for row in bindings} != expected_reviews:
        raise CoordinationError("COORDINATION.RECEIPT_TARGET_DRIFT", batch["execution_id"])
    approved_targets = []
    for ref in result["review_targets"]:
        review_ref = f"{ref}/5.review/content_review.json"
        raw = (root / review_ref).read_bytes()
        judgement = json.loads(raw)
        assert_valid(judgement, "content", "content_review", label=review_ref)
        expected_object_ref = target_descriptor_for(batch["execution_id"], ref)["canonicalObjectRef"]
        if (judgement["executionId"] != batch["execution_id"] or judgement["objectRef"] != expected_object_ref
                or {"scope": "execution", "ref": review_ref, "digest": digest_bytes(raw)} not in bindings):
            raise CoordinationError("COORDINATION.RECEIPT_TARGET_DRIFT", ref)
        if judgement["decision"] == "approved":
            approved_targets.append(ref)
        elif judgement["decision"] != "rejected" or not judgement.get("blockingIssues"):
            return result
    if not approved_targets:
        return result
    from content.release.canonical.content_pool_handoff import project_content_pool_handoff
    from content.release.canonical.content_pool_record import pool_payload_digest
    from content.release.canonical.aggregate_release_closure import object_root
    from content.release.canonical.object_transaction_contract import canonical_transaction_id, ObjectTransactionError, _verify_package
    for ref in approved_targets:
        try:
            _chain, judgement = validate_publish_review_chain(execution_id=batch["execution_id"], execution_root=root, target_ref=ref)
            kind, logical = ref.split("/", 1)
            transaction = canonical_transaction_id(execution_id=batch["execution_id"], object_kind=kind, object_ref=logical)
            package_root = root / "evidence/object-transactions" / transaction
            if not (package_root / "object_transaction_package.json").is_file():
                return result
            package = _verify_package(package_root, canonical_root=Path(roots["publish"]), require_target_absent=False)
            if package["executionId"] != batch["execution_id"] or package["transactionId"] != transaction:
                return result
            canonical_ref = package["objectRef"]
            projection = project_content_pool_handoff(publish_root=Path(roots["publish"]), object_type="homepage" if kind == "entities" else "content", object_ref=canonical_ref)
            if projection is None:
                return result
            canonical_root = object_root(Path(roots["publish"]), kind, canonical_ref)
            if pool_payload_digest(canonical_root) != projection.payload_digest:
                return result
            for original in package["objectRoot"].rglob("*"):
                relative = original.relative_to(package["objectRoot"])
                if "records" in relative.parts or not original.is_file():
                    continue
                copied = canonical_root / relative
                if copied.is_symlink() or copied.read_bytes() != original.read_bytes():
                    return result
            published = canonical_root / "content_review.json"
            if published.read_bytes() != (root / ref / "5.review/content_review.json").read_bytes():
                return result
            if judgement["decision"] != "approved":
                return result
        except (OSError, ValueError, KeyError, ObjectTransactionError):
            return result
    result["closed"] = True
    return result


def actual_roots():
    from core import paths
    roots = {"output": paths.OUTPUT_ROOT, "publish": paths.PUBLISH_ROOT,
             "library": paths.LIBRARY_ROOT, "carried": paths.carried_media_root()}
    return {key: str(Path(value).expanduser().resolve()) for key, value in roots.items()}


def producer_call(write_callable: Callable[[], R], *, operation: str, batches: dict,
                  submitted_actor: dict | None = None, require_global_closer: bool = False) -> R:
    tokens = current_tokens()
    try:
        actor = actor_key(_document(os.environ.get("QWQ_CONTENT_ACTOR", "{}")))
        if submitted_actor is not None and actor_key(submitted_actor) != actor:
            raise CoordinationError("COORDINATION.SUBMITTED_ACTOR_MISMATCH", actor)
        task_digest = os.environ.get("QWQ_CONTENT_TASK_DIGEST", "")
        nonces = _document(os.environ.get("QWQ_CONTENT_BATCH_NONCES", "{}"))
        if not isinstance(nonces, dict):
            raise ValueError("batch nonces 必须为 execution→nonce 对象")
        if require_global_closer and os.environ.get(CLOSER_ENV) != tokens[0].deployment_id:
            raise CoordinationError("COORDINATION.GLOBAL_CLOSER_REQUIRED", tokens[0].deployment_id)
        roots = actual_roots()
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise CoordinationError("COORDINATION.PRODUCER_CONTEXT_INVALID", str(exc)) from exc
    return CoordinationStore(os.environ[DB_ENV]).fenced_producer_write(
        tokens, write_callable, actor=actor, task_digest=task_digest, roots=roots,
        operation=operation, batches=batches, nonces=nonces,
    )


def governed_repackage_call(write_callable: Callable[[], R], *, target_refs: list[str], release_id: str) -> R:
    """核验 director/global closer/current generation/root binding 与 exact cohort fence；不认领或重绑 execution。"""
    tokens = current_tokens()
    try:
        actor = actor_key(_document(os.environ.get("QWQ_CONTENT_ACTOR", "{}")))
        task_digest = os.environ.get("QWQ_CONTENT_TASK_DIGEST", "")
        if os.environ.get(CLOSER_ENV) != tokens[0].deployment_id:
            raise CoordinationError("COORDINATION.GLOBAL_CLOSER_REQUIRED", tokens[0].deployment_id)
        roots = actual_roots()
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise CoordinationError("COORDINATION.PRODUCER_CONTEXT_INVALID", str(exc)) from exc
    return CoordinationStore(os.environ[DB_ENV]).fenced_governed_repackage(
        tokens, write_callable, actor=actor, task_digest=task_digest, roots=roots,
        target_refs=target_refs, release_id=release_id,
    )


def fenced_call(write_callable: Callable[[], R], *, target_ref: str | None = None, require_global_closer: bool = False) -> R:
    """低层团队临界区，不能替代正式 producer_call 的批次/角色核验。"""
    tokens = current_tokens()
    selected = tuple(token for token in tokens if target_ref is None or token.target_ref == target_ref)
    if not selected:
        raise CoordinationError("COORDINATION.WRITE_FENCE_TARGET_MISSING", str(target_ref))
    if require_global_closer and os.environ.get(CLOSER_ENV) != selected[0].deployment_id:
        raise CoordinationError("COORDINATION.GLOBAL_CLOSER_REQUIRED", selected[0].deployment_id)
    return CoordinationStore(Path(os.environ[DB_ENV])).fenced_write_many(selected, write_callable)
