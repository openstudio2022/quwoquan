"""具名分片的最小 SQLite 协作内核。

shard_id 是稳定关系身份，name 只是可改展示名；业务完成权威始终留在外部 fact ref。
"""
from __future__ import annotations

import json
import fcntl
import hashlib
import time
import sqlite3
import subprocess
import threading
from contextlib import contextmanager, ExitStack
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar

from .fence import WriteFenceToken

ROLE_NAMES = (
    "director", "homepage_creator", "article_creator", "image_creator",
    "video_creator", "qa", "computer_steward",
)
ACTIVE_CLAIM_STATES = ("claimed", "draining", "blocked")
_WRITE_RESULT = TypeVar("_WRITE_RESULT")


class CoordinationError(RuntimeError):
    """所有可预期失败均携带稳定 code。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class NotFoundError(CoordinationError):
    pass


class ConflictError(CoordinationError):
    pass


def default_database_path(cwd: str | Path | None = None) -> Path:
    """把状态放在所有 linked worktree 共用的 Git common dir 下。"""

    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd, check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CoordinationError("COORDINATION.GIT_COMMON_DIR_UNAVAILABLE", "无法解析 git common dir") from exc
    return Path(common) / "qwq-state/content-production/coordination.sqlite"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("roles", "targets", "payload", "roots"):
        if key in result and result[key] is not None:
            result[key] = json.loads(result[key])
    return result


def _control_gate(kind):
    """控制动作先取对应独占门，等待期间绝不占用 SQLite 事务。"""
    def decorate(method):
        @wraps(method)
        def guarded(self, iteration_id, identity, *args, **kwargs):
            with self._gate(kind, iteration_id, identity, exclusive=True):
                return method(self, iteration_id, identity, *args, **kwargs)
        return guarded
    return decorate


class CoordinationStore:
    """并发互斥由 SQLite 事务和唯一约束提供，不依赖进程内状态。"""

    def __init__(self, path: str | Path | None = None, *, timeout: float = 10.0) -> None:
        self.path = Path(path) if path is not None else default_database_path()
        self.timeout = timeout
        self._initialize_lock = threading.Lock()

    @contextmanager
    def _gate(self, kind, iteration_id, identity, *, exclusive):
        """同一物理 DB 的本机 flock 门；不含 generation，旧新代必须相互排斥。

        锁文件不可在运行中删除/替换；超时只拒绝，不抢占/kill。进程退出由内核释放。
        """
        directory = self.path.resolve().with_name(self.path.name + ".gates")
        directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(_json([kind, iteration_id, identity]).encode()).hexdigest()
        with (directory / key).open("a+b") as handle:
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    fcntl.flock(handle.fileno(), (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise ConflictError("COORDINATION.GATE_TIMEOUT", f"{kind}:{identity}") from exc
                    threading.Event().wait(min(.02, max(0, deadline - time.monotonic())))
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _business_gates(self, token, execution_ids=()):
        # 固定顺序：deployment SH → shard SH → 排序 execution EX → 短 SQLite → 业务锁。
        with ExitStack() as stack:
            stack.enter_context(self._gate("deployment", token.iteration_id, token.deployment_id, exclusive=False))
            stack.enter_context(self._gate("shard", token.iteration_id, token.shard_id, exclusive=False))
            for execution_id in sorted(set(execution_ids)):
                stack.enter_context(self._gate("execution", token.iteration_id, execution_id, exclusive=True))
            yield

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=%d" % int(self.timeout * 1000))
        return connection

    @contextmanager
    def _transaction(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> Path:
        with self._initialize_lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS iterations(
                  iteration_id TEXT PRIMARY KEY, authorization_ref TEXT NOT NULL, authorization_digest TEXT NOT NULL, registered_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deployments(
                  iteration_id TEXT NOT NULL REFERENCES iterations(iteration_id),
                  deployment_id TEXT NOT NULL, roles TEXT NOT NULL, instance_id TEXT,
                  account_identity_ref TEXT, resource_reservation_ref TEXT,
                  registered_at TEXT NOT NULL,
                  PRIMARY KEY(iteration_id, deployment_id)
                );
                CREATE TABLE IF NOT EXISTS shards(
                  iteration_id TEXT NOT NULL REFERENCES iterations(iteration_id), shard_id TEXT NOT NULL,
                  name TEXT NOT NULL, scope_ref TEXT NOT NULL, ordinal INTEGER NOT NULL, targets TEXT NOT NULL,
                  authorized_team TEXT, state TEXT NOT NULL DEFAULT 'available', registered_at TEXT NOT NULL,
                  PRIMARY KEY(iteration_id, shard_id), UNIQUE(iteration_id, name), UNIQUE(iteration_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS claims(
                  claim_id INTEGER PRIMARY KEY AUTOINCREMENT, iteration_id TEXT NOT NULL, shard_id TEXT NOT NULL,
                  team TEXT NOT NULL, generation INTEGER NOT NULL, state TEXT NOT NULL,
                  idempotency_key TEXT NOT NULL, deployment_id TEXT, handoff_ref TEXT, remaining INTEGER,
                  claimed_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  FOREIGN KEY(iteration_id, shard_id) REFERENCES shards(iteration_id, shard_id),
                  UNIQUE(iteration_id, shard_id, generation), UNIQUE(iteration_id, idempotency_key)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_claim_per_shard
                  ON claims(iteration_id, shard_id) WHERE state IN ('claimed','draining','blocked');
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_claim_per_team
                  ON claims(iteration_id, team) WHERE state IN ('claimed','draining','blocked');
                CREATE TABLE IF NOT EXISTS target_occupancy(
                  iteration_id TEXT NOT NULL, target_ref TEXT NOT NULL,
                  claim_id INTEGER NOT NULL REFERENCES claims(claim_id), PRIMARY KEY(iteration_id, target_ref)
                );
                CREATE TABLE IF NOT EXISTS operations(
                  iteration_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, operation TEXT NOT NULL,
                  result TEXT NOT NULL, PRIMARY KEY(iteration_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS checkpoints(
                  iteration_id TEXT NOT NULL, fact_ref TEXT NOT NULL, fact_digest TEXT NOT NULL,
                  source_type TEXT NOT NULL, shard_id TEXT, deployment_id TEXT, result TEXT NOT NULL,
                  PRIMARY KEY(iteration_id, fact_ref),
                  FOREIGN KEY(iteration_id, shard_id) REFERENCES shards(iteration_id, shard_id),
                  FOREIGN KEY(iteration_id, deployment_id) REFERENCES deployments(iteration_id, deployment_id)
                );
                CREATE TABLE IF NOT EXISTS deployment_contexts(
                  iteration_id TEXT NOT NULL, deployment_id TEXT NOT NULL,
                  task_ref TEXT NOT NULL, task_digest TEXT NOT NULL, roots TEXT NOT NULL,
                  PRIMARY KEY(iteration_id,deployment_id),
                  FOREIGN KEY(iteration_id,deployment_id) REFERENCES deployments(iteration_id,deployment_id)
                );
                CREATE TABLE IF NOT EXISTS batch_scopes(
                  claim_id INTEGER NOT NULL REFERENCES claims(claim_id),
                  execution_id TEXT NOT NULL, author TEXT NOT NULL, targets TEXT NOT NULL,
                  nonce TEXT NOT NULL, reviewer TEXT, review_nonce TEXT,
                  PRIMARY KEY(claim_id,execution_id), UNIQUE(execution_id), UNIQUE(nonce)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_review_nonce ON batch_scopes(review_nonce) WHERE review_nonce IS NOT NULL;
                CREATE TABLE IF NOT EXISTS timeline(
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT, iteration_id TEXT NOT NULL,
                  event_type TEXT NOT NULL, occurred_at TEXT, observed_at TEXT NOT NULL,
                  shard_id TEXT, shard_name_snapshot TEXT, deployment_id TEXT,
                  team_snapshot TEXT, generation INTEGER, fact_ref TEXT, fact_digest TEXT,
                  source_type TEXT, payload TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            iteration_columns = {row["name"] for row in connection.execute("PRAGMA table_info(iterations)")}
            if "authorization_digest" not in iteration_columns:
                connection.execute("ALTER TABLE iterations ADD COLUMN authorization_digest TEXT NOT NULL DEFAULT ''")
            deployment_columns = {row["name"] for row in connection.execute("PRAGMA table_info(deployments)")}
            for column in ("instance_id", "account_identity_ref", "resource_reservation_ref"):
                if column not in deployment_columns:
                    connection.execute(f"ALTER TABLE deployments ADD COLUMN {column} TEXT")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS one_active_claim_per_deployment "
                "ON claims(iteration_id, deployment_id) WHERE deployment_id IS NOT NULL "
                "AND state IN ('claimed','draining','blocked')"
            )
        return self.path

    def _event(self, connection: sqlite3.Connection, iteration_id: str, event_type: str, *,
               occurred_at: str | None = None, shard_id: str | None = None,
               shard_name: str | None = None, deployment_id: str | None = None,
               team: str | None = None, generation: int | None = None,
               fact_ref: str | None = None, fact_digest: str | None = None,
               source_type: str | None = None, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        cursor = connection.execute(
            "INSERT INTO timeline(iteration_id,event_type,occurred_at,observed_at,shard_id,shard_name_snapshot,deployment_id,team_snapshot,generation,fact_ref,fact_digest,source_type,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iteration_id, event_type, occurred_at, _now(), shard_id, shard_name, deployment_id,
             team, generation, fact_ref, fact_digest, source_type, _json(dict(payload or {}))),
        )
        return _decode(connection.execute("SELECT * FROM timeline WHERE sequence=?", (cursor.lastrowid,)).fetchone()) or {}

    @staticmethod
    def _require_iteration(connection: sqlite3.Connection, iteration_id: str) -> None:
        if connection.execute("SELECT 1 FROM iterations WHERE iteration_id=?", (iteration_id,)).fetchone() is None:
            raise NotFoundError("COORDINATION.ITERATION_NOT_FOUND", iteration_id)

    @staticmethod
    def _shard(connection: sqlite3.Connection, iteration_id: str, shard_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM shards WHERE iteration_id=? AND shard_id=?", (iteration_id, shard_id)).fetchone()
        if row is None:
            raise NotFoundError("COORDINATION.SHARD_NOT_FOUND", shard_id)
        return row

    def register_iteration(self, iteration_id: str, authorization_ref: str, authorization_digest: str = "", *, occurred_at: str | None = None) -> dict[str, Any]:
        self.initialize()
        if not iteration_id or not authorization_ref:
            raise CoordinationError("COORDINATION.INVALID_ARGUMENT", "iteration_id 和 authorization_ref 必须非空")
        from .authority import verify_authority_artifact
        if authorization_digest:
            verify_authority_artifact(authorization_ref,authorization_digest,purpose="content-repackage-user-authorization")
        with self._transaction() as connection:
            existing = connection.execute("SELECT * FROM iterations WHERE iteration_id=?", (iteration_id,)).fetchone()
            if existing:
                if existing["authorization_ref"] != authorization_ref or existing["authorization_digest"] != authorization_digest:
                    raise ConflictError("COORDINATION.ITERATION_CONFLICT", iteration_id)
                return _decode(existing) or {}
            connection.execute("INSERT INTO iterations VALUES(?,?,?,?)", (iteration_id, authorization_ref, authorization_digest, _now()))
            self._event(connection, iteration_id, "iteration.registered", occurred_at=occurred_at, fact_ref=authorization_ref)
            return _decode(connection.execute("SELECT * FROM iterations WHERE iteration_id=?", (iteration_id,)).fetchone()) or {}

    def register_deployment(
        self, iteration_id: str, deployment_id: str, roles: Mapping[str, Sequence[str]], *,
        instance_id: str | None = None, account_identity_ref: str | None = None,
        resource_reservation_ref: str | None = None, occurred_at: str | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        self._validate_roles(roles)
        if not deployment_id:
            raise CoordinationError("COORDINATION.INVALID_ROLE_BINDINGS", "deployment_id 必须非空")
        bindings = (instance_id, account_identity_ref, resource_reservation_ref)
        if any(bindings) and not all(isinstance(value, str) and value.strip() for value in bindings):
            raise CoordinationError("COORDINATION.DEPLOYMENT_BINDING_INCOMPLETE", "instance/account/resource reservation 必须同时提供")
        encoded = _json(dict(roles))
        with self._transaction() as connection:
            self._require_iteration(connection, iteration_id)
            existing = connection.execute("SELECT * FROM deployments WHERE iteration_id=? AND deployment_id=?", (iteration_id, deployment_id)).fetchone()
            if existing:
                actual = (existing["roles"], existing["instance_id"], existing["account_identity_ref"], existing["resource_reservation_ref"])
                if actual != (encoded, *bindings):
                    raise ConflictError("COORDINATION.DEPLOYMENT_CONFLICT", deployment_id)
                return _decode(existing) or {}
            from .runtime import member_key
            members = {member_key(actor) for values in roles.values() for actor in values}
            for row in connection.execute("SELECT roles FROM deployments WHERE iteration_id=?", (iteration_id,)):
                previous_roles = json.loads(row["roles"])
                self._validate_roles(previous_roles)
                if members & {member_key(actor) for values in previous_roles.values() for actor in values}:
                    raise ConflictError("COORDINATION.ACTOR_ALREADY_DEPLOYED", deployment_id)
            if instance_id and connection.execute(
                "SELECT 1 FROM deployments WHERE iteration_id=? AND (instance_id=? OR account_identity_ref=?)",
                (iteration_id, instance_id, account_identity_ref),
            ).fetchone():
                raise ConflictError("COORDINATION.DEPLOYMENT_BINDING_CONFLICT", deployment_id)
            connection.execute(
                "INSERT INTO deployments(iteration_id,deployment_id,roles,instance_id,account_identity_ref,resource_reservation_ref,registered_at) VALUES(?,?,?,?,?,?,?)",
                (iteration_id, deployment_id, encoded, instance_id, account_identity_ref, resource_reservation_ref, _now()),
            )
            self._event(connection, iteration_id, "deployment.registered", occurred_at=occurred_at,
                        deployment_id=deployment_id, fact_ref=deployment_id,
                        payload={"roles": dict(roles), "instanceId": instance_id,
                                 "accountIdentityRef": account_identity_ref,
                                 "resourceReservationRef": resource_reservation_ref})
            return _decode(connection.execute("SELECT * FROM deployments WHERE iteration_id=? AND deployment_id=?", (iteration_id, deployment_id)).fetchone()) or {}

    @staticmethod
    def _validate_roles(roles: Mapping[str, Sequence[str]]) -> None:
        if not isinstance(roles, dict) or set(roles) != set(ROLE_NAMES):
            raise CoordinationError("COORDINATION.INVALID_ROLE_BINDINGS", "岗位键必须完整")
        from .runtime import member_key
        actors = []
        for role, members in roles.items():
            if (not isinstance(members, list) or not members
                    or any(not isinstance(actor, str) or not actor.strip() for actor in members)
                    or (role in ("director", "computer_steward") and len(members) != 1)):
                raise CoordinationError("COORDINATION.INVALID_ROLE_BINDINGS", "岗位绑定必须为非空 actor 数组；旧单值绑定须显式重新部署")
            actors.extend(member_key(value) for value in members)
        if len(set(actors)) != len(actors):
            raise CoordinationError("COORDINATION.INVALID_ROLE_BINDINGS", "actor 不得兼岗或重复绑定")

    @_control_gate("deployment")
    def bind_context(self, iteration_id: str, deployment_id: str, *, task_ref: str,
                     task_digest: str, roots: Mapping[str, str], actor: str,
                     expected_digest: str | None = None) -> dict[str, Any]:
        """显式绑定已有任务报告及物理根；只保存引用，不新建授权文档。"""
        from .runtime import read_task_context, is_member
        self.initialize()
        if set(roots) != {"output", "publish", "library", "carried"}:
            raise CoordinationError("COORDINATION.ROOT_BINDING_REQUIRED", "须点名四个独立物理根")
        normalized = {key: str(Path(value).expanduser().resolve()) for key, value in roots.items()}
        locations = [Path(value) for value in normalized.values()]
        if any(left == right or left in right.parents or right in left.parents for index, left in enumerate(locations) for right in locations[index + 1:]):
            raise CoordinationError("COORDINATION.ROOT_BINDING_OVERLAP", "output/publish/library/carried 必须独立")
        if any(not Path(value).expanduser().is_absolute() for value in roots.values()):
            raise CoordinationError("COORDINATION.ROOT_BINDING_REQUIRED", "根须为绝对路径")
        with self._transaction() as connection:
            deployment = connection.execute("SELECT * FROM deployments WHERE iteration_id=? AND deployment_id=?", (iteration_id, deployment_id)).fetchone()
            if deployment is None:
                raise NotFoundError("COORDINATION.DEPLOYMENT_NOT_FOUND", deployment_id)
            roles = json.loads(deployment["roles"])
            self._validate_roles(roles)
            if not is_member(actor, roles["director"]):
                raise ConflictError("COORDINATION.DIRECTOR_REQUIRED", actor)
            read_task_context(task_ref, task_digest, roles)
            previous = connection.execute("SELECT * FROM deployment_contexts WHERE iteration_id=? AND deployment_id=?", (iteration_id, deployment_id)).fetchone()
            if previous and previous["task_digest"] != expected_digest:
                raise ConflictError("COORDINATION.TASK_CONTEXT_CAS_CONFLICT", deployment_id)
            if previous and (previous["task_digest"], previous["task_ref"], json.loads(previous["roots"])) == (task_digest, str(Path(task_ref).resolve()), normalized):
                return _decode(previous) or {}
            if previous and json.loads(previous["roots"]) != normalized:
                raise ConflictError("COORDINATION.ROOT_REBIND_FORBIDDEN", "在飞根切换须另行明确安全交接")
            connection.execute("INSERT INTO deployment_contexts VALUES(?,?,?,?,?) ON CONFLICT(iteration_id,deployment_id) DO UPDATE SET task_ref=excluded.task_ref,task_digest=excluded.task_digest",
                               (iteration_id, deployment_id, str(Path(task_ref).resolve()), task_digest, _json(normalized)))
            return _decode(connection.execute("SELECT * FROM deployment_contexts WHERE iteration_id=? AND deployment_id=?", (iteration_id, deployment_id)).fetchone()) or {}

    def _context(self, connection, token, actor, task_digest):
        from .runtime import read_task_context, is_member
        deployment = connection.execute("SELECT * FROM deployments WHERE iteration_id=? AND deployment_id=?", (token.iteration_id, token.deployment_id)).fetchone()
        context = connection.execute("SELECT * FROM deployment_contexts WHERE iteration_id=? AND deployment_id=?", (token.iteration_id, token.deployment_id)).fetchone()
        if deployment is None or context is None:
            raise ConflictError("COORDINATION.TASK_CONTEXT_REQUIRED", token.deployment_id)
        roles = json.loads(deployment["roles"])
        self._validate_roles(roles)
        if task_digest != context["task_digest"]:
            raise ConflictError("COORDINATION.TASK_VERSION_STALE", actor)
        task = read_task_context(context["task_ref"], task_digest, roles)
        if not is_member(actor, [member for members in roles.values() for member in members]) or is_member(actor, task.get("revokedActors", [])):
            raise ConflictError("COORDINATION.ACTOR_FORBIDDEN", actor)
        return roles, json.loads(context["roots"]), task

    def claim_batch(self, tokens: Sequence[WriteFenceToken], *, execution_id: str,
                    actor: str, nonce: str, task_digest: str, review: bool = False) -> dict[str, Any]:
        from .runtime import member_key, batch_facts
        self.initialize()
        self._token_set(tokens)
        token = tokens[0]
        # 同成员认领串行；只锁相关 execution，不冻结同 shard 其他作者。
        with self._gate("member", token.iteration_id, member_key(actor), exclusive=True):
            with self._connect() as connection:
                claim = self._active_claim(connection, token.iteration_id, token.shard_id)
                rows = connection.execute("SELECT * FROM batch_scopes WHERE claim_id=?", (claim["claim_id"],)).fetchall()
                relevant = [row for row in rows if row["execution_id"] == execution_id or
                            member_key(row["author"]) == member_key(actor) or
                            (row["reviewer"] and member_key(row["reviewer"]) == member_key(actor))]
            with self._business_gates(token, [execution_id, *(row["execution_id"] for row in relevant)]):
                with self._connect() as connection:
                    _roles, roots, _task = self._context(connection, token, actor, task_digest)
                    fresh = [connection.execute("SELECT * FROM batch_scopes WHERE execution_id=?", (row["execution_id"],)).fetchone() for row in relevant]
                facts = {row["execution_id"]: batch_facts(_decode(row), roots) for row in fresh}
                return self._claim_batch(tokens, execution_id=execution_id, actor=actor, nonce=nonce,
                                         task_digest=task_digest, review=review, facts=facts)

    def _claim_batch(self, tokens: Sequence[WriteFenceToken], *, execution_id: str,
                     actor: str, nonce: str, task_digest: str, review: bool, facts) -> dict[str, Any]:
        """只认领调用方点名的小批，不选题、不决定后继、不持久化阶段状态。"""
        from .runtime import batch_facts, is_member, member_key
        from content.execution.identity import validate_execution_id, parse_execution_id
        validate_execution_id(execution_id)
        self.initialize()
        self._token_set(tokens)
        if not actor or not nonce:
            raise CoordinationError("COORDINATION.BATCH_IDENTITY_REQUIRED", "actor 与 nonce 必填")
        with self._transaction() as connection:
            for token in tokens:
                self._assert_write_authorized_in_connection(connection, token)
            token = tokens[0]
            claim = self._active_claim(connection, token.iteration_id, token.shard_id)
            roles, roots, task = self._context(connection, token, actor, task_digest)
            if ("5.review" if review else "init") not in task["allowedActions"]:
                raise ConflictError("COORDINATION.ACTION_NOT_AUTHORIZED", "claim-batch")
            role = "qa" if review else parse_execution_id(execution_id).content_type.value + "_creator"
            if not is_member(actor, roles[role]):
                raise ConflictError("COORDINATION.ROLE_FORBIDDEN", actor)
            refs = sorted(token.target_ref for token in tokens)
            reused_nonce = connection.execute("SELECT execution_id FROM batch_scopes WHERE nonce=? OR review_nonce=?", (nonce, nonce)).fetchone()
            if reused_nonce and reused_nonce["execution_id"] != execution_id:
                raise ConflictError("COORDINATION.BATCH_NONCE_REUSED", execution_id)
            existing = connection.execute("SELECT * FROM batch_scopes WHERE execution_id=?", (execution_id,)).fetchone()
            if existing and existing["claim_id"] != claim["claim_id"]:
                raise ConflictError("COORDINATION.BATCH_OCCUPIED", execution_id)
            if review:
                if existing is None:
                    raise ConflictError("COORDINATION.BATCH_NOT_CLAIMED", execution_id)
                author_identity, reviewer_identity = json.loads(existing["author"]), json.loads(actor)
                if author_identity[:2] == reviewer_identity[:2] or author_identity[2] == reviewer_identity[2]:
                    raise ConflictError("COORDINATION.REVIEW_NOT_INDEPENDENT", execution_id)
                facts = batch_facts(_decode(existing), roots)
                if not facts["author_sealed"] or refs != facts["review_targets"]:
                    raise ConflictError("COORDINATION.REVIEW_SCOPE_NOT_READY", execution_id)
                if existing["reviewer"]:
                    if existing["reviewer"] == actor and existing["review_nonce"] == nonce:
                        return _decode(existing) or {}
                    raise ConflictError("COORDINATION.REVIEW_OCCUPIED", execution_id)
                for row in connection.execute("SELECT * FROM batch_scopes WHERE claim_id=? AND reviewer IS NOT NULL", (claim["claim_id"],)):
                    if member_key(row["reviewer"]) == member_key(actor) and not batch_facts(_decode(row), roots)["review_sealed"]:
                        raise ConflictError("COORDINATION.REVIEW_CAPACITY_EXCEEDED", actor)
                connection.execute("UPDATE batch_scopes SET reviewer=?,review_nonce=? WHERE execution_id=?", (actor, nonce, execution_id))
            else:
                if existing:
                    if (existing["author"], existing["nonce"], json.loads(existing["targets"])) == (actor, nonce, refs):
                        return _decode(existing) or {}
                    raise ConflictError("COORDINATION.BATCH_OCCUPIED", execution_id)
                if (Path(roots["output"]) / "data/tasks" / execution_id).exists():
                    raise ConflictError("COORDINATION.EXISTING_EXECUTION_REBIND_FORBIDDEN", execution_id)
                if claim["state"] != "claimed":
                    raise ConflictError("COORDINATION.NEW_BATCH_DRAINING", execution_id)
                rows = connection.execute("SELECT * FROM batch_scopes WHERE claim_id=?", (claim["claim_id"],)).fetchall()
                if any(set(refs) & set(json.loads(row["targets"])) for row in rows):
                    raise ConflictError("COORDINATION.BATCH_TARGET_OCCUPIED", execution_id)
                facts = [batch_facts(_decode(row), roots) for row in rows if member_key(row["author"]) == member_key(actor)]
                if sum(not fact["closed"] for fact in facts) >= 2 or any(not fact["author_sealed"] and not fact["closed"] for fact in facts):
                    raise ConflictError("COORDINATION.AUTHOR_CAPACITY_EXCEEDED", actor)
                connection.execute("INSERT INTO batch_scopes(claim_id,execution_id,author,targets,nonce) VALUES(?,?,?,?,?)", (claim["claim_id"], execution_id, actor, _json(refs), nonce))
            self._event(connection, token.iteration_id, "batch.review-claimed" if review else "batch.author-claimed",
                        shard_id=token.shard_id, deployment_id=token.deployment_id, team=token.team,
                        generation=token.generation, payload={"executionId": execution_id, "actor": actor, "nonce": nonce, "targets": refs})
            return _decode(connection.execute("SELECT * FROM batch_scopes WHERE execution_id=?", (execution_id,)).fetchone()) or {}

    @staticmethod
    def _token_set(tokens):
        if not tokens or any(not isinstance(token, WriteFenceToken) for token in tokens):
            raise CoordinationError("COORDINATION.WRITE_FENCE_TOKEN_SET_INVALID", "非空 token 数组必填")
        identities = {(token.iteration_id, token.shard_id, token.deployment_id, token.team, token.generation) for token in tokens}
        if len(identities) != 1 or len({token.target_ref for token in tokens}) != len(tokens):
            raise CoordinationError("COORDINATION.WRITE_FENCE_TOKEN_SET_INVALID", "token 必须同 claim 且 target 唯一")

    def fenced_producer_write(self, tokens, write_callable, *, actor, task_digest, roots,
                              operation, batches, nonces):
        """门保护整个业务，SQLite 查询结束后执行；不允许撤权穿过在飞写。"""
        self._token_set(tokens)
        with self._business_gates(tokens[0], batches):
            self._check_producer_write(tokens, actor=actor, task_digest=task_digest, roots=roots,
                                       operation=operation, batches=batches, nonces=nonces)
            return write_callable()

    def fenced_governed_repackage(self, tokens, write_callable, *, actor, task_digest, roots, target_refs, release_id):
        """受治理 release 重物化：复用 claim/generation/root/director gate，但不读写 batch_scopes。"""
        self._token_set(tokens)
        with self._business_gates(tokens[0]):
            self.initialize()
            with self._connect() as connection:
                for token in tokens:
                    self._assert_write_authorized_in_connection(connection, token)
                roles, bound_roots, _task = self._context(connection, tokens[0], actor, task_digest)
                from .runtime import is_member, read_repackage_task_context
                iteration = connection.execute("SELECT authorization_ref,authorization_digest FROM iterations WHERE iteration_id=?", (tokens[0].iteration_id,)).fetchone()
                context = connection.execute("SELECT task_ref,task_digest FROM deployment_contexts WHERE iteration_id=? AND deployment_id=?", (tokens[0].iteration_id,tokens[0].deployment_id)).fetchone()
                task = read_repackage_task_context(context["task_ref"], context["task_digest"], roles, authorization_ref=iteration["authorization_ref"], authorization_digest=iteration["authorization_digest"])
                if roots != bound_roots:
                    raise ConflictError("COORDINATION.ROOT_BINDING_MISMATCH", "实际根与 deployment 绑定不同")
                if task["allowedActions"] != ["repackage"]:
                    raise ConflictError("COORDINATION.ACTION_NOT_AUTHORIZED", "repackage")
                if not is_member(actor, roles["director"]):
                    raise ConflictError("COORDINATION.DIRECTOR_REQUIRED", actor)
                if set(target_refs) != {token.target_ref for token in tokens}:
                    raise ConflictError("COORDINATION.WRITE_FENCE_TARGET_SET_MISMATCH", "围栏必须恰好覆盖 target cohort")
                placeholders=",".join("?" for _ in target_refs)
                occupied=connection.execute(f"SELECT target_ref FROM target_occupancy WHERE iteration_id<>? AND target_ref IN ({placeholders}) LIMIT 1",(tokens[0].iteration_id,*target_refs)).fetchone()
                if occupied is not None:
                    raise ConflictError("COORDINATION.CROSS_ITERATION_TARGET_OCCUPIED", occupied["target_ref"])
            from content.release.canonical.object_transaction_lock import canonical_publish_lock
            from content.release.canonical.release_operation_lock import ReleaseOperationConflict, release_operation_guard, release_operation_lock_root
            release_root=Path(roots["output"])/"data"/"releases"
            try:
                with release_operation_guard(lock_root=release_operation_lock_root(release_root), release_ids=(str(release_id),), exclusive_releases=True), canonical_publish_lock(Path(roots["publish"]), blocking=False):
                    return write_callable()
            except (ReleaseOperationConflict, RuntimeError) as exc:
                raise ConflictError("COORDINATION.NATIVE_WRITER_LOCK_CONFLICT",str(release_id)) from exc

    def _check_producer_write(self, tokens, *, actor, task_digest, roots, operation, batches, nonces):
        """在外层门已稳定归属后只读核权，媒体 proof 验证不持 SQLite 写事务。"""
        from .runtime import batch_facts, is_member, member_key
        self.initialize()
        self._token_set(tokens)
        with self._connect() as connection:
            for token in tokens:
                self._assert_write_authorized_in_connection(connection, token)
            roles, bound_roots, task = self._context(connection, tokens[0], actor, task_digest)
            if roots != bound_roots:
                raise ConflictError("COORDINATION.ROOT_BINDING_MISMATCH", "实际根与 deployment 绑定不同")
            if operation not in task["allowedActions"]:
                raise ConflictError("COORDINATION.ACTION_NOT_AUTHORIZED", operation)
            if operation in ("publish", "finalize") and not is_member(actor, roles["director"]):
                raise ConflictError("COORDINATION.DIRECTOR_REQUIRED", actor)
            expected = {ref for refs in batches.values() for ref in refs}
            if expected != {token.target_ref for token in tokens}:
                raise ConflictError("COORDINATION.WRITE_FENCE_TARGET_SET_MISMATCH", "围栏必须恰好覆盖本次全部写 target")
            claim = self._active_claim(connection, tokens[0].iteration_id, tokens[0].shard_id)
            for execution_id, refs in batches.items():
                row = connection.execute("SELECT * FROM batch_scopes WHERE execution_id=? AND claim_id=?", (execution_id, claim["claim_id"])).fetchone()
                if row is None:
                    raise ConflictError("COORDINATION.BATCH_NOT_CLAIMED", execution_id)
                review = operation == "5.review"
                if operation not in ("publish", "finalize"):
                    owner = row["reviewer"] if review else row["author"]
                    nonce = row["review_nonce"] if review else row["nonce"]
                    if actor != owner or nonces.get(execution_id) != nonce:
                        raise ConflictError("COORDINATION.BATCH_ACTOR_MISMATCH", execution_id)
                if operation in ("publish", "finalize"):
                    if not set(refs) <= set(json.loads(row["targets"])):
                        raise ConflictError("COORDINATION.BATCH_TARGET_MISMATCH", execution_id)
                else:
                    authorized = batch_facts(_decode(row), roots)["review_targets"] if review else json.loads(row["targets"])
                    if sorted(refs) != sorted(authorized):
                        raise ConflictError("COORDINATION.BATCH_TARGET_MISMATCH", execution_id)

    def register_shard(self, iteration_id: str, shard_id: str, name: str, scope_ref: str, order: int,
                       targets: Sequence[str], *, authorized_team: str | None = None,
                       occurred_at: str | None = None) -> dict[str, Any]:
        self.initialize()
        if not shard_id or not name or not name.strip() or not scope_ref or order < 0 or not targets or any(not str(v) for v in targets) or len(set(targets)) != len(targets):
            raise CoordinationError("COORDINATION.INVALID_SHARD", "shard_id、非空 name、scope ref、非负顺序和唯一 targets 均必填")
        encoded = _json(list(targets))
        with self._transaction() as connection:
            self._require_iteration(connection, iteration_id)
            existing = connection.execute("SELECT * FROM shards WHERE iteration_id=? AND shard_id=?", (iteration_id, shard_id)).fetchone()
            if existing:
                expected = (name, scope_ref, order, encoded, authorized_team)
                actual = (existing["name"], existing["scope_ref"], existing["ordinal"], existing["targets"], existing["authorized_team"])
                if actual != expected:
                    raise ConflictError("COORDINATION.SHARD_CONFLICT", shard_id)
                return _decode(existing) or {}
            try:
                connection.execute("INSERT INTO shards(iteration_id,shard_id,name,scope_ref,ordinal,targets,authorized_team,registered_at) VALUES(?,?,?,?,?,?,?,?)",
                                   (iteration_id, shard_id, name, scope_ref, order, encoded, authorized_team, _now()))
            except sqlite3.IntegrityError as exc:
                raise ConflictError("COORDINATION.SHARD_CONFLICT", name) from exc
            self._event(connection, iteration_id, "shard.registered", occurred_at=occurred_at,
                        shard_id=shard_id, shard_name=name, fact_ref=scope_ref,
                        payload={"order": order, "targets": list(targets), "authorizedTeam": authorized_team})
            return _decode(connection.execute("SELECT * FROM shards WHERE iteration_id=? AND shard_id=?", (iteration_id, shard_id)).fetchone()) or {}

    def rename_shard(self, iteration_id: str, shard_id: str, new_name: str, *, occurred_at: str | None = None) -> dict[str, Any]:
        """只更新展示名；claim 外键、generation 和历史事件身份均不变。"""

        self.initialize()
        if not new_name or not new_name.strip():
            raise CoordinationError("COORDINATION.INVALID_SHARD_NAME", "新分片名必须非空")
        with self._transaction() as connection:
            shard = self._shard(connection, iteration_id, shard_id)
            if shard["name"] == new_name:
                return _decode(shard) or {}
            try:
                connection.execute("UPDATE shards SET name=? WHERE iteration_id=? AND shard_id=?", (new_name, iteration_id, shard_id))
            except sqlite3.IntegrityError as exc:
                raise ConflictError("COORDINATION.SHARD_NAME_CONFLICT", new_name) from exc
            self._event(connection, iteration_id, "shard.renamed", occurred_at=occurred_at,
                        shard_id=shard_id, shard_name=new_name, fact_ref=shard["scope_ref"],
                        payload={"previousName": shard["name"]})
            return _decode(connection.execute("SELECT * FROM shards WHERE iteration_id=? AND shard_id=?", (iteration_id, shard_id)).fetchone()) or {}

    def claim(self, iteration_id: str, team: str, idempotency_key: str, *, shard_id: str | None = None,
              deployment_id: str | None = None, occurred_at: str | None = None) -> dict[str, Any]:
        self.initialize()
        if not team or not idempotency_key:
            raise CoordinationError("COORDINATION.INVALID_ARGUMENT", "team 和 idempotency_key 必须非空")
        with self._transaction() as connection:
            self._require_iteration(connection, iteration_id)
            replay = connection.execute("SELECT operation,result FROM operations WHERE iteration_id=? AND idempotency_key=?", (iteration_id, idempotency_key)).fetchone()
            if replay:
                if replay["operation"] != "claim":
                    raise ConflictError("COORDINATION.IDEMPOTENCY_CONFLICT", idempotency_key)
                result = json.loads(replay["result"])
                if result.get("team") != team:
                    raise ConflictError("COORDINATION.IDEMPOTENCY_CONFLICT", idempotency_key)
                return result
            current = connection.execute("SELECT * FROM claims WHERE iteration_id=? AND team=? AND state IN ('claimed','draining','blocked')", (iteration_id, team)).fetchone()
            if current:
                result = self._claim_view(connection, current)
                connection.execute("INSERT INTO operations VALUES(?,?,?,?)", (iteration_id, idempotency_key, "claim", _json(result)))
                return result
            deployment = None
            if deployment_id:
                deployment = connection.execute("SELECT * FROM deployments WHERE iteration_id=? AND deployment_id=?", (iteration_id, deployment_id)).fetchone()
                if deployment is None:
                    raise NotFoundError("COORDINATION.DEPLOYMENT_NOT_FOUND", deployment_id)
                if not deployment["instance_id"] or not deployment["account_identity_ref"] or not deployment["resource_reservation_ref"]:
                    raise ConflictError("COORDINATION.RESOURCE_RESERVATION_REQUIRED", deployment_id)
                current_deployment = connection.execute(
                    "SELECT * FROM claims WHERE iteration_id=? AND deployment_id=? AND state IN ('claimed','draining','blocked')",
                    (iteration_id, deployment_id),
                ).fetchone()
                if current_deployment:
                    result = self._claim_view(connection, current_deployment)
                    if result["team"] != team:
                        raise ConflictError("COORDINATION.DEPLOYMENT_ALREADY_CLAIMED", deployment_id)
                    connection.execute("INSERT INTO operations VALUES(?,?,?,?)", (iteration_id, idempotency_key, "claim", _json(result)))
                    return result
            params: list[Any] = [iteration_id, team]
            sql = "SELECT * FROM shards WHERE iteration_id=? AND state='available' AND (authorized_team IS NULL OR authorized_team=?)"
            if shard_id is not None:
                sql += " AND shard_id=?"
                params.append(shard_id)
            sql += " ORDER BY ordinal, shard_id LIMIT 1"
            shard = connection.execute(sql, params).fetchone()
            if shard is None:
                if shard_id and connection.execute("SELECT 1 FROM shards WHERE iteration_id=? AND shard_id=?", (iteration_id, shard_id)).fetchone() is None:
                    raise NotFoundError("COORDINATION.SHARD_NOT_FOUND", shard_id)
                raise ConflictError("COORDINATION.NO_SHARD_AVAILABLE", shard_id or iteration_id)
            occupied = [target for target in json.loads(shard["targets"]) if connection.execute("SELECT 1 FROM target_occupancy WHERE target_ref=?", (target,)).fetchone()]
            if occupied:
                raise ConflictError("COORDINATION.TARGET_OCCUPIED", occupied[0])
            generation = int(connection.execute("SELECT COALESCE(MAX(generation),0)+1 FROM claims WHERE iteration_id=? AND shard_id=?", (iteration_id, shard["shard_id"])).fetchone()[0])
            now = _now()
            try:
                cursor = connection.execute("INSERT INTO claims(iteration_id,shard_id,team,generation,state,idempotency_key,deployment_id,claimed_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                            (iteration_id, shard["shard_id"], team, generation, "claimed", idempotency_key, deployment_id, now, now))
                connection.execute("UPDATE shards SET state='claimed' WHERE iteration_id=? AND shard_id=? AND state='available'", (iteration_id, shard["shard_id"]))
                for target in json.loads(shard["targets"]):
                    connection.execute("INSERT INTO target_occupancy VALUES(?,?,?)", (iteration_id, target, cursor.lastrowid))
            except sqlite3.IntegrityError as exc:
                raise ConflictError("COORDINATION.CLAIM_CONFLICT", team) from exc
            claim = connection.execute("SELECT * FROM claims WHERE claim_id=?", (cursor.lastrowid,)).fetchone()
            result = self._claim_view(connection, claim)
            connection.execute("INSERT INTO operations VALUES(?,?,?,?)", (iteration_id, idempotency_key, "claim", _json(result)))
            self._event(connection, iteration_id, "claim.acquired", occurred_at=occurred_at,
                        shard_id=shard["shard_id"], shard_name=shard["name"], deployment_id=deployment_id,
                        team=team, generation=generation, payload={"claimId": cursor.lastrowid})
            return result

    def _claim_view(self, connection: sqlite3.Connection, claim: sqlite3.Row) -> dict[str, Any]:
        shard = self._shard(connection, claim["iteration_id"], claim["shard_id"])
        result = _decode(claim) or {}
        result.update({"name": shard["name"], "scope_ref": shard["scope_ref"], "order": shard["ordinal"], "targets": json.loads(shard["targets"])})
        return result

    def _active_claim(self, connection: sqlite3.Connection, iteration_id: str, shard_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM claims WHERE iteration_id=? AND shard_id=? AND state IN ('claimed','draining','blocked')", (iteration_id, shard_id)).fetchone()
        if row is None:
            raise NotFoundError("COORDINATION.ACTIVE_CLAIM_NOT_FOUND", shard_id)
        return row

    @staticmethod
    def _assert_owner(claim: sqlite3.Row, owner: str, generation: int) -> None:
        if claim["team"] != owner or claim["generation"] != generation:
            raise ConflictError("COORDINATION.STALE_CLAIM", f"{owner}@{generation}")

    def _assert_write_authorized_in_connection(
        self, connection: sqlite3.Connection, token: WriteFenceToken,
    ) -> None:
        if (
            not isinstance(token, WriteFenceToken)
            or not token.iteration_id
            or not token.shard_id
            or not token.deployment_id
            or not token.team
            or not isinstance(token.generation, int)
            or isinstance(token.generation, bool)
            or token.generation < 1
            or not token.target_ref
        ):
            raise CoordinationError(
                "COORDINATION.WRITE_FENCE_INVALID",
                "write fence token 字段必须完整且 generation 为正整数",
            )
        self._require_iteration(connection, token.iteration_id)
        shard = self._shard(connection, token.iteration_id, token.shard_id)
        claim = connection.execute(
            "SELECT * FROM claims WHERE iteration_id=? AND shard_id=? "
            "AND state IN ('claimed','draining','blocked')",
            (token.iteration_id, token.shard_id),
        ).fetchone()
        if claim is None or claim["team"] != token.team or claim["generation"] != token.generation:
            raise ConflictError(
                "COORDINATION.WRITE_FENCE_STALE_CLAIM",
                f"{token.team}@{token.generation}",
            )
        if claim["deployment_id"] != token.deployment_id:
            raise ConflictError(
                "COORDINATION.WRITE_FENCE_DEPLOYMENT_MISMATCH",
                token.deployment_id,
            )
        if claim["state"] not in ("claimed", "draining"):
            raise ConflictError(
                "COORDINATION.WRITE_FENCE_STATE_FORBIDDEN",
                str(claim["state"]),
            )
        if token.target_ref not in json.loads(shard["targets"]):
            raise ConflictError(
                "COORDINATION.WRITE_FENCE_TARGET_OUTSIDE_SHARD",
                token.target_ref,
            )
        occupancy = connection.execute(
            "SELECT claim_id FROM target_occupancy WHERE iteration_id=? AND target_ref=?",
            (token.iteration_id, token.target_ref),
        ).fetchone()
        if occupancy is None or occupancy["claim_id"] != claim["claim_id"]:
            raise ConflictError(
                "COORDINATION.WRITE_FENCE_TARGET_NOT_OCCUPIED",
                token.target_ref,
            )

    def assert_write_authorized(self, token: WriteFenceToken) -> None:
        """执行无外部写副作用的授权预检；该快照检查不防 TOCTOU。"""

        self.initialize()
        with self._connect() as connection:
            self._assert_write_authorized_in_connection(connection, token)

    def fenced_write_many(
        self, tokens: Sequence[WriteFenceToken], write_callable: Callable[[], _WRITE_RESULT],
    ) -> _WRITE_RESULT:
        """同一 deployment/shard/generation 的多个 target 在一次有限提交中共同核权。"""

        self.initialize()
        if not tokens or not callable(write_callable):
            raise CoordinationError("COORDINATION.WRITE_FENCE_CALLABLE_REQUIRED", "tokens 与 write_callable 必须有效")
        identities = {(token.iteration_id, token.shard_id, token.deployment_id, token.team, token.generation) for token in tokens}
        if len(identities) != 1 or len({token.target_ref for token in tokens}) != len(tokens):
            raise CoordinationError("COORDINATION.WRITE_FENCE_TOKEN_SET_INVALID", "token 必须同 claim 且 target 唯一")
        with self._transaction() as connection:
            for token in tokens:
                self._assert_write_authorized_in_connection(connection, token)
            return write_callable()

    def fenced_write(
        self, token: WriteFenceToken, write_callable: Callable[[], _WRITE_RESULT],
    ) -> _WRITE_RESULT:
        """在 coordination 写锁覆盖期间核权并执行一次有限外部提交。

        锁顺序固定为 coordination DB -> execution/publish lock；禁止反序。
        callable 必须自行保证外部写原子性。若 callable 抛异常，本方法会回滚
        coordination 事务并原样传播异常，但无法替调用方回滚已经发生的外部写。
        """

        self.initialize()
        if not callable(write_callable):
            raise CoordinationError(
                "COORDINATION.WRITE_FENCE_CALLABLE_REQUIRED",
                "write_callable 必须可调用",
            )
        with self._transaction() as connection:
            self._assert_write_authorized_in_connection(connection, token)
            return write_callable()

    def begin_drain(self, iteration_id: str, shard_id: str, owner: str, generation: int, idempotency_key: str, *, occurred_at: str | None = None) -> dict[str, Any]:
        return self._transition(iteration_id, shard_id, owner, generation, idempotency_key, "draining", "claim.drain-began", occurred_at=occurred_at)

    def block(self, iteration_id: str, shard_id: str, owner: str, generation: int, idempotency_key: str, *, fact_ref: str, fact_digest: str | None = None, occurred_at: str | None = None) -> dict[str, Any]:
        return self._transition(iteration_id, shard_id, owner, generation, idempotency_key, "blocked", "claim.blocked", fact_ref=fact_ref, fact_digest=fact_digest, occurred_at=occurred_at)

    def recover(self, iteration_id: str, shard_id: str, owner: str, generation: int, idempotency_key: str, *, recovery_ref: str, fact_digest: str | None = None, occurred_at: str | None = None) -> dict[str, Any]:
        return self._transition(iteration_id, shard_id, owner, generation, idempotency_key, "claimed", "claim.manually-recovered", fact_ref=recovery_ref, fact_digest=fact_digest, occurred_at=occurred_at)

    manual_recovery = recover

    @_control_gate("shard")
    def _transition(self, iteration_id: str, shard_id: str, owner: str, generation: int, idempotency_key: str,
                    state: str, event_type: str, *, fact_ref: str | None = None,
                    fact_digest: str | None = None, occurred_at: str | None = None) -> dict[str, Any]:
        self.initialize()
        with self._transaction() as connection:
            replay = connection.execute("SELECT operation,result FROM operations WHERE iteration_id=? AND idempotency_key=?", (iteration_id, idempotency_key)).fetchone()
            if replay:
                if replay["operation"] != event_type:
                    raise ConflictError("COORDINATION.IDEMPOTENCY_CONFLICT", idempotency_key)
                return json.loads(replay["result"])
            claim = self._active_claim(connection, iteration_id, shard_id)
            self._assert_owner(claim, owner, generation)
            shard = self._shard(connection, iteration_id, shard_id)
            connection.execute("UPDATE claims SET state=?,updated_at=? WHERE claim_id=?", (state, _now(), claim["claim_id"]))
            connection.execute("UPDATE shards SET state=? WHERE iteration_id=? AND shard_id=?", (state, iteration_id, shard_id))
            result = self._claim_view(connection, connection.execute("SELECT * FROM claims WHERE claim_id=?", (claim["claim_id"],)).fetchone())
            connection.execute("INSERT INTO operations VALUES(?,?,?,?)", (iteration_id, idempotency_key, event_type, _json(result)))
            self._event(connection, iteration_id, event_type, occurred_at=occurred_at,
                        shard_id=shard_id, shard_name=shard["name"], deployment_id=claim["deployment_id"],
                        team=owner, generation=generation, fact_ref=fact_ref, fact_digest=fact_digest)
            return result

    @_control_gate("shard")
    def release(self, iteration_id: str, shard_id: str, owner: str, generation: int, idempotency_key: str, *, handoff_ref: str, remaining: bool, handoff_digest: str | None = None, occurred_at: str | None = None) -> dict[str, Any]:
        self.initialize()
        if not handoff_ref:
            raise CoordinationError("COORDINATION.HANDOFF_REQUIRED", "release 必须提供 handoff_ref")
        with self._transaction() as connection:
            replay = connection.execute("SELECT operation,result FROM operations WHERE iteration_id=? AND idempotency_key=?", (iteration_id, idempotency_key)).fetchone()
            if replay:
                if replay["operation"] != "release":
                    raise ConflictError("COORDINATION.IDEMPOTENCY_CONFLICT", idempotency_key)
                prior = json.loads(replay["result"])
                if (prior.get("shard_id"), prior.get("team"), prior.get("generation"), prior.get("handoff_ref"), prior.get("remaining")) != (shard_id, owner, generation, handoff_ref, remaining):
                    raise ConflictError("COORDINATION.IDEMPOTENCY_CONFLICT", idempotency_key)
                return prior
            claim = self._active_claim(connection, iteration_id, shard_id)
            self._assert_owner(claim, owner, generation)
            shard = self._shard(connection, iteration_id, shard_id)
            batches = connection.execute("SELECT * FROM batch_scopes WHERE claim_id=?", (claim["claim_id"],)).fetchall()
            if batches:
                from .runtime import batch_facts, is_member, member_key
                context = connection.execute("SELECT roots FROM deployment_contexts WHERE iteration_id=? AND deployment_id=?", (iteration_id, claim["deployment_id"])).fetchone()
                if context is None or any(not batch_facts(_decode(batch), json.loads(context["roots"]))["closed"] for batch in batches):
                    raise ConflictError("COORDINATION.BATCHES_UNCLOSED", "handoff/remaining boolean 不证明批次闭合")
            state = "available" if remaining else "closed"
            connection.execute("UPDATE claims SET state='released',handoff_ref=?,remaining=?,updated_at=? WHERE claim_id=?", (handoff_ref, int(remaining), _now(), claim["claim_id"]))
            connection.execute("DELETE FROM target_occupancy WHERE claim_id=?", (claim["claim_id"],))
            connection.execute("UPDATE shards SET state=? WHERE iteration_id=? AND shard_id=?", (state, iteration_id, shard_id))
            result = {"iteration_id": iteration_id, "shard_id": shard_id, "name": shard["name"], "team": owner,
                      "generation": generation, "state": state, "handoff_ref": handoff_ref, "remaining": bool(remaining)}
            connection.execute("INSERT INTO operations VALUES(?,?,?,?)", (iteration_id, idempotency_key, "release", _json(result)))
            self._event(connection, iteration_id, "claim.released", occurred_at=occurred_at,
                        shard_id=shard_id, shard_name=shard["name"], deployment_id=claim["deployment_id"],
                        team=owner, generation=generation, fact_ref=handoff_ref, fact_digest=handoff_digest,
                        payload={"remaining": bool(remaining), "resultingState": state})
            return result

    def append_checkpoint(self, iteration_id: str, *, fact_ref: str, fact_digest: str,
                          source_type: str, occurred_at: str | None = None,
                          payload: Mapping[str, Any] | None = None, shard_id: str | None = None,
                          deployment_id: str | None = None) -> dict[str, Any]:
        """追加外部事实 checkpoint；不解释 payload，也不推导 completed。"""

        self.initialize()
        if not fact_ref or not fact_digest or not source_type:
            raise CoordinationError("COORDINATION.INVALID_CHECKPOINT", "fact_ref、fact_digest、source_type 均必填")
        document = dict(payload or {})
        if "completed" in document:
            raise CoordinationError("COORDINATION.COMPLETION_AUTHORITY_FORBIDDEN", "checkpoint 不得写 completed authority")
        with self._transaction() as connection:
            self._require_iteration(connection, iteration_id)
            shard = self._shard(connection, iteration_id, shard_id) if shard_id else None
            if deployment_id and connection.execute("SELECT 1 FROM deployments WHERE iteration_id=? AND deployment_id=?", (iteration_id, deployment_id)).fetchone() is None:
                raise NotFoundError("COORDINATION.DEPLOYMENT_NOT_FOUND", deployment_id)
            existing = connection.execute("SELECT * FROM checkpoints WHERE iteration_id=? AND fact_ref=?", (iteration_id, fact_ref)).fetchone()
            if existing:
                if (existing["fact_digest"], existing["source_type"], existing["shard_id"], existing["deployment_id"]) != (fact_digest, source_type, shard_id, deployment_id):
                    raise ConflictError("COORDINATION.CHECKPOINT_FACT_DRIFT", fact_ref)
                return json.loads(existing["result"])
            result = self._event(connection, iteration_id, "checkpoint.appended", occurred_at=occurred_at,
                                 shard_id=shard_id, shard_name=shard["name"] if shard else None,
                                 deployment_id=deployment_id, fact_ref=fact_ref, fact_digest=fact_digest,
                                 source_type=source_type, payload=document)
            connection.execute("INSERT INTO checkpoints VALUES(?,?,?,?,?,?,?)",
                               (iteration_id, fact_ref, fact_digest, source_type, shard_id, deployment_id, _json(result)))
            return result

    def status(self, iteration_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as connection:
            iteration = connection.execute("SELECT * FROM iterations WHERE iteration_id=?", (iteration_id,)).fetchone()
            if iteration is None:
                raise NotFoundError("COORDINATION.ITERATION_NOT_FOUND", iteration_id)
            deployments = [_decode(row) for row in connection.execute("SELECT * FROM deployments WHERE iteration_id=? ORDER BY deployment_id", (iteration_id,))]
            shards = []
            for row in connection.execute("SELECT * FROM shards WHERE iteration_id=? ORDER BY ordinal,shard_id", (iteration_id,)):
                item = _decode(row) or {}
                claim = connection.execute("SELECT * FROM claims WHERE iteration_id=? AND shard_id=? ORDER BY generation DESC LIMIT 1", (iteration_id, row["shard_id"])).fetchone()
                item["claim"] = self._claim_view(connection, claim) if claim else None
                shards.append(item)
            contexts = [_decode(row) for row in connection.execute("SELECT * FROM deployment_contexts WHERE iteration_id=?", (iteration_id,))]
            batches = [_decode(row) for row in connection.execute("SELECT b.* FROM batch_scopes b JOIN claims c ON c.claim_id=b.claim_id WHERE c.iteration_id=?", (iteration_id,))]
            return {"iteration": _decode(iteration), "deployments": deployments, "shards": shards, "contexts": contexts, "batches": batches}

    def timeline(self, iteration_id: str, *, shard_id: str | None = None,
                 deployment_id: str | None = None, after_sequence: int = 0,
                 limit: int | None = None) -> list[dict[str, Any]]:
        self.initialize()
        clauses = ["iteration_id=?", "sequence>?"]
        params: list[Any] = [iteration_id, after_sequence]
        if shard_id is not None:
            clauses.append("shard_id=?")
            params.append(shard_id)
        if deployment_id is not None:
            clauses.append("deployment_id=?")
            params.append(deployment_id)
        sql = "SELECT * FROM timeline WHERE " + " AND ".join(clauses) + " ORDER BY sequence"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self._connect() as connection:
            return [_decode(row) or {} for row in connection.execute(sql, params)]


Store = CoordinationStore
