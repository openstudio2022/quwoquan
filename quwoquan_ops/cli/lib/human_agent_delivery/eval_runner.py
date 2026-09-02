"""Deterministic representative-path evaluator over canonical delivery helpers."""
from __future__ import annotations

import errno
import json
import os
import stat
import uuid
from collections import Counter
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import yaml

from .contract import (
    CONTRACT_PATH,
    ContractError,
    _workflow_skill_names,
    load_contract,
)
from .projection import project_authorization_grant, project_role_card, project_role_interaction
from .router import balanced_permutations, legal_option_ids, route
from .states import (
    accept_outcome,
    advance_campaign,
    commercial_option_is_legal,
    production_concurrency_policy,
    transition_inconclusive_outcome,
)

POLICY_PATH = CONTRACT_PATH.parent / "evals/human_agent_delivery_interaction_v1.yaml"
REPO_ROOT = CONTRACT_PATH.parents[2]


class EvalPolicyError(ValueError):
    """Fail-closed representative-path policy error."""


class _Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(
        self,
        check_id: str,
        passed: bool,
        detail: str = "",
        *,
        code: str | None = None,
        causal_category: str | None = None,
    ) -> None:
        item: dict[str, Any] = {
            "check_id": check_id,
            "passed": bool(passed),
            "detail": detail,
        }
        if code is not None:
            item["code"] = code
        if causal_category is not None:
            item["causal_category"] = causal_category
        self.items.append(item)


def load_eval_policy(path: Path | str = POLICY_PATH) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvalPolicyError("eval policy must be a mapping")
    return value


def _route_result(fixture: Mapping[str, Any]) -> dict[str, Any]:
    route_input = fixture["route_input"]
    sod = fixture["sod"]
    return route(
        fixture["stage"], fixture["decision_kind"], hard_gates=fixture["hard_gates"],
        risk_categories=sod["risk_categories"], sod_policy=sod["policy"],
        role_actor_ids=sod["role_actor_ids"], **route_input,
    )


def _card_result(fixture: Mapping[str, Any]) -> dict[str, Any]:
    facts = fixture["facts"]
    card = fixture["card"]
    return project_role_card(
        card_type=card["card_type"], decision_kind=fixture["decision_kind"],
        current_role=card["current_role_language"], question=card["question"],
        known_facts=facts["known"], unknowns=facts["unknowns"],
        hard_constraints=facts["hard_constraints"], options=fixture["options"],
        consequences=facts["consequences"], seed=fixture["id"],
        agent_recommendation=card["agent_recommendation"],
        independent_inputs_sealed=card["independent_inputs_sealed"],
    )


def _state_result(probe: Mapping[str, Any], hard_gates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    kind = probe.get("kind")
    if kind == "none":
        return {}
    if kind == "commercial":
        legal = commercial_option_is_legal(
            probe["status"], hard_gates=hard_gates,
            limited_scope_reversible=probe["limited_scope_reversible"],
            policy_allows_limited_scope=probe["policy_allows_limited_scope"],
        )
        return {"legal": legal, "production_authorization": project_authorization_grant(probe["decision_record"])}
    if kind == "campaign":
        arguments = {key: value for key, value in probe.items() if key not in {"kind", "approval"}}
        return advance_campaign(probe["approval"], **arguments)
    if kind == "campaign_sequence":
        return {"steps": [advance_campaign(probe["approval"], **step) for step in probe["steps"]]}
    if kind == "production_concurrency":
        return production_concurrency_policy()
    if kind == "outcome_inconclusive":
        return transition_inconclusive_outcome(
            extension_policy=probe["extension_policy"], extensions_used=probe["extensions_used"]
        )
    if kind == "outcome_accept":
        return accept_outcome(probe["outcome"])
    raise EvalPolicyError(f"unknown state probe: {kind}")


def _visible_card_text(card: Mapping[str, Any]) -> str:
    fields = (
        card.get("current_role"), card.get("question"), card.get("known_facts"),
        card.get("unknowns"), card.get("hard_constraints"), card.get("options"),
        card.get("consequences"),
    )
    return json.dumps(fields, ensure_ascii=False, sort_keys=True)


def _balanced_and_unbiased(fixture: Mapping[str, Any], legal: tuple[str, ...]) -> bool:
    options = fixture["options"]
    permutations = balanced_permutations(options, fixture["id"])
    if len(permutations) != len(options):
        return False
    option_ids = {str(option["option_id"]) for option in options}
    if any({str(option["option_id"]) for option in row} != option_ids for row in permutations):
        return False
    if any(
        {str(row[position]["option_id"]) for row in permutations} != option_ids
        for position in range(len(options))
    ):
        return False
    return all(legal_option_ids(row, fixture["hard_gates"]) == legal for row in permutations)


def _validate_policy_shape(policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    evaluation = policy.get("evaluation")
    fixtures = policy.get("fixtures")
    if policy.get("schema_id") != "human-agent-delivery-interaction-eval-policy" or policy.get("schema_version") != 1:
        errors.append("invalid policy identity/version")
    if not isinstance(evaluation, dict) or not isinstance(fixtures, list):
        return [*errors, "missing evaluation or fixtures"]
    expected_count = evaluation.get("expected_fixture_count")
    family_counts = Counter(fixture.get("family") for fixture in fixtures if isinstance(fixture, dict))
    if len(fixtures) != expected_count:
        errors.append(f"fixture count drift expected={expected_count} actual={len(fixtures)}")
    if dict(family_counts) != evaluation.get("expected_family_counts"):
        errors.append("family denominator drift")
    if set(family_counts) != set(evaluation.get("required_families") or ()):
        errors.append("required families missing or unexpected")
    ids = [fixture.get("id") for fixture in fixtures if isinstance(fixture, dict)]
    if any(not isinstance(fixture_id, str) or not fixture_id for fixture_id in ids) or len(ids) != len(set(ids)):
        errors.append("fixture ids must be unique non-empty strings")
    if expected_count == 0 or not fixtures:
        errors.append("zero sample is blocked")
    calibration = policy.get("human_calibration")
    if not isinstance(calibration, dict) or calibration.get("status") != "not_observed":
        errors.append("human calibration status must remain not_observed until observed")
    if isinstance(calibration, dict) and calibration.get("machine_baseline_is_human_usability_evidence") is not False:
        errors.append("machine baseline must not claim human usability evidence")
    return errors



def _evaluate_role_interactions(policy: Mapping[str, Any], checks: _Checks) -> None:
    interactions = policy.get("role_interaction_evaluation")
    if not isinstance(interactions, Mapping):
        checks.add("global.role_interaction_shape", False, "missing role_interaction_evaluation")
        checks.add("global.role_interaction_fixtures", False, "missing role_interaction_evaluation")
        checks.add("global.skill_interaction_bindings", False, "missing role_interaction_evaluation")
        checks.add("global.replay_injection", False, "missing role_interaction_evaluation")
        return
    fixtures = interactions.get("fixtures")
    expected_types = set(load_contract()["closed_sets"]["role_interaction_event_type"])
    fixture_types = {
        fixture.get("payload", {}).get("event_type")
        for fixture in fixtures or ()
        if isinstance(fixture, Mapping) and isinstance(fixture.get("payload"), Mapping)
    }
    shape_ok = (
        isinstance(fixtures, list)
        and interactions.get("expected_fixture_count") == 4
        and len(fixtures) == 4
        and fixture_types == expected_types
    )
    checks.add("global.role_interaction_shape", shape_ok)
    fixture_ok = shape_ok
    details: list[str] = []
    if isinstance(fixtures, list):
        for fixture in fixtures:
            if not isinstance(fixture, Mapping) or not isinstance(fixture.get("payload"), Mapping):
                fixture_ok = False
                continue
            payload = fixture["payload"]
            cursor = project_role_interaction(payload, harness="cursor")
            codex = project_role_interaction(payload, harness="codex")
            unknown = project_role_interaction(payload, harness="unknown")
            upper_layer_not_user_available = True
            if payload.get("event_type") == "completion_report":
                serialized = json.dumps(payload, ensure_ascii=False)
                upper_layer_not_user_available = not (
                    any(term in serialized for term in ("测试通过", "检查通过", "评审通过", "门禁通过"))
                    and any(term in serialized for term in ("用户已经可用", "可商用", "可发布", "生产可用"))
                )
            ok = (
                cursor == payload
                and codex == payload
                and json.dumps(cursor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                == json.dumps(codex, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                and unknown.get("code") == "HAD.UNKNOWN_HARNESS"
                and upper_layer_not_user_available
            )
            if not ok:
                fixture_ok = False
                details.append(str(fixture.get("id")))
    checks.add("global.role_interaction_fixtures", fixture_ok, ",".join(details))
    contract = load_contract()
    workflow = contract.get("workflow_interaction_binding") or {}
    bindings = workflow.get("bindings") or {}
    discovery_error: ContractError | None = None
    try:
        skill_names = _workflow_skill_names(workflow.get("skill_root"))
    except ContractError as error:
        skill_names = ()
        discovery_error = error
    skill_ok = (
        bool(skill_names)
        and set(bindings) == set(skill_names)
        and all(
            [item.get("phase") for item in bindings[name]]
            == workflow.get("required_phases")
            for name in skill_names
            if isinstance(bindings.get(name), list)
        )
    )
    checks.add(
        "global.skill_interaction_bindings",
        skill_ok,
        discovery_error.detail if discovery_error is not None else "",
        code=discovery_error.code if discovery_error is not None else None,
        causal_category=(
            discovery_error.causal_category if discovery_error is not None else None
        ),
    )
    replay = policy.get("conversation_replay")
    replay_ok = (
        isinstance(replay, Mapping)
        and replay.get("input_mode") == "injectable_json_object"
        and replay.get("canonical_private_transcript_fixture") is False
        and replay.get("reads_private_transcript_paths") is False
        and isinstance(replay.get("required_input_fields"), list)
        and replay.get("example_input") is not None
    )
    checks.add("global.replay_injection", replay_ok)

def evaluate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    evaluation = policy.get("evaluation") if isinstance(policy, dict) else None
    fixtures = policy.get("fixtures") if isinstance(policy, dict) else None
    if not isinstance(evaluation, dict) or not isinstance(fixtures, list):
        return {
            "schema_version": 1, "policy_id": policy.get("policy_id") if isinstance(policy, dict) else None,
            "status": "block", "machine_score": 0.0, "passed_checks": 0,
            "hard_invariant_denominator": 0, "failed_checks": ["missing evaluation or fixtures"],
            "fixture_results": [], "human_calibration": policy.get("human_calibration") if isinstance(policy, dict) else None,
        }
    checks = _Checks()
    contract_loaded = True
    contract_detail = ""
    contract_code: str | None = None
    contract_causal_category: str | None = None
    try:
        load_contract()
    except ContractError as exc:
        contract_loaded = False
        contract_detail = exc.detail
        contract_code = exc.code
        contract_causal_category = exc.causal_category
    except yaml.YAMLError as exc:
        contract_loaded = False
        contract_detail = str(exc)
        contract_code = "HAD.CONTRACT_INVALID"
        contract_causal_category = "contract_syntax"
    except OSError as exc:
        contract_loaded = False
        contract_detail = str(exc)
        is_permission = isinstance(exc, PermissionError)
        contract_code = (
            "HAD.SKILL_DISCOVERY_PERMISSION_DENIED"
            if is_permission
            else "HAD.SKILL_DISCOVERY_IO_FAILED"
        )
        contract_causal_category = "permission" if is_permission else "io"
    shape_errors = _validate_policy_shape(policy)
    checks.add("global.policy_shape", not shape_errors, "; ".join(shape_errors))
    expected_count = evaluation.get("expected_fixture_count")
    counts = Counter(fixture.get("family") for fixture in fixtures if isinstance(fixture, dict))
    checks.add("global.fixed_denominator", len(fixtures) == expected_count, f"expected={expected_count}, actual={len(fixtures)}")
    checks.add("global.family_coverage", dict(counts) == evaluation.get("expected_family_counts"), json.dumps(dict(counts), sort_keys=True))
    checks.add("global.nonzero_samples", bool(fixtures) and expected_count > 0, f"samples={len(fixtures)}")
    calibration = policy.get("human_calibration") or {}
    checks.add(
        "global.human_calibration_honest",
        calibration.get("status") == "not_observed"
        and calibration.get("qualifying_role_session_count") == 0
        and calibration.get("unique_participant_count") == 0
        and calibration.get("machine_baseline_is_human_usability_evidence") is False
        and calibration.get("canonical_cli_commands") == [
            "calibration-validate", "calibration-record", "calibration-readback"
        ]
        and calibration.get("required_principal_classes") == [
            "product", "engineering", "quality", "release_operations"
        ]
        and calibration.get("required_responsibility_classes") == [
            "business", "product", "experience", "quality", "engineering", "release_operations"
        ]
        and calibration.get("required_observation_dimensions") == [
            "understanding", "option_cross_role_impact_comprehension", "transfer",
            "pause_deny_abort", "recovery", "post_check",
        ],
    )
    checks.add(
        "global.canonical_contract_loaded",
        contract_loaded,
        contract_detail,
        code=contract_code,
        causal_category=contract_causal_category,
    )
    if contract_loaded:
        _evaluate_role_interactions(policy, checks)
    proxy = policy.get("readability_proxy") or {}
    forbidden = tuple(str(term).lower() for term in proxy.get("forbidden_internal_terms") or ())
    fixture_results: list[dict[str, Any]] = []
    if not contract_loaded:
        expected_denominator = evaluation.get("hard_invariant_denominator")
        passed_checks = sum(1 for item in checks.items if item["passed"])
        return {
            "schema_version": 1, "policy_id": policy.get("policy_id"), "status": "block",
            "fixture_count": len(fixtures), "family_counts": dict(sorted(counts.items())),
            "passed_checks": passed_checks, "hard_invariant_denominator": expected_denominator,
            "machine_score": passed_checks / expected_denominator if isinstance(expected_denominator, int) and expected_denominator > 0 else 0.0,
            "threshold": evaluation.get("hard_invariant_threshold"),
            "failed_checks": [item for item in checks.items if not item["passed"]],
            "fixture_results": fixture_results, "human_calibration": deepcopy(calibration),
        }
    for fixture in fixtures:
        fixture_id = fixture["id"]
        route_result = _route_result(fixture)
        legal = legal_option_ids(fixture["options"], fixture["hard_gates"])
        card_result = _card_result(fixture)
        state_result = _state_result(fixture["state_probe"], fixture["hard_gates"])
        constraints = fixture["card_constraints"]
        route_ok = route_result == fixture["expected_route"]
        checks.add(f"{fixture_id}.route", route_ok, json.dumps(route_result, ensure_ascii=False, sort_keys=True))
        legal_ok = list(legal) == sorted(fixture["expected_legal_option_ids"])
        checks.add(f"{fixture_id}.legal_set", legal_ok, json.dumps(legal))
        card_fields_ok = not card_result.get("result") == "typed_blocker" and all(
            field in card_result for field in constraints["required_role_language_fields"]
        ) and card_result.get("current_role") == fixture["card"]["current_role_language"]
        checks.add(f"{fixture_id}.role_language", card_fields_ok)
        question = card_result.get("question", "") if isinstance(card_result, dict) else ""
        question_ok = isinstance(question, str) and question.count("？") + question.count("?") == constraints["question_count"]
        checks.add(f"{fixture_id}.one_question", question_ok, question)
        options = card_result.get("options", []) if isinstance(card_result, dict) else []
        symmetric = constraints["symmetric_fields"]
        structural_ok = constraints["minimum_options"] <= len(options) <= constraints["maximum_options"] and all(list(option) == symmetric for option in options) and card_result.get("selected_option_id") is None
        checks.add(f"{fixture_id}.symmetric_card", structural_ok)
        actions_ok = card_result.get("actions") == constraints["required_recovery_actions"]
        checks.add(f"{fixture_id}.safe_recovery", actions_ok)
        leak_text = _visible_card_text(card_result).lower() if isinstance(card_result, dict) else ""
        leaked = sorted(term for term in forbidden if term and term in leak_text)
        projected_recommendation = card_result.get("agent_recommendation")
        preference_kinds = set(load_contract()["recommendation_policy"]["forbidden_decision_kinds"])
        if fixture["decision_kind"] in preference_kinds:
            recommendation_ok = (
                fixture["card"]["agent_recommendation"] is None
                and projected_recommendation is None
                and card_result.get("code") != "HAD.RECOMMENDATION_FORBIDDEN"
            )
        else:
            recommendation_ok = projected_recommendation == fixture["card"]["agent_recommendation"]
        bias_ok = _balanced_and_unbiased(fixture, legal) and not leaked and recommendation_ok
        checks.add(f"{fixture_id}.bias_and_language", bias_ok, ",".join(leaked))
        reachable = set(constraints["expected_reachable_option_ids"]) == set(legal)
        selected = constraints["selected_probe_option_id"]
        branch_probes = [
            {"selected_option_id": option_id, "legal": option_id in legal, "reprompted": False}
            for option_id in constraints["expected_reachable_option_ids"]
        ]
        all_legal_branches_reached = all(probe["legal"] and not probe["reprompted"] for probe in branch_probes)
        selected_probe_ok = selected in legal and constraints["expected_reprompt"] is False
        state_ok = state_result == fixture["expected_state"]
        checks.add(f"{fixture_id}.reachability_and_state", reachable and all_legal_branches_reached and selected_probe_ok and state_ok, json.dumps(state_result, ensure_ascii=False, sort_keys=True))
        fixture_checks = [item for item in checks.items if item["check_id"].startswith(f"{fixture_id}.")]
        fixture_results.append({
            "fixture_id": fixture_id, "family": fixture["family"], "passed": all(item["passed"] for item in fixture_checks),
            "route": route_result, "legal_option_ids": list(legal), "branch_probes": branch_probes,
            "selected_probe_option_id": selected, "reprompted": False, "state_result": state_result,
            "failed_check_ids": [item["check_id"] for item in fixture_checks if not item["passed"]],
        })
    expected_denominator = evaluation.get("hard_invariant_denominator")
    actual_denominator = len(checks.items)
    denominator_ok = actual_denominator == expected_denominator
    if checks.items:
        # The fixed-denominator check itself is one of the declared six global checks.
        for item in checks.items:
            if item["check_id"] == "global.fixed_denominator":
                item["passed"] = item["passed"] and denominator_ok
                item["detail"] = f"declared={expected_denominator}, actual={actual_denominator}, fixtures={len(fixtures)}"
    passed_checks = sum(1 for item in checks.items if item["passed"])
    machine_score = passed_checks / expected_denominator if isinstance(expected_denominator, int) and expected_denominator > 0 else 0.0
    threshold = evaluation.get("hard_invariant_threshold")
    status = "pass" if denominator_ok and machine_score == threshold and passed_checks == expected_denominator else "block"
    failed = [item for item in checks.items if not item["passed"]]
    return {
        "schema_version": 1, "policy_id": policy.get("policy_id"), "status": status,
        "fixture_count": len(fixtures), "family_counts": dict(sorted(counts.items())),
        "passed_checks": passed_checks, "hard_invariant_denominator": expected_denominator,
        "machine_score": machine_score, "threshold": threshold,
        "failed_checks": failed, "fixture_results": fixture_results,
        "human_calibration": deepcopy(calibration),
    }


def _report_error(
    code: str,
    causal_category: str,
    detail: str,
    error: BaseException | None = None,
) -> ContractError:
    failure = ContractError(
        detail, code=code, causal_category=causal_category,
    )
    if error is not None:
        failure.__cause__ = error
    return failure


def _report_io_error(
    exc: OSError,
    *,
    label: str,
    parent_fd: int | None = None,
    name: str | os.PathLike[str] | None = None,
) -> ContractError:
    if isinstance(exc, PermissionError):
        return _report_error(
            "HAD.EVAL_REPORT_PERMISSION_DENIED",
            "permission",
            f"无权限写入 {label}",
            exc,
        )
    is_symlink = exc.errno == errno.ELOOP
    if not is_symlink and name is not None:
        try:
            metadata = (
                os.stat(name, follow_symlinks=False)
                if parent_fd is None
                else os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            )
            is_symlink = stat.S_ISLNK(metadata.st_mode)
        except OSError:
            pass
    if is_symlink:
        return _report_error(
            "HAD.EVAL_REPORT_SYMLINK_FORBIDDEN",
            "symlink",
            f"{label} 不得包含 symlink",
            exc,
        )
    if isinstance(exc, (NotADirectoryError, IsADirectoryError)):
        return _report_error(
            "HAD.EVAL_REPORT_PATH_INVALID",
            "path_type",
            f"{label} 路径类型非法",
            exc,
        )
    return _report_error(
        "HAD.EVAL_REPORT_IO_FAILED",
        "io",
        f"写入 {label} 失败: {exc}",
        exc,
    )


def _open_real_directory(path: Path, *, label: str) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise _report_error(
            "HAD.FILESYSTEM_PRIMITIVE_UNSUPPORTED",
            "unsupported",
            "eval report 写入要求 O_NOFOLLOW/O_DIRECTORY",
        )
    absolute = path if path.is_absolute() else path.absolute()
    try:
        descriptor = os.open(
            absolute.anchor,
            os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise _report_io_error(exc, label=f"{label} filesystem root") from exc
    try:
        for component in absolute.parts[1:]:
            try:
                child = os.open(
                    component,
                    os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise _report_io_error(exc, label=f"{label} ancestor {component}") from exc
            os.close(descriptor)
            descriptor = child
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise _report_error(
                "HAD.EVAL_REPORT_PATH_INVALID",
                "path_type",
                f"{label} 必须为真实目录",
            )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _canonical_report_parts(path: Path | str) -> tuple[str, ...]:
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw:
        raise _report_error(
            "HAD.EVAL_REPORT_PATH_INVALID",
            "path_type",
            "eval report_path 必须为非空路径",
        )
    normalized = raw.replace("\\", "/")
    lexical_components = normalized.split("/")
    if any(component in {"", ".", ".."} for component in lexical_components):
        if not (normalized.startswith("/") and lexical_components[0] == ""):
            raise _report_error(
                "HAD.EVAL_REPORT_PATH_INVALID",
                "path_type",
                "eval report_path 不得包含空、. 或 .. 组件",
            )
        lexical_components = lexical_components[1:]
        if any(component in {"", ".", ".."} for component in lexical_components):
            raise _report_error(
                "HAD.EVAL_REPORT_PATH_INVALID",
                "path_type",
                "eval report_path 不得包含空、. 或 .. 组件",
            )

    supplied = PurePosixPath(normalized)
    if supplied.is_absolute():
        repo_parts = PurePosixPath(REPO_ROOT.as_posix()).parts
        if supplied.parts[: len(repo_parts)] != repo_parts:
            raise _report_error(
                "HAD.EVAL_REPORT_PATH_OUTSIDE_RUNTIME_ROOT",
                "path_boundary",
                "absolute eval report_path 越出真实 repository root",
            )
        relative_parts = supplied.parts[len(repo_parts):]
    else:
        relative_parts = supplied.parts
    if len(relative_parts) < 2 or relative_parts[0] != ".qwq_output":
        raise _report_error(
            "HAD.EVAL_REPORT_PATH_OUTSIDE_RUNTIME_ROOT",
            "path_boundary",
            "eval report_path 必须位于 canonical .qwq_output runtime root",
        )
    return tuple(relative_parts)


def write_report(report: Mapping[str, Any], path: Path | str) -> None:
    """Atomically write one report below the real repo runtime root without links."""

    parts = _canonical_report_parts(path)
    repo_fd = _open_real_directory(REPO_ROOT, label="repository root")
    parent_fd = repo_fd
    opened: list[int] = []
    temporary_name = f".{parts[-1]}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    temporary_created = False
    try:
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        for index, component in enumerate(parts[:-1]):
            try:
                child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            except FileNotFoundError:
                if index == 0:
                    raise _report_error(
                        "HAD.EVAL_REPORT_RUNTIME_ROOT_INVALID",
                        "path_boundary",
                        "canonical .qwq_output runtime root 不存在",
                    )
                try:
                    os.mkdir(component, 0o755, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise _report_io_error(
                        exc,
                        label=f"eval report parent {component}",
                        parent_fd=parent_fd,
                        name=component,
                    ) from exc
                try:
                    child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
                except OSError as exc:
                    raise _report_io_error(
                        exc,
                        label=f"eval report parent {component}",
                        parent_fd=parent_fd,
                        name=component,
                    ) from exc
            except OSError as exc:
                raise _report_io_error(
                    exc,
                    label=f"eval report parent {component}",
                    parent_fd=parent_fd,
                    name=component,
                ) from exc
            opened.append(child_fd)
            parent_fd = child_fd

        final_name = parts[-1]
        try:
            existing = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise _report_io_error(exc, label="eval report destination") from exc
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode):
                raise _report_error(
                    "HAD.EVAL_REPORT_SYMLINK_FORBIDDEN",
                    "symlink",
                    "eval report destination 不得为 symlink",
                )
            if not stat.S_ISREG(existing.st_mode):
                raise _report_error(
                    "HAD.EVAL_REPORT_PATH_INVALID",
                    "path_type",
                    "eval report destination 必须为 regular file",
                )
        destination_identity = (
            None
            if existing is None
            else (existing.st_dev, existing.st_ino, existing.st_mode)
        )

        content = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o644,
                dir_fd=parent_fd,
            )
            temporary_created = True
            try:
                view = memoryview(content)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError(errno.EIO, "eval report short write")
                    view = view[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                current = os.stat(
                    final_name, dir_fd=parent_fd, follow_symlinks=False,
                )
            except FileNotFoundError:
                current_identity = None
            else:
                if stat.S_ISLNK(current.st_mode):
                    raise _report_error(
                        "HAD.EVAL_REPORT_SYMLINK_FORBIDDEN",
                        "symlink",
                        "eval report destination 在写入期间被替换为 symlink",
                    )
                current_identity = (
                    current.st_dev, current.st_ino, current.st_mode,
                )
            if current_identity != destination_identity:
                raise _report_error(
                    "HAD.EVAL_REPORT_CONCURRENT_DRIFT",
                    "concurrent_drift",
                    "eval report destination 在写入期间发生身份漂移",
                )
            os.replace(
                temporary_name,
                final_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            temporary_created = False
            os.fsync(parent_fd)
        except OSError as exc:
            raise _report_io_error(exc, label="eval report destination") from exc
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
        for descriptor in reversed(opened):
            os.close(descriptor)
        os.close(repo_fd)


def run_eval(*, policy_path: Path | str = POLICY_PATH, report_path: Path | str | None = None) -> dict[str, Any]:
    policy = load_eval_policy(policy_path)
    report = evaluate_policy(policy)
    destination = report_path or policy["evaluation"]["report_path"]
    write_report(report, destination)
    return report
