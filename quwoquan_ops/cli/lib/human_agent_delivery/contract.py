"""Human-Agent Delivery canonical machine contract loader and validator."""
from __future__ import annotations

import errno
import os
import re
import stat
from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "policies/human_agent_delivery_contract.yaml"


class ContractError(ValueError):
    """Fail-closed contract validation error with a stable causal category."""

    code = "HAD.CONTRACT_INVALID"

    def __init__(
        self,
        detail: str,
        *,
        code: str | None = None,
        causal_category: str = "contract_invalid",
    ) -> None:
        super().__init__(detail)
        self.code = code or type(self).code
        self.detail = detail
        self.causal_category = causal_category


_CANONICAL_WORKFLOW_SKILL_ROOT = ".agents/skills"
_SKILL_FRONTMATTER = re.compile(
    r"\A---(?:\r\n|\n)(?P<body>.*?)(?:\r\n|\n)---(?:(?:\r\n|\n)|\Z)",
    re.DOTALL,
)
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)


def _contract_error(
    code: str,
    causal_category: str,
    detail: str,
    error: BaseException | None = None,
) -> ContractError:
    failure = ContractError(detail, code=code, causal_category=causal_category)
    if error is not None:
        failure.__cause__ = error
    return failure


def _classify_io_error(
    exc: OSError,
    *,
    label: str,
    expected_type: str,
    parent_fd: int | None = None,
    name: str | os.PathLike[str] | None = None,
) -> ContractError:
    if isinstance(exc, PermissionError):
        return _contract_error(
            "HAD.SKILL_DISCOVERY_PERMISSION_DENIED",
            "permission",
            f"无权限访问 {label}",
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
        return _contract_error(
            "HAD.SKILL_DISCOVERY_SYMLINK_FORBIDDEN",
            "symlink",
            f"{label} 不得为 symlink",
            exc,
        )
    if isinstance(exc, (FileNotFoundError, NotADirectoryError, IsADirectoryError)):
        return _contract_error(
            "HAD.SKILL_DISCOVERY_PATH_TYPE_INVALID",
            "path_type",
            f"{label} 必须为 {expected_type}",
            exc,
        )
    return _contract_error(
        "HAD.SKILL_DISCOVERY_IO_FAILED",
        "io",
        f"无法访问 {label}: {exc}",
        exc,
    )


def _secure_open_directory(
    parent_fd: int | None,
    name: str | os.PathLike[str],
    *,
    label: str,
) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise _contract_error(
            "HAD.FILESYSTEM_PRIMITIVE_UNSUPPORTED",
            "unsupported",
            "workflow Skill 发现要求 O_NOFOLLOW/O_DIRECTORY",
        )
    flags = _DIRECTORY_FLAGS | nofollow | directory
    try:
        descriptor = (
            os.open(name, flags)
            if parent_fd is None
            else os.open(name, flags, dir_fd=parent_fd)
        )
    except OSError as exc:
        raise _classify_io_error(
            exc,
            label=label,
            expected_type="真实 non-symlink directory",
            parent_fd=parent_fd,
            name=name,
        ) from exc
    try:
        metadata = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise _contract_error(
            "HAD.SKILL_DISCOVERY_IO_FAILED",
            "io",
            f"无法核验 {label}",
            exc,
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise _contract_error(
            "HAD.SKILL_DISCOVERY_PATH_TYPE_INVALID",
            "path_type",
            f"{label} 必须为真实 non-symlink directory",
        )
    return descriptor


def _secure_open_absolute_directory(path: Path, *, label: str) -> int:
    if not path.is_absolute():
        raise _contract_error(
            "HAD.SKILL_DISCOVERY_PATH_TYPE_INVALID",
            "path_type",
            f"{label} 必须为绝对路径",
        )
    descriptor = _secure_open_directory(None, path.anchor, label=f"{label} filesystem root")
    try:
        for component in path.parts[1:]:
            next_descriptor = _secure_open_directory(
                descriptor, component, label=f"{label} ancestor {component}",
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _secure_read_regular_file(
    parent_fd: int,
    name: str,
    *,
    label: str,
) -> tuple[str, tuple[int, int, int, int, int, int, int]]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    if not nofollow:
        raise _contract_error(
            "HAD.FILESYSTEM_PRIMITIVE_UNSUPPORTED",
            "unsupported",
            "workflow Skill 读取要求 O_NOFOLLOW",
        )
    flags = _FILE_FLAGS | nofollow | nonblock
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise _classify_io_error(
            exc,
            label=label,
            expected_type="regular non-symlink file",
            parent_fd=parent_fd,
            name=name,
        ) from exc
    try:
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise _contract_error(
                    "HAD.SKILL_DISCOVERY_PATH_TYPE_INVALID",
                    "path_type",
                    f"{label} 必须为 regular non-symlink file",
                )
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            content = b"".join(chunks)
        except ContractError:
            raise
        except OSError as exc:
            raise _contract_error(
                "HAD.SKILL_DISCOVERY_IO_FAILED",
                "io",
                f"无法安全读取 {label}",
                exc,
            ) from exc
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_nlink,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if identity(before) != identity(after) or len(content) != after.st_size:
            raise _contract_error(
                "HAD.SKILL_DISCOVERY_CONCURRENT_DRIFT",
                "concurrent_drift",
                f"{label} 在读取期间发生身份漂移",
            )
        try:
            return content.decode("utf-8"), identity(after)
        except UnicodeDecodeError as exc:
            raise ContractError(f"{label} 必须为 UTF-8 文本") from exc
    finally:
        os.close(descriptor)


def _directory_identity(descriptor: int, *, label: str) -> tuple[int, int, int, int, int]:
    try:
        metadata = os.fstat(descriptor)
    except OSError as exc:
        raise _contract_error(
            "HAD.SKILL_DISCOVERY_IO_FAILED",
            "io",
            f"无法核验 {label}",
            exc,
        ) from exc
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _list_direct_children(skills_fd: int) -> tuple[str, ...]:
    try:
        return tuple(sorted(os.listdir(skills_fd)))
    except OSError as exc:
        raise _classify_io_error(
            exc,
            label="canonical workflow Skill root",
            expected_type="readable directory",
        ) from exc


def _parse_workflow_skill(text: str, *, child_name: str, skill_label: str) -> str:
    match = _SKILL_FRONTMATTER.match(text)
    if match is None:
        raise ContractError(f"{skill_label} 缺合法 frontmatter")
    try:
        frontmatter = yaml.safe_load(match.group("body"))
    except yaml.YAMLError as exc:
        raise ContractError(f"{skill_label} frontmatter YAML 非法") from exc
    if not isinstance(frontmatter, dict):
        raise ContractError(f"{skill_label} frontmatter 非 mapping")
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, dict):
        raise ContractError(f"{skill_label} metadata 非 mapping")
    if metadata.get("kind") != "workflow":
        raise ContractError(f"{skill_label} metadata.kind 必须为 workflow")
    name = frontmatter.get("name")
    if not isinstance(name, str) or name != child_name:
        raise ContractError(f"{skill_label} name 与目录不一致")
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ContractError(f"{skill_label} description 必须为非空字符串")
    return name


def _workflow_skill_names(skill_root: object) -> tuple[str, ...]:
    if skill_root != _CANONICAL_WORKFLOW_SKILL_ROOT:
        raise ContractError(
            f"workflow binding skill_root 必须精确为 {_CANONICAL_WORKFLOW_SKILL_ROOT}"
        )
    repo_root = CONTRACT_PATH.parents[2]
    descriptors: list[int] = []
    child_descriptors: dict[str, int] = {}
    try:
        repo_fd = _secure_open_absolute_directory(repo_root, label="repository root")
        descriptors.append(repo_fd)
        repo_identity = _directory_identity(repo_fd, label="repository root")
        agents_fd = _secure_open_directory(repo_fd, ".agents", label=".agents")
        descriptors.append(agents_fd)
        skills_fd = _secure_open_directory(agents_fd, "skills", label=".agents/skills")
        descriptors.append(skills_fd)
        agents_identity = _directory_identity(agents_fd, label=".agents")
        skills_identity = _directory_identity(skills_fd, label=".agents/skills")
        child_names_before = _list_direct_children(skills_fd)

        names: list[str] = []
        opened_identities: dict[str, tuple[int, int, int, int, int]] = {}
        skill_file_identities: dict[str, tuple[int, int, int, int, int, int, int]] = {}
        for child_name in child_names_before:
            child_label = f".agents/skills/{child_name}"
            child_fd = _secure_open_directory(skills_fd, child_name, label=child_label)
            child_descriptors[child_name] = child_fd
            opened_identities[child_name] = _directory_identity(child_fd, label=child_label)
            skill_label = f"{child_label}/SKILL.md"
            text, skill_identity = _secure_read_regular_file(
                child_fd, "SKILL.md", label=skill_label,
            )
            skill_file_identities[child_name] = skill_identity
            names.append(
                _parse_workflow_skill(
                    text, child_name=child_name, skill_label=skill_label,
                )
            )

        current_repo_fd = _secure_open_absolute_directory(
            repo_root, label="repository root",
        )
        try:
            if (
                _directory_identity(current_repo_fd, label="repository root")
                != repo_identity
            ):
                raise _contract_error(
                    "HAD.SKILL_DISCOVERY_CONCURRENT_DRIFT",
                    "concurrent_drift",
                    "repository root 在 workflow Skill 发现期间发生身份替换",
                )
            current_agents_fd = _secure_open_directory(
                current_repo_fd, ".agents", label=".agents",
            )
            try:
                if (
                    _directory_identity(current_agents_fd, label=".agents")
                    != agents_identity
                ):
                    raise _contract_error(
                        "HAD.SKILL_DISCOVERY_CONCURRENT_DRIFT",
                        "concurrent_drift",
                        ".agents 在 workflow Skill 发现期间发生身份替换",
                    )
                current_skills_fd = _secure_open_directory(
                    current_agents_fd, "skills", label=".agents/skills",
                )
                try:
                    child_names_after = _list_direct_children(current_skills_fd)
                    if child_names_after != child_names_before:
                        raise _contract_error(
                            "HAD.SKILL_DISCOVERY_CONCURRENT_DRIFT",
                            "concurrent_drift",
                            "workflow Skill direct-child 集合在发现期间发生增删或替换",
                        )
                    if (
                        _directory_identity(current_skills_fd, label=".agents/skills")
                        != skills_identity
                    ):
                        raise _contract_error(
                            "HAD.SKILL_DISCOVERY_CONCURRENT_DRIFT",
                            "concurrent_drift",
                            "workflow Skill root 在发现期间发生身份替换",
                        )
                    for child_name in child_names_before:
                        child_label = f".agents/skills/{child_name}"
                        current_fd = _secure_open_directory(
                            current_skills_fd, child_name, label=child_label,
                        )
                        try:
                            current_identity = _directory_identity(
                                current_fd, label=child_label,
                            )
                            _, current_skill_identity = _secure_read_regular_file(
                                current_fd, "SKILL.md", label=f"{child_label}/SKILL.md",
                            )
                        finally:
                            os.close(current_fd)
                        if (
                            current_identity != opened_identities[child_name]
                            or current_skill_identity != skill_file_identities[child_name]
                        ):
                            raise _contract_error(
                                "HAD.SKILL_DISCOVERY_CONCURRENT_DRIFT",
                                "concurrent_drift",
                                f"{child_label} 在发现期间发生身份替换",
                            )
                finally:
                    os.close(current_skills_fd)
            finally:
                os.close(current_agents_fd)
        finally:
            os.close(current_repo_fd)
        if not names:
            raise ContractError("skill_root 未发现 Workflow Skill")
        return tuple(names)
    finally:
        for descriptor in reversed(tuple(child_descriptors.values())):
            os.close(descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@lru_cache(maxsize=1)
def _load_contract_cached() -> dict[str, Any]:
    value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    validate_contract(value)
    return value


def load_contract() -> dict[str, Any]:
    """Return a validated copy so callers cannot mutate the process cache."""
    return deepcopy(_load_contract_cached())


def _string_list(value: object, label: str, *, count: int | None = None) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{label} 必须为非空字符串闭集")
    if len(value) != len(set(value)):
        raise ContractError(f"{label} 包含重复值")
    if count is not None and len(value) != count:
        raise ContractError(f"{label} 必须包含 {count} 项")
    return value


def validate_contract(value: object) -> None:
    if not isinstance(value, dict):
        raise ContractError("contract 必须为映射")
    if value.get("schema_id") != "human-agent-delivery-contract" or value.get("schema_version") != 2:
        raise ContractError("contract identity/version 非法")
    namespaces = value.get("namespaces")
    closed = value.get("closed_sets")
    if not isinstance(namespaces, dict) or not isinstance(closed, dict):
        raise ContractError("缺 namespaces 或 closed_sets")
    human = namespaces.get("human_authority_role")
    review = namespaces.get("review_role")
    if not isinstance(human, dict) or not isinstance(review, dict):
        raise ContractError("HumanAuthorityRole 与 ReviewRole namespace 必须物理分离")
    human_values = _string_list(human.get("values"), "HumanAuthorityRole", count=11)
    review_values = _string_list(review.get("values"), "ReviewRole")
    if set(human_values) & set(review_values) or human.get("prefix") == review.get("prefix"):
        raise ContractError("HumanAuthorityRole 与 ReviewRole namespace 冲突")
    if review.get("may_decide_or_authorize") is not False:
        raise ContractError("ReviewRole 不得决定或授权")
    stages = _string_list(closed.get("delivery_stage"), "DeliveryStage", count=15)
    kinds = _string_list(closed.get("decision_kind"), "DecisionKind")
    event_types = _string_list(
        closed.get("role_interaction_event_type"), "RoleInteractionEventType", count=4
    )
    if event_types != [
        "progress_update", "decision_request", "exception_escalation", "completion_report"
    ]:
        raise ContractError("RoleInteractionEventType 闭集漂移")
    interaction_roles = _string_list(
        closed.get("role_interaction_audience_role"), "RoleInteractionAudienceRole", count=11
    )
    if interaction_roles != human_values:
        raise ContractError("角色交互 audience_role 必须复用 HumanAuthorityRole 闭集")
    _string_list(closed.get("role_interaction_legal_action"), "RoleInteractionLegalAction")
    _string_list(closed.get("role_interaction_safe_action"), "RoleInteractionSafeAction")
    responsibilities = _string_list(
        closed.get("decision_unit_responsibility"), "DecisionUnit responsibility", count=7
    )
    schemas = value.get("schemas")
    if not isinstance(schemas, dict):
        raise ContractError("缺 schemas")
    decision_unit = schemas.get("decision_unit")
    if not isinstance(decision_unit, dict) or not set(responsibilities).issubset(
        set(_string_list(decision_unit.get("required_fields"), "DecisionUnit.required_fields"))
    ):
        raise ContractError("DecisionUnit 未闭合七责字段")
    option = schemas.get("decision_option")
    expected_symmetric = {
        "option_id", "neutral_label", "user_outcome", "business_outcome", "cost",
        "time_to_effect", "risk", "reversibility", "scope_change", "unknowns", "next_step",
    }
    if not isinstance(option, dict) or set(_string_list(option.get("symmetric_fields"), "DecisionOption.symmetric_fields")) != expected_symmetric:
        raise ContractError("DecisionOption 对称字段漂移")
    grant = schemas.get("authorization_grant")
    if not isinstance(grant, dict) or grant.get("projection_only_until_authority_provider") is not True:
        raise ContractError("AuthorizationGrant 必须保持 projection-only")
    if grant.get("authenticated_authority") is not False or grant.get("executable") is not False:
        raise ContractError("本地 AuthorizationGrant 不得冒充 authority")
    required_schemas = {
        "decision_unit", "role_submission", "decision_option", "eligibility", "hard_gate",
        "decision_record", "human_runtime_decision_receipt",
        "human_runtime_decision_projection", "authorization_grant", "card_projection",
        "commercial_readiness_decision", "production_campaign_approval", "outcome_acceptance",
        "role_interaction_envelope", "human_calibration_session",
        "human_calibration_observation", "human_calibration_readback",
    }
    if not required_schemas.issubset(schemas):
        raise ContractError(f"schemas 缺定义: {sorted(required_schemas - set(schemas))}")
    for schema_name in required_schemas - {"decision_option"}:
        schema = schemas[schema_name]
        if not isinstance(schema, dict):
            raise ContractError(f"{schema_name} schema 必须为映射")
        _string_list(schema.get("required_fields"), f"{schema_name}.required_fields")
    principal_classes = _string_list(
        closed.get("human_calibration_principal_class"),
        "HumanCalibrationPrincipalClass", count=4,
    )
    if principal_classes != ["product", "engineering", "quality", "release_operations"]:
        raise ContractError("HumanCalibrationPrincipalClass 闭集漂移")
    responsibility_classes = _string_list(
        closed.get("human_calibration_responsibility_class"),
        "HumanCalibrationResponsibilityClass", count=6,
    )
    if responsibility_classes != [
        "business", "product", "experience", "quality", "engineering", "release_operations",
    ]:
        raise ContractError("HumanCalibrationResponsibilityClass 闭集漂移")
    dimensions = _string_list(
        closed.get("human_calibration_observation_dimension"),
        "HumanCalibrationObservationDimension", count=6,
    )
    if dimensions != [
        "understanding", "option_cross_role_impact_comprehension", "transfer",
        "pause_deny_abort", "recovery", "post_check",
    ]:
        raise ContractError("HumanCalibrationObservationDimension 闭集漂移")
    if _string_list(closed.get("human_calibration_status"), "HumanCalibrationStatus") != [
        "not_observed", "insufficient", "calibrated",
    ]:
        raise ContractError("HumanCalibrationStatus 闭集漂移")
    source_kinds = _string_list(
        closed.get("human_calibration_source_kind"), "HumanCalibrationSourceKind", count=5
    )
    if source_kinds != [
        "human_participant", "machine_fixture", "reviewer", "agent_self_test", "machine_baseline",
    ]:
        raise ContractError("HumanCalibrationSourceKind 闭集漂移")
    if _string_list(closed.get("human_calibration_observation_outcome"), "HumanCalibrationObservationOutcome") != [
        "demonstrated", "insufficient", "not_attempted",
    ]:
        raise ContractError("HumanCalibrationObservationOutcome 闭集漂移")
    _string_list(closed.get("human_calibration_blocker"), "HumanCalibrationBlocker")
    calibration = value.get("calibration_model")
    if not isinstance(calibration, dict):
        raise ContractError("缺 calibration_model")
    if calibration.get("contract_version") != "human-calibration-v2":
        raise ContractError("Human calibration contract version 漂移")
    if calibration.get("role_model_version") != "human-calibration-role-model-v2":
        raise ContractError("Human calibration role model version 漂移")
    if calibration.get("observation_model_version") != "human-calibration-observation-model-v2":
        raise ContractError("Human calibration observation model version 漂移")
    if calibration.get("freshness_seconds") != 86400 or calibration.get("minimum_qualifying_role_sessions") != 4:
        raise ContractError("Human calibration freshness/minimum sample 漂移")
    expected_mapping = {
        "product": ["business", "product", "experience"],
        "engineering": ["engineering"],
        "quality": ["quality"],
        "release_operations": ["release_operations"],
    }
    if calibration.get("principal_responsibility_mapping") != expected_mapping:
        raise ContractError("Human calibration principal/responsibility mapping 漂移")
    if (
        calibration.get("mapping_semantics") != "calibration_coverage_only"
        or calibration.get("authority_delegation") is not False
        or calibration.get("signoff_substitution") is not False
        or calibration.get("qualifying_source_kind") != "human_participant"
        or calibration.get("non_human_source_kinds") != ["machine_fixture", "reviewer", "agent_self_test", "machine_baseline"]
        or calibration.get("each_principal_requires_qualifying_role_session") is not True
        or calibration.get("same_participant_cross_principal_requires_separate_session_role_records") is not True
        or calibration.get("routine_calibration_requires_four_unique_participants") is not False
        or calibration.get("independent_principal_policy") != "independent-principal-required"
        or calibration.get("exact_session_bytes_required") is not True
        or calibration.get("timezone_aware_chronology_required") is not True
        or calibration.get("caller_status_flags_accepted") is not False
    ):
        raise ContractError("Human calibration authority/source semantics 漂移")
    session_schema = schemas["human_calibration_session"]
    readback_schema = schemas["human_calibration_readback"]
    if session_schema.get("free_text_allowed") is not False:
        raise ContractError("Human calibration 不得保存自由文本")
    if set(session_schema.get("raw_content_fields_forbidden") or ()) != {
        "prompt", "prompt_text", "message", "message_text", "payload", "raw_payload", "free_text", "transcript",
    }:
        raise ContractError("Human calibration raw-content 禁止字段漂移")
    if set(readback_schema.get("coverage_required_fields") or ()) != {
        "required_principal_classes", "completed_principal_classes",
        "required_responsibility_classes", "completed_responsibility_classes",
        "required_observation_dimensions", "completed_observation_dimensions",
    }:
        raise ContractError("Human calibration readback coverage 字段漂移")

    interaction = schemas["role_interaction_envelope"]
    expected_interaction_fields = {
        "event_type", "delivery_stage", "audience_role", "what_happened",
        "user_or_business_impact", "decision_owner", "legal_actions",
        "safe_actions_taken", "next_acceptance", "next_acceptance_role", "audit_details",
    }
    if set(interaction["required_fields"]) != expected_interaction_fields:
        raise ContractError("RoleInteractionEnvelope 公共字段漂移")
    event_required = interaction.get("event_required_fields")
    if not isinstance(event_required, dict) or set(event_required) != set(event_types):
        raise ContractError("RoleInteractionEnvelope 事件专属字段未覆盖四类事件")
    if event_required.get("exception_escalation") != ["cannot_continue_reason", "safest_default"]:
        raise ContractError("异常交互字段漂移")
    if event_required.get("completion_report") != ["proof", "limits"]:
        raise ContractError("完成交互字段漂移")
    audit_terms = _string_list(interaction.get("audit_only_internal_terms"), "RoleInteractionEnvelope.audit_only_internal_terms")
    required_audit_terms = {
        "digest", "cas", "gate_block", "typed_blocker", "fingerprint",
        "owner_manifest", "receipt", "readback", "exact_byte", "sha",
        "internal_absolute_path", "internal_command", "internal_tool_name",
    }
    if set(audit_terms) != required_audit_terms:
        raise ContractError("RoleInteractionEnvelope 审计专用术语漂移")
    sod_policies = value.get("sod_policies")
    if not isinstance(sod_policies, dict) or set(sod_policies) != {
        "role-record-only", "independent-principal-required"
    }:
        raise ContractError("SoD policy 必须为版本化两项闭集")
    if sod_policies["role-record-only"].get("distinct_authenticated_actors_required") is not False:
        raise ContractError("role-record-only 不得强制不同 principal")
    if sod_policies["independent-principal-required"].get("distinct_authenticated_actors_required") is not True:
        raise ContractError("independent-principal-required 必须强制不同 principal")
    risk_policy = value.get("risk_sod_policy")
    if not isinstance(risk_policy, dict) or risk_policy.get("default") not in sod_policies:
        raise ContractError("risk_sod_policy.default 非法")
    classifications = risk_policy.get("classifications")
    if not isinstance(classifications, dict) or not classifications or any(
        policy not in sod_policies for policy in classifications.values()
    ):
        raise ContractError("risk_sod_policy.classifications 非法")
    routes = value.get("router")
    if not isinstance(routes, list) or not routes:
        raise ContractError("router 必须为非空表")
    seen: set[tuple[str, str]] = set()
    terminals = set(_string_list(closed.get("default_terminal"), "default_terminal"))
    for route in routes:
        if not isinstance(route, dict):
            raise ContractError("router 项必须为映射")
        key = (route.get("stage"), route.get("decision_kind"))
        if key in seen or key[0] not in stages or key[1] not in kinds:
            raise ContractError(f"router key 非法或重复: {key!r}")
        seen.add(key)
        role = route.get("accountable_role")
        if role is not None and role not in human_values:
            raise ContractError(f"router accountable_role 非法: {role!r}")
        vetoes = route.get("hard_veto_roles")
        if not isinstance(vetoes, list) or any(role not in human_values for role in vetoes):
            raise ContractError(f"router hard_veto_roles 非法: {key!r}")
        if route.get("default_terminal") not in terminals:
            raise ContractError(f"router default_terminal 非法: {key!r}")
    runtime_bridge = value.get("runtime_bridge")
    expected_runtime_bridge = {
        "schema_version": 1,
        "serialization_version": "human-runtime-decision-v1",
        "canonical_cli": "quwoquan_ops/cli/human_agent_delivery.py",
        "local_store": ".qwq_output/env/repo/runs/human-decisions",
        "decision_values": ["continue", "pause", "redirect", "approve_admission"],
        "duration_scope_kinds": ["objective", "boundary", "session", "until_replaced"],
        "target_kinds": ["agent_execution", "review", "handoff"],
        "admission_classes": ["ordinary", "formal_prod"],
        "ordinary_missing_projection": "declared_not_projected_nonblocking",
        "during_poll": "explicit_command_only",
        "per_tool_hook_polling": "forbidden",
        "local_input_mode": "explicit_cli_only",
        "inferred_natural_language_verified": False,
        "self_attested_formal_production_authority": False,
        "formal_production_authority_source": "hosted_authenticated_authority_provider",
        "hosted_authority_adapter": "quwoquan_ops/cli/lib/hosted_authority",
    }
    if runtime_bridge != expected_runtime_bridge:
        raise ContractError("Human runtime bridge 字段或 authority 边界漂移")
    runtime_receipt = schemas["human_runtime_decision_receipt"]
    runtime_projection = schemas["human_runtime_decision_projection"]
    if (
        runtime_receipt.get("schema_version") != 1
        or runtime_projection.get("schema_version") != 1
        or runtime_receipt.get("authority_fields") != ["source", "duration_scope"]
        or runtime_receipt.get("duration_scope_fields") != ["kind", "value"]
        or runtime_receipt.get("provider_fields") != ["kind", "provider_id", "provider_receipt_ref"]
        or runtime_receipt.get("human_identity_fields") != ["subject", "assurance"]
    ):
        raise ContractError("Human runtime decision receipt/projection schema 漂移")
    harness = value.get("harness_projection")
    if (
        not isinstance(harness, dict)
        or harness.get("harnesses") != ["cursor", "codex"]
        or harness.get("canonical_cli") != "quwoquan_ops/cli/human_agent_delivery.py"
        or harness.get("projection_commands") != ["project-card", "project-interaction"]
        or harness.get("interaction_projection_command") != "project-interaction"
        or harness.get("harness_is_contract_field") is not True
        or harness.get("identical_json_projection") is not True
    ):
        raise ContractError("Cursor/Codex harness projection 必须显式校验且同源")
    workflow = value.get("workflow_interaction_binding")
    if not isinstance(workflow, dict):
        raise ContractError("缺 workflow_interaction_binding")
    expected_workflow_fields = {
        "canonical_projector", "skill_root", "required_phases",
        "required_binding_fields", "dynamic_audience_role", "bindings",
    }
    if set(workflow) != expected_workflow_fields:
        raise ContractError("workflow interaction binding 字段闭包漂移")
    if workflow.get("canonical_projector") != "quwoquan_ops/cli/lib/human_agent_delivery/projection.py#project_role_interaction":
        raise ContractError("workflow binding 必须使用 canonical projector")
    skill_names = _workflow_skill_names(workflow.get("skill_root"))
    bindings = workflow.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(skill_names):
        raise ContractError("workflow bindings 必须动态覆盖 skill_root 的 Workflow Skill 闭包")
    phases = workflow.get("required_phases")
    fields = workflow.get("required_binding_fields")
    if phases != ["PRE", "DURING", "POST"] or fields != ["phase", "event_type", "delivery_stage", "audience_role"]:
        raise ContractError("workflow binding phase/field 契约漂移")
    for skill in skill_names:
        skill_bindings = bindings[skill]
        if not isinstance(skill_bindings, list) or len(skill_bindings) != len(phases):
            raise ContractError(f"{skill} 必须声明 PRE/DURING/POST 三段交互")
        if [item.get("phase") for item in skill_bindings if isinstance(item, dict)] != phases:
            raise ContractError(f"{skill} 交互 phase 漂移")
        for item in skill_bindings:
            if not isinstance(item, dict) or list(item) != fields:
                raise ContractError(f"{skill} 交互字段漂移")
            if item["event_type"] not in event_types or item["delivery_stage"] not in stages:
                raise ContractError(f"{skill} 交互闭集值非法")
            if item["audience_role"] not in {*human_values, workflow.get("dynamic_audience_role")}:
                raise ContractError(f"{skill} 交互角色非法")
    production = value.get("production_policy")
    if (
        not isinstance(production, dict)
        or production.get("one_approval_per_frozen_campaign") is not True
        or production.get("objective_execution_admission_source")
        != "quwoquan_ops/policies/objective_execution_contract.yaml#admission"
        or any(key in production for key in ("s4_admission", "write_concurrency", "temporary_branch_bypass"))
    ):
        raise ContractError("production policy 必须引用 Objective execution admission，不能复制 S4 机器事实")
    recommendation = value.get("recommendation_policy")
    if not isinstance(recommendation, dict) or set(
        recommendation.get("forbidden_decision_kinds") or ()
    ) != {"product_scope", "experience_direction", "commercial_readiness", "outcome_acceptance"}:
        raise ContractError("偏好类决定的 recommendation policy 漂移")
    errors = value.get("errors")
    if not isinstance(errors, dict) or not errors:
        raise ContractError("缺 typed errors")
    for code, descriptor in errors.items():
        if not isinstance(code, str) or not code.startswith("HAD.") or not isinstance(descriptor, dict):
            raise ContractError("typed error 定义非法")
        if descriptor.get("terminal") not in terminals or not descriptor.get("recovery"):
            raise ContractError(f"typed error 缺 terminal/recovery: {code}")


def closed_values(name: str) -> tuple[str, ...]:
    contract = load_contract()
    return tuple(contract["closed_sets"][name])


def namespace_values(name: str) -> tuple[str, ...]:
    contract = load_contract()
    return tuple(contract["namespaces"][name]["values"])


def schema_fields(name: str, declaration: str = "required_fields") -> tuple[str, ...]:
    contract = load_contract()
    value = contract["schemas"][name][declaration]
    return tuple(value)


def validate_exact_fields(payload: Mapping[str, Any], schema_name: str, declaration: str = "required_fields") -> None:
    expected = set(schema_fields(schema_name, declaration))
    actual = set(payload)
    if actual != expected:
        raise ContractError(
            f"{schema_name} 字段漂移: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def typed_blocker(code: str, *, detail: str = "", terminal: str | None = None) -> dict[str, Any]:
    errors = load_contract()["errors"]
    descriptor = errors.get(code)
    if not isinstance(descriptor, dict):
        descriptor = errors["HAD.CONTRACT_INVALID"]
        code = "HAD.CONTRACT_INVALID"
    return {
        "result": "typed_blocker",
        "code": code,
        "terminal": terminal or descriptor["terminal"],
        "recovery": descriptor["recovery"],
        "detail": detail,
    }
