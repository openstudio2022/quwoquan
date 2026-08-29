"""Deterministic pre-finalization check for one Agent-authored homepage draft."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.execution import store
from content.homepage.commercial_gate import copyright_mode_issues
from content.homepage.draft_derivation import (
    paragraph_repetition_issues,
    source_overlap_issues,
)
from content.homepage.homepage import _homepage_gate_body, _page_char_count
from content.homepage.homepage_materialization import (
    _homepage_outline_issues,
    _homepage_source_figure_issues,
)
from content.homepage.quality_policy import (
    homepage_body_char_minimum,
    homepage_derivation_paragraph_char_minimum,
    homepage_intra_body_similarity_limit,
    homepage_source_fidelity_limit,
    homepage_source_paragraph_overlap_limit,
)
from content.post.article.base_draft import base_draft_source_path
from content.post.fidelity import base_draft_fidelity_issues, base_draft_similarity
from core.ai_refine_protocol import expand_image_placeholders, placeholder_consistency_issues
from core.entity_page_quality import entity_page_quality_issues
from core.io import read_json
from core.localization import fold_to_simplified
from core.paths import execution_entity_object_dir, execution_entity_page_input_path
from core.template_fingerprints import template_fingerprint_issues
from governance.coverage.entity_extract import require_domain_etype


def homepage_draft_report(execution_id: str, entity_name: str) -> dict[str, object]:
    spec = store.load_spec_model(execution_id)
    target = next(
        (row for row in spec.scope.coverage_targets if row.name == entity_name),
        None,
    )
    if target is None:
        raise ValueError(f"execution target not found: {entity_name}")
    domain, entity_type = require_domain_etype(
        target.entity_type,
        context=entity_name,
    )
    label = f"{domain}/{entity_type}/{entity_name}"
    object_dir = execution_entity_object_dir(
        execution_id,
        domain,
        entity_type,
        entity_name,
    )
    draft_path = object_dir / "4.draft" / "page.md"
    input_path = execution_entity_page_input_path(
        execution_id,
        domain,
        entity_type,
        entity_name,
    )
    issues: list[str] = []
    if not draft_path.is_file():
        issues.append(f"{label}: 4.draft/page.md missing")
    if not input_path.is_file():
        issues.append(f"{label}: 3.compose/entity_page_input.json missing")
    if issues:
        return _report(execution_id, entity_name, issues=issues)

    envelope = read_json(input_path)
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else envelope
    base = payload.get("baseDraft") if isinstance(payload.get("baseDraft"), dict) else {}
    base_text = fold_to_simplified(str(base.get("text") or "").strip())
    draft_text = fold_to_simplified(draft_path.read_text(encoding="utf-8"))
    minimum_body_chars = homepage_body_char_minimum(execution_id)
    if _page_char_count(draft_path) < minimum_body_chars:
        issues.append(
            f"{label}: draft non-whitespace chars {_page_char_count(draft_path)} < {minimum_body_chars}"
        )
    issues.extend(entity_page_quality_issues(draft_path, label=label))
    issues.extend(
        _homepage_outline_issues(
            [row for row in base.get("sectionOutline") or [] if isinstance(row, dict)],
            draft_text,
            label,
        )
    )
    issues.extend(_homepage_source_figure_issues(base, draft_text, label))
    bindings = [
        {**row, "caption": fold_to_simplified(str(row.get("caption") or ""))}
        for row in payload.get("imagePlaceholderBindings") or []
        if isinstance(row, dict)
    ]
    issues.extend(placeholder_consistency_issues(draft_text, bindings, label=label))
    gate_body = _homepage_gate_body(expand_image_placeholders(draft_text, bindings))
    issues.extend(f"{label}: {item}" for item in template_fingerprint_issues(gate_body))
    source_use_mode = str(base.get("sourceUseMode") or "factual_reference_only")
    issues.extend(
        f"{label}: {item}"
        for item in base_draft_fidelity_issues(
            gate_body,
            base_text,
            carrier="article",
            max_ratio=homepage_source_fidelity_limit(execution_id),
            source_use_mode=source_use_mode,
        )
    )
    # base_draft_fidelity_issues 对 factual_reference_only 直接放行，其抄写与压缩
    # 边界由版权模式门独立判定；checkpoint 走的是后者，自检必须同源，否则 Agent
    # 自检通过却在准出被拦。
    if base_text:
        issues.extend(
            copyright_mode_issues(gate_body, base_text, source_use_mode, label=label)
        )
    issues.extend(_derivation_issues(execution_id, base, draft_text, label))
    similarity = base_draft_similarity(gate_body, base_text, carrier="article")
    return _report(
        execution_id,
        entity_name,
        issues=list(dict.fromkeys(issues)),
        non_whitespace_chars=_page_char_count(draft_path),
        base_draft_fidelity=round(similarity, 4),
    )


def _derivation_issues(
    execution_id: str,
    base: dict[str, object],
    draft_text: str,
    label: str,
) -> list[str]:
    """派生度判据：正文对底稿的逐字重合，与正文内部的段落自我重复。

    只判字数与章节均衡时，「把底稿几行原样搬进来凑字数」与「同一段复读两遍」都能
    通过，判据本身在诱导复述原文。判否线与参与判定的段落最小字数都取自 vertical
    content supply policy 的显式声明，本函数不持有任何数字。

    行号坐标系用 `source.clean.md` 原文件行，不用 `baseDraft.text`：后者由
    `_extract_base_draft_body` 重排过行，按它给出的行号作者打开文件会数到别处。
    """
    minimum_chars = homepage_derivation_paragraph_char_minimum(execution_id)
    source_ref = str(
        base.get("primaryEvidenceRef") or base.get("sourceRef") or ""
    ).strip()
    source_path = base_draft_source_path(execution_id, source_ref)
    if source_path is None:
        # 底稿正文文件是源重合度的唯一分母。定位不到时判否而不是跳过：跳过等于
        # 「底稿来源单元不在场就免判复述原文」。
        overlap = [
            f"{label}: sourceParagraphOverlap: 底稿正文文件不可定位"
            f"（baseDraft.primaryEvidenceRef={source_ref or '<empty>'}），"
            "源重合度无法复算；先恢复 1.download 来源单元再自检"
        ]
    else:
        overlap = source_overlap_issues(
            draft_text,
            fold_to_simplified(source_path.read_text(encoding="utf-8")).splitlines(),
            max_overlap_ratio=homepage_source_paragraph_overlap_limit(execution_id),
            minimum_paragraph_chars=minimum_chars,
            label=label,
        )
    return [
        *overlap,
        *paragraph_repetition_issues(
            draft_text,
            max_similarity=homepage_intra_body_similarity_limit(execution_id),
            minimum_paragraph_chars=minimum_chars,
            label=label,
        ),
    ]


def _report(
    execution_id: str,
    entity_name: str,
    *,
    issues: list[str],
    non_whitespace_chars: int = 0,
    base_draft_fidelity: float = 0.0,
) -> dict[str, object]:
    return {
        "passed": not issues,
        "executionId": execution_id,
        "entity": entity_name,
        "nonWhitespaceChars": non_whitespace_chars,
        "baseDraftFidelity": base_draft_fidelity,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", required=True)
    parser.add_argument("--entity", required=True)
    args = parser.parse_args(argv)
    report = homepage_draft_report(str(args.execution), str(args.entity))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
