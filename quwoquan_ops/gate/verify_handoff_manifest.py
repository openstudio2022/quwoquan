#!/usr/bin/env python3
"""轮次交接单校验门禁。

HANDOFF 是宪法要求的工作流间交接契约，但聊天文本无法校验、无法跨会话消费。
交接单 `.qwq_output/env/repo/runs/handoff/<轮次>/manifest.md` 是它的物理形态；
本门禁校验其结构可裁定：

1. 头部字段：`intent 终版`、`新轮触发判定`。
2. 宪法四项段落齐全：`## 产出物`、`## 未决项去向`、`## 唯一合法下游`、`## 证据链`。
3. 未决项三向裁决零悬空：每条落到「转 OPEN-###」「Out of Scope」「下一工作流承接」之一；
   且每条带泛化判定「孤例」或「一类」留痕（显式「无未决项」豁免）。
4. canonical 身份段绑定 EvidenceFingerprint ref/digest、source HEAD/source fingerprint、
   captured metadata、freshness 与唯一 recovery token；旧 Markdown shape 不再被消费。
5. 证据链每条带「命令 + 退出码 + 时间戳 + 工作树 SHA」，下游消费时过期即复跑。

用法：
    python3 quwoquan_ops/gate/verify_handoff_manifest.py <manifest.md>
    python3 quwoquan_ops/gate/verify_handoff_manifest.py   # 校验最新轮次

退出码：0 通过；1 校验失败；2 用法错误或找不到交接单。
交接单是运行产物（可删可重建）：长期事实必须同时转出到 OPEN/spec，本门禁不校验业务内容。
接入面：on-demand gate，经 `make verify-handoff-manifest` 在轮次收口时调用；
不接入 gate_repo.sh，不进 L0 commit gate。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
HANDOFF_ROOT = ROOT / ".qwq_output/env/repo/runs/handoff"

sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
from lib.agent_governance_contract import contract_section  # noqa: E402
from lib.evidence_fingerprint import (  # noqa: E402
    EvidenceFingerprintError,
    canonical_digest,
    validate_digest,
    validate_evidence_fingerprint,
    validate_ref,
)
from lib.gate_output import emit_gate_result, finding  # noqa: E402
import handoff_consumer  # noqa: E402

REQUIRED_HEAD_FIELDS = ("intent 终版", "新轮触发判定")
REQUIRED_SECTIONS = (
    "## EvidenceFingerprint",
    "## 产出物",
    "## 未决项去向",
    "## 唯一合法下游",
    "## 证据链",
)
IDENTITY_FIELD_RE = re.compile(r"^- (?P<key>[a-z_]+):\s*(?P<value>.+?)\s*$", re.M)
SOURCE_HEAD_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")

# 三向裁决：转 OPEN / Out of Scope / 下一工作流承接。「无未决项」显式声明也合法。
RESOLUTION_RE = re.compile(r"OPEN-\d{3,}|Out of Scope|承接|无未决项")
# 泛化判定留痕：只认显式 `泛化判定：孤例/一类` 或括号标记，避免「统一类型」
# 等自然语言偶然包含「一类」而假通过；「无未决项」声明豁免。
GENERALIZATION_RE = re.compile(
    r"(?:泛化判定\s*[：:]\s*|[（(]\s*)(?:孤例|一类)"
    r"(?=\s*[：:，,；;。.（）()]|$)|^\s*无未决项\s*$"
)
EVIDENCE_RE = re.compile(
    r"exit=\d+.*\d{4}-\d{2}-\d{2}.*\b[0-9a-f]{7,40}\b|\d{4}-\d{2}-\d{2}.*exit=\d+.*\b[0-9a-f]{7,40}\b"
)
BULLET_RE = re.compile(r"^-\s+(.+)$", re.M)


def _section(text: str, heading: str) -> str | None:
    match = re.search(rf"^{re.escape(heading)}\s*$", text, re.M)
    if match is None:
        return None
    tail = text[match.end():]
    nxt = re.search(r"^##\s+", tail, re.M)
    return tail[: nxt.start()] if nxt else tail


def _identity_fields(text: str) -> tuple[dict[str, str], list[str]]:
    issues: list[str] = []
    section = _section(text, "## EvidenceFingerprint")
    if section is None:
        return {}, issues
    fields: dict[str, str] = {}
    for match in IDENTITY_FIELD_RE.finditer(section):
        key = match.group("key")
        if key in fields:
            issues.append(f"EvidenceFingerprint 字段重复：{key}")
        fields[key] = match.group("value").strip().strip("`")
    required = {
        "payload_ref",
        "ref",
        "digest",
        "source_head",
        "source_fingerprint",
        "captured_metadata",
        "freshness",
        "recovery_token",
        "digest_payload",
    }
    missing = sorted(required - set(fields))
    extra = sorted(set(fields) - required)
    if missing or extra:
        issues.append(
            f"EvidenceFingerprint 字段闭集漂移：missing={missing}, extra={extra}"
        )
    return fields, issues


def _validate_identity(text: str, rel: str) -> list[str]:
    fields, field_issues = _identity_fields(text)
    issues = [f"{rel}: {issue}" for issue in field_issues]
    if field_issues:
        return issues
    try:
        digest = validate_digest(fields["digest"])
        validate_ref(fields["ref"], digest=digest)
        source_fingerprint = validate_digest(fields["source_fingerprint"])
    except (KeyError, EvidenceFingerprintError) as exc:
        issues.append(f"{rel}: canonical EvidenceFingerprint ref/digest 非法：{exc}")
        return issues
    if source_fingerprint != digest:
        issues.append(f"{rel}: source_fingerprint 必须等于 canonical digest")
    if not SOURCE_HEAD_RE.fullmatch(fields["source_head"]):
        issues.append(f"{rel}: source_head 必须为 40 或 64 位小写 hex")
    else:
        current_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if not current_head or fields["source_head"] != current_head:
            issues.append(
                f"{rel}: source_head 已 stale，必须重新采集 canonical fingerprint"
            )
    try:
        metadata = json.loads(fields["captured_metadata"])
    except json.JSONDecodeError as exc:
        issues.append(f"{rel}: captured_metadata 必须为 JSON object：{exc.msg}")
        metadata = None
    expected_metadata = contract_section("evidence_fingerprint")["handoff"][
        "captured_metadata_fields"
    ]
    if not isinstance(metadata, dict) or set(metadata) != set(expected_metadata):
        issues.append(
            f"{rel}: captured_metadata 字段必须精确为 {expected_metadata}"
        )
    elif not all(isinstance(metadata[field], str) and metadata[field] for field in expected_metadata):
        issues.append(f"{rel}: captured_metadata 值必须为非空字符串")
    try:
        payload = json.loads(fields["digest_payload"])
    except json.JSONDecodeError as exc:
        issues.append(f"{rel}: digest_payload 必须为 JSON object：{exc.msg}")
        payload = None
    if isinstance(payload, dict) and canonical_digest(payload) != digest:
        issues.append(f"{rel}: digest_payload 与 canonical digest 不一致")
    elif not isinstance(payload, dict):
        issues.append(f"{rel}: digest_payload 必须为 JSON object")
    handoff = contract_section("evidence_fingerprint")["handoff"]
    if fields["freshness"] != handoff["required_freshness"]:
        issues.append(
            f"{rel}: evidence freshness={fields['freshness']!r}，必须为 fresh 后再消费"
        )
    if fields["recovery_token"] != handoff["recovery_token"]:
        issues.append(
            f"{rel}: recovery_token 非法，必须为 {handoff['recovery_token']}"
        )
    payload_ref = fields.get("payload_ref")
    if payload_ref:
        try:
            _, handoff_payload = handoff_consumer._load_json_ref(
                payload_ref, label="handoff payload"
            )
            handoff_consumer.validate_handoff_payload(handoff_payload)
            current = validate_evidence_fingerprint(
                handoff_payload["fingerprint_receipt"]
            )
            if current["digest"] != digest or current["ref"] != fields["ref"]:
                issues.append(f"{rel}: Markdown identity 与 canonical payload 不一致")
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(f"{rel}: canonical handoff payload stale：{exc}")
    return issues


def validate(text: str, rel: str) -> list[str]:
    issues: list[str] = []
    for field in REQUIRED_HEAD_FIELDS:
        if field not in text:
            issues.append(f"{rel}: 缺头部字段「{field}」")

    for heading in REQUIRED_SECTIONS:
        if _section(text, heading) is None:
            issues.append(f"{rel}: 缺 required 段落「{heading}」")
    issues.extend(_validate_identity(text, rel))

    pending = _section(text, "## 未决项去向")
    if pending is not None:
        for bullet in BULLET_RE.findall(pending):
            if not RESOLUTION_RE.search(bullet):
                issues.append(
                    f"{rel}: 未决项悬空「{bullet[:40]}」——必须落到"
                    "「转 OPEN-###」「Out of Scope」「下一工作流承接」之一"
                )
            if not GENERALIZATION_RE.search(bullet):
                issues.append(
                    f"{rel}: 未决项缺泛化判定「{bullet[:40]}」——必须标注"
                    "「孤例」或「一类」（一类须写系统性排查方式）"
                )

    downstream = _section(text, "## 唯一合法下游")
    if downstream is not None and not BULLET_RE.search(downstream):
        issues.append(f"{rel}: 「唯一合法下游」段为空，下一轮 RESOLVE 无从消费")

    evidence = _section(text, "## 证据链")
    if evidence is not None:
        bullets = BULLET_RE.findall(evidence)
        if not bullets:
            issues.append(f"{rel}: 证据链为空——完成宣称没有任何可复跑证据")
        for bullet in bullets:
            if not EVIDENCE_RE.search(bullet):
                issues.append(
                    f"{rel}: 证据条目缺字段「{bullet[:40]}」——必须带"
                    "命令 + exit=退出码 + 时间戳 + 工作树 SHA"
                )
    return issues


def _latest_manifest() -> Path | None:
    if not HANDOFF_ROOT.is_dir():
        return None
    manifests = sorted(HANDOFF_ROOT.glob("*/manifest.md"), key=lambda p: p.stat().st_mtime)
    return manifests[-1] if manifests else None


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        target = Path(argv[1])
        if not target.is_absolute():
            target = ROOT / target
    else:
        found = _latest_manifest()
        if found is None:
            print(
                f"[verify_handoff_manifest] 用法错误：{HANDOFF_ROOT.relative_to(ROOT)} "
                "下没有任何轮次交接单，且未指定路径",
                file=sys.stderr,
            )
            return 2
        target = found

    if not target.is_file():
        print(f"[verify_handoff_manifest] 找不到交接单 {target}", file=sys.stderr)
        return 2

    rel = target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else str(target)
    issues = validate(target.read_text(encoding="utf-8"), rel)
    emit_gate_result(
        "verify-handoff-manifest",
        [finding(issue, path=rel) for issue in issues],
        ROOT,
    )
    if issues:
        print("[verify_handoff_manifest] FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print(
        f"[verify_handoff_manifest] OK: {rel} canonical fingerprint fresh、"
        "裁决零悬空、证据字段完整"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
