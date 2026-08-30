"""spec/design Markdown 解析：锚点、OPEN、结果子句与工程归属声明。"""
from __future__ import annotations

import re
from pathlib import Path

from .nodes import Node
from .patterns import (
    ACCEPTANCE_ID_RE,
    ACCEPTANCE_SECTION_RE,
    APP_JOURNEY_ENGINEERING_ROOT_RE,
    CODE_SPAN_RE,
    ENGINEERING_CLAIM_RE,
    HEADING_RE,
    ID_RE,
    INHERITING_BULLET_RE,
    NESTED_BULLET_RE,
    OPEN_BLOCK_RE,
    OUTCOME_CLAUSE_SPLIT_RE,
    PATH_RE,
    PRECONDITION_BULLET_RE,
    TOP_BULLET_RE,
)


def markdown_anchor(heading: str) -> str:
    text = re.sub(r"<[^>]+>", "", heading).strip().lower()
    text = re.sub(r"[`*_~]", "", text)
    text = re.sub(r"[^\w\-\u4e00-\u9fff ]", "", text)
    return re.sub(r"\s+", "-", text)


def headings(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    result = {markdown_anchor(match.group(2)) for match in HEADING_RE.finditer(text)}
    result.update(re.findall(r'<a\s+id=["\']([^"\']+)["\']\s*></a>', text, re.IGNORECASE))
    return result


def title(path: Path) -> str:
    if not path.is_file():
        return path.parent.name
    match = HEADING_RE.search(path.read_text(encoding="utf-8"))
    return match.group(2).strip() if match else path.parent.name


def ids(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [f"{kind}-{number}" for kind, number in ID_RE.findall(path.read_text(encoding="utf-8"))]


def acceptance_ids(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [f"{kind}-{number}" for kind, number in ACCEPTANCE_ID_RE.findall(path.read_text(encoding="utf-8"))]


def outcome_bullets(body: str) -> list[str]:
    """切出锚点正文中结果角色的顶层 bullet，含缩进续行。

    角色完全由行首关键字决定，不推断语义；嵌套子 bullet 与前置条件 bullet 都不承载
    结果子句。
    """

    bullets: list[str] = []
    role_is_outcome = True
    current: list[str] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            bullets.append(" ".join(current))
            current = None

    for line in body.splitlines():
        match = TOP_BULLET_RE.match(line)
        if match:
            flush()
            bullet = match.group(1)
            if INHERITING_BULLET_RE.match(bullet):
                pass
            elif PRECONDITION_BULLET_RE.match(bullet):
                role_is_outcome = False
            else:
                role_is_outcome = True
            if role_is_outcome:
                current = [bullet]
            continue
        if current is None or NESTED_BULLET_RE.match(line):
            continue
        if line.strip() and line.startswith((" ", "\t")):
            current.append(line.strip())
        else:
            flush()
    flush()
    return bullets


def outcome_sub_clauses(bullet: str) -> list[str]:
    """把一个结果 bullet 拆成其中相互独立的结果。

    折叠漏口：把多个相互独立的结果用 `；` 或 `，且` 折叠进同一个 bullet，会让整组
    结果只占一个子句位——测试覆盖其中任意一个就足以让全部结果显示为已绑定，剩下的
    结果实际无人验证却呈现为已闭合。按并列分隔符切分后，每个独立结果各占一个可裁定
    的子句位。

    反引号代码片段整体屏蔽，标识符里的标点不会被当成分隔符。
    """

    masked = CODE_SPAN_RE.sub(lambda match: "\x00" * len(match.group(0)), bullet)
    pieces: list[str] = []
    start = 0
    for match in OUTCOME_CLAUSE_SPLIT_RE.finditer(masked):
        pieces.append(bullet[start : match.start()])
        start = match.end()
    pieces.append(bullet[start:])
    return [piece for piece in (item.strip() for item in pieces) if piece]


def outcome_clause_count(body: str) -> int:
    """统计锚点正文的结果子句数。

    判据只读行首角色关键字与并列分隔符，不推断语义，因此同一段文本任何时候都得到
    同一个数；也不存在「把独立结果折叠进 `AND`、`；` 或 `，且` 以规避子句级绑定」
    的写法。
    """

    return sum(len(outcome_sub_clauses(bullet)) for bullet in outcome_bullets(body))


def acceptance_clause_counts_in_text(text: str) -> dict[str, int]:
    """从验收锚点正文派生结果子句数量。

    子句 ID 由 spec 文本自身决定（第 N 条结果子句即 `tN`），不额外声明数量，
    避免出现与正文并列的第二真相源。
    """

    return {
        match.group(1): outcome_clause_count(match.group(2))
        for match in ACCEPTANCE_SECTION_RE.finditer(text)
    }


def acceptance_clause_counts(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    return acceptance_clause_counts_in_text(path.read_text(encoding="utf-8"))


def open_completion_field(block: str) -> str:
    """返回 OPEN 的完成判定全文，含缩进续行与子 bullet。

    完成判定经常写成「一句总述 + 逐条证据子 bullet」，锚点引用往往落在子 bullet 里。
    只读首行会同时造成两种错判：把已引用锚点的 OPEN 误报为不可裁定，以及放过子
    bullet 里引用了不存在锚点的 OPEN。
    """

    match = re.search(
        r"^- 完成判定：(.*(?:\n(?:[ \t]+\S.*|[ \t]*$))*)", block, re.MULTILINE
    )
    return match.group(1) if match else ""


def acceptance_refs_in_open_text(text: str) -> set[str]:
    refs: set[str] = set()
    for block in open_blocks_in_text(text).values():
        refs.update(
            re.findall(r"\b(?:UAT|DOM|SIT|GWT)-\d{3,}\b", open_completion_field(block))
        )
    return refs


def acceptance_refs_in_open(path: Path) -> set[str]:
    """返回同一 spec 的 OPEN 完成判定所引用的尚未闭合验收。"""

    if not path.is_file():
        return set()
    return acceptance_refs_in_open_text(path.read_text(encoding="utf-8"))


def invalid_acceptance_refs_in_open(path: Path) -> set[str]:
    """返回 OPEN 完成判定中不存在于同一 spec 的验收锚点。"""

    return acceptance_refs_in_open(path) - set(acceptance_ids(path))


def open_blocks_in_text(text: str) -> dict[str, str]:
    """返回 OPEN 编号到其正文块的映射。

    块尾空白随后续内容变化（末块到 `\\Z`，非末块到下一个标题），必须归一化，
    否则在既有 OPEN 后面插入新 OPEN 会把前者误判为「本次改动过」。
    """

    return {
        match.group(1): match.group(0).rstrip()
        for match in OPEN_BLOCK_RE.finditer(text)
    }


def anchorless_opens_in_text(text: str) -> set[str]:
    """返回完成判定不引用任何验收锚点的 OPEN。

    这类 OPEN 结构上不可裁定：没有任何证据能证明它关闭，也不会被双向门禁看见，
    因此既不能推动实现，也不会因为长期悬空而暴露。
    """

    anchorless: set[str] = set()
    for open_id, block in open_blocks_in_text(text).items():
        completion = open_completion_field(block)
        if not completion or not re.search(r"\b(?:UAT|DOM|SIT|GWT)-\d{3,}\b", completion):
            anchorless.add(open_id)
    return anchorless


def validate_acceptance_clause_coverage(
    spec_rel: str,
    clause_counts: dict[str, int],
    pending: set[str],
    bound_clauses: dict[str, set[int]],
    ratchet_anchors: set[str],
) -> list[str]:
    """校验复合验收的子句级覆盖。

    - 精度不可半途：锚点一旦出现任一子句级绑定，其全部 THEN 组必须都被绑定，
      禁止只绑定容易验证的那一条却对外表现为精确覆盖。
    - 闭合即需精度：本次增量中开始声称已闭合的复合锚点（THEN 组 >= 2）必须逐条绑定。
    """

    errors: list[str] = []
    for anchor_id, count in sorted(clause_counts.items()):
        if anchor_id in pending or count < 2:
            continue
        bound = bound_clauses.get(anchor_id, set())
        expected = set(range(1, count + 1))
        missing = sorted(expected - bound)
        if bound and missing:
            errors.append(
                f"{spec_rel}#{anchor_id.lower()}: 子句级绑定不完整，"
                f"共 {count} 条结果子句，缺 {', '.join(f't{index}' for index in missing)}"
            )
        elif not bound and anchor_id in ratchet_anchors:
            errors.append(
                f"{spec_rel}#{anchor_id.lower()}: 声称已闭合的复合验收共 {count} 条结果子句，"
                f"缺少子句级 spec_ref（需 {anchor_id.lower()}.t1..t{count} 逐条绑定）"
            )
    return errors


def open_item_details(node: Node) -> list[dict[str, str | int]]:
    """从节点 spec 解析可检索的 OPEN 当前事实，不建立独立台账。"""

    if not node.spec.is_file():
        return []
    text = node.spec.read_text(encoding="utf-8")
    details: list[dict[str, str | int]] = []
    matches = list(re.finditer(r"^###\s+(OPEN-\d{3,})\s+(.+)$", text, re.MULTILINE))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]

        def value(label: str) -> str:
            field_match = re.search(rf"^- {re.escape(label)}：(.+?)\s*$", body, re.MULTILINE)
            raw = field_match.group(1).strip() if field_match else ""
            if len(raw) >= 2 and raw.startswith("`") and raw.endswith("`"):
                return raw[1:-1]
            return raw

        details.append(
            {
                "node": node.rel,
                "level": node.level,
                "id": match.group(1),
                "title": match.group(2).strip(),
                "type": value("类型"),
                "priority": value("优先级"),
                "releaseImpact": value("准出影响"),
                "impactOrValue": value("影响或价值"),
                "completion": value("完成判定"),
                "dependency": value("依赖"),
            }
        )
    return details


def anchor_sections(text: str) -> dict[str, str]:
    """提取可追踪 ID 对应的小节，用于 Git 增量语义比较。"""

    matches = list(ID_RE.finditer(text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        key = f"{match.group(1)}-{match.group(2)}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[key] = text[match.start() : end].strip()
    return result


def section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+(?:\d+\.\s+)?{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.start() : end].strip()


def engineering_claims(node: Node) -> list[tuple[str, str]]:
    if node.level != 1 or not node.spec.is_file():
        return []
    body = section(node.spec.read_text(encoding="utf-8"), "工程归属")
    claims: list[tuple[str, str]] = []
    for line in body.splitlines():
        match = ENGINEERING_CLAIM_RE.match(line.strip())
        if "协作引用" in line or match is None:
            continue
        claims.extend(
            (match.group(1), root.rstrip("/"))
            for root in PATH_RE.findall(line)
        )
    return sorted(set(claims))


def app_journey_engineering_roots(node: Node) -> list[str]:
    """Return exact App Journey roots explicitly claimed by an L1 spec.

    Journey claims live under the nested ``测试`` section rather than an App
    production-root bullet, so ``engineering_claims`` intentionally does not
    consume them.  Only the canonical, dependency-level-specific Journey root
    is accepted here; project roots and the shared ``journeys`` parent remain
    ineligible as owner fallbacks.
    """

    if node.level != 1 or not node.spec.is_file():
        return []
    body = section(node.spec.read_text(encoding="utf-8"), "工程归属")
    roots: set[str] = set()
    for line in body.splitlines():
        if "协作引用" in line:
            continue
        for raw_root in PATH_RE.findall(line):
            root = raw_root.rstrip("/")
            if APP_JOURNEY_ENGINEERING_ROOT_RE.fullmatch(root):
                roots.add(root)
    return sorted(roots)


def singleton_repository_roots(node: Node) -> list[str]:
    """解析只用于工程归属的仓库根单例，不扩张通用路径语法。"""

    if node.level != 1 or not node.spec.is_file():
        return []
    body = section(node.spec.read_text(encoding="utf-8"), "工程归属")
    roots: set[str] = set()
    for line in body.splitlines():
        if "协作引用" in line:
            continue
        match = ENGINEERING_CLAIM_RE.match(line.strip())
        if match is not None and "`Makefile`" in line:
            roots.add("Makefile")
    return sorted(roots)


def engineering_roots(node: Node) -> list[str]:
    return sorted(
        {root for _, root in engineering_claims(node)}
        | set(app_journey_engineering_roots(node))
        | set(singleton_repository_roots(node))
    )


def block_open_items(path: Path) -> list[str]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    result: list[str] = []
    for match in re.finditer(r"^###\s+(OPEN-\d{3,})\s+(.+)$", text, re.MULTILINE):
        tail = text[match.end() :]
        next_open = re.search(r"^###\s+OPEN-\d{3,}\b", tail, re.MULTILINE)
        block = tail[: next_open.start()] if next_open else tail
        if re.search(r"^- 准出影响：`?block`?\s*$", block, re.MULTILINE):
            result.append(f"{match.group(1)} {match.group(2).strip()}")
    return result
