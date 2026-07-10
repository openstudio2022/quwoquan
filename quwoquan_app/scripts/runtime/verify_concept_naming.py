#!/usr/bin/env python3
"""Guard user-facing concept names for the 2026H1 positioning refactor."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    token: str
    message: str
    suggestion: str


APP_TEXT_ROOTS = [
    REPO_ROOT / "quwoquan_app/lib/ui",
    REPO_ROOT / "quwoquan_app/lib/app",
    REPO_ROOT / "quwoquan_app/lib/cloud",
    REPO_ROOT / "quwoquan_app/lib/core/constants",
    REPO_ROOT / "quwoquan_app/lib/core/errors",
    REPO_ROOT / "quwoquan_app/lib/core/services/search_repository.dart",
    REPO_ROOT / "quwoquan_app/lib/ui/search",
    REPO_ROOT / "quwoquan_app/lib/l10n",
]

SEARCH_METADATA_FILES = [
    REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/search_objects.yaml",
]

QUOTE_RE = re.compile(r"""(['"])(?P<value>.*?)(?<!\\)\1""")

# 2026H1 定位刷新后，消息域 group 概念前台统一回滚为「群聊」。
# 因此「群聊」不再是禁用词；仅保留其余历史别名作为禁用，避免再次出现「群组/趣群/空间/频道/论坛」等
# 与「群聊」并行的旧前台心智。「讨论」保留给实体/圈子内容讨论分区与全局检索聚合，不在此禁用。
GROUP_FORBIDDEN = ("群组", "趣群", "讨论群", "空间", "频道", "论坛")
CONTENT_ACTION_FORBIDDEN = ("收藏", "收藏夹", "稍后看", "关注内容", "共同关注内容")
# v3 交集主轴（§18.7 / §24）：前台入口统一「交集配对」、今日卡统一「今日交集」、成就模块统一「打动」，
# 旧词「兴趣配对 / 今日同趣机会 / 影响力」退场。机器标识 interest_match / impact / route / surface 保持不变（§14.2）。
# 只禁无歧义旧词：不含「找同趣」——「同趣」作情感修饰（如「找同趣的人 / 找到同趣的人」）仍被 §18.7.1
# 允许，substring 会误伤；「影响力」为前台成就文案词（§18.7.1 收敛为「打动」），机器名/注释里的「影响力」
# 属 impact 内部语义，门禁只扫引号内 value + 跳过 // /// 注释与 generated，不误伤。
INTERSECTION_FRONTEND_FORBIDDEN = ("今日同趣机会", "兴趣配对", "影响力")
OLD_INTERSECTION_TOKENS = (
    "mutualFriend",
    "commonFollow",
    "friendVisited",
    "contactVisited",
    "friendInCircle",
    "contactInCircle",
    "friendActiveHere",
    "coCollectedEntity",
    "coVisitedPlace",
    "coFavorited",
    "coFollowedContent",
)
FAVORITE_CODE_TOKENS = (
    "FavoritePost",
    "UnfavoritePost",
    "favoriteCount",
    "favorited",
    "favoritedAt",
    "AuthGateReason.favorite",
    "savedPostIds",
    "bookmarkCounts",
    "isSaved",
    "setSaved",
    "enqueuePostSave",
)


def iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.exists():
        return []
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".dart", ".arb", ".yaml", ".yml"}
    ]


def rel(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def is_test_or_generated_context(path: Path) -> bool:
    parts = set(path.parts)
    if "test" in parts:
        return True
    normalized = path.as_posix()
    return "/generated/" in normalized or normalized.endswith(".g.dart")


def is_allowed_group_context(path: Path, line: str) -> bool:
    normalized = rel(path).as_posix()
    stripped = line.strip()
    if stripped.startswith("//") or stripped.startswith("///") or stripped.startswith("*"):
        return True
    if "namespace" in line or "命名空间" in line:
        return True
    if "空间美学" in line:
        return True
    if "group" in line and any(
        token in normalized
        for token in (
            "start_group_chat",
            "group_manage_page",
            "chat_settings_page",
            "conversation_members_provider",
        )
    ):
        return True
    return False


def scan_user_visible_text() -> list[Finding]:
    findings: list[Finding] = []
    files: list[Path] = []
    for root in APP_TEXT_ROOTS:
        files.extend(iter_files(root))
    for path in sorted(set(files)):
        if is_test_or_generated_context(path):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if is_allowed_group_context(path, line):
                continue
            quoted_values = [m.group("value") for m in QUOTE_RE.finditer(line)]
            for value in quoted_values:
                for token in GROUP_FORBIDDEN:
                    if token in value:
                        findings.append(
                            Finding(
                                path,
                                line_no,
                                token,
                                "用户前台 chat group 概念统一为「群聊」，不得再用群组/趣群/讨论群等旧别名",
                                "将用户可见文案改为「群聊」（内容/圈子讨论分区仍用「讨论」）；若是机器契约，请移动到技术 allowlist 或生成源。",
                            )
                        )
                for token in CONTENT_ACTION_FORBIDDEN:
                    if token in value:
                        findings.append(
                            Finding(
                                path,
                                line_no,
                                token,
                                "内容长期动作已退场，用户前台不得恢复收藏/稍后看/关注内容心智",
                                "改为赞/评/转，或改写为私有足迹/浏览记录语义。",
                            )
                        )
                for token in INTERSECTION_FRONTEND_FORBIDDEN:
                    if token in value:
                        findings.append(
                            Finding(
                                path,
                                line_no,
                                token,
                                "v3 交集主轴：前台入口统一「交集配对」、今日卡统一「今日交集」，旧词兴趣配对/今日同趣机会退场",
                                "改为「交集配对 / 今日交集」；机器标识 interest_match/route/surface 保持不变（§14.2）。",
                            )
                        )
            # Some constants do not appear as quoted strings in ARB metadata.
            # 用标识符边界匹配，避免退役 token 命中合法的超集标识符（如 commonFollow ⊂ commonFollower）。
            for token in OLD_INTERSECTION_TOKENS + FAVORITE_CODE_TOKENS:
                token_re = re.compile(r"(?<![A-Za-z])" + re.escape(token) + r"(?![A-Za-z])")
                if token_re.search(line) and not line.strip().startswith(("//", "///", "*")):
                    findings.append(
                        Finding(
                            path,
                            line_no,
                            token,
                            "退役交集 kind 或 favorite 代码模式不得回流到 App 用户链路",
                            "使用六类交集母表达与最新 standard kind；favorite 残留请回 WP1 清理。",
                        )
                    )
    return findings


def scan_search_metadata() -> list[Finding]:
    findings: list[Finding] = []
    for path in SEARCH_METADATA_FILES:
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(r"\b(label|title):", line):
                for token in GROUP_FORBIDDEN:
                    if token in line:
                        findings.append(
                            Finding(
                                path,
                                line_no,
                                token,
                                "搜索展示 label/title 不得使用群组/趣群/讨论群等旧别名",
                                "修改 search_objects.yaml 后运行 make codegen-app（chat 群聊用「群聊」，跨对象聚合分区用「讨论」）。",
                            )
                        )
    return findings


def main() -> int:
    findings = scan_user_visible_text() + scan_search_metadata()
    if not findings:
        print("[concept-naming] OK")
        return 0
    print("[concept-naming] FAIL: found retired or inconsistent concept names")
    for finding in findings:
        print(
            f"{rel(finding.path)}:{finding.line_no}: {finding.token}: "
            f"{finding.message}；建议：{finding.suggestion}"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
