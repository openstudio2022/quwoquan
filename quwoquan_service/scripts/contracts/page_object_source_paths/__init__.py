"""page_object_contract 路径同步工具的实现包。

单轨实现按职责拆分为若干子模块；稳定 CLI 入口是同目录的
``sync_page_object_source_paths.py``，它 re-export 本包全部 API（含既有
消费者依赖的私有 ``_`` 符号），入口路径与行为契约不变。
"""

from __future__ import annotations

from .contract_io import (
    _atomic_write,
    _field_region,
    _page_block_range,
    contract_pages,
    load_contract,
    replace_page_path,
)
from .dart_analysis import (
    _consumed_dart_identifiers,
    _consumed_public_behavior_symbols,
    _dart_source_tokens,
    _is_application_public_path,
    _looks_like_object_presentation,
    _matching_paren_end,
    _page_library_evidence,
    _parse_dart_uri_directives,
    _public_behavior_symbols,
    _public_instance_behavior_symbols,
    _public_named_declarations,
    _resolve_app_dart_uri,
)
from .gate_classify import (
    GATE_FAILURE_CLASSES,
    classify_gate_failures,
    run_page_quality_gates,
)
from .models import (
    APP_DIR_NAME,
    CONTRACT_REL,
    EVIDENCE_FIELDS,
    GIT_RENAME_MAX_HOPS,
    REPORT_DIR_NAME,
    REPOSITORY_ROOT,
    ContractError,
    ManualDecision,
    ReviewFinding,
    SourcePathFix,
    SyncReport,
)
from .moved_path import (
    _dart_library_text,
    _rename_target_in_commit,
    _run_git,
    defines_entry_widget,
    git_rename_target,
    lib_basename_candidates,
    references_widget,
    resolve_moved_path,
)
from .repo_reuse import (
    _default_report_dir,
    _importable,
    _load_disk_scan_paths,
    _load_shape_resolver,
)
from .reporting import render_markdown_report, render_report, write_run_report
from .review import object_presentation_participant_findings, page_scan_set_findings
from .sync_flow import _entry_widget, _expected_document, sync
from .cli import main

__all__ = [
    "APP_DIR_NAME",
    "CONTRACT_REL",
    "EVIDENCE_FIELDS",
    "GATE_FAILURE_CLASSES",
    "GIT_RENAME_MAX_HOPS",
    "REPORT_DIR_NAME",
    "REPOSITORY_ROOT",
    "ContractError",
    "ManualDecision",
    "ReviewFinding",
    "SourcePathFix",
    "SyncReport",
    "classify_gate_failures",
    "contract_pages",
    "defines_entry_widget",
    "git_rename_target",
    "lib_basename_candidates",
    "load_contract",
    "main",
    "object_presentation_participant_findings",
    "page_scan_set_findings",
    "references_widget",
    "render_markdown_report",
    "render_report",
    "replace_page_path",
    "resolve_moved_path",
    "run_page_quality_gates",
    "sync",
    "write_run_report",
]
