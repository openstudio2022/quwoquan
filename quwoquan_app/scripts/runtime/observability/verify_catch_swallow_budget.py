#!/usr/bin/env python3
"""业务 catch 吞错预算门禁（棘轮：只减不增）。

异常链路收敛主线：已捕获异常默认应走 `ExceptionTelemetryPort.recordHandledException`
（或把结构化失败写入状态供 UI 消费），禁止新增「捕获后仅本地打印 / 空吞」的旁路。

判定口径（`quwoquan_app/lib/**`，排除 generated）：
- empty_catch：catch 体去掉注释后为空；
- log_only_catch：catch 体只由 developer.log / debugPrint / print 语句组成。

两类合计按文件与基线 `catch_swallow_baseline.json` 比较：
- 任一文件超出基线计数，或新文件出现吞错 → BLOCK；
- 计数下降 → 提示运行 `--update-baseline` 固化战果（基线只减不增）。
"""

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

from _common.paths import APP_ROOT
from _common.ratchet_baseline import load_counts, write_counts

LIB_ROOT = APP_ROOT / "lib"
BASELINE_PATH = Path(__file__).with_name("catch_swallow_baseline.json")

_LOG_ONLY_PREFIXES = ("developer.log(", "debugPrint(", "print(")


def _strip_comments_and_strings(source: str) -> str:
    """把注释置空、字符串字面量替换为占位符，保持长度与行结构不变。"""
    out: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "*":
            out.append("  ")
            i += 2
            while i < n and not (source[i] == "*" and i + 1 < n and source[i + 1] == "/"):
                out.append("\n" if source[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("  ")
                i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            triple = source[i : i + 3] == quote * 3
            token = quote * 3 if triple else quote
            out.append("s" * len(token))
            i += len(token)
            while i < n:
                if source[i] == "\\":
                    out.append("ss")
                    i += 2
                    continue
                if source[i : i + len(token)] == token:
                    out.append("s" * len(token))
                    i += len(token)
                    break
                out.append("\n" if source[i] == "\n" else "s")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _catch_bodies(clean: str) -> list[str]:
    """提取所有 catch 块 body（花括号配对，输入已剥离字符串/注释）。"""
    bodies: list[str] = []
    idx = 0
    while True:
        idx = clean.find("catch", idx)
        if idx < 0:
            break
        before = clean[idx - 1] if idx > 0 else " "
        after = clean[idx + 5] if idx + 5 < len(clean) else " "
        if before.isalnum() or before == "_" or after.isalnum() or after == "_":
            idx += 5
            continue
        paren = clean.find("(", idx)
        if paren < 0:
            break
        depth = 1
        j = paren + 1
        while j < len(clean) and depth > 0:
            if clean[j] == "(":
                depth += 1
            elif clean[j] == ")":
                depth -= 1
            j += 1
        while j < len(clean) and clean[j] in " \n\t\r":
            j += 1
        if j >= len(clean) or clean[j] != "{":
            idx = j
            continue
        depth = 1
        k = j + 1
        while k < len(clean) and depth > 0:
            if clean[k] == "{":
                depth += 1
            elif clean[k] == "}":
                depth -= 1
            k += 1
        bodies.append(clean[j + 1 : k - 1])
        idx = k
    return bodies


def _classify(body: str) -> str | None:
    stripped = body.strip()
    if not stripped:
        return "empty_catch"
    statements = [part.strip() for part in stripped.split(";") if part.strip()]
    if statements and all(
        any(stmt.startswith(prefix) for prefix in _LOG_ONLY_PREFIXES)
        for stmt in statements
    ):
        return "log_only_catch"
    return None


def scan() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(LIB_ROOT.rglob("*.dart")):
        rel = path.relative_to(APP_ROOT).as_posix()
        if "/generated/" in rel or rel.endswith(".g.dart"):
            continue
        clean = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        hits = sum(1 for body in _catch_bodies(clean) if _classify(body))
        if hits:
            counts[rel] = hits
    return counts


def main() -> int:
    update = "--update-baseline" in sys.argv
    counts = scan()
    if update:
        write_counts(BASELINE_PATH, counts)
        print(f"OK: 吞错基线已更新（{sum(counts.values())} 处 / {len(counts)} 文件）")
        return 0

    if not BASELINE_PATH.is_file():
        print("FAIL: 缺少 catch_swallow_baseline.json，先运行 --update-baseline 固化存量")
        return 1
    baseline = load_counts(BASELINE_PATH)

    errors: list[str] = []
    for rel, count in sorted(counts.items()):
        allowed = baseline.get(rel, 0)
        if count > allowed:
            errors.append(
                f"{rel}: 吞错 catch {count} 处，超出基线 {allowed}；"
                "请改走 ExceptionTelemetryPort.recordHandledException 或向上抛结构化失败"
            )

    total_now = sum(counts.values())
    total_baseline = sum(baseline.values())
    if errors:
        print("FAIL: 业务 catch 吞错预算超标（禁止新增本地打印/空吞旁路）：")
        for error in errors:
            print(f"  - {error}")
        return 1
    if total_now < total_baseline:
        print(
            f"OK: 吞错 catch {total_now}（基线 {total_baseline}，已下降；"
            "可运行 --update-baseline 固化战果）"
        )
        return 0
    print(f"OK: 业务 catch 吞错预算未超出基线（{total_now} 处）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
