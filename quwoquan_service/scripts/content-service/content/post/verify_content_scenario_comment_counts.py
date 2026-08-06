#!/usr/bin/env python3
"""内容域评论计数自洽门禁：fixture 的 commentCount / replyCount 不得与评论集漂移。

背景（缺口A 防回归）：
    `content_scenarios.json` 是端云共享的内容域 seed 真相源。alpha 端侧 MockContentRepository
    从 seedSets 初始化，云侧 beta/gamma 由该 fixture reset+seed。此前出现过「卡片显示评论 26、
    详情页只有 2」的不一致，根因是 fixture 的 `commentCount` 与实际评论集脱节，却没有任何门禁守护。
    本脚本固化「计数单一真相源」不变量，任何漂移都会阻断。

口径（与 fixture 实际表达 + 端侧 `_liveCommentCountForPost` 派生口径一致）：
    - 跨 seedSet 收集 posts（按 postId 去重）；同一 postId 在多个 seedSet 的 commentCount 声明必须一致。
    - 跨 seedSet 收集 comments（按 commentId 去重）；同一 commentId 的关键字段必须一致。
    - status == "deleted" 的评论不计入（软删墓碑语义，与端云一致）。
    - 对每个 post：commentCount == 该 postId 的全部评论数（一级 + 二级回复，全部计入）。
    - 对每个 comment：replyCount（缺省视为 0）== 直接挂在其下的回复数（parentCommentId == 该 comment.id）。

模式：
    - 默认（check）：只读校验，发现漂移则打印 post/comment id、声明值、实际值、差额并以非 0 退出。
    - --write：重新对齐能力（沉淀正式脚本，替代以往一次性 /tmp 脚本）。按评论集重算
      commentCount / replyCount 并写回；commentCount 总是写实际值，replyCount 仅在 > 0 时写、
      为 0 时移除字段（回归「缺省即 0」表达，保持最小 diff）。

默认校验范围：
    仅 `content_scenarios.json`（端云共享真相源）。派生产物 `*.lite.json` / `*.gamma-curated.json`
    由各自的 bundle 生成器从真相源裁剪而来，其计数自洽应由生成器在派生时重算保证。可用
    `--include-derived` 或 `--paths` 显式纳入校验/对齐。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]

SCENARIO_DIR = (
    ROOT / "quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios"
)

# 端云共享真相源（默认门禁范围）。
CANONICAL_FIXTURE = SCENARIO_DIR / "content_scenarios.json"

# 由真相源裁剪派生的产物（默认不纳入门禁，--include-derived 时校验）。
DERIVED_FIXTURES = [
    SCENARIO_DIR / "content_scenarios.lite.json",
    SCENARIO_DIR / "content_scenarios.gamma-curated.json",
]

DELETED_STATUS = "deleted"


def _comment_id(comment: dict[str, Any]) -> str:
    for key in ("commentId", "_id", "id"):
        value = comment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _post_id(post: dict[str, Any]) -> str:
    for key in ("postId", "id", "_id"):
        value = post.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _parent_id(comment: dict[str, Any]) -> str:
    value = comment.get("parentCommentId")
    return value.strip() if isinstance(value, str) else ""


def _declared_reply_count(comment: dict[str, Any]) -> int:
    value = comment.get("replyCount")
    if value is None:
        return 0
    if isinstance(value, bool):  # 防御：bool 是 int 子类
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


class FixtureCounts:
    """从单个 fixture 文件或内存 payload 解析出的去重计数模型。

    构造时二选一：传 ``path``（从磁盘读取、可写回）或传 ``payload``（直接对内存对象
    对齐，供 bundle 生成器在裁剪后写出前复用同一口径）。
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        payload: dict[str, Any] | None = None,
    ):
        if (path is None) == (payload is None):
            raise ValueError("FixtureCounts 需要且仅需要 path 或 payload 之一")
        if payload is None:
            payload = json.loads(path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
        self.path = path
        self.payload: dict[str, Any] = payload
        self.seed_sets: dict[str, Any] = self.payload.get("seedSets") or {}
        self.errors: list[str] = []

        # postId -> {seedSet: 声明的 commentCount}
        self._post_decls: dict[str, dict[str, Any]] = {}
        # commentId -> 首次出现的 comment（用于去重统计）
        self._comment_by_id: dict[str, dict[str, Any]] = {}

        self._collect()
        self._actual_total = self._compute_actual_total()
        self._actual_reply = self._compute_actual_reply()

    def _collect(self) -> None:
        for seed_name, seed_set in self.seed_sets.items():
            if not isinstance(seed_set, dict):
                continue
            for post in seed_set.get("posts", []) or []:
                if not isinstance(post, dict):
                    continue
                pid = _post_id(post)
                if not pid:
                    self.errors.append(f"seedSet '{seed_name}' 存在无 id 的 post 条目")
                    continue
                self._post_decls.setdefault(pid, {})[seed_name] = post.get(
                    "commentCount"
                )
            for comment in seed_set.get("comments", []) or []:
                if not isinstance(comment, dict):
                    continue
                cid = _comment_id(comment)
                if not cid:
                    self.errors.append(
                        f"seedSet '{seed_name}' 存在无 id 的 comment 条目"
                    )
                    continue
                if cid in self._comment_by_id:
                    self._assert_dup_consistent(seed_name, cid, comment)
                    continue
                self._comment_by_id[cid] = comment

    def _assert_dup_consistent(
        self, seed_name: str, cid: str, comment: dict[str, Any]
    ) -> None:
        prev = self._comment_by_id[cid]
        for field in (
            "postId",
            "parentCommentId",
            "replyToCommentId",
            "replyCount",
            "status",
        ):
            if prev.get(field) != comment.get(field):
                self.errors.append(
                    f"comment '{cid}' 跨 seedSet 字段不一致：{field} "
                    f"前值={prev.get(field)!r} 现值={comment.get(field)!r}（seedSet '{seed_name}'）"
                )

    def _is_live(self, comment: dict[str, Any]) -> bool:
        return comment.get("status") != DELETED_STATUS

    def _compute_actual_total(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for comment in self._comment_by_id.values():
            if not self._is_live(comment):
                continue
            pid = comment.get("postId")
            if not isinstance(pid, str) or not pid.strip():
                continue
            totals[pid.strip()] = totals.get(pid.strip(), 0) + 1
        return totals

    def _compute_actual_reply(self) -> dict[str, int]:
        replies: dict[str, int] = {}
        for comment in self._comment_by_id.values():
            if not self._is_live(comment):
                continue
            parent = _parent_id(comment)
            if parent:
                replies[parent] = replies.get(parent, 0) + 1
        return replies

    # ---- 校验 ----

    def check(self) -> list[str]:
        problems = list(self.errors)

        # post commentCount 跨 seedSet 一致性
        for pid, decls in self._post_decls.items():
            distinct = {json.dumps(v, sort_keys=True) for v in decls.values()}
            if len(distinct) > 1:
                problems.append(
                    f"post '{pid}' commentCount 跨 seedSet 声明不一致："
                    + ", ".join(f"{s}={c!r}" for s, c in decls.items())
                )

        # post commentCount == 实际评论总数
        for pid, decls in self._post_decls.items():
            declared = next(iter(decls.values()))
            declared_int = declared if isinstance(declared, int) else None
            actual = self._actual_total.get(pid, 0)
            if declared_int is None or declared_int != actual:
                problems.append(
                    f"post '{pid}' commentCount 漂移：声明={declared!r} 实际(含一级+二级)={actual} "
                    f"差额={('NA' if declared_int is None else declared_int - actual)}"
                )

        # comment replyCount == 直接回复数
        for cid, comment in self._comment_by_id.items():
            declared = _declared_reply_count(comment)
            actual = self._actual_reply.get(cid, 0)
            if declared != actual:
                problems.append(
                    f"comment '{cid}' replyCount 漂移：声明={declared} 实际(直接回复)={actual} "
                    f"差额={declared - actual}"
                )

        return problems

    # ---- 重新对齐（写回） ----

    def realign_in_memory(self) -> int:
        """原地按裁剪后评论集重算 commentCount / replyCount，返回被修改的字段数。

        只修改 ``self.payload``，不触碰磁盘。bundle 生成器在 prune 评论后、写出前
        调用本方法（经 :func:`realign_payload_counts`），使派生产物的计数与本脚本
        ``check`` 口径同源——commentCount 永远等于该 postId 实际保留的评论数（一级 +
        二级，软删不计），replyCount 等于实际保留的直接回复数（为 0 时回归缺省表达）。
        """
        changes = 0
        for seed_set in self.seed_sets.values():
            if not isinstance(seed_set, dict):
                continue
            for post in seed_set.get("posts", []) or []:
                if not isinstance(post, dict):
                    continue
                pid = _post_id(post)
                if not pid:
                    continue
                target = self._actual_total.get(pid, 0)
                if post.get("commentCount") != target:
                    post["commentCount"] = target
                    changes += 1
            for comment in seed_set.get("comments", []) or []:
                if not isinstance(comment, dict):
                    continue
                cid = _comment_id(comment)
                if not cid:
                    continue
                target = self._actual_reply.get(cid, 0)
                # 与 check 口径一致：缺省字段与显式 0 都视为 0，已自洽则不动（最小 diff）。
                if _declared_reply_count(comment) == target:
                    continue
                if target > 0:
                    comment["replyCount"] = target
                    changes += 1
                elif "replyCount" in comment:
                    comment.pop("replyCount")
                    changes += 1
        return changes

    def realign(self) -> int:
        """按评论集重算 commentCount / replyCount 并写回磁盘，返回被修改的字段数。"""
        changes = self.realign_in_memory()
        if changes and self.path is not None:
            self.path.write_text(
                json.dumps(self.payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return changes


def realign_payload_counts(payload: dict[str, Any]) -> int:
    """对内存 payload 原地重算 commentCount / replyCount，返回被修改的字段数。

    这是「计数单一真相源」对外暴露的复用入口：``*.lite.json`` /
    ``*.gamma-curated.json`` 的 bundle 生成器在裁剪评论后、写出前调用本函数，避免
    复制第二套统计口径。对齐结果与本脚本默认 ``check`` 完全一致。
    """
    return FixtureCounts(payload=payload).realign_in_memory()


def _resolve_paths(args: argparse.Namespace) -> list[Path]:
    if args.paths:
        return [Path(p).resolve() for p in args.paths]
    paths = [CANONICAL_FIXTURE]
    if args.include_derived:
        paths.extend(DERIVED_FIXTURES)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="*",
        help="显式指定要校验/对齐的 fixture 文件（默认仅 content_scenarios.json）",
    )
    parser.add_argument(
        "--include-derived",
        action="store_true",
        help="额外校验派生产物（*.lite.json / *.gamma-curated.json）",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="重新对齐：按评论集重算 commentCount / replyCount 并写回（默认只读校验）",
    )
    args = parser.parse_args(argv)

    paths = _resolve_paths(args)
    exit_code = 0

    for path in paths:
        if not path.exists():
            print(f"[fixture-counts] MISSING: {path}", file=sys.stderr)
            exit_code = 1
            continue
        rel = path.relative_to(ROOT) if ROOT in path.parents else path
        counts = FixtureCounts(path)

        if args.write:
            changed = counts.realign()
            if changed:
                print(f"[fixture-counts] REALIGNED {rel}: {changed} 处字段已重算写回")
            else:
                print(f"[fixture-counts] OK {rel}: 已自洽，无需对齐")
            # 写回后复算一遍，确保对齐结果自洽
            verify = FixtureCounts(path).check()
            if verify:
                print(
                    f"[fixture-counts] FAIL {rel}: 对齐后仍不自洽（请检查脚本口径）",
                    file=sys.stderr,
                )
                for line in verify:
                    print(f"  - {line}", file=sys.stderr)
                exit_code = 1
            continue

        problems = counts.check()
        if problems:
            print(f"[fixture-counts] FAIL {rel}: {len(problems)} 处计数漂移", file=sys.stderr)
            for line in problems:
                print(f"  - {line}", file=sys.stderr)
            print(
                "  修复：先在真相源补/改评论集，再运行 "
                "`python3 quwoquan_service/scripts/content-service/content/post/verify_content_scenario_comment_counts.py "
                "--write --paths <fixture>` 重新对齐计数。",
                file=sys.stderr,
            )
            exit_code = 1
        else:
            posts = len(counts._post_decls)
            comments = len(counts._comment_by_id)
            print(
                f"[fixture-counts] OK {rel}: posts={posts} comments={comments} "
                "commentCount/replyCount 全部自洽"
            )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
