#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "quwoquan_ops/policies/branch_policy.yaml"
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
FAILURE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*$")
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
        "production_source_branch",
        "production_workflow",
        "required_promotion_checks",
        "allowed_pull_request_edges",
        "integration_branch_activation",
        "system_backsync",
        "persistent_lane_admission",
        "failure_codes",
    }
)
POLICY_INVALID_RECOVERY = "repair_canonical_branch_policy"
AUTHORITY_UNAVAILABLE_RECOVERY = "restore_git_authority_then_retry"
ACTIVATION_EVIDENCE_SCHEMA_VERSION = 1
ACTIVATION_STATES = frozenset({"bootstrap", "active"})
ACTIVATION_TRANSITION_COMMAND = (
    "python3 -B quwoquan_ops/gate/verify_git_branch_policy.py "
    "--activation-transition --evidence-path "
    ".qwq_output/env/repo/runs/branch-policy/dev1.0-activation.json"
)
SYSTEM_BACKSYNC_WORKFLOW_REF_SUFFIX = (
    "/.github/workflows/system-backsync.yml@refs/heads/main"
)
RECOVERY_BY_FAILURE_KEY = {
    "policy_invalid": POLICY_INVALID_RECOVERY,
    "ref_not_allowed": "use_declared_branch_and_allowed_pr_edge_then_retry",
    "direct_push_not_allowed": "open_allowed_pull_request_then_retry",
    "backsync_not_fast_forward": "restore_fast_forward_backsync_precondition",
    "backsync_cas_conflict": "refresh_remote_refs_and_retry_compare_and_swap",
    "authority_unavailable": AUTHORITY_UNAVAILABLE_RECOVERY,
    "source_not_main_reachable": "select_exact_main_reachable_source",
    "integration_read_only": "commit_from_a_lane_worktree_then_open_pull_request",
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
class IntegrationBranchActivation:
    state: str
    transition_command: str
    evidence_kind: str
    bootstrap_remote_before_oid: str
    bootstrap_remote_after_oid: str
    bootstrap_source_branch: str
    bootstrap_target_branch: str
    bootstrap_release_eligibility: bool
    active_accepted_updates: tuple[str, ...]
    active_direct_push: str


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
    production_source_branch: str
    production_workflow: str
    required_promotion_checks: tuple[RequiredPromotionCheck, ...]
    allowed_pull_request_edges: tuple[PullRequestEdge, ...]
    integration_branch_activation: IntegrationBranchActivation
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


def _run_git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


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


def _integration_branch_activation(
    payload: Mapping[str, object], *, integration_branch: str
) -> IntegrationBranchActivation:
    key = "integration_branch_activation"
    raw = _exact_mapping(
        payload.get(key),
        label=key,
        fields=frozenset(
            {"state", "transition_command", "evidence_kind", "bootstrap", "active"}
        ),
    )
    state = _strict_string(raw.get("state"), f"{key}.state")
    if state not in ACTIVATION_STATES:
        raise ValueError(
            "branch policy integration_branch_activation.state must be "
            "'bootstrap' or 'active'"
        )
    transition_command = _strict_string(
        raw.get("transition_command"), f"{key}.transition_command"
    )
    if transition_command != ACTIVATION_TRANSITION_COMMAND:
        raise ValueError(
            "branch policy integration_branch_activation.transition_command must equal "
            "the canonical activation transition CLI"
        )
    evidence_kind = _strict_string(raw.get("evidence_kind"), f"{key}.evidence_kind")
    if evidence_kind != "integration_branch_activation_v1":
        raise ValueError(
            "branch policy integration_branch_activation.evidence_kind must be "
            "'integration_branch_activation_v1'"
        )
    bootstrap = _exact_mapping(
        raw.get("bootstrap"),
        label=f"{key}.bootstrap",
        fields=frozenset(
            {
                "remote_before_oid",
                "remote_after_oid",
                "source_branch",
                "target_branch",
                "release_eligibility",
            }
        ),
    )
    active = _exact_mapping(
        raw.get("active"),
        label=f"{key}.active",
        fields=frozenset({"accepted_updates", "direct_push"}),
    )
    activation = IntegrationBranchActivation(
        state=state,
        transition_command=transition_command,
        evidence_kind=evidence_kind,
        bootstrap_remote_before_oid=_strict_string(
            bootstrap.get("remote_before_oid"), f"{key}.bootstrap.remote_before_oid"
        ),
        bootstrap_remote_after_oid=_strict_string(
            bootstrap.get("remote_after_oid"), f"{key}.bootstrap.remote_after_oid"
        ),
        bootstrap_source_branch=_strict_string(
            bootstrap.get("source_branch"), f"{key}.bootstrap.source_branch"
        ),
        bootstrap_target_branch=_strict_string(
            bootstrap.get("target_branch"), f"{key}.bootstrap.target_branch"
        ),
        bootstrap_release_eligibility=_strict_bool(
            bootstrap.get("release_eligibility"),
            f"{key}.bootstrap.release_eligibility",
        ),
        active_accepted_updates=_string_tuple(
            active, "accepted_updates", label_prefix=f"{key}.active"
        ),
        active_direct_push=_strict_string(
            active.get("direct_push"), f"{key}.active.direct_push"
        ),
    )
    if (
        activation.bootstrap_remote_before_oid != "absent"
        or activation.bootstrap_remote_after_oid != "exact_local_integration_head"
        or activation.bootstrap_source_branch != integration_branch
        or activation.bootstrap_target_branch != integration_branch
        or activation.bootstrap_release_eligibility is not False
    ):
        raise ValueError(
            "branch policy integration_branch_activation.bootstrap must declare the exact "
            "create-only matching integration branch exception without release eligibility"
        )
    if set(activation.active_accepted_updates) != {
        "lane_pull_request_merge",
        "system_fast_forward_backsync",
    } or activation.active_direct_push != "forbidden":
        raise ValueError(
            "branch policy integration_branch_activation.active must accept exactly lane PR "
            "merge/system fast-forward backsync and forbid direct push"
        )
    return activation


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
        production_source_branch=_required_string(payload, "production_source_branch"),
        production_workflow=_required_string(payload, "production_workflow"),
        required_promotion_checks=_required_promotion_checks(payload),
        allowed_pull_request_edges=_pull_request_edges(payload),
        integration_branch_activation=_integration_branch_activation(
            payload, integration_branch=integration_branch
        ),
        system_backsync=_system_backsync(payload),
        persistent_lane_admission=_persistent_lane_admission(payload),
        failure_codes=_failure_codes(payload),
    )
    for branch_name in (
        policy.integration_branch,
        policy.release_branch,
        policy.production_source_branch,
    ):
        if (
            branch_name not in policy.allowed_local
            or branch_name not in policy.allowed_remote
        ):
            raise ValueError(
                f"branch policy role branch {branch_name!r} must be allowed both locally and remotely"
            )
    if policy.production_source_branch != policy.release_branch:
        raise ValueError(
            "branch policy production_source_branch must equal release_branch"
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


def load_policy(path: Path = POLICY_PATH) -> BranchPolicy:
    """Read canonical policy bytes once, then delegate to the sole parser."""
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
        integration_direct_push_allowed = (
            policy.integration_branch_activation.state == "bootstrap"
            and transition.head == policy.integration_branch
            and transition.base == policy.integration_branch
            and transition.before_oid == ZERO_SHA
            and bool(transition.after_oid)
            and transition.after_oid != ZERO_SHA
        )
        if integration_direct_push_allowed or (
            transition.head == transition.base
            and transition.head in policy.allowed_local
            and _matches_pull_request_prefix(
                transition.head, policy.pull_request_prefixes
            )
        ):
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


def _issue(policy: BranchPolicy, failure_key: str, message: str) -> str:
    return (
        f"{policy.failure_code(failure_key)}: terminal=blocked; {message}; "
        f"recovery={RECOVERY_BY_FAILURE_KEY[failure_key]}"
    )


def branch_policy_issues(
    *,
    policy: BranchPolicy,
    local_branches: list[str],
    remote_branches: list[str],
    current_branch: str | None,
    ci_head_branch: str | None = None,
    ci_base_branch: str | None = None,
) -> list[str]:
    issues: list[str] = []
    active_pull_request_branch = (
        current_branch if current_branch in policy.allowed_local else None
    )
    has_pr_context = ci_head_branch is not None or ci_base_branch is not None
    if has_pr_context:
        if not ci_head_branch or not ci_base_branch:
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    "pull-request branch policy requires both head and base refs",
                )
            )
        else:
            decision = evaluate_transition(
                policy=policy,
                transition=BranchTransition(
                    event="pull_request",
                    actor_kind="github",
                    repository="github",
                    head=ci_head_branch,
                    base=ci_base_branch,
                ),
            )
            if not decision.allowed:
                issues.append(
                    _issue(
                        policy,
                        "ref_not_allowed",
                        f"pull-request edge '{ci_head_branch} -> {ci_base_branch}' is not allowed",
                    )
                )

    if not current_branch:
        if ci_head_branch in policy.allowed_local:
            pass
        else:
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    "detached HEAD is forbidden; use one of the declared repository branches",
                )
            )
    elif (
        current_branch not in policy.allowed_local
        and active_pull_request_branch is None
    ):
        issues.append(
            _issue(
                policy,
                "ref_not_allowed",
                f"current branch '{current_branch}' is not allowed; declared long-lived branches are "
                f"{sorted(policy.allowed_local)}",
            )
        )

    permitted_local = set(policy.allowed_local)
    if active_pull_request_branch:
        permitted_local.add(active_pull_request_branch)
    if ci_head_branch in policy.allowed_local:
        permitted_local.add(ci_head_branch)
    permitted_remote = set(policy.allowed_remote)
    if ci_head_branch in policy.allowed_remote:
        permitted_remote.add(ci_head_branch)
    elif active_pull_request_branch in policy.allowed_remote:
        permitted_remote.add(active_pull_request_branch)

    extra_local = sorted(
        branch for branch in local_branches if branch not in permitted_local
    )
    extra_remote = sorted(
        branch for branch in remote_branches if branch not in permitted_remote
    )
    if extra_local:
        issues.append(
            _issue(
                policy,
                "ref_not_allowed",
                f"unexpected local branches: {', '.join(extra_local)}",
            )
        )
    if extra_remote:
        issues.append(
            _issue(
                policy,
                "ref_not_allowed",
                f"unexpected remote branches: {', '.join(extra_remote)}",
            )
        )
    return issues


def current_repo_issues(policy: BranchPolicy | None = None) -> list[str]:
    policy = policy or load_policy()
    ci_head_branch, ci_base_branch = pull_request_context_from_environment(os.environ)
    if (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_EVENT_NAME") == "pull_request"
    ):
        # Hosted PR checkout state is an implementation detail. The event's remote
        # head/base pair is the only branch fact this gate needs to authorize.
        return branch_policy_issues(
            policy=policy,
            local_branches=[],
            remote_branches=[],
            current_branch=None,
            ci_head_branch=ci_head_branch,
            ci_base_branch=ci_base_branch,
        )
    local_branches = _run_git("for-each-ref", "--format=%(refname:short)", "refs/heads")
    remote_branches = [
        ref[len("origin/") :]
        for ref in _run_git(
            "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"
        )
        if ref not in {"origin", "origin/HEAD"}
    ]
    hosted_branch = repository_branch_context_from_environment(os.environ)
    current_branch = _current_branch()
    if hosted_branch is not None:
        current_branch = hosted_branch
    issues = branch_policy_issues(
        policy=policy,
        local_branches=local_branches,
        remote_branches=remote_branches,
        current_branch=current_branch,
        ci_head_branch=ci_head_branch,
        ci_base_branch=ci_base_branch,
    )
    # A generic GitHub push event does not carry the update provenance needed to
    # distinguish a direct push from a server-side PR merge. Direct-push decisions
    # are therefore constructed only by explicit update sources such as pre-push.
    return issues


def _failure_key_for_code(policy: BranchPolicy, code: str | None) -> str:
    for key, candidate in policy.failure_codes:
        if candidate == code:
            return key
    return "policy_invalid"


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    raise OSError(_safe_error_detail(RuntimeError(completed.stderr)))


def _is_managed_system_backsync_environment(
    environment: Mapping[str, str],
) -> bool:
    workflow_ref = environment.get("GITHUB_WORKFLOW_REF", "")
    return (
        environment.get("GITHUB_ACTIONS") == "true"
        and environment.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and environment.get("GITHUB_REF_TYPE") == "branch"
        and environment.get("GITHUB_REF_NAME") == "main"
        and environment.get("GITHUB_ACTOR") == "github-actions[bot]"
        and workflow_ref.endswith(SYSTEM_BACKSYNC_WORKFLOW_REF_SUFFIX)
    )


def activation_readback(policy: BranchPolicy) -> dict[str, object]:
    activation = policy.integration_branch_activation
    return {
        "schema_version": ACTIVATION_EVIDENCE_SCHEMA_VERSION,
        "kind": activation.evidence_kind,
        "integration_branch": policy.integration_branch,
        "state": activation.state,
        "transition_command": activation.transition_command,
        "tracked_policy_mutated": False,
    }


def _activation_evidence_path(path_text: str) -> Path:
    path = Path(path_text)
    candidate = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    output_root = (ROOT / ".qwq_output").resolve()
    if candidate == output_root or output_root not in candidate.parents:
        raise ValueError("activation evidence path must be below .qwq_output")
    return candidate


def write_activation_transition_evidence(
    *, policy: BranchPolicy, evidence_path: str
) -> dict[str, object]:
    activation = policy.integration_branch_activation
    if activation.state != "bootstrap":
        raise ValueError(
            "integration branch activation transition requires current state 'bootstrap'"
        )
    path = _activation_evidence_path(evidence_path)
    payload = {
        "schema_version": ACTIVATION_EVIDENCE_SCHEMA_VERSION,
        "kind": activation.evidence_kind,
        "integration_branch": policy.integration_branch,
        "from_state": "bootstrap",
        "proposed_state": "active",
        "policy_sha256": "sha256:" + hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest(),
        "tracked_policy_mutated": False,
        "proposal": {
            "path": str(POLICY_PATH.relative_to(ROOT)),
            "field": "integration_branch_activation.state",
            "current": "bootstrap",
            "replacement": "active",
        },
        "instructions": [
            f"review evidence at {path.relative_to(ROOT)}",
            "change integration_branch_activation.state from bootstrap to active",
            "commit the tracked policy change through the normal human-controlled workflow",
            "run --activation-readback after the active policy is checked out",
        ],
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError("activation evidence already exists; create-once transition refused") from error
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
    return payload


def _emit_json(payload: Mapping[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def pre_push_issues(
    *,
    policy: BranchPolicy,
    current_branch: str | None,
    update_lines: Iterable[str],
    environment: Mapping[str, str],
) -> list[str]:
    issues: list[str] = []
    if not current_branch:
        return [
            _issue(
                policy,
                "ref_not_allowed",
                "detached HEAD is forbidden; push from a declared branch",
            )
        ]
    if current_branch not in policy.allowed_local:
        issues.append(
            _issue(
                policy,
                "ref_not_allowed",
                f"current branch '{current_branch}' is not allowed; declared long-lived branches are "
                f"{sorted(policy.allowed_local)}",
            )
        )

    parsed_updates: list[tuple[str, str, str, str]] = []
    for raw_line in update_lines:
        fields = raw_line.strip().split()
        if not fields:
            continue
        if len(fields) != 4:
            issues.append(
                _issue(
                    policy,
                    "policy_invalid",
                    "pre-push update must contain local_ref local_sha remote_ref remote_sha",
                )
            )
            continue
        parsed_updates.append((fields[0], fields[1], fields[2], fields[3]))

    for local_ref, local_sha, remote_ref, remote_sha in parsed_updates:
        if not remote_ref.startswith("refs/heads/"):
            continue
        remote_branch = remote_ref.removeprefix("refs/heads/")
        if local_sha == ZERO_SHA:
            # 所有声明的长期分支受保护；未声明 ref 同样禁止借删除操作进入协议。
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    f"deletion of protected or undeclared branch '{remote_branch}' is blocked",
                )
            )
            continue
        if remote_branch not in policy.allowed_remote:
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    f"push to undeclared remote branch '{remote_branch}' is blocked",
                )
            )
            continue
        if _matches_pull_request_prefix(remote_branch, policy.pull_request_prefixes):
            if (
                remote_branch != current_branch
                or local_ref != f"refs/heads/{current_branch}"
            ):
                issues.append(
                    _issue(
                        policy,
                        "ref_not_allowed",
                        f"persistent lane push must update its matching remote ref: {current_branch!r}",
                    )
                )
            continue
        if remote_branch == policy.integration_branch:
            activation = policy.integration_branch_activation
            matching_integration_source = (
                current_branch == policy.integration_branch
                and local_ref == f"refs/heads/{policy.integration_branch}"
            )
            matching_backsync_source = (
                current_branch == policy.release_branch
                and local_ref == f"refs/heads/{policy.release_branch}"
            )
            if activation.state == "bootstrap":
                if not matching_integration_source or remote_sha != ZERO_SHA:
                    issues.append(
                        _issue(
                            policy,
                            "direct_push_not_allowed",
                            f"bootstrap update of '{remote_branch}' is create-only from the "
                            f"matching local {policy.integration_branch} branch",
                        )
                    )
            elif matching_backsync_source and _is_managed_system_backsync_environment(
                environment
            ):
                decision = evaluate_transition(
                    policy=policy,
                    transition=BranchTransition(
                        event="system_backsync",
                        actor_kind="system",
                        repository=environment.get("GITHUB_REPOSITORY", "github"),
                        head=policy.release_branch,
                        base=policy.integration_branch,
                        before_oid=remote_sha,
                        after_oid=local_sha,
                    ),
                    is_ancestor=lambda ancestor, descendant: _git_is_ancestor(
                        ancestor, descendant
                    ),
                )
                if not decision.allowed:
                    failure_key = _failure_key_for_code(policy, decision.reason_code)
                    issues.append(
                        _issue(
                            policy,
                            failure_key,
                            f"managed system backsync to '{remote_branch}' was rejected",
                        )
                    )
            else:
                issues.append(
                    _issue(
                        policy,
                        "direct_push_not_allowed",
                        f"direct update of active integration branch '{remote_branch}' is blocked; "
                        "use a lane pull request or managed system fast-forward backsync",
                    )
                )
            continue
        elif remote_branch == policy.release_branch:
            issues.append(
                _issue(
                    policy,
                    "direct_push_not_allowed",
                    f"direct update of '{remote_branch}' is blocked; use "
                    f"{policy.integration_branch} -> {policy.release_branch} promotion PR",
                )
            )
        else:
            issues.append(
                _issue(
                    policy,
                    "direct_push_not_allowed",
                    f"direct update of long-lived branch '{remote_branch}' is blocked",
                )
            )
    return issues


def local_commit_issues(
    policy: BranchPolicy, current_branch: str | None,
) -> list[str]:
    """Validate the commit branch, then enforce read-only integration surfaces."""
    if not current_branch:
        return [
            _issue(
                policy,
                "ref_not_allowed",
                "detached HEAD is forbidden; commit from a declared local branch",
            )
        ]
    if current_branch not in policy.allowed_local:
        return [
            _issue(
                policy,
                "ref_not_allowed",
                f"current branch '{current_branch}' is not allowed; declared long-lived branches are "
                f"{sorted(policy.allowed_local)}",
            )
        ]
    if current_branch in {policy.integration_branch, policy.release_branch}:
        return [
            _issue(
                policy,
                "integration_read_only",
                f"local commits on read-only branch '{current_branch}' are blocked",
            )
        ]
    return []


def _current_branch() -> str | None:
    try:
        rows = _run_git("symbolic-ref", "--quiet", "--short", "HEAD")
    except subprocess.CalledProcessError as error:
        if error.returncode == 1:
            return None
        raise
    if not rows:
        raise OSError("git symbolic-ref returned no branch")
    return rows[0]


def _safe_error_detail(error: BaseException) -> str:
    return " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__


def _emit_terminal_failure(*, code: str, detail: str, recovery: str) -> int:
    print("[verify_git_branch_policy] FAIL")
    print(f"  - {code}: terminal=blocked; {detail}; recovery={recovery}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the canonical Git branch policy"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--pre-push",
        action="store_true",
        help="validate pre-push update lines from stdin",
    )
    mode.add_argument(
        "--local-commit",
        action="store_true",
        help="reject local commits from read-only dev1.0/main worktrees",
    )
    mode.add_argument(
        "--activation-readback",
        action="store_true",
        help="print the canonical integration branch activation state",
    )
    mode.add_argument(
        "--activation-transition",
        action="store_true",
        help="create transition evidence and print the tracked-policy proposal",
    )
    parser.add_argument(
        "--evidence-path",
        help="create-once evidence path below .qwq_output for --activation-transition",
    )
    args = parser.parse_args(argv)
    if bool(args.evidence_path) != bool(args.activation_transition):
        parser.error("--evidence-path is required exactly with --activation-transition")
    try:
        policy = load_policy()
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError) as error:
        return _emit_terminal_failure(
            code="OPS.BRANCH.POLICY_INVALID",
            detail=f"branch policy is invalid: {_safe_error_detail(error)}",
            recovery=POLICY_INVALID_RECOVERY,
        )
    try:
        if args.activation_readback:
            _emit_json(activation_readback(policy))
            return 0
        if args.activation_transition:
            _emit_json(
                write_activation_transition_evidence(
                    policy=policy, evidence_path=args.evidence_path
                )
            )
            return 0
        if args.pre_push:
            issues = pre_push_issues(
                policy=policy,
                current_branch=_current_branch(),
                update_lines=sys.stdin,
                environment=os.environ,
            )
        elif args.local_commit:
            issues = local_commit_issues(
                policy=policy,
                current_branch=_current_branch(),
            )
        else:
            issues = current_repo_issues(policy)
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        return _emit_terminal_failure(
            code=policy.failure_code("authority_unavailable"),
            detail=f"Git authority is unavailable: {_safe_error_detail(error)}",
            recovery=AUTHORITY_UNAVAILABLE_RECOVERY,
        )
    if issues:
        print("[verify_git_branch_policy] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_git_branch_policy] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
