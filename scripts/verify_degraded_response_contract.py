#!/usr/bin/env python3
"""
L0 门禁：降级响应契约静态分析

检查规则：
1. 每处 '助手暂时不可用' 返回时必须同时设置 errorCode（非空）
2. 每处 degraded: true 返回时必须设置 errorCode
3. finalText 中不得直接携带 JSON envelope 关键字（assistant_turn_v2, contractVersion）
4. capability_gateway.dart 中每处 catch 必须保留 rootCause 信息在 trace.message 中

违反任意规则 → 以非零退出，打印定位信息。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
GATEWAY_FILE = ROOT / "quwoquan_app/lib/personal_assistant/app/capability_gateway.dart"
AGENT_LOOP_FILE = ROOT / "quwoquan_app/lib/personal_assistant/engine/agent_loop.dart"


def error(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def check_unavailable_has_error_code(path: Path) -> list[str]:
    """
    规则 1：每处 '助手暂时不可用' 附近（±5 行）必须有 errorCode: 或 errorCode = 赋值。
    仅检查真正返回 AssistantRunResponse 的构造场景（含 finalText: 的代码块）。
    跳过纯字符串比较行（如 startsWith / contains / == 等判断）。
    """
    violations = []
    if not path.exists():
        return violations
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if "助手暂时不可用" not in line:
            continue
        # 跳过纯条件判断行（非构造 AssistantRunResponse 的地方）
        stripped = line.strip()
        if any(k in stripped for k in [
            "startsWith(",
            "contains(",
            ".startsWith",
            ".contains(",
            "== '",
            '== "',
            "// ",
            "/*",
            "#",
        ]):
            continue
        # 仅检查 finalText: 字符串字面量赋值场景（表示是在构造 Response 对象）
        window = lines[max(0, i - 3) : min(len(lines), i + 8)]
        window_text = "\n".join(window)
        is_in_response_constructor = "finalText:" in window_text or "AssistantRunResponse(" in window_text
        if not is_in_response_constructor:
            continue
        has_error_code = bool(
            re.search(r"errorCode\s*[:=]", window_text)
        )
        if not has_error_code:
            violations.append(
                f"{path.relative_to(ROOT)}:{i + 1}  "
                f"— '助手暂时不可用' 缺少 errorCode 设置（±8行窗口内未找到）"
            )
    return violations


def check_degraded_true_has_error_code(path: Path) -> list[str]:
    """
    规则 2：degraded: true 附近（±5 行）必须有 errorCode。
    """
    violations = []
    if not path.exists():
        return violations
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if re.search(r"degraded\s*:\s*true", line):
            window = lines[max(0, i - 5) : min(len(lines), i + 5)]
            window_text = "\n".join(window)
            has_error_code = bool(
                re.search(r"errorCode\s*[:=]", window_text)
            )
            if not has_error_code:
                violations.append(
                    f"{path.relative_to(ROOT)}:{i + 1}  "
                    f"— degraded: true 缺少 errorCode 设置（±5行窗口内未找到）"
                )
    return violations


def check_no_json_envelope_leak(path: Path) -> list[str]:
    """
    规则 3：finalText 的字符串字面量不得含 assistant_turn_v2 / contractVersion。
    仅检测 finalText: '...' 形式的赋值行。
    """
    violations = []
    if not path.exists():
        return violations
    content = path.read_text(encoding="utf-8")
    # 查找 finalText 字符串字面量中含 JSON envelope key 的地方
    pattern = re.compile(
        r"finalText\s*:\s*['\"]([^'\"]*(?:assistant_turn_v2|contractVersion)[^'\"]*)['\"]"
    )
    for m in pattern.finditer(content):
        lineno = content[: m.start()].count("\n") + 1
        violations.append(
            f"{path.relative_to(ROOT)}:{lineno}  "
            f"— finalText 字面量含 JSON envelope key: {m.group(1)[:60]!r}"
        )
    return violations


def check_catch_preserves_root_cause(path: Path) -> list[str]:
    """
    规则 4：capability_gateway.dart 中每处 catch (error) 块内的 trace.message
    必须含 $error（即保留原始异常信息），不得只有固定字符串。
    """
    violations = []
    if not path.exists():
        return violations
    content = path.read_text(encoding="utf-8")
    # 找 catch (error) { ... } 块（简单行扫描，检测 message: 中是否含 $error）
    lines = content.splitlines()
    in_catch = False
    catch_start = 0
    catch_depth = 0

    for i, line in enumerate(lines):
        if re.search(r"catch\s*\(\s*error\s*\)", line):
            in_catch = True
            catch_start = i + 1
            catch_depth = 0

        if in_catch:
            catch_depth += line.count("{") - line.count("}")
            # 查找 message: 赋值（只在 catch 块内）
            if re.search(r"message\s*:", line) and "助手暂时不可用" not in line:
                if "$error" not in line and "error.toString" not in line:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{i + 1}  "
                        f"— catch 块中 trace.message 未保留 $error 根因信息"
                    )
            if catch_depth < 0 or (catch_depth == 0 and i > catch_start):
                in_catch = False

    return violations


def check_acceptance_test_files_exist(root: Path) -> list[str]:
    """
    规则 5：acceptance.yaml 中 tests 字段引用的测试文件必须实际存在。
    """
    import re as _re

    acceptance_path = (
        root
        / "specs/feature-tree/assistant-run-learning"
        / "world-class-trinity-experience-baseline/acceptance.yaml"
    )
    if not acceptance_path.exists():
        return []

    content = acceptance_path.read_text(encoding="utf-8")
    # 提取所有 - quwoquan_app/test/... 格式的测试路径
    pattern = _re.compile(r"-\s+(quwoquan_app/test/\S+\.dart)")
    missing = []
    for m in pattern.finditer(content):
        test_path = root / m.group(1)
        if not test_path.exists():
            missing.append(
                f"acceptance.yaml 引用的测试文件不存在: {m.group(1)}"
            )
    return missing


def main() -> int:
    all_violations: list[str] = []

    dart_files_to_check = [GATEWAY_FILE, AGENT_LOOP_FILE]

    for f in dart_files_to_check:
        all_violations += check_unavailable_has_error_code(f)
        all_violations += check_degraded_true_has_error_code(f)
        all_violations += check_no_json_envelope_leak(f)

    all_violations += check_catch_preserves_root_cause(GATEWAY_FILE)
    all_violations += check_acceptance_test_files_exist(ROOT)

    if all_violations:
        print(
            "[verify_degraded_response_contract] 发现违规（共 "
            f"{len(all_violations)} 处）：",
            file=sys.stderr,
        )
        for v in all_violations:
            error(v)
        return 1

    print("[verify_degraded_response_contract] OK — 降级响应契约检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
