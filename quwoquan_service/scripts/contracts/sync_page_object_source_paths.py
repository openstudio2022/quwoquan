#!/usr/bin/env python3
"""把 ``page_object_contract.yaml`` 的 App 相对路径收敛回磁盘真相。

覆盖 ``source_path`` 与 ``route_registration_evidence`` / ``mount_evidence``：
端侧 ``quwoquan_app/lib`` 正在从「技术角色分层」搬迁成
``lib/<domain>/<context>/<object>/<layer>/`` 的对象树。页面文件每被搬走一次，
``page_object_contract.yaml`` 的路径就失效一条：

- ``quwoquan_app/scripts/runtime/page/verify_page_object_contract.py`` 直接 BLOCK。
- ``quwoquan_ops/gate/object_path_map.py`` 的 ``page_object_contract`` 认领
  **无声失效**，退化成别名启发式或 ``context_only``。

本工具是该 YAML 的唯一写入口：搬迁流不要手改契约，跑一次本工具即可。
定位不唯一时一律报错退出，绝不代替业务猜测。

用法::

    # 只检测，不落盘（CI / gate 用）
    python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --check

    # 搬完页面后一条命令收敛 + 门禁分类（运行报告落 .qwq_output，可删可重建）
    python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --with-gate

    # 把需人工裁决的 REVIEW 项也视为失败
    python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --check --fail-on-review

退出码：``0`` 无待处理 drift；``1`` 存在需人工裁决项；``2`` 工具/契约自身错误。
``--with-gate`` 只读消费门禁输出用于分类，退出码不受门禁影响，也绝不修改门禁。
"""
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_DIR_NAME = "quwoquan_app"
CONTRACT_REL = "quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml"

#: 搬迁流每 15~30 秒提交一次，重命名链可能跨多个提交，逐跳追到磁盘存在为止。
GIT_RENAME_MAX_HOPS = 8

#: 与 ``source_path`` 一样承载 App 相对路径、同样会被搬迁打断的装配证据字段。
EVIDENCE_FIELDS = ("route_registration_evidence", "mount_evidence")

#: 运行报告目录名；落在 `.qwq_output` 下，可删除可重建，不是第二套页面台账。
REPORT_DIR_NAME = "page-object-source-path"


# ---------------------------------------------------------------------------
# 结果模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourcePathFix:
    """一条已被唯一确定并修正的 App 相对路径。"""

    page_id: str
    field_name: str
    old_path: str
    new_path: str
    method: str


@dataclass(frozen=True)
class ManualDecision:
    """无法唯一确定、必须人工裁决的条目。"""

    page_id: str
    field_name: str
    old_path: str
    reason: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewFinding:
    """不阻断 source_path 收敛、但必须人工看见的伴生风险。"""

    kind: str
    page_id: str
    source_path: str
    detail: str


@dataclass
class SyncReport:
    total_pages: int = 0
    fixes: list[SourcePathFix] = field(default_factory=list)
    manual: list[ManualDecision] = field(default_factory=list)
    review: list[ReviewFinding] = field(default_factory=list)
    changed: bool = False

    @property
    def drift_total(self) -> int:
        return len(self.fixes) + len(self.manual)

    def as_json(self) -> dict:
        return {
            "totalPages": self.total_pages,
            "driftTotal": self.drift_total,
            "changed": self.changed,
            "fixes": [
                {
                    "pageId": item.page_id,
                    "field": item.field_name,
                    "oldPath": item.old_path,
                    "newPath": item.new_path,
                    "method": item.method,
                }
                for item in self.fixes
            ],
            "manual": [
                {
                    "pageId": item.page_id,
                    "field": item.field_name,
                    "oldPath": item.old_path,
                    "reason": item.reason,
                    "candidates": list(item.candidates),
                }
                for item in self.manual
            ],
            "review": [
                {
                    "kind": item.kind,
                    "pageId": item.page_id,
                    "sourcePath": item.source_path,
                    "detail": item.detail,
                }
                for item in self.review
            ],
        }


class ContractError(RuntimeError):
    """契约文件本身不可用（结构非法、页面块不可定位等）。"""


# ---------------------------------------------------------------------------
# 契约读取与逐行改写
# ---------------------------------------------------------------------------


def load_contract(contract_path: Path) -> tuple[dict, str]:
    text = contract_path.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ContractError(f"{contract_path}: YAML 根必须是 mapping")
    pages = document.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ContractError(f"{contract_path}: pages 必须是非空列表")
    return document, text


def contract_pages(document: dict) -> list[dict]:
    pages: list[dict] = []
    for index, page in enumerate(document["pages"]):
        if not isinstance(page, dict):
            raise ContractError(f"pages[{index}] 必须是 mapping")
        page_id = page.get("page_id")
        source_path = page.get("source_path")
        if not isinstance(page_id, str) or not page_id.strip():
            raise ContractError(f"pages[{index}]: page_id 缺失")
        if not isinstance(source_path, str) or not source_path.strip():
            raise ContractError(f"{page_id}: source_path 缺失")
        pages.append(page)
    return pages


def _page_block_range(lines: Sequence[str], page_id: str) -> tuple[int, int]:
    item_pattern = re.compile(rf"\s*-\s+page_id:\s*{re.escape(page_id)}\s*$")
    starts = [
        index
        for index, line in enumerate(lines)
        if item_pattern.fullmatch(line.rstrip("\n"))
    ]
    if len(starts) != 1:
        raise ContractError(f"{page_id}: 页面块定位不唯一（命中 {len(starts)} 次）")
    start = starts[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    for index in range(start + 1, len(lines)):
        stripped = lines[index].lstrip()
        if stripped.startswith("- ") and (len(lines[index]) - len(stripped)) <= indent:
            return start, index
    return start, len(lines)


def _field_region(
    lines: Sequence[str], start: int, end: int, page_id: str, field_name: str
) -> tuple[int, int]:
    """返回页面块内某字段自身及其续行（block list）的行区间。"""

    field_pattern = re.compile(rf"(\s*){re.escape(field_name)}:.*$")
    hits: list[int] = []
    for index in range(start, end):
        if field_pattern.fullmatch(lines[index].rstrip("\n")):
            hits.append(index)
    if len(hits) != 1:
        raise ContractError(
            f"{page_id}: 字段 {field_name} 定位不唯一（命中 {len(hits)} 次）"
        )
    field_line = hits[0]
    indent = len(lines[field_line]) - len(lines[field_line].lstrip())
    region_end = field_line + 1
    for index in range(field_line + 1, end):
        stripped = lines[index].strip()
        if not stripped:
            break
        if len(lines[index]) - len(lines[index].lstrip()) <= indent:
            break
        region_end = index + 1
    return field_line, region_end


def replace_page_path(
    text: str, page_id: str, field_name: str, old_path: str, new_path: str
) -> str:
    """只替换指定页面指定字段内那一处路径，不触碰任何其它字节。

    整文件 ``yaml.dump`` 会抹掉注释、flow-style 与空行，并把并发搬迁流的其它改动
    一起重排；这里坚持逐行外科手术，保证 diff 只有目标行。
    """

    lines = text.splitlines(keepends=True)
    start, end = _page_block_range(lines, page_id)
    field_start, field_end = _field_region(lines, start, end, page_id, field_name)
    token = re.compile(rf"(?<![\w./-]){re.escape(old_path)}(?![\w./-])")
    hits = [
        index
        for index in range(field_start, field_end)
        if token.search(lines[index])
    ]
    if len(hits) != 1 or len(token.findall(lines[hits[0]])) != 1:
        raise ContractError(
            f"{page_id}.{field_name}: 路径出现次数不唯一，放弃改写: {old_path}"
        )
    target = hits[0]
    lines[target] = token.sub(lambda _: new_path, lines[target], count=1)
    return "".join(lines)


def _atomic_write(target: Path, payload: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# 定位搬迁后的页面
# ---------------------------------------------------------------------------


def _run_git(repository_root: Path, arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout


def _rename_target_in_commit(
    repository_root: Path, commit: str, old_path: str
) -> str | None:
    """在单个提交的完整 diff 里找 ``old_path`` 的重命名落点。

    不能用 ``git log --diff-filter=R -- <old_path>``：pathspec 会把新路径从 diff
    中裁掉，重命名对就配不上，结果永远为空。必须先定位删除该路径的提交，再看那
    个提交的**全量** ``--name-status``。
    """

    shown = _run_git(
        repository_root,
        ["show", "-M", "--name-status", "--format=", commit],
    )
    for line in shown.splitlines():
        if not line.startswith("R"):
            continue
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        _, old, new = fields
        if old == old_path:
            return new
    return None


def git_rename_target(repository_root: Path, relative_from_root: str) -> str | None:
    """沿 git 重命名链正向追一个已消失的路径，返回磁盘上存在的落点。

    链上任一跳落地即返回；追不到磁盘存在的文件则返回 ``None``，把决定权交回
    文件名匹配或人工裁决，绝不返回猜测值。
    """

    current = relative_from_root
    visited = {current}
    for _ in range(GIT_RENAME_MAX_HOPS):
        commit = _run_git(
            repository_root,
            ["log", "--diff-filter=D", "--format=%H", "-1", "--", current],
        ).strip()
        if not commit:
            return None
        target = _rename_target_in_commit(repository_root, commit, current)
        if target is None or target in visited:
            return None
        visited.add(target)
        current = target
        if (repository_root / current).is_file():
            return current
    return None


def _dart_library_text(source: Path) -> str:
    text = source.read_text(encoding="utf-8", errors="ignore")
    chunks = [text]
    for match in re.finditer(r"^\s*part\s+['\"]([^'\"]+)['\"]\s*;", text, re.MULTILINE):
        part = (source.parent / match.group(1)).resolve()
        if part.is_file():
            chunks.append(part.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def defines_entry_widget(source: Path, entry_widget: str) -> bool:
    pattern = re.compile(rf"\bclass\s+{re.escape(entry_widget)}\b")
    return bool(pattern.search(_dart_library_text(source)))


def lib_basename_candidates(app_root: Path, source_path: str) -> list[str]:
    """按文件名在 ``lib/**`` 全树收集候选，返回 App 相对路径。"""

    lib_root = app_root / "lib"
    if not lib_root.is_dir():
        return []
    basename = Path(source_path).name
    return sorted(
        candidate.relative_to(app_root).as_posix()
        for candidate in lib_root.rglob(basename)
        if candidate.is_file()
    )


def references_widget(source: Path, entry_widget: str) -> bool:
    pattern = re.compile(rf"\b{re.escape(entry_widget)}\b")
    return bool(pattern.search(source.read_text(encoding="utf-8", errors="ignore")))


def resolve_moved_path(
    repository_root: Path,
    app_root: Path,
    *,
    page_id: str,
    field_name: str,
    old_path: str,
    entry_widget: str,
    widget_predicate: Callable[[Path, str], bool],
    excluded_paths: frozenset[str],
    missing_reason: str,
) -> SourcePathFix | ManualDecision:
    """定位一个已失效路径的新位置；不唯一即返回人工裁决项，绝不猜测。

    ``git`` 重命名链是最权威证据；其次是 ``lib/**`` 内同名文件唯一匹配。
    ``entry_widget`` 只用来收窄候选（页面必须**定义**它，装配证据必须**引用**它），
    不用来放宽任何判定。
    """

    candidates = [
        candidate
        for candidate in lib_basename_candidates(app_root, old_path)
        if candidate not in excluded_paths
    ]

    rename_target = git_rename_target(repository_root, f"{APP_DIR_NAME}/{old_path}")
    rename_candidate: str | None = None
    if rename_target and rename_target.startswith(f"{APP_DIR_NAME}/lib/"):
        relative = rename_target[len(APP_DIR_NAME) + 1 :]
        if relative not in excluded_paths:
            rename_candidate = relative

    if entry_widget:
        matched = [
            candidate
            for candidate in candidates
            if widget_predicate(app_root / candidate, entry_widget)
        ]
        if matched:
            candidates = matched
        elif candidates:
            return ManualDecision(
                page_id=page_id,
                field_name=field_name,
                old_path=old_path,
                reason=(
                    f"同名候选均与 entry_widget {entry_widget} 无关，"
                    "文件可能已被拆分或改名，需人工裁决"
                ),
                candidates=tuple(candidates),
            )

    if rename_candidate and rename_candidate in candidates:
        return SourcePathFix(
            page_id=page_id,
            field_name=field_name,
            old_path=old_path,
            new_path=rename_candidate,
            method="git_rename",
        )
    if len(candidates) == 1:
        return SourcePathFix(
            page_id=page_id,
            field_name=field_name,
            old_path=old_path,
            new_path=candidates[0],
            method="lib_basename_unique",
        )
    if not candidates:
        return ManualDecision(
            page_id=page_id,
            field_name=field_name,
            old_path=old_path,
            reason=missing_reason,
        )
    return ManualDecision(
        page_id=page_id,
        field_name=field_name,
        old_path=old_path,
        reason="lib/** 下存在多个同名候选且 git 重命名链无法唯一定位，需人工裁决",
        candidates=tuple(candidates),
    )


# ---------------------------------------------------------------------------
# 伴生风险校验
# ---------------------------------------------------------------------------


def _looks_like_object_presentation(path_parts: tuple[str, ...]) -> bool:
    if len(path_parts) < 6 or path_parts[0] != "lib":
        return False
    if path_parts[4] == "presentation":
        return True
    return (
        len(path_parts) >= 7
        and path_parts[1] == "service"
        and path_parts[5] == "presentation"
    )


def multi_object_presentation_findings(
    pages: Sequence[dict],
    shape_of: Callable[[str], tuple[str, str, str, str] | None],
) -> list[ReviewFinding]:
    """只报告无法证明 physical owner 的多 participant 页面。

    ``object_ids`` 表达页面参与对象集合，不代表每个 participant 都要拥有一份
    ``presentation``。页面位于 canonical
    ``lib/<domain>/<context>/<object>/presentation/**``，且由对象 roster 派生出的
    physical owner 已在 ``object_ids`` 中时，单一 presentation 正是合法形状。

    只有 physical owner 缺席、canonical 路径无法反推，或 participant 集合本身
    含空值/重复值时才保留 REVIEW。非对象化的 runtime/design-system shell 不在本
    检查职责内；伪装成对象 presentation 的 shell 路径会因无法命中 roster 而阻断。
    """

    findings: list[ReviewFinding] = []
    for page in pages:
        object_ids = page.get("object_ids")
        if not isinstance(object_ids, list) or len(object_ids) < 2:
            continue
        source_path = str(page["source_path"]).strip()
        path_parts = Path(source_path).parts
        looks_like_object_presentation = _looks_like_object_presentation(path_parts)
        shape = shape_of(source_path)
        if shape is None and not looks_like_object_presentation:
            continue

        normalized_object_ids = tuple(
            str(item).strip() for item in object_ids if isinstance(item, str)
        )
        participant_set_is_valid = (
            len(normalized_object_ids) == len(object_ids)
            and all(normalized_object_ids)
            and len(set(normalized_object_ids)) == len(normalized_object_ids)
        )

        physical_owner: str | None = None
        reason: str
        if shape is None:
            reason = (
                "source_path 看似单对象 presentation，但无法从 ContractGraph roster "
                "反推 physical owner；可能是 ownerless 路径或 shell 伪装"
            )
        else:
            domain, context, object_name, layer = shape
            physical_owner = f"{domain}.{object_name}"
            if layer != "presentation" or not looks_like_object_presentation:
                reason = (
                    "source_path 与派生层不一致，不能证明 canonical 单对象 "
                    f"presentation（派生 {domain}.{context}.{object_name}/{layer}）"
                )
            elif not participant_set_is_valid:
                reason = "object_ids 含空值、非字符串或重复 participant，集合发生漂移"
            elif physical_owner not in normalized_object_ids:
                reason = (
                    f"派生 physical owner {physical_owner} 未出现在 object_ids，"
                    "页面参与集合与物理归属漂移"
                )
            else:
                continue

        findings.append(
            ReviewFinding(
                kind="multi_object_single_presentation",
                page_id=str(page["page_id"]).strip(),
                source_path=source_path,
                detail=(
                    f"声明 {len(object_ids)} 个 object_ids "
                    f"({', '.join(str(item) for item in object_ids)}) "
                    f"但{reason}；需人工修正 owner/participant 契约，不能靠多对象页面"
                    "计数消失视为闭合"
                ),
            )
        )
    return findings


def page_scan_set_findings(
    pages: Sequence[dict],
    disk_scan_paths: frozenset[str] | None,
) -> list[ReviewFinding]:
    """``source_path`` 已修正但不在页面扫描集内时如实报告。

    ``verify_page_object_contract.py`` 用 ``matrix_disk_scan_paths`` 判定「磁盘页面
    必须由 metadata 唯一拥有」，而该扫描集只认 ``lib/ui``、``lib/components``、
    ``lib/app/shell``。搬进对象树的页面既不在扫描集里，也就无法被门禁认账。
    本工具不改门禁，只保证这条缺口不会无声存在。
    """

    if disk_scan_paths is None:
        return []
    findings: list[ReviewFinding] = []
    for page in pages:
        source_path = str(page["source_path"]).strip()
        if source_path in disk_scan_paths:
            continue
        findings.append(
            ReviewFinding(
                kind="outside_page_scan_set",
                page_id=str(page["page_id"]).strip(),
                source_path=source_path,
                detail=(
                    "已搬出 page_disk_scan_paths.matrix_disk_scan_paths 的扫描范围，"
                    "verify_page_object_contract 会报「canonical source 不在页面扫描集」；"
                    "需要页面质量门禁 owner 扩展扫描规则，本工具不改门禁"
                ),
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


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
            multi_object_presentation_findings(effective_pages, shape_of)
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


@contextmanager
def _importable(directory: Path):
    """临时把目录挂进 ``sys.path`` 做只读 import，且不在源码树留 ``__pycache__``。

    仓库禁止源码树出现 ``__pycache__``；本工具会被反复执行，绝不能顺手污染
    ``quwoquan_ops/gate`` 或 ``quwoquan_app/scripts/runtime``。
    """

    previous_bytecode_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(directory))
    try:
        yield
    finally:
        if sys.path and sys.path[0] == str(directory):
            sys.path.pop(0)
        sys.dont_write_bytecode = previous_bytecode_flag


def _load_shape_resolver(repository_root: Path) -> Callable[[str], tuple[str, str, str, str] | None]:
    """只读复用 ``object_path_map`` 的对象身份派生，不复制别名规则。"""

    with _importable(repository_root / "quwoquan_ops" / "gate"):
        import object_path_map  # type: ignore

    graph_path = repository_root / object_path_map.CONTRACT_GRAPH_PATH
    roster = object_path_map.ObjectRoster(json.loads(graph_path.read_bytes()))

    def shape_of(source_path: str) -> tuple[str, str, str, str] | None:
        parts = Path(source_path).parts
        if not parts or parts[0] != "lib":
            return None
        return object_path_map.derive_app_target_shape_identity(parts[1:], roster)

    return shape_of


def _load_disk_scan_paths(repository_root: Path) -> frozenset[str]:
    with _importable(repository_root / APP_DIR_NAME / "scripts" / "runtime" / "page"):
        import page_disk_scan_paths  # type: ignore
    return page_disk_scan_paths.matrix_disk_scan_paths(repository_root)


def _default_report_dir(repository_root: Path) -> Path:
    """复用 Ops 的唯一输出根契约，不在本工具复制 ``.qwq_output`` 布局规则。"""

    with _importable(repository_root):
        from quwoquan_ops.cli.lib.output_paths import repo_runs_root  # type: ignore
    return repo_runs_root() / REPORT_DIR_NAME


# ---------------------------------------------------------------------------
# 门禁失败分类（只读消费门禁输出，不改门禁）
# ---------------------------------------------------------------------------

#: 门禁失败按「谁能修」分类，避免每轮人工重读一遍 flat 列表。
GATE_FAILURE_CLASSES: tuple[tuple[str, str, str], ...] = (
    (
        "page_scan_set_gap",
        r"不在页面扫描集|磁盘页面未登记",
        "页面已在对象树目标位置，但 page_disk_scan_paths 的扫描规则尚未跟随；"
        "属页面质量门禁 owner，不能靠改契约绕过",
    ),
    (
        "contract_path_drift",
        r"source_path 不存在|evidence 不存在|Dart part 不存在",
        "契约路径尚未同步；重跑本工具即可收敛",
    ),
    (
        "contract_reference_drift",
        r"typed_presentation .*不存在|object_id 无 object.yaml 定义"
        r"|Query Slice 引用不存在|route_id 引用不存在|surface 引用不存在"
        r"|capability 未在 PlatformCapabilities 定义",
        "契约引用的类型/对象/路由已被端云改名或删除；需按实际实现裁决后改契约",
    ),
    (
        "owner_or_object_missing",
        r"experience_owner .*佐证|data_owner .*佐证|未列入 data_owners"
        r"|experience_owner 必填|data_owners 必须",
        "页面缺 owner 或对象归属佐证；需业务裁决后补契约",
    ),
    (
        "assembly_evidence_broken",
        r"未装配 entry_widget|未消费 entry_widget|未注册 route"
        r"|没有对应 Surface 覆盖|未定义 entry_widget",
        "页面装配点已改动但契约声明的 entry_widget/route 装配不再成立；"
        "需对应 domain 流确认落位后再同步契约",
    ),
)


def classify_gate_failures(output: str) -> dict[str, list[str]]:
    classified: dict[str, list[str]] = {}
    for line in output.splitlines():
        message = line.strip()
        if not message.startswith("- "):
            continue
        message = message[2:].strip()
        bucket = "unclassified"
        for name, pattern, _ in GATE_FAILURE_CLASSES:
            if re.search(pattern, message):
                bucket = name
                break
        classified.setdefault(bucket, []).append(message)
    return classified


def run_page_quality_gates(repository_root: Path) -> dict:
    """只读跑页面横向质量门禁并分类失败，不修改门禁脚本。"""

    runtime = repository_root / APP_DIR_NAME / "scripts" / "runtime" / "page"
    results: list[dict] = []
    for script, extra in (
        ("verify_page_object_contract.py", ()),
        ("verify_page_abc_governance.py", ("--quiet",)),
    ):
        completed = subprocess.run(
            [sys.executable, str(runtime / script), *extra],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = completed.stdout + completed.stderr
        results.append(
            {
                "script": script,
                "exitCode": completed.returncode,
                "output": output.strip(),
                "failuresByClass": classify_gate_failures(output),
            }
        )
    return {
        "classes": {
            name: description for name, _, description in GATE_FAILURE_CLASSES
        },
        "gates": results,
    }


def render_report(report: SyncReport, *, write: bool) -> str:
    lines = [
        "[page-object-source-path] "
        f"pages={report.total_pages} drift={report.drift_total} "
        f"fixed={len(report.fixes)} manual={len(report.manual)} "
        f"review={len(report.review)} written={'yes' if report.changed else 'no'}"
    ]
    for fix in report.fixes:
        verb = "FIXED" if write else "WOULD-FIX"
        lines.append(f"  {verb} {fix.page_id}.{fix.field_name} [{fix.method}]")
        lines.append(f"        {fix.old_path}")
        lines.append(f"     -> {fix.new_path}")
    for item in report.manual:
        lines.append(f"  MANUAL {item.page_id}.{item.field_name}")
        lines.append(f"        {item.field_name}={item.old_path}")
        lines.append(f"        {item.reason}")
        for candidate in item.candidates:
            lines.append(f"        candidate: {candidate}")
    for item in report.review:
        lines.append(f"  REVIEW [{item.kind}] {item.page_id}")
        lines.append(f"        source_path={item.source_path}")
        lines.append(f"        {item.detail}")
    return "\n".join(lines)


def render_markdown_report(payload: dict) -> str:
    lines = [
        "# page_object_contract 路径同步运行报告",
        "",
        "一次性运行输出，可删除可重建；页面集合真相仍是磁盘扫描与 "
        "`page_object_contract.yaml`，本文件不是台账。",
        "",
        f"- 扫描时点：`{payload['scanAt']}`",
        f"- HEAD：`{payload['headCommit']}`",
        f"- 契约登记页面：{payload['sync']['totalPages']}",
        f"- 本轮 drift：{payload['sync']['driftTotal']}"
        f"（已修 {len(payload['sync']['fixes'])}，"
        f"待人工裁决 {len(payload['sync']['manual'])}）",
        f"- 契约是否被写入：{'是' if payload['sync']['changed'] else '否'}",
        "",
    ]
    if payload["sync"]["fixes"]:
        lines += ["## 已同步", ""]
        for item in payload["sync"]["fixes"]:
            lines.append(
                f"- `{item['pageId']}`.{item['field']} [{item['method']}]："
                f"`{item['oldPath']}` -> `{item['newPath']}`"
            )
        lines.append("")
    if payload["sync"]["manual"]:
        lines += ["## 需人工裁决（无法唯一定位）", ""]
        for item in payload["sync"]["manual"]:
            lines.append(f"- `{item['pageId']}`.{item['field']}：{item['reason']}")
            for candidate in item["candidates"]:
                lines.append(f"  - 候选：`{candidate}`")
        lines.append("")
    if payload["sync"]["review"]:
        lines += ["## 需人工裁决（伴生风险）", ""]
        for item in payload["sync"]["review"]:
            lines.append(
                f"- [{item['kind']}] `{item['pageId']}`（`{item['sourcePath']}`）："
                f"{item['detail']}"
            )
        lines.append("")
    gate = payload.get("gate")
    if gate:
        lines += ["## 页面横向质量门禁", ""]
        for entry in gate["gates"]:
            lines.append(f"### `{entry['script']}` exit={entry['exitCode']}")
            lines.append("")
            for bucket, messages in sorted(entry["failuresByClass"].items()):
                lines.append(
                    f"- **{bucket}**（{gate['classes'].get(bucket, '未归类')}）："
                    f"{len(messages)} 条"
                )
                for message in messages:
                    lines.append(f"  - {message}")
            if not entry["failuresByClass"]:
                lines.append("- 无失败项")
            lines.append("")
    return "\n".join(lines) + "\n"


def write_run_report(report_dir: Path, payload: dict) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (report_dir / "report.md").write_text(
        render_markdown_report(payload), encoding="utf-8"
    )
    return report_dir


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="同步 page_object_contract.yaml 的 source_path 到磁盘真相"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检测不写入；存在 drift 即失败",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="把 REVIEW（多对象页面落单对象 presentation、页面扫描集缺口）也视为失败",
    )
    parser.add_argument("--json", action="store_true", help="额外输出机器可读报告")
    parser.add_argument(
        "--with-gate",
        action="store_true",
        help="同步后顺带只读跑页面横向质量门禁并按「谁能修」分类失败",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="运行报告目录（默认 .qwq_output/env/repo/runs/page-object-source-path）",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="不落运行报告（默认落 .qwq_output 下的一次性可重建报告）",
    )
    parser.add_argument(
        "--repository-root",
        default=None,
        help="覆盖仓库根（测试与工具链自检用）",
    )
    arguments = parser.parse_args(argv)

    repository_root = (
        Path(arguments.repository_root).resolve()
        if arguments.repository_root
        else REPOSITORY_ROOT
    )

    try:
        report = sync(
            repository_root,
            write=not arguments.check,
            shape_of=_load_shape_resolver(repository_root),
            disk_scan_paths=_load_disk_scan_paths(repository_root),
        )
    except (ContractError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"[page-object-source-path] BLOCK: {error}", file=sys.stderr)
        return 2

    print(render_report(report, write=not arguments.check))
    if arguments.json:
        print(json.dumps(report.as_json(), ensure_ascii=False, indent=2, sort_keys=True))

    payload = {
        "schema": "page-object-source-path-sync-run",
        "scanAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headCommit": _run_git(repository_root, ["rev-parse", "HEAD"]).strip()
        or "unknown",
        "mode": "check" if arguments.check else "write",
        "sync": report.as_json(),
    }
    if arguments.with_gate:
        payload["gate"] = run_page_quality_gates(repository_root)
        for entry in payload["gate"]["gates"]:
            print(f"[page-quality-gate] {entry['script']} exit={entry['exitCode']}")
            for bucket, messages in sorted(entry["failuresByClass"].items()):
                print(f"  {bucket}: {len(messages)}")
                for message in messages:
                    print(f"    - {message}")
    if not arguments.no_report:
        report_dir = (
            Path(arguments.report_dir).resolve()
            if arguments.report_dir
            else _default_report_dir(repository_root)
        )
        write_run_report(report_dir, payload)
        print(f"[page-object-source-path] report -> {report_dir}")

    if report.manual:
        return 1
    if arguments.check and report.fixes:
        return 1
    if arguments.fail_on_review and report.review:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
