#!/usr/bin/env python3
"""Fail-closed readback：证明 dev1.0 ruleset 真把 `04. Lane Gate` 设为 hosted required check。

触发范围：`.github/workflows/lane-gate.yml` governance job 在每个 `lane/* -> dev1.0` PR 上以
只读 `github.token` 运行；本地可用 `GITHUB_TOKEN="$(gh auth token)"` 对真实仓库读回。
它不接入 `gate_repo.sh`（需要 hosted API），其合同经 `make test-gate-companion-local-contract`
进入 gate 链。

阻断条件（任一即 `GATE_BLOCK`，lane PR 的 check 转红）：适用于 `refs/heads/dev1.0` 的
active ruleset 不唯一；存在 bypass actor；缺 `deletion`/`non_fast_forward`；出现 `pull_request`
规则（会封死 daily-merge-release-strategy 定义的 integration fast-forward 通道）；
`required_status_checks` 不恰为 `branch_policy.yaml#required_integration_checks`（GitHub Actions
producer）、非 strict 或 `do_not_enforce_on_create` 不为 false。

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
RECOVERY_RESTORE = "restore_git_authority_then_retry"
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


def _branch_ruleset(*, repository: str, token: str, branch: str) -> dict[str, Any]:
    summaries = _object_list(_api_get(repository, "/rulesets", token), "rulesets")
    details = []
    for summary in summaries:
        ruleset_id = summary.get("id")
        if isinstance(ruleset_id, int):
            details.append(_object(
                _api_get(repository, f"/rulesets/{ruleset_id}", token),
                f"ruleset {ruleset_id}",
            ))
    expected_ref = f"refs/heads/{branch}"
    matches = []
    for detail in details:
        conditions = detail.get("conditions") or {}
        ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
        if isinstance(ref_name, dict) and expected_ref in (ref_name.get("include") or []):
            matches.append(detail)
    if len(matches) != 1:
        raise _block(
            f"{branch} must have exactly one applicable branch ruleset (found {len(matches)})",
            recovery=RECOVERY_RULESET,
        )
    return matches[0]


def _verify_ruleset(
    *, ruleset: Mapping[str, Any], branch: str, required_checks: tuple[str, ...],
) -> dict[str, Any]:
    if ruleset.get("enforcement") != "active":
        raise _block(f"{branch} ruleset must be active", recovery=RECOVERY_RULESET)
    if ruleset.get("bypass_actors") != []:
        raise _block(
            f"{branch} ruleset must have no bypass actors "
            f"(observed {json.dumps(ruleset.get('bypass_actors'), sort_keys=True)})",
            recovery=RECOVERY_RULESET,
        )
    conditions = ruleset.get("conditions") or {}
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if ref_name != {"exclude": [], "include": [f"refs/heads/{branch}"]}:
        raise _block(f"{branch} ruleset ref condition drifted", recovery=RECOVERY_RULESET)
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
    if not required_checks:
        raise _block(f"{branch} has no declared required checks in branch policy")
    required = _rule(ruleset, "required_status_checks").get("parameters") or {}
    checks = required.get("required_status_checks") if isinstance(required, dict) else None
    if (
        required.get("strict_required_status_checks_policy") is not True
        or required.get("do_not_enforce_on_create") is not False
        or not isinstance(checks, list)
    ):
        raise _block(
            f"{branch} required-check protection is incomplete (strict + enforce-on-create required)",
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
    return {
        "id": int(ruleset["id"]), "name": str(ruleset["name"]), "branch": branch,
        "requiredChecks": [
            {"name": name, "integrationId": GITHUB_ACTIONS_APP_ID}
            for name in required_checks
        ],
        "mergeExecutor": "integration_fast_forward_push",
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
) -> dict[str, Any]:
    """只读回 dev1.0 ruleset：lane PR 的 required check 必须由 hosted 强制。

    `branch_policy.yaml#required_integration_checks` 只是仓内声明，若 hosted ruleset 未把
    同名 check 设为 required_status_checks，lane PR 的复算就只是可见证据而非阻断。
    """
    if not repository or "/" not in repository or not token:
        raise _block("repository and authenticated GitHub token are required")
    branch_policy = policy or load_policy()
    branch = branch_policy.integration_branch
    ruleset = _verify_ruleset(
        ruleset=_branch_ruleset(repository=repository, token=token, branch=branch),
        branch=branch,
        required_checks=tuple(item.name for item in branch_policy.required_integration_checks),
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
    parser.add_argument("--expected-digest", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = verify_hosted_integration_ruleset(
            repository=args.repository,
            token=os.environ.get(args.token_env, "").strip(),
        )
        if args.expected_digest and receipt["evidenceDigest"] != args.expected_digest:
            raise _block("hosted ruleset changed between preflight and readback")
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
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write("applicability=required\n")
            stream.write("decision=pass\n")
            stream.write(f"authority_digest={receipt['evidenceDigest']}\n")
    print(
        f"hosted integration ruleset verified repository={args.repository} "
        f"branch={receipt['branch']} digest={receipt['evidenceDigest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
