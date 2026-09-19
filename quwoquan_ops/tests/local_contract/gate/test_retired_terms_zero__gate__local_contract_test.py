# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
"""退役术语零容忍门的行为合约。

258 处存量清零后,这道门的价值在于「不回流」:任何新的 legacy/compat 运行时
标识直接 BLOCK,且不存在可以扩大的豁免名单——历史上这类债正是靠豁免名单
悄悄增长起来的。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_app/scripts/runtime/architecture/verify_retired_terms_zero.py"


def test_repository_has_zero_retired_runtime_identifiers() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", str(GATE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "OK" in completed.stdout


@pytest.fixture
def runtime_tree(tmp_path: Path) -> Path:
    """只复制扫描器及路径依赖，生产实现保持 exact bytes。"""
    for source in (GATE, ROOT / "quwoquan_app/scripts/_common/paths.py"):
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    runtime = tmp_path / "quwoquan_ops/cli"
    runtime.mkdir(parents=True)
    (runtime / "value.py").write_text("legacyAvailable = True\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("entry", ["scanner", "l0", "readiness"])
def test_real_retired_terms_failure_propagates(runtime_tree: Path, entry: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t2
    from quwoquan_ops.ci.local_readiness_planner import STATIC_COMMANDS

    command = STATIC_COMMANDS["retired_terms_zero"][0]
    if entry == "l0":
        source = (ROOT / "quwoquan_ops/gate/commit_gate.sh").read_text()
        function = source.split("run_static_check() {", 1)[1].split("\nexport -f", 1)[0]
        command = ["bash", "-c", "set -e\nrun_static_check() {" + function + "\nrun_static_check retired_terms_zero\nprintf unexpected-success"]
    elif entry == "readiness":
        sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
        from lib.local_readiness.core import _run_check

        result = _run_check(
            {"id": "static:retired_terms_zero", "command": command, "cwd": ".", "timeout_seconds": 30},
            runtime_tree / ".qwq_output/check.log",
            repo_root=runtime_tree,
        )
        assert result["status"] == "FAIL", result
        assert result["exit_code"] == 1
        assert "value.py:1:legacyAvailable" in Path(result["log"]).read_text()
        return
    completed = subprocess.run(command, cwd=runtime_tree, capture_output=True, text=True, timeout=30)
    assert completed.returncode != 0
    assert "value.py:1:legacyAvailable" in completed.stdout
    assert "unexpected-success" not in completed.stdout


def test_scanner_excludes_dependency_lockfile_but_scans_runtime_json(runtime_tree: Path) -> None:
    # package-lock 由 npm 生成，第三方依赖元数据不是 executable compatibility identity。
    runtime = runtime_tree / "quwoquan_data/control_plane/example"
    runtime.mkdir(parents=True)
    (runtime_tree / "quwoquan_ops/cli/value.py").unlink()
    (runtime / "package-lock.json").write_text('{"dependency": "legacy-package"}\n', encoding="utf-8")
    gate = runtime_tree / GATE.relative_to(ROOT)
    accepted = subprocess.run([sys.executable, "-B", str(gate)], capture_output=True, text=True, timeout=30)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr

    (runtime / "runtime.json").write_text('{"legacyMode": true}\n', encoding="utf-8")
    rejected = subprocess.run([sys.executable, "-B", str(gate)], capture_output=True, text=True, timeout=30)
    assert rejected.returncode == 1
    assert "runtime.json:1:legacyMode" in rejected.stdout


def test_scanner_accepts_current_names_comments_and_test_exclusion(runtime_tree: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t2
    runtime = runtime_tree / "quwoquan_ops/cli"
    (runtime / "value.py").write_text("# legacyAvailable is retired\navailability = True\n", encoding="utf-8")
    (runtime / "test_value.py").write_text("legacyFixture = True\n", encoding="utf-8")
    completed = subprocess.run([sys.executable, "-B", str(runtime_tree / GATE.relative_to(ROOT))], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("scope,phase", [("all", "all"), ("app", "all"), ("service", "all"), ("service", "packaging"), ("data", "all"), ("portal", "all"), ("ops-portal", "all"), ("patrol", "all")])
def test_gate_prefix_fails_before_heavy_commands(runtime_tree: Path, scope: str, phase: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t4
    source = ROOT / "quwoquan_ops/gate/gate_repo.sh"
    target = runtime_tree / source.relative_to(ROOT)
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    text = source.read_text()
    assert text.count("verify_retired_terms_zero.py") == 1
    assert text.index("verify_retired_terms_zero.py") < text.index("run_vertical_architecture_ratchet()")
    assert "verify_retired_terms_zero.py" not in text.split("run_app()", 1)[1]
    completed = subprocess.run(
        ["bash", str(target), "--scope", scope], cwd=runtime_tree,
        env={**os.environ, "GATE_SERVICE_PHASE": phase, "GATE_DATA_PHASE": "all"},
        capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode != 0
    assert "value.py:1:legacyAvailable" in completed.stdout, completed.stdout + completed.stderr
    assert "vertical architecture static ratchet" not in completed.stdout


def test_gate_has_no_allowlist_escape() -> None:
    """禁止通过扩大豁免名单达成归零(OPEN-002 收口时的硬约束)。"""
    source = GATE.read_text(encoding="utf-8")
    for escape in ("ALLOWLIST", "allowlist_path", "exempt_paths", "baseline_path"):
        assert escape not in source, f"retired-terms gate must not grow {escape}"


# --- 退役内容轴(micro / moment / contentIdentity / displayFormat / PromotePostToWork) ---
#
# 这套判据必须双向成立：新违规样本变红，仓内真实存在的同形合规写法不得误报。
# 只写单向用例的门会在两个方向上骗人——要么放过回流,要么逼开发去改无关的
# micro-batch / microseconds / wechat_moments / 笔记字段。


@pytest.fixture
def scanner_tree(tmp_path: Path) -> Path:
    """只复制扫描器及路径依赖，被判样本由用例写入，生产实现保持 exact bytes。"""
    for source in (GATE, ROOT / "quwoquan_app/scripts/_common/paths.py"):
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (tmp_path / "quwoquan_app/lib").mkdir(parents=True)
    return tmp_path


def _scan(tree: Path, sample: str, lines: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    (tree / "quwoquan_app/lib" / sample).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-B", str(tree / GATE.relative_to(ROOT))],
        capture_output=True,
        text=True,
        timeout=60,
    )


RETIRED_CONTENT_AXIS_VIOLATIONS = (
    ("content_type_micro_member.dart", ("      case ContentType.micro:",), "micro"),
    ("content_type_micro_wire.dart", ("      'contentType': 'micro',",), "micro"),
    ("content_surface_kind_micro.dart", ("enum ContentSurfaceKind { micro, image }",), "micro"),
    ("search_content_type_micro.dart", ("  static const String searchContentTypeMicro = 'x';",), "ContentTypeMicro"),
    ("content_identity_moment_value.dart", ("      identity: 'moment',",), "'moment'"),
    ("content_identity_moment_member.dart", ("    return CreateContentIdentity.moment;",), "ContentIdentity"),
    ("content_identity_closed_set.dart", ("enum CreateContentIdentity { moment, work }",), "ContentIdentity"),
    ("works_affinity_closed_set.py", ('AFFINITIES = ("work", "moment")',), "ContentIdentity{moment,work}"),
    ("post_content_identity_field.dart", ("  final id = wire.contentIdentity ?? '';",), "contentIdentity"),
    ("post_content_identity_type.go", ('	ContentIdentity string `json:"contentIdentity"`',), "ContentIdentity"),
    ("retired_content_identity_outcome.dart", ("String? contentIdentityOutcome;",), "contentIdentity"),
    ("retired_content_identity_outcome_type.dart", ("class AppTelemetryValueContentIdentityOutcome {}",), "ContentIdentity"),
    ("content_identity_type.dart", ("ContentIdentity value;",), "ContentIdentity"),
    ("generated_content_identity.go", ("type ContentIDentity string",), "ContentIDentity"),
    ("identity_dto.yaml", ("- {name: contentIdentity, type: ContentIdentity}",), "contentIdentity"),
    ("description_sequence_sibling.yaml", ("- description: micro 已退役", "  values: [micro, image]"), "micro"),
    ("description_empty_sibling.yaml", ("description:", "values: [micro, image]"), "micro"),
    ("not_description_key.yaml", ("wire_description: micro",), "micro"),
    ("description_container.yaml", ("description: {type: ContentIdentity}",), "ContentIdentity"),
    ("description_then_enum.yaml", ("- {description: '退役 micro，不得回流', values: [micro, image]}",), "micro"),
    ("enum_then_description.yaml", ("- {values: [micro, image], description: micro 已退役}",), "micro"),
    ("description_then_identity.yaml", ("- {description: '不用 micro', type: ContentIDentity}",), "ContentIDentity"),
    ("description_then_legacy.yaml", ("- {description: '不用 legacy', name: legacyMode}",), "legacyMode"),
    ("description_sibling_next_line.yaml", ("description: |", "  micro 已退役", "values: [micro, image]"), "micro"),
    ("comment_then_violation.dart", ("/* micro 已退役 */ final value = ContentType.micro;",), "micro"),
    ("inline_comment_violation.py", ("value = 'micro'  # micro 已退役",), "micro"),
    ("quoted_comment_markers.dart", ("const url = 'https://host/micro';",), "micro"),
    ("quoted_hash.yaml", ("value: '# micro'",), "micro"),
    ("non_prose_description.dart", ("final description = ContentType.micro;",), "micro"),
    ("prose_near_note.yaml", ("description: 'photo 与 micro 历史说明'", "displayFormat: note"), "displayFormat"),
    ("display_format_axis.dart", ("        displayFormat: switch (type) {",), "displayFormat"),
    ("promote_post_to_work_route.go", ('	case "PromotePostToWork":',), "PromotePostToWork"),
    ("promote_to_work_operation.dart", ("    await client.post('/posts/1:promoteToWork');",), "promoteToWork"),
    ("promote_to_work_metric.dart", ("      metric: 'content_post_promote_to_work',",), "promote_to_work"),
    ("post_promoted_to_work_event.go", ('	OperationID: "content.post.PostPromotedToWork",',), "PromotedToWork"),
    (
        "display_format_note_arm.dart",
        ("        displayFormat: switch (type) {", "          'article' => 'note',", "        };"),
        "displayFormat='note'",
    ),
    (
        "display_format_note_request_alias.go",
        ('	case "photo":', '		return "image"', '	case "note":', '		return "article"'),
        'displayFormat="note"',
    ),
)


@pytest.mark.parametrize(
    "sample,lines,token",
    RETIRED_CONTENT_AXIS_VIOLATIONS,
    ids=[sample for sample, _, _ in RETIRED_CONTENT_AXIS_VIOLATIONS],
)
def test_retired_content_axis_rejects_new_violation(
    scanner_tree: Path, sample: str, lines: tuple[str, ...], token: str
) -> None:
    # spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
    completed = _scan(scanner_tree, sample, lines)
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "verify_retired_terms_zero: FAIL" in completed.stdout
    assert f"quwoquan_app/lib/{sample}:" in completed.stdout, completed.stdout
    assert token in completed.stdout, completed.stdout


@pytest.mark.parametrize("action", ["Impression", "DeepEngage", "Click", "Like", "Share", "Comment"])
@pytest.mark.parametrize("content_type", ["Moment", "Photo"])
@pytest.mark.parametrize("style", ["camel", "snake"])
def test_scanner_rejects_retired_metric_compound_identifiers(
    scanner_tree: Path, action: str, content_type: str, style: str
) -> None:
    if style == "camel":
        token = action + content_type
        line = f"{token} atomic.Int64"
    else:
        prefix = "deep_engage" if action == "DeepEngage" else action.lower()
        token = f"{prefix}_{content_type.lower()}"
        line = f'"{token}": counter.Load(),'
    completed = _scan(scanner_tree, "metrics.go", (line,))
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert token in completed.stdout


@pytest.mark.parametrize("sample", ["monitoring/alerts/content_contract/post.yaml", "monitoring/dashboards/content.json"])
def test_scanner_covers_ops_observability(scanner_tree: Path, sample: str) -> None:
    target = scanner_tree / "quwoquan_ops/observability" / sample
    target.parent.mkdir(parents=True)
    target.write_text('{"operation": "content.post.PromotePostToWork"}\n', encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-B", str(scanner_tree / GATE.relative_to(ROOT))],
        capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert f"quwoquan_ops/observability/{sample}:1:" in completed.stdout


# 每一条都是仓内真实存在的写法：recommendation 的打分 micro-batch、Dart 的
# microsecondsSinceEpoch / microtask、录音权限、intersection 的意图时态 moment、
# 微信朋友圈 wechat_moments、trip-moment-content-link、release 内容身份、
# gathering plan 的 note 与 article 笔记字段。任一条命中都是误伤，不是收紧。
RETIRED_CONTENT_AXIS_COMPLIANT = (
    ("assistant_content_identity_flag.yaml", ("- {name: enableAssistantContentIdentityIndex, type: bool}",)),
    ("assistant_content_identity_flag.go", ('EnableAssistantContentIdentityIndex *bool `json:"enable_assistant_content_identity_index,omitempty"`',)),
    ("assistant_content_identity_flag.dart", ("?flags.enableAssistantContentIdentityIndex,",)),
    ("prose_description.yaml", ("description: micro 与 ContentIdentity / displayFormat 已退役",)),
    ("inline_prose_description.yaml", ("- {name: contentType, description: 对象身份轴，退役成员（micro）不是合法取值。}",)),
    ("quoted_prose_description.yaml", ('- {description: "micro, ContentIdentity: 已退役", type: string}',)),
    ("escaped_prose_description.yaml", ('description: "历史 \\"micro\\" 已退役"',)),
    ("block_prose_description.yaml", ("description: |", "  micro / legacyMode / ContentIdentity", "  moment 与 work", "type: string")),
    ("folded_prose_description.yaml", ("description: >-", "  micro 已退役", "  displayFormat 已退役", "type: string")),
    ("inline_comment.py", ("value = True  # micro / legacyMode / ContentIdentity",)),
    ("inline_comment.dart", ("final value = true; // micro / legacyMode / ContentIdentity",)),
    ("block_comment.dart", ("/* 历史说明", "micro / ContentIdentity / legacyMode", "*/", "final value = true;")),
    ("prose_near_note.yaml", ("description: 'photo 与 micro 历史说明'", "kind: 'note'")),
    ("comment_near_note.go", ('// displayFormat photo 已退役', 'const PlanItemKindNote = "note"')),
    (
        "micro_batch.yaml",
        (
            "        - micro_batch_window_2ms",
            "    microblog: { baseTier: tier4_casual }",
        ),
    ),
    (
        "micro_word_senses.dart",
        (
            "final ts = DateTime.now().microsecondsSinceEpoch;",
            "    Future<void>.microtask(_load);",
            "      AppPermissionKind.microphone,",
            "  static Future<bool> _microphoneRecordGranted() async {",
        ),
    ),
    (
        "micro_word_senses.go",
        (
            "	issuedAt := time.Now().UTC().Truncate(time.Microsecond)",
            "	elapsed := float64(time.Since(started).Microseconds()) / 1000.0",
            "	return strconv.FormatInt(now.UnixMicro(), 36)",
            '	case strings.Contains(ua, "micromessenger"):',
        ),
    ),
    (
        "intersection_moment_tense.yaml",
        ("    moment: retrospective", "moments:", "  - retrospective"),
    ),
    (
        "intersection_moment_tense.go",
        (
            '	Moment  string  `json:"moment"`',
            '	var IntersectionMoments = []string{"retrospective", "current"}',
        ),
    ),
    ("intersection_moment_tense.json", ('  "moment": "prospective",',)),
    ("intersection_moment_field.yaml", ("- name: moment",)),
    (
        "moment_local_variable.py",
        (
            "    moment = now if now is not None else int(time.time())",
            "    overdue = [c for c in pending if c.is_overdue(policy, now=moment)]",
            '    return {"checkedAt": moment}',
        ),
    ),
    (
        "wechat_moments_share.dart",
        (
            "enum NativeShareTarget { wechatFriend, wechatMoments }",
            "                    : 'wechat_moments',",
            "  static const String forwardActionWechatMoments = 'x';",
        ),
    ),
    ("same_moment_as.dart", ("        readback.createdAt.isAtSameMomentAs(receipt.createdAt);",)),
    ("assistant_moment_marker.dart", ("          momentId: marker['momentId'] as String,",)),
    ("trip_moment_content_link.json", ('  "trip-moment-content-link": { "owner": "content" }',)),
    (
        "release_content_identity.py",
        (
            "def _content_identity(value: object, *, field: str) -> str:",
            "    identity = load_release_content_identity(release_root)",
            "    content_identity = link_target",
        ),
    ),
    (
        "note_field_senses.go",
        ('	PlanItemKindNote PlanItemKind = "note"', '	Note  string  `json:"note"`'),
    ),
    (
        "note_field_senses.dart",
        (
            "      note: (json['note'] as String?)?.trim() ?? '',",
            "  static const String note = 'note';",
            "    articleTemplate: ArticleTemplate.notePaper,",
            "    await center.publish(Notification.draftSaved);",
        ),
    ),
    ("notes_collection.json", ('  "notes": ["first"],', '  "note": "closed release-media domain"')),
    ("promote_to_workspace.py", ("    workspacePromotion = resolve_promote_to_workspace(plan)",)),
    ("canonical_metrics.go", ('ImpressionImage atomic.Int64', '"deep_engage_video": counter.Load(),', 'CommentArticle atomic.Int64')),
    ("unrelated_metric_words.go", ('ShareWechatMoments atomic.Int64', 'ClickMomentaryButton()', 'ImpressionPhotographer atomic.Int64', '"share_photo_library": enabled,')),
    ("negative_metric__local_contract_test.go", ('ImpressionMoment atomic.Int64', '"click_photo": counter.Load(),')),
)


@pytest.mark.parametrize(
    "sample,lines",
    RETIRED_CONTENT_AXIS_COMPLIANT,
    ids=[sample for sample, _ in RETIRED_CONTENT_AXIS_COMPLIANT],
)
def test_retired_content_axis_accepts_real_compliant_spelling(
    scanner_tree: Path, sample: str, lines: tuple[str, ...]
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t2
    completed = _scan(scanner_tree, sample, lines)
    assert completed.returncode == 0, f"{sample} 被误伤:\n{completed.stdout}{completed.stderr}"
    assert "verify_retired_terms_zero: OK" in completed.stdout


# --- 退役取值的 canonical 单点声明与其生成投影 ---
#
# 退役取值只有一个合法表达：共享 enum owner 的 retired_enum_values 记录，以及生成
# 链对同一条记录的投影。这里钉住三件事——合法声明通过、声明不成立时同一份投影
# 照旧 BLOCK、任何伪造形态或未声明的对仍然 BLOCK。判据是记录形态加 canonical
# 声明集合，不是路径或文件名，所以控制样本全部写在普通被扫描目录里。

CANONICAL_TYPES = "quwoquan_service/contracts/metadata/_shared/types.yaml"
CANONICAL_DECLARATION = (
    "enums:\n"
    "  ContentType: [image, video, article]\n"
    "retired_enum_values:\n"
    "  - {enum: ContentType, retired_value: micro}\n"
)
PROJECTED_RECORD = '\t{Enum: "ContentType", RetiredValue: "micro"},'


def _declare(tree: Path, declaration: str) -> None:
    target = tree / CANONICAL_TYPES
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(declaration, encoding="utf-8")


def _project(tree: Path, record: str) -> None:
    target = tree / "quwoquan_service/services/content-service/generated/content/post"
    target.mkdir(parents=True, exist_ok=True)
    (target / "contracts.go").write_text(
        "package generated\n\nvar RetiredContentTypeValues = []RetiredEnumValue{\n"
        f"{record}\n}}\n",
        encoding="utf-8",
    )


def _run_gate(tree: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(tree / GATE.relative_to(ROOT))],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_canonical_retired_declaration_and_projection_pass(scanner_tree: Path) -> None:
    # spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-003
    _declare(scanner_tree, CANONICAL_DECLARATION)
    _project(scanner_tree, PROJECTED_RECORD)
    completed = _run_gate(scanner_tree)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "verify_retired_terms_zero: OK" in completed.stdout


def test_projection_blocks_when_canonical_declaration_is_absent(scanner_tree: Path) -> None:
    """删掉声明，同一份生成投影立刻变红——接受来自声明，不来自文件位置。"""
    _project(scanner_tree, PROJECTED_RECORD)
    completed = _run_gate(scanner_tree)
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "generated/content/post/contracts.go:" in completed.stdout, completed.stdout


FORGED_RETIRED_VALUE_RECORDS = (
    ("wrong_key.yaml", "  - {enum: ContentType, value: micro}"),
    ("abbreviated_key.yaml", "  - {enum: ContentType, retired: micro}"),
    ("missing_enum_binding.yaml", "  - {retired_value: micro}"),
    ("extra_key.yaml", "  - {enum: ContentType, retired_value: micro, accept_on_wire: true}"),
    ("bare_key.yaml", "  retired_value: micro"),
    ("quoted_value.yaml", "  - {enum: ContentType, retired_value: 'micro'}"),
    ("borrowed_enum.go", '\t{Enum: "MediaType", RetiredValue: "micro"},'),
    ("missing_go_enum.go", '\t{RetiredValue: "micro"},'),
    ("extra_go_field.go", '\t{Enum: "ContentType", RetiredValue: "micro", Accept: true},'),
    ("hand_written_constant.go", '\tconst retiredContentType = "micro"'),
    ("wire_value.dart", "      'contentType': 'micro',"),
    ("closed_set_member.yaml", "  ContentType: [micro, image, video, article]"),
    ("retired_enum_member.yaml", "  - {enum: ContentIdentity, retired_value: moment}"),
)


@pytest.mark.parametrize(
    "sample,line",
    FORGED_RETIRED_VALUE_RECORDS,
    ids=[sample for sample, _ in FORGED_RETIRED_VALUE_RECORDS],
)
def test_forged_retired_value_records_are_rejected(
    scanner_tree: Path, sample: str, line: str
) -> None:
    """canonical 声明就位也不豁免伪造形态、未声明的对或手写字面量。"""
    # spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-007
    _declare(scanner_tree, CANONICAL_DECLARATION)
    completed = _scan(scanner_tree, sample, (line,))
    assert completed.returncode == 1, f"{sample} 未被阻断:\n{completed.stdout}"
    assert f"quwoquan_app/lib/{sample}:" in completed.stdout, completed.stdout


INVALID_CANONICAL_DECLARATIONS = (
    (
        "retired_value_still_in_closed_set",
        "enums:\n  ContentType: [micro, image, video]\n"
        "retired_enum_values:\n  - {enum: ContentType, retired_value: micro}\n",
    ),
    (
        "retired_value_for_undeclared_enum",
        "enums:\n  ContentType: [image, video, article]\n"
        "retired_enum_values:\n  - {enum: MediaType, retired_value: micro}\n",
    ),
    (
        "record_carries_a_third_key",
        "enums:\n  ContentType: [image, video, article]\n"
        "retired_enum_values:\n  - {enum: ContentType, retired_value: micro, accept_on_wire: true}\n",
    ),
    (
        "mapping_instead_of_records",
        "enums:\n  ContentType: [image, video, article]\n"
        "retired_enum_values:\n  ContentType: [micro]\n",
    ),
)


@pytest.mark.parametrize(
    "case,declaration",
    INVALID_CANONICAL_DECLARATIONS,
    ids=[case for case, _ in INVALID_CANONICAL_DECLARATIONS],
)
def test_invalid_canonical_declaration_grants_no_acceptance(
    scanner_tree: Path, case: str, declaration: str
) -> None:
    """声明本身不成立时不产生任何接受，投影与声明文件一起变红。"""
    _declare(scanner_tree, declaration)
    _project(scanner_tree, PROJECTED_RECORD)
    completed = _run_gate(scanner_tree)
    assert completed.returncode == 1, f"{case} 被当成合法声明:\n{completed.stdout}"


@pytest.mark.parametrize(
    "sample,lines",
    [
        (
            "micro_word_senses.dart",
            (
                "final ts = DateTime.now().microsecondsSinceEpoch;",
                "    Future<void>.microtask(_load);",
                "      AppPermissionKind.microphone,",
            ),
        ),
        ("micro_batch.yaml", ("        - micro_batch_window_2ms", "    microblog: { baseTier: tier4 }")),
        ("intersection_moment_tense.yaml", ("    moment: retrospective",)),
    ],
)
def test_declaration_does_not_widen_near_word_handling(
    scanner_tree: Path, sample: str, lines: tuple[str, ...]
) -> None:
    """声明只接受记录里的那一个取值，近似词既不被误伤也不被额外放行。"""
    _declare(scanner_tree, CANONICAL_DECLARATION)
    completed = _scan(scanner_tree, sample, lines)
    assert completed.returncode == 0, f"{sample} 被误伤:\n{completed.stdout}{completed.stderr}"


WEAKENED_CRITERIA = (
    ("micro", r'r"(?<![A-Za-z0-9_-])micro(?![A-Za-z0-9_-])"', r'r"(?<![A-Za-z0-9_-])micro_off(?![A-Za-z0-9_-])"'),
    ("moment", "(?P<moment_quote>['\\\"])moment(?P=moment_quote)", "(?P<moment_quote>['\\\"])moment_off(?P=moment_quote)"),
    ("contentIdentity", 'r"|[Cc]ontent(?:Id|ID)entity(?:Outcome)?(?![A-Za-z0-9_])"', 'r"|[Cc]ontent(?:Id|ID)entityOff(?:Outcome)?(?![A-Za-z0-9_])"'),
    ("displayFormat", 'r"|(?i:display_?format)"', 'r"|(?i:display_?format_off)"'),
    ("promoteToWork", 'r"|(?i:promoted?_?(?:post_?)?to_?work)(?![a-z])"', 'r"|(?i:promoted?_?(?:post_?)?to_?work_off)"'),
    ("note", '(?P<note_quote>[\'\\"])note(?P=note_quote)', '(?P<note_quote>[\'\\"])note_off(?P=note_quote)'),
    ("metricCompound", "(?:moment|photo))(?![A-Za-z0-9_])", "(?:moment_off|photo_off))(?![A-Za-z0-9_])"),
    # 退役取值的接受判据同样只能整体成立：去掉 canonical 声明核对、闭集重叠核对
    # 或记录键闭集，扫描器自身的控制样本立刻阻断启动。
    ("retiredValueDeclaredPair", "not in declared:", "is None:"),
    ("retiredValueClosedSetOverlap", "        if value in closed_set:", "        if value is None:"),
    (
        "retiredValueRecordKeys",
        'set(record) != {"enum", "retired_value"}',
        'set(record) >= {"enum", "retired_value"}',
    ),
)


@pytest.mark.parametrize(
    "rule,original,weakened", WEAKENED_CRITERIA, ids=[rule for rule, _, _ in WEAKENED_CRITERIA]
)
def test_criteria_cannot_be_quietly_weakened(
    scanner_tree: Path, rule: str, original: str, weakened: str
) -> None:
    """判据只能整体成立：删掉任一条,扫描器自身的 control fixture 就会阻断启动。"""
    gate = scanner_tree / GATE.relative_to(ROOT)
    source = gate.read_text(encoding="utf-8")
    assert source.count(original) == 1, f"{rule} 判据原文漂移: {original}"
    gate.write_text(source.replace(original, weakened), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-B", str(gate)], capture_output=True, text=True, timeout=60
    )
    assert completed.returncode != 0, completed.stdout
    assert "missed a control fixture" in completed.stderr, completed.stderr
