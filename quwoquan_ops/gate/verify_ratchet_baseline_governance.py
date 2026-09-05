#!/usr/bin/env python3
"""棘轮基线的治理留痕门禁。

棘轮基线是「债只减不增」的唯一凭据，而它最容易被绕开的方式不是把数字调大——那
太显眼——而是**悄悄换度量口径再重建基线**。换口径之后新旧数字不可比，漂移被重新
归零，门禁全程显示绿色。仓库里已经发生过两次：

- assistant 弱类型棘轮在旧口径下漂移到 292/522，CI 全程没拦；
- `ui_map_literal_budget` 的旧口径只扫 `lib/ui`，该目录随 UI 迁走后计数静默归零，
  预算 4 长期假绿。

因此每个基线都必须声明：

- `owner`：谁负责把它降到零；
- `reason`：为什么这笔债被允许暂存；
- `expires_when`：什么条件下删除这个文件；
- `measure`：当前度量口径，必须具体到扫描范围与判定规则，能据此复算。

并且 `measure` 一旦相对 HEAD 发生变化，同一次提交必须写下 `superseded_measure`，
说明旧口径是什么、为什么换、以及**旧口径下的实测值**。没有这句话，换口径就等于
无痕销账。

治理留痕齐备并不等于债务在下降，所以本门禁还直接比对 HEAD：**债务计数型基线的
任何条目变大、或出现新条目，一律失败。** 只有这一条是机械判定的，写得再完整的
`reason` 也不能替代它。

「债务计数型」按键的形状识别：顶层键是文件路径（含 `/`）时，值里的整数是违规处数，
只能减少；键是场景名的耗时预算不在其列——预算随机器和产品形态变化，它的正当性由
`superseded_measure` 承载，不该被当成债务。

spec_ref: specs/feature-tree/runtime/runtime-client-foundation/spec.md#sit-001
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#req-004
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]

#: 棘轮基线的物理位置。新增基线必须落在这里，否则不受治理约束。
BASELINE_PATHS = (
    "quwoquan_ops/policies/gates",
    "quwoquan_ops/policies/baselines",
    "quwoquan_app/scripts/runtime/page",
    "quwoquan_app/scripts/runtime/observability",
    "quwoquan_service/scripts/verify/structure",
    "quwoquan_ops/environments",
)
BASELINE_SUFFIXES = {".json", ".yaml", ".yml"}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

#: 棘轮基线的命名标记。按名字而不是按豁免名单识别，是为了让新增的基线自动落入
#: 治理范围：漏登记一个豁免只会放过一个文件，而漏更新一份「纳入名单」会放过全部
#: 新增基线。清单、manifest、策略声明这类不承载可增长计数的文件天然不匹配。
RATCHET_NAME_MARKERS = ("baseline", "budget", "allowlist", "ratchet")

#: 名字带标记、但只声明架构策略而不承载任何计数的文件。
NON_RATCHET_POLICIES = frozenset(
    {
        "cloud_runtime_single_path_policy.json",
    }
)

REQUIRED_FIELDS = ("owner", "reason", "expires_when", "measure")

#: 不对应任何规格节点的横向治理职能。
#:
#: 有些债确实归属职能而不是产品能力（门禁耗时、仓库结构、契约治理），强行塞进某个
#: 产品节点只会造成错误归属。但白名单必须是封闭的：`owner` 曾经写着
#: `cross-domain-architecture`，那个名字在规格树和这里都不存在，等于字段填了却无人
#: 负责 —— 治理留痕最容易被架空的方式，就是写一个看起来像 owner 的字符串。
GOVERNANCE_FUNCTIONS = frozenset(
    {
        "cloud-contract-governance",
        "delivery-gate",
        "feature-tree-governance",
        "repository-architecture",
    }
)


def known_owners() -> frozenset[str]:
    """规格树里的真实节点名，并上横向治理职能。"""
    tree = ROOT / "specs" / "feature-tree"
    nodes = {path.name for path in tree.rglob("*") if path.is_dir()} if tree.is_dir() else set()
    return frozenset(nodes | GOVERNANCE_FUNCTIONS)


def _is_ratchet(relative: str) -> bool:
    name = Path(relative).name
    return (
        Path(relative).suffix in BASELINE_SUFFIXES
        and name not in NON_RATCHET_POLICIES
        and any(marker in name for marker in RATCHET_NAME_MARKERS)
    )


def baseline_files(*, sha: str | None = None) -> list[Path]:
    """Discover candidate or exact-tree baselines recursively."""
    relative_paths: set[str] = set()
    for relative in BASELINE_PATHS:
        if sha is not None:
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", "-z", sha, "--", relative],
                cwd=ROOT, capture_output=True, check=False,
            )
            if result.returncode != 0:
                raise ValueError(result.stderr.decode("utf-8", "replace").strip() or "git ls-tree failed")
            relative_paths.update(
                item.decode("utf-8", "replace")
                for item in result.stdout.split(b"\0")
                if item and _is_ratchet(item.decode("utf-8", "replace"))
            )
            continue
        directory = ROOT / relative
        if directory.is_dir():
            relative_paths.update(
                path.relative_to(ROOT).as_posix()
                for path in directory.rglob("*")
                if path.is_file() and _is_ratchet(path.relative_to(ROOT).as_posix())
            )
    return [ROOT / relative for relative in sorted(relative_paths)]


def governance_block(path: Path) -> dict[str, str]:
    """抽出治理块。

    JSON 用 `_governance`，YAML 用顶层 `governance:`。这里刻意不引入 YAML 解析器：
    只认这两种固定形状，能让「治理块长什么样」本身无法被悄悄改写。
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        document = json.loads(text)
        block = document.get("_governance")
        return block if isinstance(block, dict) else {}

    fields: dict[str, str] = {}
    inside = False
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("governance:"):
            inside = True
            continue
        if inside and line and not line.startswith((" ", "\t")):
            break
        if not inside:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("  ") and not line.startswith("    ") and ":" in stripped:
            key, _, value = stripped.partition(":")
            current = key.strip()
            fields[current] = value.strip()
        elif current:
            fields[current] = f"{fields[current]} {stripped}".strip()
    return fields


def revision(relative: str, sha: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{sha}:{relative}"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return result.stdout if result.returncode == 0 else None


def head_revision(relative: str) -> str | None:
    return revision(relative, "HEAD")


def _base_revision(relative: str, sha: str) -> str | None:
    # Preserve the dirty-worktree seam used by local contract fixtures.
    return head_revision(relative) if sha == "HEAD" else revision(relative, sha)


def _load_document(body: str, suffix: str) -> object:
    return json.loads(body) if suffix == ".json" else yaml.safe_load(body)


def debt_entries(document: object) -> dict[str, int]:
    """Flatten known debt identities from JSON/YAML without a second schema registry."""
    entries: dict[str, int] = {}

    if (
        isinstance(document, dict)
        and document.get("schema") == "single-track-exact-fingerprint-baseline"
    ):
        paths = document.get("paths")
        if isinstance(paths, dict):
            for path, item in paths.items():
                if not isinstance(path, str) or not isinstance(item, dict):
                    continue
                fingerprints = item.get("fingerprints")
                if isinstance(fingerprints, dict):
                    for fingerprint, count in fingerprints.items():
                        if isinstance(fingerprint, str) and isinstance(count, int) and not isinstance(count, bool):
                            entries[f"{path}::{fingerprint}"] = count
        return entries

    def visit(value: object, context: tuple[str, ...] = ()) -> None:
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                spec = item.get("spec")
                identity: str | None = None
                if isinstance(path, str) and "/" in path:
                    identity = path
                elif isinstance(spec, str) and "/" in spec:
                    anchor = item.get("anchor") or item.get("open_id") or item.get("id")
                    identity = f"{spec}::{anchor}" if isinstance(anchor, str) and anchor else spec
                if identity is not None:
                    discriminator = item.get("fingerprint") or item.get("id")
                    if isinstance(discriminator, str) and discriminator and discriminator not in identity:
                        identity = f"{identity}::{discriminator}"
                    measured = False
                    for measure in ("max_lines", "count"):
                        count = item.get(measure)
                        if isinstance(count, int) and not isinstance(count, bool):
                            entries[f"{'/'.join(context)}::{identity}::{measure}"] = count
                            measured = True
                    if not measured:
                        entries[f"{'/'.join(context)}::{identity}"] = 1
                visit(item, context)
            return
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            if key in {"_governance", "governance"}:
                continue
            if isinstance(key, str) and "/" in key:
                if isinstance(child, int) and not isinstance(child, bool):
                    entries[f"{'/'.join(context)}::{key}" if context else key] = child
                elif isinstance(child, dict):
                    for identity, count in child.items():
                        if isinstance(count, int) and not isinstance(count, bool):
                            entries[f"{'/'.join(context)}::{key}::{identity}" if context else f"{key}::{identity}"] = count
            if isinstance(child, (dict, list)):
                visit(child, (*context, str(key)))

    visit(document)
    return entries


def debt_growth(path: Path, relative: str, *, base_sha: str = "HEAD", candidate_body: str | None = None) -> list[str]:
    """Compare one candidate baseline to an exact base revision."""
    body = _base_revision(relative, base_sha)
    if body is None:
        return []
    try:
        before = debt_entries(_load_document(body, path.suffix))
        after_body = path.read_text(encoding="utf-8") if candidate_body is None else candidate_body
        after = debt_entries(_load_document(after_body, path.suffix))
    except (json.JSONDecodeError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"{relative}: baseline 无法解析（{error}）") from error
    if not before and not after:
        return []
    growth: list[str] = []
    for identity in sorted(after):
        was = before.get(identity, 0)
        if after[identity] > was:
            growth.append(f"{identity}: {was} -> {after[identity]}")
    return growth


def measure_of_revision(path: Path, relative: str, sha: str = "HEAD") -> str | None:
    """Read the governance measure from an exact revision."""
    body = _base_revision(relative, sha)
    if body is None:
        return None
    # 进程唯一命名：并发 gate 进程处理同名 baseline 时禁止共享 scratch 文件互删。
    scratch = (
        ROOT
        / ".qwq_output/env/repo/local/ratchet-governance"
        / f"{os.getpid()}-{uuid.uuid4().hex[:8]}-{path.name}"
    )
    scratch.parent.mkdir(parents=True, exist_ok=True)
    scratch.write_text(body, encoding="utf-8")
    try:
        return governance_block(scratch).get("measure")
    except (json.JSONDecodeError, UnicodeError):
        return None
    finally:
        scratch.unlink(missing_ok=True)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha")
    parser.add_argument("--head-sha")
    args = parser.parse_args(argv)
    if (args.base_sha is None) != (args.head_sha is None):
        parser.error("--base-sha 与 --head-sha 必须成对提供")
    for label in ("base_sha", "head_sha"):
        value = getattr(args, label)
        if value is not None and not _SHA_RE.fullmatch(value):
            parser.error(f"--{label.replace('_', '-')} 必须为 lowercase exact SHA")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args([] if argv is None else argv)
    except SystemExit as error:
        return int(error.code or 0)
    failures: list[str] = []
    checked = 0
    owners = known_owners()
    base_sha = args.base_sha or "HEAD"
    candidate_sha = args.head_sha
    try:
        candidate_files = baseline_files(sha=candidate_sha) if candidate_sha else baseline_files()
        base_files = baseline_files(sha=base_sha) if candidate_sha else candidate_files
    except ValueError as error:
        print(f"[ratchet-baseline-governance] GATE_BLOCK: {error}")
        return 2
    relatives = sorted(
        {path.relative_to(ROOT).as_posix() for path in candidate_files}
        | {path.relative_to(ROOT).as_posix() for path in base_files}
    )
    for relative in relatives:
        path = ROOT / relative
        candidate_body = revision(relative, candidate_sha) if candidate_sha else (
            path.read_text(encoding="utf-8") if path.is_file() else None
        )
        base_body = _base_revision(relative, base_sha)
        if candidate_body is None:
            if base_body is not None:
                try:
                    has_debt = bool(debt_entries(_load_document(base_body, path.suffix)))
                except (json.JSONDecodeError, UnicodeError, yaml.YAMLError) as error:
                    failures.append(f"{relative}: base baseline 无法解析（{error}）")
                    continue
                if has_debt:
                    failures.append(f"{relative}: 仍含债务的 baseline 不得删除")
            continue
        checked += 1
        scratch = (
            ROOT / ".qwq_output/env/repo/local/ratchet-governance"
            / f"{os.getpid()}-{uuid.uuid4().hex[:8]}-{path.name}"
        )
        scratch.parent.mkdir(parents=True, exist_ok=True)
        scratch.write_text(candidate_body, encoding="utf-8")
        try:
            block = governance_block(scratch)
        except (json.JSONDecodeError, yaml.YAMLError) as error:
            failures.append(f"{relative}: 无法解析（{error}）")
            scratch.unlink(missing_ok=True)
            continue
        finally:
            scratch.unlink(missing_ok=True)

        missing = [field for field in REQUIRED_FIELDS if not block.get(field)]
        if missing:
            failures.append(
                f"{relative}: 治理块缺 {', '.join(missing)}；"
                "棘轮基线必须能被独立复算，否则换口径重建就无痕"
            )
            continue
        owner = block["owner"]
        if owner not in owners:
            failures.append(
                f"{relative}: owner {owner!r} 既不是 specs/feature-tree 下的节点，"
                "也不在 GOVERNANCE_FUNCTIONS 里；无法追责的 owner 等于没有 owner"
            )
        previous = measure_of_revision(path, relative, base_sha)
        if previous is not None and previous != block["measure"] and not block.get("superseded_measure"):
            failures.append(
                f"{relative}: measure 相对 HEAD 已变更（exact range 时 HEAD 指 base），但没有 superseded_measure；"
                "换度量口径必须同批写下旧口径是什么、为什么换、旧口径下的实测值"
            )
        try:
            growth = debt_growth(
                path, relative, base_sha=base_sha, candidate_body=candidate_body
            )
        except ValueError as error:
            failures.append(str(error))
            continue
        if growth:
            listed = "；".join(growth[:5])
            more = f"（另有 {len(growth) - 5} 项）" if len(growth) > 5 else ""
            failures.append(
                f"{relative}: {len(growth)} 处债务条目相对 HEAD 变大或新增（exact range 时 HEAD 指 base） —— "
                f"{listed}{more}；棘轮只能下降，先消化债务再谈基线"
            )

    if failures:
        print(f"[ratchet-baseline-governance] FAIL: {len(failures)} 项")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"[ratchet-baseline-governance] OK: {checked} 个棘轮基线治理留痕完整")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
