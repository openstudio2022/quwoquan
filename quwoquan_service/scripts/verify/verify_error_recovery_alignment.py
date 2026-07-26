#!/usr/bin/env python3
"""
verify_error_recovery_alignment.py

recovery 对齐门禁（云侧）。

对使用 AppError 工厂风格（runtime/errors.NewAppError(...).WithRecovery(...)）生成的
对象，断言：errors.yaml 中每个声明了 recovery_action 的错误，其对象级
generated/<context>/<object>/errors.go 必含同一 code 对应的
.WithRecovery("<action>", <afterSeconds>)。

目的：锁定 recovery_action / recovery_after_seconds 从 errors.yaml -> 生成 Go ->
随 ErrorResponse 下发的链路不被回退（如有人误删 codegen 的 goErrorRecoveryCall、
手改生成产物、或某服务未重新 codegen）。客户端消费 recovery 由
quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors 的 codec/policy 测试单独锁定。

检查对象直接由服务 contracts/generated 目录反向映射，不维护第二份域、对象或
输出路径注册表。客户端可见对象不得再登记 sentinel-only 豁免。

Usage:
  python3 quwoquan_service/scripts/verify/verify_error_recovery_alignment.py
Exit 0 on success, 1 on misalignment.
"""

import os
import re
import sys
from pathlib import Path

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

def discover_factory_objects() -> dict[str, dict[str, list[str]]]:
    """Derive object-level errors.yaml -> errors.go pairs from physical paths."""
    repo_root = Path(REPO_ROOT)
    services_root = repo_root / "quwoquan_service/services"
    objects: dict[str, dict[str, list[str]]] = {}
    for go_path in sorted(services_root.glob("*/generated/*/*/errors.go")):
        service_root = go_path.parents[3]
        context, object_name = go_path.parts[-3:-1]
        yaml_path = service_root / "contracts" / context / object_name / "errors.yaml"
        owner = f"{service_root.name}:{context}/{object_name}"
        objects[owner] = {
            "yaml": [yaml_path.relative_to(repo_root).as_posix()],
            "go": [go_path.relative_to(repo_root).as_posix()],
        }
    return objects

# 解析 errors.yaml 的逐条 error：code / recovery_action / recovery_after_seconds。
# errors.yaml 为缩进块，逐 error 项以 "- code:" 起。简单状态机解析。
CODE_RE = re.compile(r"^\s*-?\s*code:\s*(\S+)\s*$")
ACTION_RE = re.compile(r"^\s*recovery_action:\s*(\S+)\s*$")
AFTER_RE = re.compile(r"^\s*recovery_after_seconds:\s*(\d+)\s*$")
STRUCTURED_RECOVERY_RE = re.compile(
    r"^\s*recovery:\s*\{.*action:\s*([a-z_]+).*\}\s*$"
)
STRUCTURED_AFTER_RE = re.compile(r"afterSeconds:\s*(\d+)")
# 生成 Go 中的工厂注释 + .WithRecovery("action", secs)，按 code 精确绑定。
FACTORY_BLOCK_RE = re.compile(
    r"//\s+AppErrorFrom[A-Za-z0-9_]+\s+returns\s+\*AppError\s+for\s+"
    r"([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z0-9_]+)"
    r"[\s\S]{0,520}?\.WithRecovery(?:Directive)?\(\s*\"([a-z_]+)\"\s*,"
    r"(?:\s*\"[A-Za-z]+\"\s*,)?\s*(\d+)\s*\)",
    re.MULTILINE,
)


def parse_yaml_recoveries(rel_paths: list[str]) -> tuple[dict[str, tuple[str, int]], list[str]]:
    """Return {code: (action, after_seconds)} required by yaml entries, plus missing files."""
    required: dict[str, tuple[str, int]] = {}
    missing: list[str] = []
    for rel in rel_paths:
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.isfile(path):
            missing.append(rel)
            continue
        cur_action = None
        cur_after = 0
        cur_code = None
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                code_match = CODE_RE.match(line)
                if code_match:
                    # flush previous entry
                    if cur_code and cur_action:
                        required[cur_code] = (cur_action, cur_after)
                    cur_code = code_match.group(1)
                    cur_action = None
                    cur_after = 0
                    continue
                m = ACTION_RE.match(line)
                if m:
                    cur_action = m.group(1).strip('"\'')
                    continue
                m = STRUCTURED_RECOVERY_RE.match(line)
                if m:
                    cur_action = m.group(1)
                    after_match = STRUCTURED_AFTER_RE.search(line)
                    cur_after = int(after_match.group(1)) if after_match else 0
                    continue
                m = AFTER_RE.match(line)
                if m:
                    cur_after = int(m.group(1))
                    continue
            if cur_code and cur_action:
                required[cur_code] = (cur_action, cur_after)
    return required, missing


def parse_go_recoveries(rel_paths: list[str]) -> tuple[dict[str, tuple[str, int]], list[str]]:
    present: dict[str, tuple[str, int]] = {}
    missing: list[str] = []
    for rel_path in rel_paths:
        path = os.path.join(REPO_ROOT, rel_path)
        if not os.path.isfile(path):
            missing.append(rel_path)
            continue
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        for code, action, secs in FACTORY_BLOCK_RE.findall(content):
            present[code] = (action, int(secs))
    return present, missing


def main() -> int:
    failed = False
    factory_objects = discover_factory_objects()
    if not factory_objects:
        print("verify_error_recovery_alignment: 未发现对象级 errors.go", file=sys.stderr)
        return 1
    for domain, cfg in sorted(factory_objects.items()):
        required, missing_yaml = parse_yaml_recoveries(cfg["yaml"])
        if missing_yaml:
            print(f"[{domain}] errors.yaml 缺失: {', '.join(missing_yaml)}")
            failed = True
            continue
        go_paths = cfg["go"] if isinstance(cfg["go"], list) else [cfg["go"]]
        present, missing_go = parse_go_recoveries(go_paths)
        if missing_go:
            print(f"[{domain}] 生成 Go errors.go 缺失: {', '.join(missing_go)}（请运行 make codegen-app）")
            failed = True
            continue
        for code, expected in sorted(required.items()):
            actual = present.get(code)
            if actual != expected:
                print(f"[{domain}] {code} recovery 对齐失败:")
                print(f"    yaml: .WithRecovery(\"{expected[0]}\", {expected[1]})")
                if actual is None:
                    print("    go:   缺少对应 AppErrorFrom* 或 .WithRecovery")
                else:
                    print(f"    go:   .WithRecovery(\"{actual[0]}\", {actual[1]})")
                failed = True

    if failed:
        print(
            "\nverify_error_recovery_alignment: recovery 对齐不一致已被阻断。\n"
            "  先在 errors.yaml 声明 recovery_action/recovery_after_seconds，再 make codegen-app。",
            file=sys.stderr,
        )
        return 1
    print(
        "verify_error_recovery_alignment: recovery 对齐 OK"
        f"（factory 对象 {len(factory_objects)} 个强约束；无 sentinel 客户端可见对象豁免）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
