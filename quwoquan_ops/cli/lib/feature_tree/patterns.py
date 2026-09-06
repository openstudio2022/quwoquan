"""全部正则与目录/文件闭集常量。"""
from __future__ import annotations

import re

ID_RE = re.compile(r"^#{3,6}\s+(REQ|UAT|DOM|SIT|GWT|DEC|OPEN)-(\d{3,})\b", re.MULTILINE)
ACCEPTANCE_ID_RE = re.compile(r"^#{3,6}\s+(UAT|DOM|SIT|GWT)-(\d{3,})\b", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
PATH_RE = re.compile(
    r"`((?:quwoquan_app|quwoquan_service|quwoquan_data|quwoquan_ops"
    r"|\.github|\.agents|\.codex|\.cursor)(?:/[^`\s；，]+)*)`"
)
ENGINEERING_CLAIM_RE = re.compile(
    r"^-\s+(App|Contracts|Metadata|Service|Data|Ops|CI|Agent)(?:（[^）]*）)?："
)
# 仓库根单例：只允许精确匹配、不作为目录前缀参与归属。闭集而非通用路径语法，
# 避免把 `report.json` 之类任意根文件也纳入 owner 解析。
REPOSITORY_SINGLETON_ROOTS = frozenset(
    {"Makefile", "AGENTS.md", "README.md", "specs/feature-tree/README.md"}
)
SPEC_REF_RE = re.compile(
    r"specs/feature-tree/(?:[A-Za-z0-9_.-]+/)*spec\.md#[A-Za-z0-9_.%\-\u4e00-\u9fff]+"
)
# 绑定标记有两种显式形态：ref 同行前置 `spec_ref` token（注释/常量），或
# 独占一行的 `spec_ref:` 后接连续列表项。裸字符串（fixture、断言消息、文档提及）
# 不构成绑定；`not_a_spec_ref` 子串与 Go `SpecRef:` readiness 字段也故意不匹配。
SPEC_REF_MARKER_RE = re.compile(r"\bspec_ref\b", re.IGNORECASE)
SPEC_REF_BLOCK_MARKER_RE = re.compile(
    r"^\s*(?:[#*/]+\s*)?spec_ref\s*:\s*$", re.IGNORECASE
)
SPEC_REF_BLOCK_ITEM_RE = re.compile(r"^\s*(?:[#*/]+\s*)?-\s+")
SPEC_REF_CODE_SPAN_RE = re.compile(
    r"^\s*spec_ref\s*:\s*(?P<reference>.+?)\s*$",
    re.IGNORECASE,
)
REPO_SPEC_PATH_RE = re.compile(r"`(specs/[A-Za-z0-9_./-]+\.md)(?:#[^`]*)?`")
# 复合验收的结果子句：结果角色的顶层 bullet 是子句的载体。角色只由行首关键字决定，
# `GIVEN`/`WHEN`/`条件：` 是前置条件，`AND` 不表达独立性、只继承最近一条角色 bullet 的角色，
# 因此 `GIVEN` 后的 `AND` 仍是前置条件，`THEN` 后的 `AND` 是另一条结果。
TOP_BULLET_RE = re.compile(r"^-\s+(\S.*)$")
NESTED_BULLET_RE = re.compile(r"^\s+[-*]\s")
PRECONDITION_BULLET_RE = re.compile(r"^(?:GIVEN|WHEN)\b|^条件：")
INHERITING_BULLET_RE = re.compile(r"^AND\b")
# 一个结果 bullet 内部的并列独立结果分隔符。
#
# 中文技术写作里，顶层并列小句必带前置停顿：`；` 本身就是并列小句分隔符，`，` 紧跟
# 并列连词同理。而单一结果的自然表述——定语并列（`非 mutual 且未拉黑的用户`）、
# 形容词并列（`明确且可恢复的终态`、`有序且无重复`）——从不在连词前带停顿。因此以
# 「前置停顿 + 并列连词」为界，能切出真正相互独立、需要各自观测才能证伪的结果，
# 又不会把同一个结果的多个属性拆成噪音。
#
# `以及` 在本仓库只用于并列名词短语（`answerText，以及状态、trace 与恢复状态`），
# 因此不作为分隔符；`并` 排除 `并发/并行/并列/并存` 等构词，避免切开名词。
OUTCOME_CLAUSE_SPLIT_RE = re.compile(r"；|，\s*(?:且|并且|同时|并(?![发行列存]))")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
ACCEPTANCE_SECTION_RE = re.compile(
    r"^#{3,6}\s+((?:UAT|DOM|SIT|GWT)-\d{3,})\b.*?$([\s\S]*?)(?=^#{1,6}\s|\Z)", re.MULTILINE
)
# 子句级 spec_ref：`...spec.md#gwt-004.t2` 绑定该锚点第 2 个结果子句。
CLAUSE_ANCHOR_RE = re.compile(r"^((?:uat|dom|sit|gwt)-\d{3,})\.t(\d+)$")
# 验收锚点闭集与位数的唯一定义点：消费方语义过滤（coverage-map、
# service-architecture、domain-remote 等）引用本常量做「验收锚点 + 可选 .tN
# 子句」判定（group(1) 为剥离子句后的主锚点），不得各自字面枚举闭集——
# 新增锚点类型只改这一处。位数与 ACCEPTANCE_ID_RE 同源为 \d{3,}。
ACCEPTANCE_ANCHOR_RE = re.compile(
    r"^((?:uat|dom|sit|gwt)-\d{3,})(?:\.t\d+)?$", re.IGNORECASE
)
OPEN_BLOCK_RE = re.compile(r"^###\s+(OPEN-\d{3,})\b[\s\S]*?(?=^###\s|^##\s|\Z)", re.MULTILINE)
FORBIDDEN_GLOBALS = (
    "tree_index.yaml",
    "journey_scenario_registry.yaml",
)
FORBIDDEN_NODE_NAMES = {
    "README.md",
    "acceptance.yaml",
    "tree.yaml",
    "plan.md",
    "plan.yaml",
    "tasks.md",
    "tasks.yaml",
}
FORBIDDEN_CENTRAL_PATHS = (
    "specs/changelog",
    "specs/gates",
    "specs/inventories",
    "specs/launch-plan",
    "specs/product",
    "docs/outstanding_risks_backlog.md",
)
EVIDENCE_ROOTS = (
    "quwoquan_app/test",
    "quwoquan_app/scripts",
    "quwoquan_service",
    "quwoquan_data/tests",
    "quwoquan_ops/gate",
    "quwoquan_ops/tests",
)
TEST_SUFFIXES = {".dart", ".go", ".py", ".sh", ".yaml", ".yml"}
VALID_LEVELS = {0: "AppRoot Spec", 1: "L1 Domain Service", 2: "L2 Business Capability", 3: "L3 Story"}
APP_TEST_LAYERS = {"local_contract", "api_integration", "user_acceptance"}
APP_JOURNEY_ENGINEERING_ROOT_RE = re.compile(
    r"^quwoquan_app/test/(?:local_contract|user_acceptance)/journeys/"
    r"[a-z][a-z0-9_]*$"
)
