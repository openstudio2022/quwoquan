#!/usr/bin/env python3
"""逐文件审计特性树规格、设计与当前工程证据的一致性。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURE_TREE_MODULE = Path(__file__).with_name("feature_tree.py")
OUTPUT_ROOT = REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "feature-tree"
TEMPLATE_ROOT = REPO_ROOT / "specs" / "templates" / "feature-tree"

SPEC = importlib.util.spec_from_file_location("directory_native_feature_tree", FEATURE_TREE_MODULE)
assert SPEC and SPEC.loader
feature_tree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = feature_tree
SPEC.loader.exec_module(feature_tree)


SPEC_SECTIONS = {
    0: (
        "1. 产品目标与用户价值",
        "2. 范围与非目标",
        "3. 术语与全局要求",
        "4. 用户旅程",
        "5. 全局验收",
    ),
    1: (
        "1. 目标与用户价值",
        "2. 领域边界",
        "3. Journey / Scenario 职责",
        "4. 业务能力",
        "5. 领域要求",
        "6. 领域验收",
        "7. 工程归属",
    ),
    2: (
        "1. 能力目标",
        "2. 范围与非目标",
        "3. Journey / Scenario 贡献",
        "4. Story",
        "5. 能力要求",
        "6. 契约与依赖",
        "7. 集成验收",
    ),
    3: (
        "1. 用户价值",
        "2. 范围与非目标",
        "3. 行为要求",
        "4. 契约引用",
        "5. 验收场景",
        "6. 依赖",
    ),
}

DESIGN_SECTIONS = {
    0: (
        "1. 背景、设计目标与非目标",
        "2. 全局上下文与所有权",
        "3. 跨域协作与数据流",
        "4. 全局架构",
        "5. 关键决策",
        "6. 质量与运行约束",
        "7. 失败与恢复",
    ),
    1: (
        "1. 背景与设计目标",
        "2. 领域模型与所有权",
        "3. 上下文边界与协作",
        "4. 架构与数据流",
        "5. 关键决策",
        "6. 质量与运行约束",
        "7. 失败与恢复",
    ),
    2: (
        "1. 背景、目标与非目标",
        "2. Story 协作与状态流",
        "3. 端云与数据流",
        "4. 关键决策",
        "5. 失败与恢复",
        "6. 质量与观测",
    ),
}

SPEC_OPTIONAL_SECTIONS = {
    0: ("6. 开放事项",),
    1: ("8. 开放事项",),
    2: ("8. 开放事项",),
    3: ("7. 开放事项",),
}

DESIGN_OPTIONAL_SECTIONS = {
    0: ("8. 迁移与回滚",),
    1: ("8. 迁移与回滚",),
    2: ("7. 迁移与回滚",),
}

TEMPLATE_CONTRACTS = {
    "app-root-spec.md": ("AppRoot Spec Template", SPEC_SECTIONS[0], ("REQ-001", "UAT-001")),
    "app-root-design.md": ("AppRoot Design Template", DESIGN_SECTIONS[0], ("DEC-001",)),
    "l1-spec.md": ("L1 Spec Template", SPEC_SECTIONS[1], ("REQ-001", "DOM-001")),
    "l1-design.md": ("L1 Design Template", DESIGN_SECTIONS[1], ("DEC-001",)),
    "l2-spec.md": ("L2 Spec Template", SPEC_SECTIONS[2], ("REQ-001", "SIT-001")),
    "l2-design.md": ("L2 Design Template", DESIGN_SECTIONS[2], ("DEC-001",)),
    "l3-spec.md": ("L3 Spec Template", SPEC_SECTIONS[3], ("REQ-001", "GWT-001")),
}

FORBIDDEN_CONTENT = (
    (re.compile(r"待补充"), "存在待补充占位"),
    (re.compile(r"必须满足“.*”的核心行为："), "REQ 保留批量迁移的核心行为套话"),
    (
        re.compile(r"成功时必须返回可观察结果；失败时必须返回 canonical failure，且不得写入成功事实"),
        "REQ 保留全节点重复的成功失败套话",
    ),
    (re.compile(r"最小价值点闭环"), "使用空泛最小价值占位"),
    (re.compile(r"细化 .+特性的功能边界与端云协同行为"), "使用空泛特性描述"),
    (re.compile(r"完成[“`].+[”`]的最小可观察行为"), "In Scope 仅复述节点名"),
    (re.compile(r"满足规格声明的前置条件"), "GIVEN 未声明具体条件"),
    (re.compile(r"对应用户或系统动作"), "WHEN 未声明具体动作"),
    (re.compile(r"前置条件明确"), "GIVEN 使用占位语句"),
    (re.compile(r"用户或系统动作发生"), "WHEN 使用占位语句"),
    (re.compile(r"可观察结果符合预期"), "THEN 使用占位语句"),
    (re.compile(r"能力内 Story 组合、状态机、异常路径和端云协同可验证"), "能力要求未表达业务结果"),
    (re.compile(r"稳定业务结果并交给下游"), "Journey 输出未表达具体事实"),
    (re.compile(r"作为用户或平台调用方"), "L3 未声明具体参与者"),
    (re.compile(r"从而获得可观察、可恢复的独立价值"), "L3 未声明具体价值"),
    (re.compile(r"遵循对应规格声明的边界，并通过公开契约协作"), "design 使用迁移占位"),
    (re.compile(r"当前有效架构边界"), "DEC 标题未表达具体决定"),
    (re.compile(r"由三层特性树迁移脚本补齐"), "保留迁移脚本历史"),
    (re.compile(r"来源迁移"), "保留来源迁移历史"),
    (re.compile(r"当前无额外迁移；变更采用原子切换并删除旧实现"), "保留空迁移章节"),
    (re.compile(r"\bCR-[A-Za-z0-9-]+"), "引用已退役 changelog"),
    (re.compile(r"^###\s+REQ-\d{3,}\s+现行边界约束\s*$", re.MULTILINE), "REQ 标题未表达具体要求"),
    (
        re.compile(r"基于 runtime L2 能力完成该子特性的可复用封装"),
        "使用 runtime 批量迁移占位语义",
    ),
    (re.compile(r"owner 领域公开 (?:query/projection|command)"), "依赖未声明具体事实或 owner"),
    (
        re.compile(r"canonical command/query/event 可观察结果"),
        "Journey 职责未声明具体交付结果",
    ),
    (
        re.compile(r"本领域负责：为“.+?”交付本领域拥有的业务结果"),
        "Journey 职责仅复制 AppRoot 叙事",
    ),
    (
        re.compile(r"本能力接收：完成“.+?”所需的上游公开事实"),
        "能力输入仅复制 AppRoot 叙事",
    ),
    (
        re.compile(r"契约与字段策略必须与 OpenAPI 与 metadata 保持一致"),
        "使用已退役的 OpenAPI/中心 metadata 权威口径",
    ),
    (re.compile(r"A\d+(?:/A\d+)+ 必须可验证"), "引用已退役验收轴编号"),
    (re.compile(r"\bR-[A-Z][A-Za-z0-9~-]*\b"), "引用已退役 backlog 编号"),
    (re.compile(r"\b(?:DK|KD)\d+\b"), "引用已退役决策清单编号"),
    (re.compile(r"(?:本次 PRD|PRD baseline|保留记录路径名)"), "保留迁移或 PRD 阶段口径"),
    (re.compile(r"(?:：。|：，|；。)"), "存在迁移残留的病句标点"),
    (
        re.compile(r"字段演进、迁移\s*/?\s*回填、必要时双读双写(?:方案)?"),
        "设计仍允许双读双写兼容轨",
    ),
    (
        re.compile(r"^###\s+DEC-\d{3,}.+采用单一事实 owner 与公开契约\s*$", re.MULTILINE),
        "DEC 标题使用通用治理占位",
    ),
    (
        re.compile(r"规格拥有业务语义，metadata 拥有 wire 契约，代码与测试分别承担实现与证据"),
        "DEC 内容使用全局治理占位",
    ),
    (
        re.compile(r"在节点外维护第二套索引、状态或兼容语义"),
        "被否决方案使用全局治理占位",
    ),
    (
        re.compile(r"下层设计只能细化规格，不得覆盖父级边界"),
        "设计影响使用全局治理占位",
    ),
    (re.compile(r"(?:本轮|最新需求|最新基线|记录上)"), "使用会话或历史时间口径"),
    (
        re.compile(r"(?:已归档|迁移前|此前|测试已绿|本期|下一轮|另会话|可以推进|当前实现同步|spec\.md 状态)"),
        "使用历史状态或阶段性计划口径",
    ),
    (re.compile(r"\b20\d{2}-\d{2}(?:-\d{2})?\b"), "在当前规格或设计中冻结日期快照"),
    (
        re.compile(r"(?:per-op ready|当前 blocked|测试已绿|\b全绿\b|metadata v3)"),
        "使用阶段状态、测试日报或退役契约版本口径",
    ),
    (
        re.compile(
            r"(?:当前变更|该 Journey 冻结|该节点负责冻结|该 Scenario 用来冻结|本次只冻结|规格、设计、验收与计划已落地|已迁移 canonical run evidence)"
        ),
        "保留会话增量、冻结或迁移记录",
    ),
    (
        re.compile(r"(?:我希望系统提供[“\"]|我希望能够按[“\"].+公开规则完成目标|通过父能力公开入口完成|父能力公开入口执行|使调用方能够)"),
        "使用批量迁移生成的通用用户价值或行为占位",
    ),
    (
        re.compile(r"(?:从而获得一致、可诊断且可复现的工程能力|从而完成有证据、可恢复的主页操作)"),
        "用户价值仍使用批量迁移的通用结果占位",
    ),
    (re.compile(r"^###\s+(?:REQ|DEC)-\d{3,}.*….*$", re.MULTILINE), "标题包含截断省略号"),
    (re.compile(r"^-.+：-\s+", re.MULTILINE), "父子说明保留机械拼接列表标记"),
    # Markdown 模板中的 ``<角色>`` 需要阻断；规格使用的显式 HTML 锚点不是占位符。
    (
        re.compile(
            r"<(?:中文名称|l[123]-id|用户或平台调用方|完成一个可观察行为|获得独立价值|要求标题|标题)>"
        ),
        "存在模板占位符",
    ),
)


@dataclass
class Review:
    path: str
    kind: str
    issues: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    repo_refs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def h2_sections(text: str) -> list[str]:
    return re.findall(r"^##\s+(.+?)\s*$", text, re.MULTILINE)


def section_body(text: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end].strip()


def substantive_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "<a ", ">")) or line in {"- 无", "无", "不适用"}:
            continue
        lines.append(line)
    return lines


def validate_sections(
    review: Review,
    text: str,
    expected: tuple[str, ...],
    optional: tuple[str, ...] = (),
) -> None:
    actual = h2_sections(text)
    positions: list[int] = []
    for heading in expected:
        if heading not in actual:
            review.issues.append(f"缺少章节 `{heading}`")
            continue
        positions.append(actual.index(heading))
        if not substantive_lines(section_body(text, heading)):
            review.issues.append(f"章节 `{heading}` 没有实质内容")
    if positions != sorted(positions):
        review.issues.append("核心章节顺序不符合模板")
    unexpected = [heading for heading in actual if heading not in {*expected, *optional}]
    if unexpected:
        review.issues.append(f"存在模板外章节 `{unexpected[0]}`")
    allowed_actual = [heading for heading in actual if heading in {*expected, *optional}]
    expected_actual = [*expected, *(heading for heading in optional if heading in actual)]
    if allowed_actual != expected_actual and "核心章节顺序不符合模板" not in review.issues:
        review.issues.append("核心章节顺序不符合模板")


def validate_content(review: Review, text: str) -> None:
    for pattern, message in FORBIDDEN_CONTENT:
        if pattern.search(text):
            review.issues.append(message)

    for raw in text.splitlines():
        if raw.count("（") != raw.count("）"):
            review.issues.append(f"中文括号不完整，疑似机械迁移截断 `{raw[:56]}`")
            break

    behavioral_text = re.split(r"^##\s+\d+\.\s+开放事项\s*$", text, maxsplit=1, flags=re.MULTILINE)[0]
    test_as_behavior = re.search(
        r"(?:测试通过|单测证明|测试证明|测试覆盖|local_contract 有断言|api_integration 有断言|user_acceptance 有断言|聚合测试覆盖)",
        behavioral_text,
    )
    evidence_domains = (
        "runtime/runtime-testinfra/",
        "runtime/runtime-test-pyramid/",
        "runtime/system-architecture-and-engineering-guide/",
        "discovery-content/content-service-contract-foundation/three-layer-test-contract/",
        "platform-ops-governance/commercial-readiness-risk-closure/",
        "runtime/runtime-external-integration/provider-adapter-conformance-suite/",
        "runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/",
        "runtime/development-workflow-governance/",
        "runtime/runtime-agentpack/",
        "runtime/runtime-external-integration/",
        "object-homepage-network/intersection-unified-experience/object-homepage-gamma-real-data-closure/",
        "user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/",
        "global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/",
        "runtime/runtime-client-foundation/app-remote-config/",
    )
    if test_as_behavior and not any(domain in review.path for domain in evidence_domains):
        review.issues.append("行为要求或验收把测试实现当成产品结果")

    behavior_acceptance_sections: list[str] = []
    for heading in ("3. 行为要求", "5. 验收场景", "5. 能力要求", "7. 集成验收"):
        body = section_body(text, heading)
        if body:
            behavior_acceptance_sections.append(body)
    detailed_test_proof = re.search(
        r"(?:local_contract|api_integration|user_acceptance|Widget 测试|contract 测试|协议测试|测试证据|测试断言|测试通过|测试覆盖|单测|spec_ref)",
        "\n".join(behavior_acceptance_sections),
    )
    if (
        detailed_test_proof
        and not any(domain in review.path for domain in evidence_domains)
        and "行为要求或验收把测试实现当成产品结果" not in review.issues
    ):
        review.issues.append("行为要求或验收包含应留在测试代码中的证据细节")

    lines = text.splitlines()
    for index, raw in enumerate(lines):
        heading = re.match(r"^### (?:REQ|DEC|UAT|DOM|SIT|GWT|OPEN)-\d+\s+(.+)$", raw)
        if not heading:
            continue
        title = heading.group(1).strip("` ")
        for following in lines[index + 1 : index + 6]:
            if not following.startswith("- "):
                continue
            body = following[2:].strip()
            candidates = (body, re.sub(r"^(?:系统|本领域|本能力)", "", body))
            for candidate in candidates:
                if not candidate.startswith(title):
                    continue
                suffix = candidate[len(title) :]
                if 0 < len(suffix) <= 12 and suffix[0] not in "。；：，、）)":
                    review.issues.append(f"三级标题疑似为正文截断前缀 `{raw[:56]}`")
                    break
            else:
                continue
            break
        if review.issues and review.issues[-1].startswith("三级标题疑似"):
            break

    if "Design" in review.kind:
        normalized_lines: dict[str, int] = {}
        for raw in text.splitlines():
            line = raw.strip()
            if len(line) < 20 or line.startswith(
                ("#", ">", "```", "- canonical：", "- 关联要求：", "- 关联验收：")
            ):
                continue
            normalized_lines[line] = normalized_lines.get(line, 0) + 1
        duplicates = [line for line, count in normalized_lines.items() if count > 1]
        if duplicates:
            review.issues.append(f"存在重复长句 `{duplicates[0][:56]}…`")

    dangling = re.findall(
        r"^- (?:关键设计决策|选型决策|当前状态|现有代码与目标态对照|状态机与状态迁移|数据流（目标态）|设计目标|设计原则|数据流|边界|观测|回滚|降级与回滚|范围与目标|现状与问题|核心规则|当前实现|目标态|当前目标结构|目标链|状态机|迁移策略)[:：]?\s*$",
        text,
        re.MULTILINE,
    )
    if dangling:
        review.issues.append(f"存在无内容的设计残片 `{dangling[0]}`")
    if re.search(r"^-.+(?:；.+){2,}$", text, re.MULTILINE):
        review.issues.append("存在由历史文档机械拼接的多段列表项")
    if "Design" in review.kind:
        if re.search(r"^- \d+\.\s+", text, re.MULTILINE):
            review.issues.append("设计保留旧文档编号列表残片")
        if re.search(r"^- .+(?:：|,|，|、|；)\s*$", text, re.MULTILINE):
            review.issues.append("设计存在未完成的列表句")
        if re.search(
            r"(?:只通过对应 spec 引用的公开 command/query/event 协作|本次设计|本次 `/design`|后续 `/dev`|spec\.md 已|设计状态|迁移后目标态)",
            text,
        ):
            review.issues.append("设计保留会话阶段、迁移状态或通用占位口径")


def validate_title(review: Review, text: str, node: feature_tree.Node) -> None:
    first = text.splitlines()[0] if text else ""
    if node.level > 0 and f"(`{node.node_id}`)" not in first:
        review.issues.append(f"标题 ID 与目录 `{node.node_id}` 不一致")
    display = re.sub(r"^# [^：]+：", "", first)
    display = re.sub(r"\s+\(`[^`]+`\)\s*$", "", display)
    if node.level > 0 and not re.search(r"[\u4e00-\u9fff]", display):
        review.issues.append("标题缺少便于人工评审的中文名称")
    if first.count("(") != first.count(")") or first.count("（") != first.count("）"):
        review.issues.append("标题括号不完整，疑似机械迁移截断")


def validate_acceptance(review: Review, text: str, node: feature_tree.Node, refs: dict[str, set[str]]) -> None:
    expected_kind = {0: "UAT", 1: "DOM", 2: "SIT", 3: "GWT"}[node.level]
    review.acceptance = feature_tree.acceptance_ids(node.spec)
    if not review.acceptance:
        review.issues.append(f"缺少 {expected_kind} 验收锚点")
        return
    if any(not item.startswith(expected_kind + "-") for item in review.acceptance):
        review.issues.append(f"验收锚点必须只使用 {expected_kind}")
    pending = feature_tree.acceptance_refs_in_open(node.spec)
    all_refs = {ref for values in refs.values() for ref in values}
    clause_counts = feature_tree.acceptance_clause_counts(node.spec)
    for acceptance_id in review.acceptance:
        canonical = feature_tree.canonical_spec_ref(node.spec, acceptance_id)
        clause_refs = {
            f"{canonical}.t{index}"
            for index in range(1, clause_counts.get(acceptance_id, 0) + 1)
        }
        if canonical in all_refs or bool(clause_refs & all_refs):
            review.evidence.append(canonical)
        elif acceptance_id not in pending:
            review.issues.append(f"{acceptance_id} 既无真实 spec_ref，也未由同节点 OPEN 声明未完成")
    review.open_items = [item for item in feature_tree.ids(node.spec) if item.startswith("OPEN-")]

    body = section_body(text, {0: "5. 全局验收", 1: "6. 领域验收", 2: "7. 集成验收", 3: "5. 验收场景"}[node.level])
    for acceptance_id in review.acceptance:
        match = re.search(
            rf"^###\s+{re.escape(acceptance_id)}\b[\s\S]*?(?=^##\s+|^###\s+(?:{expected_kind}|OPEN)-\d+\b|\Z)",
            body,
            re.MULTILINE,
        )
        block = match.group(0) if match else ""
        if node.level in (0, 2, 3):
            for keyword in ("GIVEN", "WHEN", "THEN"):
                if not re.search(rf"^- {keyword}\b", block, re.MULTILINE):
                    review.issues.append(f"{acceptance_id} 缺少 {keyword}")
            if re.search(r"^- (?!(?:GIVEN|WHEN|THEN|AND)\b)", block, re.MULTILINE):
                review.issues.append(
                    f"{acceptance_id} 存在未标记为 GIVEN/WHEN/THEN/AND 的步骤"
                )
        elif not re.search(r"^- (?:条件|可观察结果|禁止结果)：", block, re.MULTILINE):
            review.issues.append(f"{acceptance_id} 未按领域条件/结果格式书写")


def validate_open_items(review: Review, text: str, node: feature_tree.Node) -> None:
    details = feature_tree.open_item_details(node)
    review.open_items = [str(item["id"]) for item in details]
    if not details:
        return
    expected_heading = {0: "6. 开放事项", 1: "8. 开放事项", 2: "8. 开放事项", 3: "7. 开放事项"}[node.level]
    if expected_heading not in h2_sections(text):
        review.issues.append(f"OPEN 未归入 `{expected_heading}`")
    semantic_items: dict[tuple[str, ...], str] = {}
    for item in details:
        item_id = str(item["id"])
        item_type = str(item["type"])
        priority = str(item["priority"])
        release_impact = str(item["releaseImpact"])
        if item_type not in {"capability_gap", "external_blocker", "risk", "future_plan"}:
            review.issues.append(f"{item_id} 类型非法或缺失")
        if priority not in {"P0", "P1", "P2", "P3"}:
            review.issues.append(f"{item_id} 优先级非法或缺失")
        if release_impact not in {"block", "track"}:
            review.issues.append(f"{item_id} 准出影响非法或缺失")
        if not str(item["impactOrValue"]).strip():
            review.issues.append(f"{item_id} 缺少影响或价值")
        if not str(item["completion"]).strip():
            review.issues.append(f"{item_id} 缺少完成判定")
        if item_type == "capability_gap" and not re.match(
            r"(?:尚|缺|未|仍|当前|存在|无法|不能|不得|不可|需要|依赖|缺口)",
            str(item["impactOrValue"]).strip(),
        ):
            review.issues.append(f"{item_id} 未明确说明尚缺的实现或验收证据")
        semantic_key = tuple(
            re.sub(r"OPEN-\d{3,}|\s+", "", str(item[field]))
            for field in (
                "type",
                "priority",
                "releaseImpact",
                "impactOrValue",
                "completion",
                "dependency",
            )
        )
        if semantic_key in semantic_items:
            review.issues.append(
                f"{item_id} 与 {semantic_items[semantic_key]} 是同一未完成事项的重复登记"
            )
        else:
            semantic_items[semantic_key] = item_id


def validate_child_descriptions(review: Review, text: str, node: feature_tree.Node) -> None:
    if node.level not in (1, 2):
        return
    heading = "4. 业务能力" if node.level == 1 else "4. Story"
    body = section_body(text, heading)
    for child_id, description in re.findall(r"^- \[`([^`]+)`\]\([^)]*\)：(.+)$", body, re.MULTILINE):
        normalized = description.strip().rstrip("。`).")
        if normalized.lower().replace(" ", "-") == child_id.lower() or normalized in {child_id, f"L3 场景：{child_id}"}:
            review.issues.append(f"子节点 `{child_id}` 说明只复制目录名")


def validate_repo_refs(review: Review, text: str) -> None:
    refs = sorted(set(feature_tree.PATH_RE.findall(text)))
    review.repo_refs = refs
    for ref in refs:
        path = ref.split("#", 1)[0]
        # 模板路径和 glob 表达的是目录契约，不应当成一个字面文件检查。
        if any(token in path for token in ("<", ">", "*", "{", "}")):
            continue
        if not (REPO_ROOT / path).exists():
            review.issues.append(f"工程或 metadata 引用不存在 `{ref}`")

    if re.search(r"^- canonical：`[^`]*\s+[^`]*`\s*$", text, re.MULTILINE):
        review.issues.append("canonical 使用含空格的自然语言伪引用")

    central_domain_refs = sorted(
        set(
            re.findall(
                r"quwoquan_service/contracts/metadata/(?!_)[A-Za-z0-9_.-]+(?:/[^`\s；，]*)?",
                text,
            )
        )
    )
    for ref in central_domain_refs:
        review.issues.append(f"业务域契约必须引用所属服务 contracts，不得引用中心 metadata `{ref}`")


def review_spec(node: feature_tree.Node, refs: dict[str, set[str]]) -> Review:
    path = node.spec.relative_to(REPO_ROOT).as_posix()
    review = Review(path=path, kind=feature_tree.VALID_LEVELS[node.level])
    text = node.spec.read_text(encoding="utf-8")
    validate_title(review, text, node)
    validate_sections(
        review,
        text,
        SPEC_SECTIONS[node.level],
        SPEC_OPTIONAL_SECTIONS[node.level],
    )
    validate_content(review, text)
    validate_acceptance(review, text, node, refs)
    validate_open_items(review, text, node)
    validate_child_descriptions(review, text, node)
    validate_repo_refs(review, text)
    return review


def review_design(node: feature_tree.Node) -> Review | None:
    if not node.design.is_file():
        return None
    path = node.design.relative_to(REPO_ROOT).as_posix()
    review = Review(path=path, kind=f"{feature_tree.VALID_LEVELS[node.level]} Design")
    text = node.design.read_text(encoding="utf-8")
    if node.level == 3:
        review.issues.append("L3 禁止 design.md")
        return review
    validate_sections(
        review,
        text,
        DESIGN_SECTIONS[node.level],
        DESIGN_OPTIONAL_SECTIONS[node.level],
    )
    validate_content(review, text)
    validate_repo_refs(review, text)
    decisions = [item for item in feature_tree.ids(node.design) if item.startswith("DEC-")]
    if not decisions:
        review.issues.append("缺少 DEC 决策锚点")
    if node.level == 2:
        trigger = re.search(r"^> 设计触发原因：(.+)$", text, re.MULTILINE)
        if not trigger or trigger.group(1).strip() in {"存在状态/数据所有权或跨组件质量权衡。", "……"}:
            review.issues.append("L2 design 未说明具体设计触发原因")
        for required in ("- 影响 Story：", "- 关联要求：", "- 关联验收："):
            if required not in text:
                review.issues.append(f"L2 DEC 缺少 `{required.removeprefix('- ')}`")
    elif node.level == 1 and "- 关联能力：" not in text:
        review.issues.append("L1 DEC 缺少 `关联能力`")
    return review


def review_templates() -> list[Review]:
    reviews: list[Review] = []
    for filename, (kind, expected_sections, required_ids) in TEMPLATE_CONTRACTS.items():
        path = TEMPLATE_ROOT / filename
        review = Review(path=path.relative_to(REPO_ROOT).as_posix(), kind=kind)
        if not path.is_file():
            review.issues.append("缺少模板文件")
            reviews.append(review)
            continue
        text = path.read_text(encoding="utf-8")
        level = {
            "app-root": 0,
            "l1": 1,
            "l2": 2,
            "l3": 3,
        }[filename.removesuffix("-spec.md").removesuffix("-design.md")]
        optional = (
            SPEC_OPTIONAL_SECTIONS[level]
            if "Spec Template" in kind
            else DESIGN_OPTIONAL_SECTIONS[level]
        )
        validate_sections(review, text, expected_sections, optional)
        for required_id in required_ids:
            if not re.search(rf"^###\s+{re.escape(required_id)}\b", text, re.MULTILINE):
                review.issues.append(f"缺少示例锚点 `{required_id}`")
        if "Spec Template" in kind and "<" not in text:
            review.issues.append("规格模板未声明可替换字段")
        if "Design Template" in kind and "被否决方案" not in text:
            review.issues.append("设计模板未要求记录被否决方案")
        reviews.append(review)
    return reviews


def render(reviews: list[Review]) -> tuple[str, dict[str, object]]:
    failures = [item for item in reviews if not item.ok]
    templates = [item for item in reviews if item.kind.endswith("Template")]
    documents = len(reviews) - len(templates)
    lines = [
        "# Feature Tree Content Review",
        "",
        f"- 实际 spec/design：{documents}",
        f"- 模板：{len(templates)}",
        f"- 审计文件合计：{len(reviews)}",
        f"- 通过：{len(reviews) - len(failures)}",
        f"- 阻断：{len(failures)}",
        f"- 问题：{sum(len(item.issues) for item in failures)}",
        "",
    ]
    for item in reviews:
        lines.extend(
            [
                f"## {'PASS' if item.ok else 'GATE_BLOCK'} · `{item.path}`",
                "",
                f"- 类型：{item.kind}",
                f"- 验收：{', '.join(item.acceptance) or '不适用'}",
                f"- 真实证据：{len(item.evidence)}",
                f"- OPEN：{', '.join(item.open_items) or '无'}",
                f"- 工程引用：{len(item.repo_refs)}",
            ]
        )
        if item.issues:
            lines.extend(["- 问题：", *[f"  - {issue}" for issue in item.issues]])
        lines.append("")
    payload = {
        "reviewed": len(reviews),
        "documents": documents,
        "templates": len(templates),
        "passed": len(reviews) - len(failures),
        "blocked": len(failures),
        "issues": sum(len(item.issues) for item in failures),
        "files": [item.__dict__ | {"ok": item.ok} for item in reviews],
    }
    return "\n".join(lines), payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="生成报告但不以内容问题返回失败")
    args = parser.parse_args()
    nodes = feature_tree.discover_nodes()
    refs = feature_tree.test_spec_refs()
    reviews: list[Review] = []
    for node in nodes:
        reviews.append(review_spec(node, refs))
        design = review_design(node)
        if design:
            reviews.append(design)
    reviews.extend(review_templates())
    content, payload = render(reviews)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    markdown = OUTPUT_ROOT / "content-review.md"
    machine = OUTPUT_ROOT / "content-review.json"
    markdown.write_text(content.rstrip() + "\n", encoding="utf-8")
    machine.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(markdown.relative_to(REPO_ROOT))
    print(machine.relative_to(REPO_ROOT))
    if payload["blocked"]:
        message = f"GATE_BLOCK: {payload['blocked']} files / {payload['issues']} content issues"
        if not args.report_only:
            print(message, file=sys.stderr)
            return 1
        print(f"REPORT_ONLY: {message}")
        return 0
    print(f"OK: reviewed {payload['reviewed']} feature-tree spec/design/template files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
