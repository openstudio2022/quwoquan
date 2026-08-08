#!/usr/bin/env python3
"""
verify_unified_error_semantics_ratchet.py

Ratchet for newly introduced coarse-grained UI error handling patterns.

Blocks new occurrences of:
1) `_errorText = '加载失败...'` style hardcoded page error text assignments.
2) `runtimeErrorDisplayMessage(...)` direct page consumption.
3) `AppToast.show(... failed ...)` style fallback-only action errors.
4) page-level `state.error` / provider `error:` branches that draw custom
   `Center/Padding/Text/...` instead of unified error semantics components.
5) generic error UI that uses alarming icons, old "加载失败/重试" titles, or
   routes list append failures through section cards instead of footer.
6) circular exclamation icons outside the shared inline error primitive.

当前历史基线已清零，任何命中均直接阻断。
"""

import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT


import argparse
import os
import re
import sys
CANONICAL_INLINE_ERROR_ICON = (
    "quwoquan_app/lib/design_system/feedback/error_states/app_error_states.dart"
)

LINE_RULES = [
    (
        re.compile(r"_errorText\s*=\s*['\"][^'\"]*(?:加载失败|请稍后重试|提交失败|请先登录)[^'\"]*['\"]"),
        "页内错误文案应收敛到 UiErrorSemantic / AppPageErrorState，禁止新增 _errorText 硬编码",
    ),
    (
        re.compile(r"AppToast\.show\([^,\n]+,\s*runtimeErrorDisplayMessage\("),
        "动作失败应优先使用 UiErrorSemantic / AppActionErrorFeedback，禁止新增直接 toast(runtimeErrorDisplayMessage)",
    ),
    (
        re.compile(r"runtimeErrorDisplayMessage\("),
        "页面应消费 runtimeErrorSemantic + 统一错误组件，禁止直接读取 runtimeErrorDisplayMessage",
    ),
    (
        re.compile(r"AppToast\.show\([^,\n]+,\s*UITextConstants\.[A-Za-z0-9_]*(?:Failed(?:Toast)?|loadFailed)\b"),
        "页面动作失败应优先使用 UiErrorSemantic / AppActionErrorFeedback，禁止新增失败 toast 常量回退",
    ),
    (
        re.compile(r"AppToast\.show\([^,\n]+,\s*['\"][^'\"]*(?:失败|请稍后重试|暂时不可用)[^'\"]*['\"]"),
        "页面动作失败应优先使用 UiErrorSemantic / AppActionErrorFeedback，禁止新增失败 toast 字面量回退",
    ),
    (
        re.compile(r"(?:CupertinoIcons\.exclamationmark\b|Icons\.error\b)"),
        "通用错误态禁止新增惊叹/错误图标；请使用 AppPageErrorState/AppSectionErrorCard 的低打扰视觉",
    ),
    (
        re.compile(r"title:\s*(?:UITextConstants|context\.l10n)\.loadFailed\b"),
        "通用错误态禁止把“加载失败”作为大标题；请使用具体且柔和的 UiErrorSemantic 标题",
    ),
    (
        re.compile(r"label:\s*(?:UITextConstants|context\.l10n)\.retry\b"),
        "通用错误态操作文案应使用“再试一次”等恢复导引，禁止新增旧式“重试”按钮",
    ),
    (
        re.compile(r"child:\s*(?:const\s+)?Text\(\s*(?:UITextConstants\.retry|['\"]重试['\"])\s*\)"),
        "通用错误态操作文案应使用“再试一次”等恢复导引，禁止新增旧式“重试”按钮",
    ),
]

BLOCK_RULES = [
    (
        re.compile(
            r"AppSectionErrorCard\([\s\S]{0,260}UiErrorCategory\.listAppend",
            re.MULTILINE,
        ),
        "分页/加载更多失败必须使用 AppListAppendErrorFooter，禁止用 section 错误卡常驻",
    ),
    (
        re.compile(
            r"AppPageErrorState\([\s\S]{0,260}staleDataError",
            re.MULTILINE,
        ),
        "已有内容刷新失败必须使用 AppTransientErrorNotice，禁止替换成整页错误态",
    ),
    (
        re.compile(
            r"if\s*\(\s*state\.error\s*!=\s*null(?:\s*&&[^\)]*)?\)\s*\{\s*return\s+(?![\s\S]{0,220}?App(?:PageErrorState|SectionErrorCard|InlineGateState)\()(?:Center|Padding|Text|Column|Container)\(",
            re.MULTILINE,
        ),
        "页面加载错误应收敛到 AppPageErrorState / AppSectionErrorCard，禁止自绘 state.error 分支",
    ),
    (
        re.compile(
            r"state\.error\s*!=\s*null(?:\s*&&[^\?]*)?\s*\?\s*(?![\s\S]{0,220}?App(?:PageErrorState|SectionErrorCard|InlineGateState)\()(?:Center|Padding|Text|Column|Container)\(",
            re.MULTILINE,
        ),
        "页面加载错误应收敛到 AppPageErrorState / AppSectionErrorCard，禁止三元表达式自绘 state.error 分支",
    ),
    (
        re.compile(
            r"error:\s*\(error,\s*_\)\s*=>\s*(?![\s\S]{0,220}?App(?:PageErrorState|SectionErrorCard|InlineGateState)\()(?:Center|Padding|Text|Column|Container)\(",
            re.MULTILINE,
        ),
        "页面 provider/error builder 应收敛到 AppPageErrorState / AppSectionErrorCard，禁止自绘 error 分支",
    ),
]


def is_page_like(rel: str) -> bool:
    if not rel.endswith(".dart"):
        return False
    parts = rel.split("/")
    if (
        len(parts) >= 8
        and parts[:3] == ["quwoquan_app", "lib", "service"]
        and parts[6] == "presentation"
    ):
        return True
    return rel.startswith(
        (
            "quwoquan_app/lib/runtime/shell/",
            "quwoquan_app/lib/runtime/shell/",
        )
    )


def collect_violations(target_root: str, repo_root: str) -> list[tuple[str, int, str, str]]:
    results: list[tuple[str, int, str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(target_root):
        for name in filenames:
            if not name.endswith(".dart"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, repo_root).replace("\\", "/")
            try:
                with open(path, encoding="utf-8") as handle:
                    content = handle.read()
                if (
                    "CupertinoIcons.exclamationmark_circle" in content
                    and rel != CANONICAL_INLINE_ERROR_ICON
                ):
                    for line_no, line in enumerate(content.splitlines(), 1):
                        if "CupertinoIcons.exclamationmark_circle" in line:
                            results.append(
                                (
                                    rel,
                                    line_no,
                                    line.rstrip(),
                                    "圆形感叹号仅允许由共享 AppInlineFieldError / "
                                    "AppFormErrorCard 原语渲染",
                                )
                            )
                for line_no, line in enumerate(content.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("//"):
                        continue
                    for pattern, hint in LINE_RULES:
                        if pattern.search(line) and is_page_like(rel):
                            results.append((rel, line_no, line.rstrip(), hint))
                            break
                if is_page_like(rel):
                    for pattern, hint in BLOCK_RULES:
                        for match in pattern.finditer(content):
                            line_no = content.count("\n", 0, match.start()) + 1
                            snippet = content[match.start() : content.find("\n", match.start())]
                            results.append((rel, line_no, snippet.strip(), hint))
            except OSError as exc:
                print(
                    f"verify_unified_error_semantics_ratchet: ERROR reading {rel}: {exc}",
                    file=sys.stderr,
                )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify unified UI error semantics ratchet"
    )
    parser.add_argument(
        "--targets",
        default="quwoquan_app/lib",
        help="Path to scan (default: quwoquan_app/lib)",
    )
    args = parser.parse_args()

    repo_root = str(REPO_ROOT)
    target_root = os.path.normpath(os.path.join(repo_root, args.targets))
    if not os.path.isdir(target_root):
        print(
            f"verify_unified_error_semantics_ratchet: ERROR {target_root} not found",
            file=sys.stderr,
        )
        return 1

    violations = collect_violations(target_root, repo_root)

    for rel, line_no, line_content, hint in violations:
        print(f"{rel}:{line_no}: {hint}")
        print(f"  {line_content.strip()}")

    if violations:
        print(
            "\nverify_unified_error_semantics_ratchet: 新增粗糙错误处理已被阻断",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
