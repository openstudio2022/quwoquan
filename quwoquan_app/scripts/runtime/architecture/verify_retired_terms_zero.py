#!/usr/bin/env python3
"""Reject retired runtime identifiers without prose scans or path allowlists."""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

import yaml

ROOT = REPO_ROOT
RUNTIME_ROOTS = (
    "quwoquan_app/lib",
    "quwoquan_app/android/app/src",
    "quwoquan_app/ios/Runner",
    "quwoquan_service/contracts/metadata",
    "quwoquan_service/runtime",
    "quwoquan_service/services",
    "quwoquan_data/control_plane",
    "quwoquan_data/scripts/core",
    "quwoquan_data/scripts/content",
    "quwoquan_data/scripts/governance",
    "quwoquan_ops/cli",
    "quwoquan_ops/environments",
    "quwoquan_ops/observability",
    "quwoquan_ops/portal/src",
)

SKIP_DIR_NAMES = {
    ".dart_tool",
    ".qwq_output",
    "__pycache__",
    "build",
    "node_modules",
    "test",
    "tests",
    "testdata",
    "vendor",
}

SOURCE_SUFFIXES = {
    ".dart",
    ".go",
    ".java",
    ".json",
    ".kt",
    ".mjs",
    ".py",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}

# This gate targets executable compatibility identities, not natural-language
# history. Negative tests and governance scanners have their own contract gates.
RETIRED_IDENTIFIER = re.compile(
    r"\b(?:"
    r"(?i:legacy)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]+(?:Legacy|_legacy)[A-Za-z0-9_]*|"
    r"compat(?:Mode|Parser|Shim|Alias|Fallback)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]+Compat(?:Mode|Parser|Shim|Alias|Fallback)[A-Za-z0-9_]*"
    r")\b"
)

# 退役内容轴身份：ContentType.micro、ContentIdentity.moment、Post.contentIdentity、
# 读侧派生 displayFormat、点滴升级作品命令与事件。同上只认可执行的兼容身份，
# 中文说明与散文历史不在范围内。
RETIRED_CONTENT_AXIS = re.compile(
    # ContentType 退役成员只作为独立 token 出现（'micro'、ContentType.micro、YAML
    # 闭集项）。micro-batch、microseconds、microtask、microphone、microblog 是别的
    # 词，不是该成员，因此边界同时排除连字符与下划线。
    r"(?<![A-Za-z0-9_-])micro(?![A-Za-z0-9_-])"
    r"|(?i:content_?(?:type|surface_?kind)_?micro)"
    # ContentIdentity 退役成员只作为值位置的字面量或 Identity 族成员访问出现。
    # 字段名位置是别的字段：intersection 的意图时态 moment 就住在 JSON/YAML key 与
    # 序列化 tag 里，本地时间戳变量同样不带引号。
    r"|(?<![A-Za-z0-9_])(?<!json:)(?<!bson:)(?<!yaml:)(?<!db:)(?<!form:)(?<!query:)"
    r"(?P<moment_quote>['\"])moment(?P=moment_quote)(?!\s*:)"
    r"|[A-Za-z0-9_]*Identity\.moment(?![A-Za-z0-9_])"
    # ContentIdentity 本体，含 codegen 的 ContentIDentity 拼写。snake_case
    # content_identity 在本仓另有语义（release 内容身份、ops 样本身份校验），
    # 不是该枚举的兼容身份。要求标识符右边界，避免将独立 assistant indexing
    # 开关中的 ContentIdentityIndex 当成枚举；规格明确退役的 Outcome 投影仍阻断。
    r"|[Cc]ontent(?:Id|ID)entity(?:Outcome)?(?![A-Za-z0-9_])"
    # 读侧派生轴。
    r"|(?i:display_?format)"
    # 点滴升级作品命令 PromotePostToWork 与事件 PostPromotedToWork；尾部排除小写
    # 续写，避免误伤 to_workspace 一类无关词。
    r"|(?i:promoted?_?(?:post_?)?to_?work)(?![a-z])"
    # 按类型拆分的互动指标不能保留退役类型的组合名；只匹配完整指标标识符，
    # 不把意图时态、WechatMoments、Momentary 或 photo library 当作内容类型。
    r"|(?<![A-Za-z0-9_])(?i:(?:impression|deep_?engage|click|like|share|comment)_?(?:moment|photo))(?![A-Za-z0-9_])"
)

# ContentIdentity 闭集是 {moment, work}：同一行同时出现两个裸成员即闭集声明。
# 单独的意图时态 moment 与工作流语义 work 不会同行出现。
IDENTITY_MEMBER_MOMENT = re.compile(r"(?<![A-Za-z0-9_-])moment(?![A-Za-z0-9_-])")
IDENTITY_MEMBER_WORK = re.compile(r"(?<![A-Za-z0-9_-])work(?![A-Za-z0-9_-])")

# displayFormat 语义下的 note 才是退役展示形态。笔记字段、gathering plan 的
# PlanItemKindNote、认领备注与 JSON 注记都不是展示形态，因此要求同一展示形态
# 词表就在附近：displayFormat 本体，或同一映射里的 photo / micro 兄弟取值。
DISPLAY_FORMAT_NOTE = re.compile(r"(?<![A-Za-z0-9_])(?P<note_quote>['\"])note(?P=note_quote)")
DISPLAY_FORMAT_CONTEXT = re.compile(
    r"(?i:display_?format)|(?P<sibling_quote>['\"])(?:photo|micro)(?P=sibling_quote)"
)
DISPLAY_FORMAT_WINDOW = 6

# 退役取值的 canonical 声明点是共享 enum owner 的 `retired_enum_values`，生成链把
# 同一条记录投影成 Go 记录。两种形态都把 enum 与退役取值绑在同一行，所以退役取值
# 永远不会作为裸字面量出现，而形态里没有第三个键可以夹带别的语义。
RETIRED_VALUE_SOURCE = "quwoquan_service/contracts/metadata/_shared/types.yaml"
RETIRED_VALUE_DECLARATION = re.compile(
    r"\{\s*enum:\s*(?P<enum>[A-Za-z][A-Za-z0-9_]*)\s*,"
    r"\s*retired_value:\s*(?P<value>[A-Za-z0-9_]+)\s*\}"
)
RETIRED_VALUE_PROJECTION = re.compile(
    r"\{\s*Enum:\s*\"(?P<enum>[A-Za-z][A-Za-z0-9_]*)\"\s*,"
    r"\s*RetiredValue:\s*\"(?P<value>[A-Za-z0-9_]+)\"\s*\}"
)


def _declared_retired_values(document: object) -> frozenset[tuple[str, str]]:
    """把 canonical 声明化为被接受的 (enum, 退役取值) 对。

    这不是按位置豁免：声明自身不成立的对根本不进集合，它在任何位置（包括声明
    文件本身与生成投影）都照旧 BLOCK。记录形态不完整、取值空白、enum 未声明，
    以及取值仍在该 enum 的合法闭集内，都不产生任何接受。
    """
    if not isinstance(document, dict):
        return frozenset()
    enums = document.get("enums")
    records = document.get("retired_enum_values")
    if not isinstance(enums, dict) or not isinstance(records, list):
        return frozenset()
    declared: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"enum", "retired_value"}:
            continue
        name, value = record["enum"], record["retired_value"]
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        name, value = name.strip(), value.strip()
        closed_set = enums.get(name)
        if not name or not value or not isinstance(closed_set, list):
            continue
        if value in closed_set:
            continue
        declared.add((name, value))
    return frozenset(declared)


def _canonical_retired_values(root: Path) -> frozenset[tuple[str, str]]:
    """读取 canonical 声明；缺失或无法解析时返回空集合，于是不接受任何退役取值。"""
    source = root / RETIRED_VALUE_SOURCE
    if not source.is_file():
        return frozenset()
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return frozenset()
    return _declared_retired_values(document)


def _without_retired_value_records(
    line: str, declared: frozenset[tuple[str, str]]
) -> str:
    """只屏蔽 canonical 记录里的那一个退役取值，行内其余内容照常受全部判据约束。"""

    def mask(match: re.Match[str]) -> str:
        if (match.group("enum"), match.group("value")) not in declared:
            return match.group(0)
        record = match.group(0)
        start, end = match.span("value")
        offset = match.start()
        return record[: start - offset] + " " * (end - start) + record[end - offset :]

    for pattern in (RETIRED_VALUE_DECLARATION, RETIRED_VALUE_PROJECTION):
        line = pattern.sub(mask, line)
    return line


def _is_runtime_source(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return False
    if path.name == "package-lock.json":
        return False
    if path.suffix not in SOURCE_SUFFIXES:
        return False
    return not (
        path.name.endswith("_test.go")
        or path.name.endswith("_test.dart")
        or path.name.startswith("test_")
    )


# 字符串优先于注释，保留 URL、wire 字面量及 Go struct tag；屏蔽时保留换行以维持定位。
QUOTED_TOKEN = r'''"""[\s\S]*?"""|\x27\x27\x27[\s\S]*?\x27\x27\x27|"(?:\\.|[^"\\])*"|'(?:\\.|''|[^'\\])*'|`[^`]*`'''
YAML_DESCRIPTION = re.compile(r'''(?<![^\s{,?])(?:description|"description"|'description')[ \t]*:[ \t]*''')
YAML_TOKEN = re.compile(QUOTED_TOKEN + r"|[^\s]")


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _without_comments(text: str, suffix: str) -> str:
    comments = r"\#[^\n]*" if suffix in {".py", ".sh", ".yaml", ".yml"} else r"//[^\n]*|/\*[\s\S]*?\*/"
    if suffix in {".yaml", ".yml"}:
        comments = r"(?<!\S)\#[^\n]*"
    if suffix == ".json":
        return text
    tokens = re.compile(f"({QUOTED_TOKEN})|(?:{comments})")
    return tokens.sub(lambda match: match.group(0) if match.group(1) else _blank(match.group(0)), text)


def _yaml_description_end(text: str, token: re.Match[str], flow_depth: int) -> int:
    if flow_depth:
        return next(
            (part.start() for part in YAML_TOKEN.finditer(text, token.end())
             if part.group(0) in {",", "}", "]"}),
            len(text),
        )
    # block scalar、折叠标量、普通多行标量均由缩进决定边界。
    line_start = text.rfind("\n", 0, token.start()) + 1
    prefix = text[line_start:token.start()]
    indent = len(prefix) if prefix.strip() == "-" else len(prefix) - len(prefix.lstrip())
    end = text.find("\n", token.end())
    if end < 0:
        return len(text)
    end += 1
    for line in text[end:].splitlines(keepends=True):
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        end += len(line)
    return end


def _without_yaml_descriptions(text: str) -> str:
    """只移除 description 的标量值，绝不忽略整行或同行其他映射成员。"""
    tokens = re.compile(YAML_DESCRIPTION.pattern + "|" + QUOTED_TOKEN + r"|[^\s]")
    masked = list(text)
    flow_depth = 0
    skip_until = 0
    for token in tokens.finditer(text):
        if token.start() < skip_until:
            continue
        value = token.group(0)
        if value in {"{", "["}:
            flow_depth += 1
        elif value in {"}", "]"}:
            flow_depth -= 1
        elif YAML_DESCRIPTION.fullmatch(value):
            start = token.end()
            # 容器值不是自然语言描述；必须继续扫描其中的 executable 内容。
            if text[start:start + 1] in {"{", "["}:
                continue
            end = _yaml_description_end(text, token, flow_depth)
            masked[start:end] = _blank(text[start:end])
            skip_until = end
    return "".join(masked)


def _findings(
    relative_path: str,
    lines: list[str],
    declared_retired: frozenset[tuple[str, str]],
) -> list[str]:
    suffix = Path(relative_path).suffix
    text = _without_comments("\n".join(lines), suffix)
    if suffix in {".yaml", ".yml"}:
        text = _without_yaml_descriptions(text)
    lines = [
        _without_retired_value_records(line, declared_retired)
        for line in text.split("\n")
    ]
    findings: list[str] = []
    for index, line in enumerate(lines):
        line_number = index + 1
        for pattern in (RETIRED_IDENTIFIER, RETIRED_CONTENT_AXIS):
            match = pattern.search(line)
            if match:
                findings.append(f"{relative_path}:{line_number}:{match.group(0)}")
        # 下面两条判据各自都要求行内出现字面子串，所以先做子串预筛与直接跑正则等价，
        # 只是省掉大部分行的回溯开销。
        if ("moment" in line and "work" in line
                and IDENTITY_MEMBER_MOMENT.search(line) and IDENTITY_MEMBER_WORK.search(line)):
            findings.append(f"{relative_path}:{line_number}:ContentIdentity{{moment,work}}")
        note = DISPLAY_FORMAT_NOTE.search(line) if "note" in line else None
        window = lines[max(0, index - DISPLAY_FORMAT_WINDOW) : index + DISPLAY_FORMAT_WINDOW + 1]
        if note and any(DISPLAY_FORMAT_CONTEXT.search(near) for near in window):
            findings.append(f"{relative_path}:{line_number}:displayFormat={note.group(0)}")
    return findings


def _self_test() -> None:
    declared = frozenset({("ContentType", "micro")})
    rejected = (
        ("final legacyAvailable = true;",),
        ('const wireKey = "legacyMedia";',),
        ("compatMode: enabled",),
        ("ImpressionMoment atomic.Int64",),
        ('"deep_engage_moment": counter.Load(),',),
        ("ClickPhoto atomic.Int64",),
        ('"comment_photo": counter.Load(),',),
        ("report_dir_legacy = output",),
        ("      case ContentType.micro:",),
        ("enum ContentSurfaceKind { micro, image, video, article }",),
        ("      'contentType': 'micro',",),
        ('  static const String searchContentTypeMicro = "text";',),
        ("      identity: 'moment',",),
        ('	if p.ContentIdentity != "moment" {',),
        ("        return CreateContentIdentity.moment;",),
        ("enum CreateContentIdentity { moment, work }",),
        ('VALID_WORKS_AFFINITIES = ("work_strong", "work", "neutral", "moment")',),
        ("  final identity = wire.contentIdentity?.trim() ?? '';",),
        ("	ContentIdentity   string   `json:\"contentIdentity\"`",),
        ("      - {name: contentIdentity, type: ContentIdentity}",),
        ("type ContentIDentity string",),
        ("String? contentIdentityOutcome;",),
        ("class AppTelemetryValueContentIdentityOutcome {}",),
        ("- {description: 'micro 已退役', values: [micro, image]}",),
        ("- {values: [micro, image], description: micro 已退役}",),
        ("- {description: '不用 micro', type: ContentIDentity}",),
        ("        displayFormat: switch (type) {",),
        ("  bool get isTextOnly => displayFormat == 'note' && !hasAnyMedia;",),
        ('	case "PromotePostToWork":',),
        ("      metric: 'content_post_promote_to_work',",),
        ("	OperationID: \"content.post.PostPromotedToWork\",",),
        ("        displayFormat: switch (type) {", "          'article' => 'note',", "        };"),
        ('	case "photo":', '		return "image"', '	case "note":', '		return "article"'),
        # canonical 记录的近似形态不构成声明：键名不对、缺 enum 归属、夹带第三个
        # 键、记录外的裸键，以及手写常量，都必须照旧命中。
        ("  - {enum: ContentType, value: micro}",),
        ("  - {enum: ContentType, retired: micro}",),
        ("  - {retired_value: micro}",),
        ("  - {enum: ContentType, retired_value: micro, accept_on_wire: true}",),
        ("  retired_value: micro",),
        ('	const retiredContentType = "micro"',),
        ('	{RetiredValue: "micro"},',),
        ('	{Enum: "ContentType", RetiredValue: "micro", Accept: true},',),
        # 形态正确但这一对没有 canonical 声明：别的 enum 借不到 ContentType 的声明。
        ("  - {enum: MediaType, retired_value: micro}",),
        ('	{Enum: "MediaType", RetiredValue: "micro"},',),
        # 整个 enum 已退役时不得借退役槽复活它的成员。
        ("  - {enum: ContentIdentity, retired_value: moment}",),
    )
    accepted = (
        ("- {name: enableAssistantContentIdentityIndex, type: bool}",),
        ("EnableAssistantContentIdentityIndex *bool",),
        ("?flags.enableAssistantContentIdentityIndex,",),
        ("description: micro 与 ContentIdentity 已退役",),
        ("- {name: contentType, description: micro 已退役}",),
        ("description: |", "  micro 已退役", "type: string"),
        ("final availability = OneTapAvailability.available;",),
        ("compatibleRuntimeVersion: current",),
        ("final comparison = left == right;",),
        ("        - micro_batch_window_2ms          # micro-batch merge",),
        ("    microblog: { baseTier: tier4_casual }",),
        ("final ts = DateTime.now().microsecondsSinceEpoch;",),
        ("    Future<void>.microtask(_load);",),
        ("      AppPermissionKind.microphone,",),
        ("	issuedAt := time.Now().UTC().Truncate(time.Microsecond)",),
        ("	elapsed := float64(time.Since(started).Microseconds()) / 1000.0",),
        ("	return strconv.FormatInt(now.UnixMicro(), 36)",),
        ("    moment: retrospective",),
        ('  "moment": "prospective",',),
        ("	Moment  string  `json:\"moment\"`",),
        ("- name: moment",),
        ("    moment: str",),
        ("    moment = now if now is not None else int(time.time())",),
        ('        "checkedAt": moment,',),
        ("enum NativeShareTarget { wechatFriend, wechatMoments }",),
        ("                    : 'wechat_moments',",),
        ("        readback.createdAt.isAtSameMomentAs(receipt.createdAt);",),
        ("          momentId: marker['momentId'] as String,",),
        ('  "trip-moment-content-link": { "owner": "content" }',),
        ('var IntersectionMoments = []string{"retrospective", "current"}',),
        ("def _content_identity(value: object, *, field: str) -> str:",),
        ("    identity = load_release_content_identity(release_root)",),
        ("	PlanItemKindNote PlanItemKind = \"note\"",),
        ("      note: (json['note'] as String?)?.trim() ?? '',",),
        ("	Note  string  `json:\"note\"`",),
        ('  "notes": ["first"],',),
        ("    await center.publish(Notification.draftSaved);",),
        ("    articleTemplate: ArticleTemplate.notePaper,",),
        ('    summary["note"] = "lane acceptance only"',),
        ("    workspacePromotion = resolve_promote_to_workspace(plan)",),
    )
    for fixture in rejected:
        if not _findings("self_test.yaml", list(fixture), declared):
            raise AssertionError(
                f"retired identifier detector missed a control fixture: {fixture!r}"
            )
    for fixture in accepted:
        rejections = _findings("self_test.yaml", list(fixture), declared)
        if rejections:
            raise AssertionError(
                f"retired identifier detector rejected a current fixture: {rejections}"
            )
    _self_test_retired_declaration(declared)


def _self_test_retired_declaration(declared: frozenset[tuple[str, str]]) -> None:
    """canonical 声明与其生成投影必须成对成立：声明在，两者都通过；声明不在，
    两者都 BLOCK。缺了后半句，任何文件抄一份记录形态就能自行豁免。"""
    canonical = (
        ("self_test.yaml", ("  - {enum: ContentType, retired_value: micro}",)),
        ("self_test.go", ('\t{Enum: "ContentType", RetiredValue: "micro"},',)),
    )
    for path, fixture in canonical:
        rejections = _findings(path, list(fixture), declared)
        if rejections:
            raise AssertionError(
                f"retired value declaration missed a control fixture: {rejections}"
            )
        if not _findings(path, list(fixture), frozenset()):
            raise AssertionError(
                "retired value declaration missed a control fixture: "
                f"{fixture!r} was accepted without a canonical declaration"
            )
    live = {"enums": {"ContentType": ["image", "video", "article"]}}
    valid = {**live, "retired_enum_values": [{"enum": "ContentType", "retired_value": "micro"}]}
    if _declared_retired_values(valid) != declared:
        raise AssertionError(
            "retired value declaration missed a control fixture: canonical record was not resolved"
        )
    invalid = {
        "blank value": [{"enum": "ContentType", "retired_value": "  "}],
        "still in closed set": [{"enum": "ContentType", "retired_value": "article"}],
        "unknown enum": [{"enum": "MediaType", "retired_value": "micro"}],
        "missing enum": [{"retired_value": "micro"}],
        "extra key": [{"enum": "ContentType", "retired_value": "micro", "accept_on_wire": True}],
        "mapping instead of records": {"ContentType": ["micro"]},
    }
    for name, records in invalid.items():
        if _declared_retired_values({**live, "retired_enum_values": records}):
            raise AssertionError(
                f"retired value declaration missed a control fixture: {name} was accepted"
            )


def main() -> int:
    _self_test()
    declared_retired = _canonical_retired_values(ROOT)
    findings: list[str] = []
    for relative_root in RUNTIME_ROOTS:
        source_root = ROOT / relative_root
        if not source_root.exists():
            continue
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or not _is_runtime_source(path.relative_to(ROOT)):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            findings.extend(
                _findings(
                    path.relative_to(ROOT).as_posix(), lines, declared_retired
                )
            )

    if findings:
        print("verify_retired_terms_zero: FAIL")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("verify_retired_terms_zero: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
