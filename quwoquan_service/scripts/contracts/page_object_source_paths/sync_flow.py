"""同步主流程：定位失效路径、逐行改写并做等价性自证。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable, Sequence

import yaml

from .contract_io import (
    _atomic_write,
    contract_pages,
    load_contract,
    replace_page_path,
)
from .models import (
    APP_DIR_NAME,
    CONTRACT_REL,
    EVIDENCE_FIELDS,
    ContractError,
    ManualDecision,
    SourcePathFix,
    SyncReport,
)
from .moved_path import defines_entry_widget, references_widget, resolve_moved_path
from .review import object_presentation_participant_findings, page_scan_set_findings


def _entry_widget(page: dict) -> str:
    value = page.get("entry_widget")
    return value.strip() if isinstance(value, str) else ""


def sync(
    repository_root: Path,
    *,
    write: bool,
    shape_of: Callable[[str], tuple[str, str, str, str] | None] | None = None,
    disk_scan_paths: frozenset[str] | None = None,
) -> SyncReport:
    contract_path = repository_root / CONTRACT_REL
    app_root = repository_root / APP_DIR_NAME
    document, text = load_contract(contract_path)
    pages = contract_pages(document)

    report = SyncReport(total_pages=len(pages))
    healthy_sources = {
        str(page["source_path"]).strip()
        for page in pages
        if (app_root / str(page["source_path"]).strip()).is_file()
    }

    updated_text = text
    planned: list[SourcePathFix] = []

    for page in pages:
        source_path = str(page["source_path"]).strip()
        if source_path in healthy_sources:
            continue
        # 页面身份唯一：新落点不得抢占别的页面已经登记的 source_path。
        excluded = frozenset(
            healthy_sources
            | {fix.new_path for fix in planned if fix.field_name == "source_path"}
        )
        outcome = resolve_moved_path(
            repository_root,
            app_root,
            page_id=str(page["page_id"]).strip(),
            field_name="source_path",
            old_path=source_path,
            entry_widget=_entry_widget(page),
            widget_predicate=defines_entry_widget,
            excluded_paths=excluded,
            missing_reason=(
                "lib/** 下找不到同名页面文件；页面可能被删除、改名或拆成多个文件，需人工裁决"
            ),
        )
        if isinstance(outcome, ManualDecision):
            report.manual.append(outcome)
            continue
        planned.append(outcome)
        updated_text = replace_page_path(
            updated_text,
            outcome.page_id,
            outcome.field_name,
            outcome.old_path,
            outcome.new_path,
        )

    # 装配证据路径与 source_path 一样会被搬迁打断，且同样只有本工具有写权限。
    for page in pages:
        for field_name in EVIDENCE_FIELDS:
            values = page.get(field_name)
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    continue
                evidence = value.strip()
                if (app_root / evidence).is_file():
                    continue
                outcome = resolve_moved_path(
                    repository_root,
                    app_root,
                    page_id=str(page["page_id"]).strip(),
                    field_name=field_name,
                    old_path=evidence,
                    entry_widget=_entry_widget(page),
                    widget_predicate=references_widget,
                    excluded_paths=frozenset(),
                    missing_reason=(
                        "lib/** 下找不到同名装配证据文件；装配点可能已改名或被删除，需人工裁决"
                    ),
                )
                if isinstance(outcome, ManualDecision):
                    report.manual.append(outcome)
                    continue
                planned.append(outcome)
                updated_text = replace_page_path(
                    updated_text,
                    outcome.page_id,
                    outcome.field_name,
                    outcome.old_path,
                    outcome.new_path,
                )

    report.fixes.extend(planned)
    if planned:
        expected = _expected_document(document, planned)
        if yaml.safe_load(updated_text) != expected:
            raise ContractError("逐行改写结果与预期文档不一致，已放弃写入")
        document = expected
        if write:
            _atomic_write(contract_path, updated_text)
            report.changed = True

    effective_pages = document["pages"]
    if shape_of is not None:
        report.review.extend(
            object_presentation_participant_findings(
                effective_pages,
                shape_of,
                app_root=app_root,
            )
        )
    report.review.extend(page_scan_set_findings(effective_pages, disk_scan_paths))
    report.review.sort(key=lambda item: (item.kind, item.page_id))
    return report


def _expected_document(document: dict, planned: Sequence[SourcePathFix]) -> dict:
    """按计划变更在内存中构造期望文档，用于逐行改写的等价性自证。"""

    expected = deepcopy(document)
    by_page: dict[str, dict] = {
        str(page.get("page_id") or "").strip(): page for page in expected["pages"]
    }
    for fix in planned:
        page = by_page[fix.page_id]
        if fix.field_name == "source_path":
            page["source_path"] = fix.new_path
            continue
        values = page[fix.field_name]
        values[values.index(fix.old_path)] = fix.new_path
    return expected
