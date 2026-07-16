"""五阶段 Prompt 快照：可重放、可校验、绝不持久化密钥。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from content.execution.runtime_contract import canonical_sha256, stage_execution_context
from core.io import write_json
from core.prompt_render import prompt_template_material
from content.execution.production_contracts import sha256_text


_SECRET_KEY_TOKENS = (
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
)
_PUBLIC_PROVENANCE_FIELD_NAMES = frozenset({"authorizationproof"})
_STAGE_PROMPT_ROLES = frozenset({"source", "reviewer", "repair"})


def prompt_bundle_revision(template_family: str) -> str:
    """Return the canonical revision shared by compose packets and prompt snapshots."""
    material = prompt_template_material(template_family)
    return canonical_sha256(
        {
            "templateFamily": template_family,
            "system": material["system"],
            "task": material["task"],
            "partials": list(material["partials"]),
        }
    )


def prompt_snapshot_paths(
    *,
    role: str,
    run_id: str,
    stage_dir: Path | None = None,
    execution_root: Path | None = None,
    checkpoint: str = "",
) -> tuple[Path, Path]:
    """冻结 author/stage/controller 三种 Prompt 归位，不提供兼容路径。"""
    if not run_id or "/" in run_id or ".." in run_id:
        raise ValueError("runId must be a non-empty path-safe segment")
    if role == "author":
        if stage_dir is None or stage_dir.name != "4.draft":
            raise ValueError("author prompt requires 4.draft stage_dir")
        return stage_dir / "prompt.md", stage_dir / "prompt_snapshot.json"
    if role in _STAGE_PROMPT_ROLES:
        if stage_dir is None:
            raise ValueError(f"{role} prompt requires its stage_dir")
        root = stage_dir / "prompts" / run_id
        return root / "prompt.md", root / "prompt_snapshot.json"
    if role == "controller":
        if execution_root is None or not checkpoint:
            raise ValueError("controller prompt requires execution_root and checkpoint")
        root = execution_root / "_shared" / "prompt_snapshots" / checkpoint / run_id
        return root / "prompt.md", root / "prompt_snapshot.json"
    raise ValueError(f"unsupported prompt role: {role}")


def secret_paths(value: Any, *, prefix: str = "vars") -> list[str]:
    """递归找出疑似密钥字段；值不回显，避免错误日志二次泄露。"""
    issues: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("-", "_")
            child_path = f"{prefix}.{key}"
            if (
                normalized not in _PUBLIC_PROVENANCE_FIELD_NAMES
                and any(token in normalized for token in _SECRET_KEY_TOKENS)
            ):
                issues.append(child_path)
            issues.extend(secret_paths(child, prefix=child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            issues.extend(secret_paths(child, prefix=f"{prefix}[{index}]"))
    return issues


def build_prompt_snapshot(
    *,
    execution_id: str,
    stage: str,
    template_family: str,
    variables: Mapping[str, Any],
    rendered_prompt: str,
    provider: str,
    model: str,
    run_id: str,
    output_refs: Sequence[str],
) -> dict[str, Any]:
    leaked = secret_paths(variables)
    if leaked:
        raise ValueError(f"prompt snapshot vars contain secret-like fields: {sorted(leaked)}")
    material = prompt_template_material(template_family)
    partials = list(material["partials"])
    execution = stage_execution_context(execution_id)
    bundle_revision = prompt_bundle_revision(template_family)
    return {
        "schemaVersion": "quwoquan_data.prompt_snapshot/1",
        "stage": stage,
        **execution,
        "templateFamily": template_family,
        "templateRevision": bundle_revision,
        "templateRefs": {
            "system": material["system"]["ref"],
            "task": material["task"]["ref"],
            "partials": [row["ref"] for row in partials],
        },
        "systemHash": material["system"]["sha256"],
        "taskHash": material["task"]["sha256"],
        "partialsHash": canonical_sha256(partials),
        "varsHash": canonical_sha256(dict(variables)),
        "variables": dict(variables),
        "promptBundleRevision": bundle_revision,
        "renderedHash": sha256_text(rendered_prompt),
        "provider": provider,
        "model": model,
        "runId": run_id,
        "outputRefs": list(output_refs),
    }


def write_prompt_snapshot(path: Path, **kwargs: Any) -> Path:
    snapshot = build_prompt_snapshot(**kwargs)
    write_json(path, snapshot)
    return path


def prompt_snapshot_issues(snapshot: Mapping[str, Any], prompt_path: Path) -> list[str]:
    issues: list[str] = []
    leaked = secret_paths(snapshot.get("variables") or {})
    if leaked:
        issues.append(f"secret-like vars forbidden: {sorted(leaked)}")
    if not prompt_path.is_file():
        issues.append(f"rendered prompt missing: {prompt_path}")
    else:
        actual = sha256_text(prompt_path.read_text(encoding="utf-8"))
        if actual != snapshot.get("renderedHash"):
            issues.append(
                f"renderedHash mismatch: {snapshot.get('renderedHash') or '<empty>'} != {actual}"
            )
    if canonical_sha256(dict(snapshot.get("variables") or {})) != snapshot.get("varsHash"):
        issues.append("varsHash mismatch")
    return issues
