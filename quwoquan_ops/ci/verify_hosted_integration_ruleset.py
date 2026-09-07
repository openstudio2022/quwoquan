#!/usr/bin/env python3
"""Fail-closed readback：证明 dev1.0 ruleset 真把 `04. Lane Gate` 设为 hosted required check。

触发范围：`.github/workflows/lane-gate.yml` governance job 在每个 `lane/* -> dev1.0` PR 上以
只读 `github.token` 运行；本地可用 `GITHUB_TOKEN="$(gh auth token)"` 对真实仓库读回。
它不接入 `gate_repo.sh`（需要 hosted API），其合同经 `make test-gate-companion-local-contract`
进入 gate 链。

阻断条件（任一即 `GATE_BLOCK`，lane PR 的 check 转红）：按 GitHub ref_name 语义
（`~ALL`/`~DEFAULT_BRANCH`/fnmatch，exclude 优先）对 `refs/heads/dev1.0` 生效的 active branch
ruleset 不唯一；`bypass_actors` 可见且非空；缺 `deletion`/`non_fast_forward`；出现 `pull_request`
规则（会封死 daily-merge-release-strategy 定义的 integration fast-forward 通道）；
`required_status_checks` 不恰为 `branch_policy.yaml#required_integration_checks`（GitHub Actions
producer）、非 strict 或 `do_not_enforce_on_create` 不为 false。

GitHub 只向对 ruleset 有 write 权限的调用者返回 `bypass_actors`；governance job 的只读
`github.token` 读不到该字段。不可见时本脚本不假装已证明为空，而是在收据
`ruleset.bypassActorsObservable=false` 如实留痕并打印到 stdout；bypass 为空的证明由 admin 侧以
`--require-bypass-observable` 读回承担（不可见即阻断）。

修复方式：每条阻断的 `recovery=` 直接给出要在 GitHub ruleset 上做的改动；本脚本不写任何
hosted 配置，也不签发 release authority。main ruleset、approval 与 threads 的读回由
`quwoquan_ops/ci/promotion_hosted.py hosted-authority` 在 03. Delivery Gate 内单轨承担。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.lib.github_actions_api import GithubActionsApiError, request_json  # noqa: E402
from quwoquan_ops.gate.verify_git_branch_policy import BranchPolicy, load_policy  # noqa: E402

AUTHORITY_CODE = "OPS.BRANCH.AUTHORITY_UNAVAILABLE"
GITHUB_ACTIONS_APP_ID = 15368
RECEIPT_SCHEMA = "hosted-integration-ruleset-receipt"
RULESET_PAGE_SIZE = 100
RECOVERY_RESTORE = "restore_git_authority_then_retry"
RECOVERY_WRITE_TOKEN = "rerun_readback_with_ruleset_write_token"
RECOVERY_PAGINATE = "reduce_rulesets_below_page_size_or_paginate_readback"
RECOVERY_RULESET = (
    "configure the dev1.0 branch ruleset: exactly one active ruleset for refs/heads/dev1.0, "
    "rules deletion + non_fast_forward + required_status_checks(strict, GitHub Actions context "
    "from branch_policy.yaml#required_integration_checks), no pull_request rule, no bypass actors"
)


class HostedIntegrationRulesetError(RuntimeError):
    """One stable fail-closed hosted authority terminal."""


def _block(detail: object, *, recovery: str = RECOVERY_RESTORE) -> HostedIntegrationRulesetError:
    safe = " ".join(str(detail).replace("\x00", "\\x00").split())
    return HostedIntegrationRulesetError(
        f"{AUTHORITY_CODE}: terminal=blocked; {safe}; recovery={recovery}"
    )


def _api_get(repository: str, path: str, token: str) -> Any:
    try:
        payload, _stats = request_json(
            f"https://api.github.com/repos/{repository}{path}", token
        )
        return payload
    except GithubActionsApiError as error:
        raise _block(
            f"GitHub authority query failed for {path or '/'}: {error.reason}"
        ) from error


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _block(f"{label} response is not an object")
    return value


def _object_list(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise _block(f"{label} response is not an object list")
    return list(value)


def _rules(ruleset: Mapping[str, Any], rule_type: str) -> list[dict[str, Any]]:
    rules = ruleset.get("rules")
    return [
        item
        for item in (rules if isinstance(rules, list) else [])
        if isinstance(item, dict) and item.get("type") == rule_type
    ]


def _rule(ruleset: Mapping[str, Any], rule_type: str) -> dict[str, Any]:
    matches = _rules(ruleset, rule_type)
    if len(matches) != 1:
        raise _block(
            f"ruleset {ruleset.get('name')!r} must contain one {rule_type!r} rule",
            recovery=RECOVERY_RULESET,
        )
    return matches[0]


def _github_fnmatch_regex(pattern: str) -> "re.Pattern[str]":
    """GitHub ruleset 的 fnmatch 方言（Ruby `File.fnmatch` + `FNM_PATHNAME`）。

    与 Python `fnmatch` 不同：`*`/`?` 不跨 `/`；位于路径段首的 `**/` 匹配零个或多个路径段，
    段中的 `**` 退化为 `*`（所以 `qa**/**/*` 比 `qa/**/*` 更宽）；`[...]` 字符集按字面、`[!...]`
    取补（GitHub 不支持 `[^...]` 与反斜杠转义，二者按字面）。不支持 `]` 作字符集首成员与字符集内
    的 `/`——GitHub ruleset 中无此写法。用 Python `fnmatch` 会把 `refs/heads/**/*`（GitHub 文档
    的「全部分支」惯用写法）判为不命中 `refs/heads/dev1.0`。
    """
    try:
        return re.compile("^" + _FNMATCH_TOKEN.sub(_translate_fnmatch_token, pattern) + "$")
    except re.error as error:
        raise _block(
            f"ruleset ref pattern {pattern!r} is not a translatable GitHub fnmatch pattern: {error}"
        ) from error


# 分词顺序即优先级：段首 `**/` → 连续 `*` → `?` → 非空字符集 → 任意单字符。
_FNMATCH_TOKEN = re.compile(r"(?:^|(?<=/))\*\*/|\*+|\?|\[[^\]]+\]|.", re.DOTALL)


def _translate_fnmatch_token(match: "re.Match[str]") -> str:
    token = match.group(0)
    if token == "**/":
        return "(?:[^/]+/)*"
    if token.startswith("*"):
        return "[^/]*"
    if token == "?":
        return "[^/]"
    if token.startswith("[") and token.endswith("]") and len(token) > 2:
        body = token[1:-1].replace("\\", "\\\\").replace("^", "\\^")
        return "[^" + body[1:] + "]" if body.startswith("!") and len(body) > 1 else "[" + body + "]"
    return re.escape(token)


def _ref_pattern_matches(pattern: object, *, ref: str, default_branch_ref: str) -> bool:
    """GitHub ref_name 条件语义：`~ALL`、`~DEFAULT_BRANCH` 与 GitHub 方言 fnmatch 通配。"""
    if not isinstance(pattern, str):
        return False
    if pattern == "~ALL":
        return True
    if pattern == "~DEFAULT_BRANCH":
        return ref == default_branch_ref
    return _github_fnmatch_regex(pattern).match(ref) is not None


def _applies_to_ref(ruleset: Mapping[str, Any], *, ref: str, default_branch_ref: str) -> bool:
    if ruleset.get("enforcement") != "active" or ruleset.get("target") != "branch":
        return False
    conditions = ruleset.get("conditions") or {}
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if not isinstance(ref_name, dict):
        return False
    included = any(
        _ref_pattern_matches(pattern, ref=ref, default_branch_ref=default_branch_ref)
        for pattern in (ref_name.get("include") or [])
    )
    excluded = any(
        _ref_pattern_matches(pattern, ref=ref, default_branch_ref=default_branch_ref)
        for pattern in (ref_name.get("exclude") or [])
    )
    return included and not excluded


def _branch_ruleset(*, repository: str, token: str, branch: str) -> dict[str, Any]:
    """唯一对 refs/heads/<branch> 生效的 active branch ruleset。

    生效判定按 GitHub 自身语义（`~ALL`/`~DEFAULT_BRANCH`/fnmatch，且 exclude 优先），而不是字面
    include；否则第二条以通配命中 dev1.0 并带 pull_request 规则的 ruleset 会被漏掉。
    """
    default_branch = _object(_api_get(repository, "", token), "repository").get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        # `~DEFAULT_BRANCH` 的适用判定依赖它；读不到就不能宣称已判完唯一性。
        raise _block("repository response lacks default_branch; ~DEFAULT_BRANCH applicability is not observable")
    default_branch_ref = f"refs/heads/{default_branch}"
    summaries = _object_list(_api_get(repository, f"/rulesets?per_page={RULESET_PAGE_SIZE}", token), "rulesets")
    if len(summaries) >= RULESET_PAGE_SIZE:
        raise _block(
            f"ruleset list may be truncated at per_page={RULESET_PAGE_SIZE}; "
            "uniqueness cannot be proven without reading every ruleset",
            recovery=RECOVERY_PAGINATE,
        )
    ref = f"refs/heads/{branch}"
    matches = []
    for summary in summaries:
        ruleset_id = summary.get("id")
        if not isinstance(ruleset_id, int):
            raise _block(
                f"ruleset summary lacks integer id ({json.dumps(summary, sort_keys=True)}); "
                "uniqueness cannot be proven"
            )
        detail = _object(_api_get(repository, f"/rulesets/{ruleset_id}", token), f"ruleset {ruleset_id}")
        if _applies_to_ref(detail, ref=ref, default_branch_ref=default_branch_ref):
            matches.append(detail)
    if len(matches) != 1:
        raise _block(
            f"{branch} must have exactly one applicable active branch ruleset (found {len(matches)})",
            recovery=RECOVERY_RULESET,
        )
    return matches[0]


def _verify_bypass_actors(ruleset: Mapping[str, Any], *, branch: str, require_observable: bool) -> bool:
    """可见且非空即阻断；不可见时返回 False 供收据留痕，除非调用方要求必须可见（admin 侧读回）。

    GitHub 只向对 ruleset 有 write 权限的调用者返回 bypass_actors；只读 token 下该字段缺席或为 null。
    """
    bypass_actors = ruleset.get("bypass_actors")
    observable = isinstance(bypass_actors, list)
    if observable and bypass_actors != []:
        raise _block(
            f"{branch} ruleset must have no bypass actors "
            f"(observed {json.dumps(bypass_actors, sort_keys=True)})",
            recovery=RECOVERY_RULESET,
        )
    if require_observable and not observable:
        raise _block(
            f"{branch} ruleset bypass_actors is not observable with this token; "
            "admin-side readback requires a token with ruleset write access",
            recovery=RECOVERY_WRITE_TOKEN,
        )
    return observable


def _verify_required_checks(
    ruleset: Mapping[str, Any], *, branch: str, required_checks: tuple[str, ...],
) -> None:
    required = _rule(ruleset, "required_status_checks").get("parameters") or {}
    checks = required.get("required_status_checks") if isinstance(required, dict) else None
    if (
        required.get("strict_required_status_checks_policy") is not True
        or required.get("do_not_enforce_on_create") is not False
        or not isinstance(checks, list)
    ):
        observed_shape = {
            key: required.get(key)
            for key in ("strict_required_status_checks_policy", "do_not_enforce_on_create")
        }
        raise _block(
            f"{branch} required-check protection is incomplete (strict + enforce-on-create required; "
            f"observed {json.dumps(observed_shape, sort_keys=True)}, checks list {isinstance(checks, list)})",
            recovery=RECOVERY_RULESET,
        )
    observed = {
        str(item.get("context")): item.get("integration_id")
        for item in checks if isinstance(item, dict)
    }
    expected = {name: GITHUB_ACTIONS_APP_ID for name in required_checks}
    if observed != expected:
        raise _block(
            f"{branch} required checks must be exactly {sorted(expected)} produced by GitHub Actions "
            f"(observed {sorted(observed)})",
            recovery=RECOVERY_RULESET,
        )


def _verify_ruleset(
    *, ruleset: Mapping[str, Any], branch: str, required_checks: tuple[str, ...],
    require_bypass_observable: bool = False,
) -> dict[str, Any]:
    bypass_observable = _verify_bypass_actors(
        ruleset, branch=branch, require_observable=require_bypass_observable,
    )
    conditions = ruleset.get("conditions") or {}
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    expected_ref_name = {"exclude": [], "include": [f"refs/heads/{branch}"]}
    if ref_name != expected_ref_name:
        # 唯一命中的 ruleset 还必须以字面 include 指向 dev1.0：通配写法会让它随其他分支的变更漂移。
        raise _block(
            f"{branch} ruleset ref condition must be exactly {json.dumps(expected_ref_name, sort_keys=True)} "
            f"(observed {json.dumps(ref_name, sort_keys=True)})",
            recovery=RECOVERY_RULESET,
        )
    _rule(ruleset, "deletion")
    _rule(ruleset, "non_fast_forward")
    # dev1.0 的合入执行者是 integration 工作区 fast-forward push（DEC-011），pull_request
    # 规则会封死该通道，出现即视为 hosted 漂移。
    if _rules(ruleset, "pull_request"):
        raise _block(
            f"{branch} ruleset must not require pull requests; "
            "its merge executor is the integration fast-forward push",
            recovery=RECOVERY_RULESET,
        )
    _verify_required_checks(ruleset, branch=branch, required_checks=required_checks)
    return {
        "id": int(ruleset["id"]), "name": str(ruleset["name"]), "branch": branch,
        "requiredChecks": [
            {"name": name, "integrationId": GITHUB_ACTIONS_APP_ID}
            for name in required_checks
        ],
        "mergeExecutor": "integration_fast_forward_push",
        "bypassActorsObservable": bypass_observable,
        "updatedAt": str(ruleset.get("updated_at") or ""),
    }


def _seal(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt["observedAt"] = (
        dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    )
    digest_payload = {
        key: value for key, value in receipt.items()
        if key not in {"observedAt", "evidenceDigest"}
    }
    receipt["evidenceDigest"] = "sha256:" + hashlib.sha256(json.dumps(
        digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return receipt


def verify_hosted_integration_ruleset(
    *, repository: str, token: str, policy: BranchPolicy | None = None,
    require_bypass_observable: bool = False,
) -> dict[str, Any]:
    """只读回 dev1.0 ruleset：lane PR 的 required check 必须由 hosted 强制。

    `branch_policy.yaml#required_integration_checks` 只是仓内声明，若 hosted ruleset 未把
    同名 check 设为 required_status_checks，lane PR 的复算就只是可见证据而非阻断。
    收据顶层 `requiredIntegrationChecksEnforced` 只证明 required_status_checks 规则形状；
    bypass 为空的证明以 `ruleset.bypassActorsObservable` 为界，不可见时不在本收据内。
    """
    if not repository or "/" not in repository or not token:
        raise _block("repository and authenticated GitHub token are required")
    branch_policy = policy or load_policy()
    branch = branch_policy.integration_branch
    ruleset = _verify_ruleset(
        ruleset=_branch_ruleset(repository=repository, token=token, branch=branch),
        branch=branch,
        required_checks=tuple(item.name for item in branch_policy.required_integration_checks),
        require_bypass_observable=require_bypass_observable,
    )
    return _seal({
        "schema": RECEIPT_SCHEMA,
        "repository": repository,
        "branch": branch,
        "requiredIntegrationChecksEnforced": True,
        "ruleset": ruleset,
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--require-bypass-observable", action="store_true",
        help="admin 侧读回：bypass_actors 不可见即阻断，用于证明 bypass 为空（需 ruleset write 权限 token）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = verify_hosted_integration_ruleset(
            repository=args.repository,
            token=os.environ.get(args.token_env, "").strip(),
            require_bypass_observable=args.require_bypass_observable,
        )
    except (HostedIntegrationRulesetError, OSError, TypeError, ValueError) as error:
        detail = str(error)
        if AUTHORITY_CODE not in detail:
            detail = str(_block(detail))
        print(f"GATE_BLOCK: {detail}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"hosted integration ruleset verified repository={args.repository} "
        f"branch={receipt['branch']} bypassActorsObservable={receipt['ruleset']['bypassActorsObservable']} "
        f"digest={receipt['evidenceDigest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
