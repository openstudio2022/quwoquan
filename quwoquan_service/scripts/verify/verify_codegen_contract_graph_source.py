#!/usr/bin/env python3
"""阻断 codegen/metadata verifier 绕过 ContractGraph 直接读取 metadata。"""

from __future__ import annotations

import re
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = SERVICE_ROOT / "tools"

REQUIRED_SOURCE_IMPORT = "quwoquan_service/internal/metadata/codegen"
FORBIDDEN_PATTERNS = {
    r"\bLoadFromDirectory\s*\(": "旧 registry 目录加载器",
    r"\bcompiler\.(?:Build|RequireValid)\s*\(": "绕过统一 codegen Source",
    r"\brec(?:impact|intersection)meta\.Read\s*\(": "注册表直接文件读取",
    r"\bos\.(?:ReadFile|ReadDir)\s*\([^)]*\bmetadata(?:Dir|Root|Path)\b": (
        "直接读取 metadata 路径"
    ),
    r"\bfilepath\.WalkDir\s*\([^)]*\bmetadata(?:Dir|Root|Path)\b": (
        "直接遍历 metadata 路径"
    ),
}


def production_go_sources(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.glob("*.go")
        if not path.name.endswith("_test.go")
    )


def check_generator(directory: Path, failures: list[str]) -> None:
    sources = production_go_sources(directory)
    merged = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    relative = directory.relative_to(SERVICE_ROOT).as_posix()

    if REQUIRED_SOURCE_IMPORT not in merged:
        failures.append(f"{relative}: generator 未消费统一 ContractGraph Source")

    for pattern, reason in FORBIDDEN_PATTERNS.items():
        if re.search(pattern, merged):
            failures.append(f"{relative}: {reason}")


def check_no_metadata_filesystem_scan(
    directory: Path,
    failures: list[str],
) -> None:
    merged = "\n".join(
        path.read_text(encoding="utf-8")
        for path in production_go_sources(directory)
    )
    relative = directory.relative_to(SERVICE_ROOT).as_posix()
    if REQUIRED_SOURCE_IMPORT not in merged:
        failures.append(f"{relative}: 未消费统一 ContractGraph Source")
    for token in ("os.ReadFile(", "os.ReadDir(", "filepath.WalkDir("):
        if token in merged:
            failures.append(f"{relative}: 禁止 metadata 文件系统扫描 {token}")


def main() -> int:
    failures: list[str] = []
    generators = sorted(
        main_file.parent
        for main_file in TOOLS_ROOT.glob("codegen_*/main.go")
    )
    if not generators:
        failures.append("tools/codegen_*/main.go: 未发现 generator")
    for directory in generators:
        check_generator(directory, failures)

    check_no_metadata_filesystem_scan(
        TOOLS_ROOT / "verify_metadata",
        failures,
    )

    for retired in (
        SERVICE_ROOT / "runtime" / "registry",
        SERVICE_ROOT / "runtime" / "codegen",
    ):
        if any(retired.glob("*.go")):
            failures.append(
                f"{retired.relative_to(SERVICE_ROOT)}: 旧 runtime 生成栈必须退役"
            )
    retired_imports = (
        "quwoquan_service/runtime/registry",
        "quwoquan_service/runtime/codegen",
        "quwoquan_service/runtime/repository",
    )
    for source in SERVICE_ROOT.rglob("*.go"):
        text = source.read_text(encoding="utf-8")
        for retired_import in retired_imports:
            if f'"{retired_import}' in text:
                failures.append(
                    f"{source.relative_to(SERVICE_ROOT)}: "
                    f"禁止引用退役包 {retired_import}"
                )

    if failures:
        for failure in failures:
            print(f"[verify] FAIL: {failure}")
        return 1

    print(
        "[verify] OK: all generators and metadata validators "
        "consume ContractGraph Source"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
