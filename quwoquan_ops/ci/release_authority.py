#!/usr/bin/env python3
"""人工发布权威事实的 canonical 生产者：初始 release train 激活授权与 RC 选择。

两者都是"人做出的决定"的 create-once 记录，不推导、不解释：谁（GitHub login，经 `gh api user`
读回）、何时、针对哪个精确对象（版本 / tag / peeled commit / tree / manifest digest）。
它们随后由 `release_tag_admission.py` 校验（schema / status / purpose / 精确绑定），本模块不改动
校验语义，只补上此前缺失的生产者。
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.promotion_evidence import (
    PromotionEvidenceError,
    _sha,
    _text,
    _timestamp,
    _write_once,
    digest,
)

INITIAL_AUTHORITY_SCHEMA = "quwoquan_ops.initial_release_authority_fact.v1"
INITIAL_AUTHORITY_PURPOSE = "activate_initial_product_release_train"
RC_SELECTION_SCHEMA = "quwoquan_ops.release_candidate_selection_fact.v1"
_SEMVER_CORE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_RC_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-rc\.([1-9][0-9]*)$")
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def _login(value: object, field: str) -> str:
    text = _text(value, field)
    if _LOGIN.fullmatch(text) is None:
        raise PromotionEvidenceError("RELEASE_AUTHORITY.INVALID", f"{field} must be a GitHub login")
    return text


def _repository(value: object) -> str:
    text = _text(value, "repository")
    if text.count("/") != 1 or text != text.lower():
        raise PromotionEvidenceError("RELEASE_AUTHORITY.INVALID", "repository must be lowercase owner/name")
    return text


def create_initial_release_authority(
    *, store_root: Path, repository: str, target_version: str, approver_login: str,
    approved_at: str, basis: str, readback: Mapping[str, Any],
) -> Path:
    """首个 release train 的激活授权；`readback` 是 `gh api user` 的精确回读，证明审批人就是当前操作者。"""
    root = store_root.resolve()
    version = _text(target_version, "targetVersion")
    if _SEMVER_CORE.fullmatch(version) is None:
        raise PromotionEvidenceError("RELEASE_AUTHORITY.INVALID", "targetVersion must be strict SemVer core")
    approver = _login(approver_login, "approverLogin")
    if not isinstance(readback, Mapping) or readback.get("login") != approver or not isinstance(readback.get("id"), int):
        raise PromotionEvidenceError("RELEASE_AUTHORITY.INVALID", "approver readback does not bind the approver login")
    body: dict[str, Any] = {
        "schema": INITIAL_AUTHORITY_SCHEMA, "status": "approved", "purpose": INITIAL_AUTHORITY_PURPOSE,
        "repository": _repository(repository), "targetVersion": version,
        "approver": {"login": approver, "id": int(readback["id"]), "source": "github_rest:/user"},
        "approvedAt": _timestamp(approved_at, "approvedAt")[0], "basis": _text(basis, "basis"),
        "recordedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    body["authorityId"] = digest(body)
    return _write_once(root / "release-train" / "initial-release-authority" / f"{body['authorityId']}.json", body)


def create_release_candidate_selection(
    *, store_root: Path, repository_root: Path, repository: str, tag_name: str, source_git_sha: str,
    product_version_manifest: Path, selector_login: str, selected_at: str, readback: Mapping[str, Any],
) -> Path:
    """产品方选择"对这个 main-reachable commit 打这个 RC 标签"的 create-once 记录。"""
    root = store_root.resolve()
    tag = _text(tag_name, "tagName")
    if _RC_TAG.fullmatch(tag) is None:
        raise PromotionEvidenceError("RELEASE_AUTHORITY.INVALID", "tagName must be vMAJOR.MINOR.PATCH-rc.N")
    commit = _sha(source_git_sha, "sourceGitSha")
    repo = repository_root.resolve()
    tree = subprocess.run(["git", "show", "-s", "--format=%T", commit], cwd=repo, text=True, capture_output=True, check=False)
    if tree.returncode != 0:
        raise PromotionEvidenceError("RELEASE_AUTHORITY.INVALID", "sourceGitSha is not a commit in this repository")
    reachable = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "refs/remotes/origin/main"], cwd=repo, check=False)
    if reachable.returncode != 0:
        raise PromotionEvidenceError("RELEASE_AUTHORITY.SOURCE_NOT_MAIN_REACHABLE", "sourceGitSha is not reachable from origin/main")
    manifest = product_version_manifest.resolve()
    if not manifest.is_file() or manifest.is_symlink():
        raise PromotionEvidenceError("RELEASE_AUTHORITY.INVALID", "product version manifest is missing")
    selector = _login(selector_login, "selectorLogin")
    if not isinstance(readback, Mapping) or readback.get("login") != selector or not isinstance(readback.get("id"), int):
        raise PromotionEvidenceError("RELEASE_AUTHORITY.INVALID", "selector readback does not bind the selector login")
    body: dict[str, Any] = {
        "schema": RC_SELECTION_SCHEMA, "status": "approved", "repository": _repository(repository),
        "tagKind": "rc", "tagName": tag, "sourceGitSha": commit, "sourceTree": _sha(tree.stdout.strip(), "sourceTree"),
        "productVersionManifestDigest": digest(manifest),
        "selector": {"login": selector, "id": int(readback["id"]), "source": "github_rest:/user"},
        "selectedAt": _timestamp(selected_at, "selectedAt")[0],
        "recordedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    body["selectionId"] = digest(body)
    return _write_once(root / "release-train" / "rc-selections" / tag / f"{body['selectionId']}.json", body)
