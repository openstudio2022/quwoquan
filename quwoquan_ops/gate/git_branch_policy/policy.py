"""Git 分支政策模型、严格 YAML 解析与无副作用转换判定。"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

ZERO_SHA = "0" * 40
FAILURE_CODE_KEYS = frozenset(
    {
        "policy_invalid",
        "ref_not_allowed",
        "direct_push_not_allowed",
        "backsync_not_fast_forward",
        "backsync_cas_conflict",
        "authority_unavailable",
        "source_not_main_reachable",
        "integration_read_only",
    }
)
FAILURE_CODE_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*$"
)
FIXED_PERSISTENT_LANE_BRANCHES = frozenset(
    {
        "lane/product-mainline",
        "lane/data-engineering",
        "lane/engineering",
        "lane/ops",
        "lane/small-fix",
        "lane/refactor",
    }
)
BRANCH_POLICY_FIELDS = frozenset(
    {
        "allowed_local_branches",
        "allowed_remote_branches",
        "pull_request_branch_prefixes",
        "integration_branch",
        "release_branch",
        "source_admission_branch",
        "production_selector",
        "production_workflow",
        "required_promotion_checks",
        "allowed_pull_request_edges",
        "integration_branch_updates",
        "system_backsync",
        "persistent_lane_admission",
        "failure_codes",
    }
)
RECOVERY_BY_FAILURE_KEY = {
    "policy_invalid": "repair_canonical_branch_policy",
    "ref_not_allowed": "use_declared_branch_and_allowed_pr_edge_then_retry",
    "direct_push_not_allowed": "use_canonical_publisher_or_allowed_pull_request_then_retry",
    "backsync_not_fast_forward": "restore_fast_forward_backsync_precondition",
    "backsync_cas_conflict": "refresh_remote_refs_and_retry_compare_and_swap",
    "authority_unavailable": "restore_git_authority_then_retry",
    "source_not_main_reachable": "select_exact_main_reachable_source",
    "integration_read_only": "commit_from_writable_lane_or_integration_worktree",
}


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects ambiguous mappings at every nesting level."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)

@dataclass(frozen=True)
class PullRequestEdge:
    base: str
    head: str

    def matches(self, *, head: str, base: str) -> bool:
        if base != self.base:
            return False
        if self.head.endswith("*"):
            return head.startswith(self.head[:-1])
        return head == self.head

    @property
    def prefix(self) -> str | None:
        return self.head[:-1] if self.head.endswith("*") else None


@dataclass(frozen=True)
class SystemBacksync:
    head: str
    base: str
    mode: str


@dataclass(frozen=True)
class IntegrationBranchUpdates:
    accepted: tuple[str, ...]
    ordinary_direct_push: str


@dataclass(frozen=True)
class ProductionSelector:
    source: str
    accepted_tag_kind: str
    exact_oci_digests_required: bool
    main_head_denied: bool
    mutable_pointer_denied: bool


@dataclass(frozen=True)
class RequiredPromotionCheck:
    name: str
    workflow: str


@dataclass(frozen=True)
class PersistentLaneAdmission:
    isolation: str
    promotion: str
    resync: str
    worktree_lifecycle: str
    concurrency_evidence: str


@dataclass(frozen=True)
class BranchPolicy:
    allowed_local: frozenset[str]
    allowed_remote: frozenset[str]
    pull_request_prefixes: frozenset[str]
    integration_branch: str
    release_branch: str
    source_admission_branch: str
    production_selector: ProductionSelector
    production_workflow: str
    required_promotion_checks: tuple[RequiredPromotionCheck, ...]
    allowed_pull_request_edges: tuple[PullRequestEdge, ...]
    integration_branch_updates: IntegrationBranchUpdates
    system_backsync: SystemBacksync | None
    persistent_lane_admission: PersistentLaneAdmission | None
    failure_codes: tuple[tuple[str, str], ...]

    def failure_code(self, name: str) -> str:
        for key, code in self.failure_codes:
            if key == name:
                return code
        raise KeyError(name)


@dataclass(frozen=True)
class BranchTransition:
    event: str
    actor_kind: str
    repository: str
    head: str | None = None
    base: str | None = None
    before_oid: str | None = None
    after_oid: str | None = None
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class BranchDecision:
    status: str
    reason_code: str | None = None
    recovery_action: str | None = None
    string_context: tuple[tuple[str, str], ...] = ()

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


def _strict_string(value: object, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"branch policy {label} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"branch policy {label} must be non-empty and trimmed")
    return value


def _required_string(payload: Mapping[str, object], key: str) -> str:
    return _strict_string(payload.get(key), key)


def _string_set(
    payload: Mapping[str, object], key: str, *, allow_empty: bool = False
) -> frozenset[str]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise TypeError(f"branch policy {key} must be a list")
    rows = [
        _strict_string(value, f"{key}[{index}]")
        for index, value in enumerate(raw)
    ]
    if (not rows and not allow_empty) or len(rows) != len(set(rows)):
        qualifier = "duplicate-free" if allow_empty else "non-empty and duplicate-free"
        raise ValueError(f"branch policy {key} must be {qualifier}")
    return frozenset(rows)


def _required_promotion_checks(
    payload: Mapping[str, object],
) -> tuple[RequiredPromotionCheck, ...]:
    key = "required_promotion_checks"
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise TypeError(f"branch policy {key} must be a list")
    rows: list[RequiredPromotionCheck] = []
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise TypeError(f"branch policy {key}[{index}] must be a mapping")
        rows.append(
            RequiredPromotionCheck(
                name=_required_string(value, "name"),
                workflow=_required_string(value, "workflow"),
            )
        )
    if not rows or len(rows) != len(set(rows)):
        raise ValueError(f"branch policy {key} must be non-empty and duplicate-free")
    if len({row.name for row in rows}) != len(rows):
        raise ValueError(f"branch policy {key} names must be duplicate-free")
    if len({row.workflow for row in rows}) != len(rows):
        raise ValueError(f"branch policy {key} workflows must be duplicate-free")
    for row in rows:
        if not row.workflow.startswith(".github/workflows/") or not row.workflow.endswith(
            (".yml", ".yaml")
        ):
            raise ValueError(
                f"branch policy {key} workflow must be a repository workflow path"
            )
    return tuple(rows)


def _pull_request_edges(payload: Mapping[str, object]) -> tuple[PullRequestEdge, ...]:
    raw = payload.get("allowed_pull_request_edges")
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "branch policy allowed_pull_request_edges must be a non-empty list"
        )
    edges: list[PullRequestEdge] = []
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise TypeError(
                f"branch policy allowed_pull_request_edges[{index}] must be a mapping"
            )
        base = _required_string(value, "base")
        head = _required_string(value, "head")
        if "*" in head and (not head.endswith("*") or head.count("*") != 1):
            raise ValueError(
                f"branch policy allowed_pull_request_edges[{index}].head only supports a single trailing wildcard"
            )
        edges.append(PullRequestEdge(base=base, head=head))
    if len(edges) != len(set(edges)):
        raise ValueError(
            "branch policy allowed_pull_request_edges must be duplicate-free"
        )
    return tuple(edges)


def _exact_mapping(
    value: object, *, label: str, fields: frozenset[str]
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"branch policy {label} must be a mapping")
    actual = set(value)
    if actual != fields:
        raise ValueError(
            f"branch policy {label} fields drifted; "
            f"missing={sorted(fields - actual)}, unexpected={sorted(actual - fields, key=repr)}"
        )
    return value


def _strict_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"branch policy {label} must be a boolean")
    return value


def _string_tuple(
    payload: Mapping[str, object], key: str, *, label_prefix: str = ""
) -> tuple[str, ...]:
    label = f"{label_prefix}.{key}" if label_prefix else key
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise TypeError(f"branch policy {label} must be a list")
    rows = tuple(
        _strict_string(value, f"{label}[{index}]")
        for index, value in enumerate(raw)
    )
    if not rows or len(rows) != len(set(rows)):
        raise ValueError(f"branch policy {label} must be non-empty and duplicate-free")
    return rows


def _production_selector(payload: Mapping[str, object]) -> ProductionSelector:
    key = "production_selector"
    raw = _exact_mapping(
        payload.get(key),
        label=key,
        fields=frozenset(
            {
                "source",
                "acceptedTagKind",
                "exactOciDigestsRequired",
                "mainHeadDenied",
                "mutablePointerDenied",
            }
        ),
    )
    selector = ProductionSelector(
        source=_strict_string(raw.get("source"), f"{key}.source"),
        accepted_tag_kind=_strict_string(
            raw.get("acceptedTagKind"), f"{key}.acceptedTagKind"
        ),
        exact_oci_digests_required=_strict_bool(
            raw.get("exactOciDigestsRequired"),
            f"{key}.exactOciDigestsRequired",
        ),
        main_head_denied=_strict_bool(
            raw.get("mainHeadDenied"), f"{key}.mainHeadDenied"
        ),
        mutable_pointer_denied=_strict_bool(
            raw.get("mutablePointerDenied"),
            f"{key}.mutablePointerDenied",
        ),
    )
    if selector != ProductionSelector(
        source="ReleaseTagAdmissionFact",
        accepted_tag_kind="stable",
        exact_oci_digests_required=True,
        main_head_denied=True,
        mutable_pointer_denied=True,
    ):
        raise ValueError(
            "branch policy production_selector must accept only stable "
            "ReleaseTagAdmissionFact exact OCI digests and deny main HEAD/mutable pointers"
        )
    return selector


def _integration_branch_updates(payload: Mapping[str, object]) -> IntegrationBranchUpdates:
    key = "integration_branch_updates"
    raw = _exact_mapping(
        payload.get(key),
        label=key,
        fields=frozenset({"accepted", "ordinary_direct_push"}),
    )
    updates = IntegrationBranchUpdates(
        accepted=_string_tuple(raw, "accepted", label_prefix=key),
        ordinary_direct_push=_strict_string(
            raw.get("ordinary_direct_push"), f"{key}.ordinary_direct_push"
        ),
    )
    if updates.accepted != (
        "trusted_integration_publisher_cas",
        "integration_worktree_fast_forward",
        "system_fast_forward_backsync",
    ) or (
        updates.ordinary_direct_push
        != "matching_integration_fast_forward_only"
    ):
        raise ValueError(
            "branch policy integration_branch_updates must accept exactly trusted "
            "publisher CAS/integration worktree fast-forward/system fast-forward "
            "backsync and restrict ordinary direct push to matching integration "
            "fast-forward only"
        )
    return updates

def _system_backsync(payload: Mapping[str, object]) -> SystemBacksync | None:
    raw = payload.get("system_backsync")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise TypeError("branch policy system_backsync must be a mapping")
    return SystemBacksync(
        head=_required_string(raw, "head"),
        base=_required_string(raw, "base"),
        mode=_required_string(raw, "mode"),
    )


def _persistent_lane_admission(
    payload: Mapping[str, object],
) -> PersistentLaneAdmission | None:
    raw = payload.get("persistent_lane_admission")
    if raw is None:
        return None
    expected = {
        "isolation": "branch_per_writer",
        "promotion": "declared_pull_request_edge_only",
        "resync": "mandatory_fast_forward_after_integration_or_abort",
        "worktree_lifecycle": "retained",
        "concurrency_evidence": "required",
    }
    if not isinstance(raw, Mapping) or set(raw) != set(expected):
        raise ValueError(
            "branch policy persistent_lane_admission must contain the exact "
            "isolation/promotion/resync/worktree_lifecycle/concurrency_evidence lifecycle fields"
        )
    values = {
        key: _strict_string(raw.get(key), f"persistent_lane_admission.{key}")
        for key in expected
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            raise ValueError(
                f"branch policy persistent_lane_admission.{key} must be "
                f"{expected_value!r}"
            )
    return PersistentLaneAdmission(**values)


def _failure_codes(payload: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    raw = payload.get("failure_codes")
    if not isinstance(raw, Mapping):
        raise TypeError("branch policy failure_codes must be a mapping")
    for key in raw:
        _strict_string(key, "failure_codes key")
    keys = frozenset(raw)
    if keys != FAILURE_CODE_KEYS:
        missing = sorted(FAILURE_CODE_KEYS - keys)
        unexpected = sorted(keys - FAILURE_CODE_KEYS)
        raise ValueError(
            "branch policy failure_codes must contain the exact canonical keys; "
            f"missing={missing}, unexpected={unexpected}"
        )
    rows: list[tuple[str, str]] = []
    for key in sorted(FAILURE_CODE_KEYS):
        code = _strict_string(raw.get(key), f"failure_codes.{key}")
        if not FAILURE_CODE_PATTERN.fullmatch(code):
            raise ValueError(
                f"branch policy failure_codes.{key} must use MODULE.KIND.REASON"
            )
        rows.append((key, code))
    if len({code for _, code in rows}) != len(rows):
        raise ValueError("branch policy failure_codes must be duplicate-free")
    return tuple(rows)


def load_policy_bytes(raw: bytes) -> BranchPolicy:
    """Parse and validate one exact byte snapshot of canonical branch policy."""
    if not isinstance(raw, bytes):
        raise TypeError("branch policy raw input must be bytes")
    decoded = raw.decode("utf-8", errors="strict")
    loaded = yaml.load(decoded, Loader=_UniqueKeySafeLoader)
    payload = {} if loaded is None else loaded
    if not isinstance(payload, Mapping):
        raise TypeError("branch policy root must be a mapping")
    actual_fields = set(payload)
    required_fields = BRANCH_POLICY_FIELDS - {
        "system_backsync", "persistent_lane_admission",
    }
    missing = sorted(required_fields - actual_fields)
    unexpected = sorted(actual_fields - BRANCH_POLICY_FIELDS, key=repr)
    if missing or unexpected:
        raise ValueError(
            "branch policy root fields drifted; "
            f"missing={missing}, unexpected={unexpected}"
        )
    integration_branch = _required_string(payload, "integration_branch")
    policy = BranchPolicy(
        allowed_local=_string_set(payload, "allowed_local_branches"),
        allowed_remote=_string_set(payload, "allowed_remote_branches"),
        pull_request_prefixes=_string_set(
            payload, "pull_request_branch_prefixes", allow_empty=True
        ),
        integration_branch=integration_branch,
        release_branch=_required_string(payload, "release_branch"),
        source_admission_branch=_required_string(payload, "source_admission_branch"),
        production_selector=_production_selector(payload),
        production_workflow=_required_string(payload, "production_workflow"),
        required_promotion_checks=_required_promotion_checks(payload),
        allowed_pull_request_edges=_pull_request_edges(payload),
        integration_branch_updates=_integration_branch_updates(payload),
        system_backsync=_system_backsync(payload),
        persistent_lane_admission=_persistent_lane_admission(payload),
        failure_codes=_failure_codes(payload),
    )
    for branch_name in (
        policy.integration_branch,
        policy.release_branch,
        policy.source_admission_branch,
    ):
        if (
            branch_name not in policy.allowed_local
            or branch_name not in policy.allowed_remote
        ):
            raise ValueError(
                f"branch policy role branch {branch_name!r} must be allowed both locally and remotely"
            )
    if policy.source_admission_branch != policy.release_branch:
        raise ValueError(
            "branch policy source_admission_branch must equal release_branch"
        )
    if not policy.production_workflow.startswith(
        ".github/workflows/"
    ) or not policy.production_workflow.endswith((".yml", ".yaml")):
        raise ValueError(
            "branch policy production_workflow must be a repository workflow path"
        )
    for edge in policy.allowed_pull_request_edges:
        if edge.base not in policy.allowed_remote:
            raise ValueError(
                f"branch policy PR base {edge.base!r} is not an allowed remote branch"
            )
        if edge.prefix is None and edge.head not in policy.allowed_local:
            raise ValueError(
                f"branch policy PR head {edge.head!r} is not an allowed local branch"
            )
        if edge.prefix is not None and edge.prefix not in policy.pull_request_prefixes:
            raise ValueError(
                f"branch policy PR head pattern {edge.head!r} is not a declared pull-request prefix"
            )
    if policy.persistent_lane_admission is not None:
        if policy.pull_request_prefixes != {"lane/"}:
            raise ValueError(
                "branch policy persistent lane admission requires the exact lane/ prefix"
            )
        expected_branches = FIXED_PERSISTENT_LANE_BRANCHES | {
            policy.integration_branch,
            policy.release_branch,
        }
        if policy.allowed_local != expected_branches or policy.allowed_remote != expected_branches:
            raise ValueError(
                "branch policy persistent lane admission requires exactly the six fixed "
                "lane branches plus integration and release"
            )
        expected_edges = {
            PullRequestEdge(head="lane/*", base=policy.integration_branch),
            PullRequestEdge(head=policy.integration_branch, base=policy.release_branch),
        }
        if set(policy.allowed_pull_request_edges) != expected_edges:
            raise ValueError(
                "branch policy persistent lane admission requires exactly the declared "
                "lane integration and integration promotion edges"
            )
    if policy.integration_branch == policy.release_branch:
        if policy.system_backsync is not None:
            raise ValueError(
                "branch policy with one integration/release branch cannot declare backsync"
            )
    else:
        expected_backsync = SystemBacksync(
            head=policy.release_branch,
            base=policy.integration_branch,
            mode="fast-forward-only",
        )
        if policy.system_backsync != expected_backsync:
            raise ValueError(
                "branch policy system_backsync must be release -> integration and fast-forward-only"
            )
    return policy


def load_policy(path: Path) -> BranchPolicy:
    """Read policy bytes once, then delegate to the sole parser."""
    return load_policy_bytes(path.read_bytes())


def _matches_pull_request_prefix(branch: str | None, prefixes: frozenset[str]) -> bool:
    return bool(branch) and any(branch.startswith(prefix) for prefix in prefixes)


def pull_request_context_from_environment(
    environment: Mapping[str, str],
) -> tuple[str | None, str | None]:
    """Return the reviewed source/base pair for GitHub's detached PR checkout."""
    if environment.get("GITHUB_ACTIONS") != "true":
        return None, None
    if environment.get("GITHUB_EVENT_NAME") != "pull_request":
        return None, None
    head_ref = environment.get("GITHUB_HEAD_REF", "").strip() or None
    base_ref = environment.get("GITHUB_BASE_REF", "").strip() or None
    return head_ref, base_ref


def repository_branch_context_from_environment(
    environment: Mapping[str, str],
) -> str | None:
    """Return the authoritative repository branch for push/manual GitHub runs."""
    if environment.get("GITHUB_ACTIONS") != "true":
        return None
    if environment.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}:
        return None
    ref_type = environment.get("GITHUB_REF_TYPE", "").strip()
    ref_name = environment.get("GITHUB_REF_NAME", "").strip()
    if ref_type != "branch" or not ref_name:
        return None
    return ref_name


def _decision_context(**values: str | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value) for key, value in values.items() if value))


def evaluate_transition(
    *,
    policy: BranchPolicy,
    transition: BranchTransition,
    is_ancestor: Callable[[str, str], bool] | None = None,
) -> BranchDecision:
    """Evaluate one immutable branch transition without performing side effects."""

    context = _decision_context(
        event=transition.event,
        actorKind=transition.actor_kind,
        repository=transition.repository,
        head=transition.head,
        base=transition.base,
        beforeOid=transition.before_oid,
        afterOid=transition.after_oid,
    )
    if transition.event == "pull_request":
        if (
            transition.head in policy.allowed_local
            and transition.head in policy.allowed_remote
            and transition.base in policy.allowed_remote
            and any(
                edge.matches(head=transition.head, base=transition.base)
                for edge in policy.allowed_pull_request_edges
            )
        ):
            return BranchDecision(status="allowed", string_context=context)
        return BranchDecision(
            status="blocked",
            reason_code=policy.failure_code("ref_not_allowed"),
            recovery_action=RECOVERY_BY_FAILURE_KEY["ref_not_allowed"],
            string_context=context,
        )
    if transition.event == "direct_push":
        if (
            transition.head == transition.base
            and transition.head in policy.allowed_local
            and _matches_pull_request_prefix(
                transition.head, policy.pull_request_prefixes
            )
        ):
            return BranchDecision(status="allowed", string_context=context)
        if (
            transition.actor_kind == "integration_worktree"
            and transition.head == policy.integration_branch
            and transition.base == policy.integration_branch
        ):
            if (
                not transition.before_oid
                or not transition.after_oid
                or transition.before_oid == ZERO_SHA
                or transition.after_oid == ZERO_SHA
            ):
                return BranchDecision(
                    status="blocked",
                    reason_code=policy.failure_code("direct_push_not_allowed"),
                    recovery_action=RECOVERY_BY_FAILURE_KEY["direct_push_not_allowed"],
                    string_context=context,
                )
            if transition.before_oid == transition.after_oid:
                return BranchDecision(status="allowed", string_context=context)
            if is_ancestor is None:
                return BranchDecision(
                    status="blocked",
                    reason_code=policy.failure_code("authority_unavailable"),
                    recovery_action=RECOVERY_BY_FAILURE_KEY["authority_unavailable"],
                    string_context=context,
                )
            try:
                ancestor = is_ancestor(
                    transition.before_oid, transition.after_oid
                )
            except (OSError, RuntimeError, subprocess.SubprocessError):
                return BranchDecision(
                    status="blocked",
                    reason_code=policy.failure_code("authority_unavailable"),
                    recovery_action=RECOVERY_BY_FAILURE_KEY["authority_unavailable"],
                    string_context=context,
                )
            if ancestor:
                return BranchDecision(status="allowed", string_context=context)
        return BranchDecision(
            status="blocked",
            reason_code=policy.failure_code("direct_push_not_allowed"),
            recovery_action=RECOVERY_BY_FAILURE_KEY["direct_push_not_allowed"],
            string_context=context,
        )
    if transition.event == "system_backsync":
        backsync = policy.system_backsync
        if (
            transition.actor_kind != "system"
            or backsync is None
            or transition.head != backsync.head
            or transition.base != backsync.base
            or not transition.before_oid
            or not transition.after_oid
        ):
            return BranchDecision(
                status="blocked",
                reason_code=policy.failure_code("ref_not_allowed"),
                recovery_action=RECOVERY_BY_FAILURE_KEY["ref_not_allowed"],
                string_context=context,
            )
        if transition.before_oid == transition.after_oid:
            return BranchDecision(status="allowed", string_context=context)
        if is_ancestor is None:
            return BranchDecision(
                status="blocked",
                reason_code=policy.failure_code("authority_unavailable"),
                recovery_action=RECOVERY_BY_FAILURE_KEY["authority_unavailable"],
                string_context=context,
            )
        try:
            ancestor = is_ancestor(transition.before_oid, transition.after_oid)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return BranchDecision(
                status="blocked",
                reason_code=policy.failure_code("authority_unavailable"),
                recovery_action=RECOVERY_BY_FAILURE_KEY["authority_unavailable"],
                string_context=context,
            )
        if ancestor:
            return BranchDecision(status="allowed", string_context=context)
        return BranchDecision(
            status="blocked",
            reason_code=policy.failure_code("backsync_not_fast_forward"),
            recovery_action=RECOVERY_BY_FAILURE_KEY["backsync_not_fast_forward"],
            string_context=context,
        )
    return BranchDecision(
        status="blocked",
        reason_code=policy.failure_code("policy_invalid"),
        recovery_action=RECOVERY_BY_FAILURE_KEY["policy_invalid"],
        string_context=context,
    )
