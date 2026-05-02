#!/usr/bin/env python3
"""
拆分「生产代码 / 测试代码」文件清单，交给 cloc 统计「code」列（等价于非空、非注释、非文档块统计口径）。
统计范围默认为端云交付树干；排除 ref/vendor/node_modules 等依赖与产物目录。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def repo_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".git").is_dir():
            return d
    raise RuntimeError("无法在上级路径定位 .git 仓库根")


REPO = repo_root(Path(__file__).resolve())

ROOTS = [
    REPO / "quwoquan_service",
    REPO / "quwoquan_app",
    REPO / "scripts",
    REPO / "tools",
    REPO / "apps",
]

SKIP_SEGMENTS = frozenset(
    {
        "node_modules",
        "vendor",
        ".git",
        "target",
        "build",
        ".dart_tool",
        "dist",
        "coverage",
        "__pycache__",
        "artifacts",
        "ref",
        "assistant_ref",
        "tmp",
        ".pnpm-store",
        ".turbo",
        ".next",
        # 本地下载依赖 / 缓存
        ".venv",
        "venv",
        ".tox",
        "Pods",
        ".gradle",
        ".cxx",
        "opencv2.framework",
    }
)


def normalize(path: Path) -> str:
    """用仓库根为锚点生成相对 POSIX 路径；遇到指向仓库外的符号链接则抛 ValueError（调用方跳过）。"""
    rel = Path(path).resolve().relative_to(REPO.resolve())
    return rel.as_posix()


def should_prune(dirname: str) -> bool:
    return dirname in SKIP_SEGMENTS


def is_js_style_test_filename(basename: str) -> bool:
    lowered = basename.lower()
    # foo.test.ts / foo.spec.js / xxx.test.mjs
    tail_ok = lowered.endswith(
        (
            ".spec.ts",
            ".spec.tsx",
            ".test.ts",
            ".test.tsx",
            ".spec.js",
            ".test.js",
            ".spec.jsx",
            ".test.jsx",
            ".test.mjs",
            ".spec.mjs",
            ".test.cjs",
            ".spec.cjs",
        )
    )
    if tail_ok:
        return True
    if ".test." in lowered or ".spec." in lowered:
        ok_ext = lowered.endswith(
            (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
        )
        if ok_ext:
            return True
    return False


def is_test_asset(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    basename = parts[-1] if parts else rel_posix
    lowered = basename.lower()

    if "__tests__" in parts:
        return True

    # Go / Dart / Python（单一文件）
    if lowered.endswith("_test.go"):
        return True
    if lowered.endswith("_test.dart"):
        return True
    if lowered.startswith("test_") and lowered.endswith(".py"):
        return True
    if lowered.endswith("_test.py"):
        return True

    if is_js_style_test_filename(basename):
        return True

    if parts[:1] == ["quwoquan_app"] and len(parts) > 2:
        if parts[1] in ("test", "integration_test", "benchmark"):
            return True

    for seg in parts[:-1]:
        if seg == "tests":
            return True

    if "test_fixtures" in parts:
        return True

    return False


def collect_files() -> tuple[list[str], list[str]]:
    prod: list[str] = []
    test: list[str] = []

    for root in ROOTS:
        if not root.is_dir():
            continue

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not should_prune(d))

            for name in filenames:
                p = Path(dirpath) / name
                if not p.is_file():
                    continue
                try:
                    np = normalize(p)
                except ValueError:
                    continue
                (test if is_test_asset(np) else prod).append(np)

    prod.sort()
    test.sort()
    return prod, test


def write_list(paths: list[str], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(paths) + ("\n" if paths else "")
    out.write_text(text, encoding="utf-8")


def run_cloc(list_file: Path) -> dict:
    proc = subprocess.run(
        ["cloc", "--list-file", str(list_file), "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"cloc failed: stderr={proc.stderr!r}")

    return json.loads(proc.stdout)


def pick_langs(row: dict, keys: tuple[str, ...]) -> int:
    code = 0
    for k in keys:
        ent = row.get(k)
        if isinstance(ent, dict):
            code += int(ent.get("code") or 0)
    return code


def summarize_block(title: str, data: dict) -> None:
    langs = sorted(
        [
            (k, v)
            for k, v in data.items()
            if isinstance(v, dict) and k not in {"header", "SUMMARY", "SUM"}
        ],
        key=lambda kv: (-int(kv[1].get("code") or 0), kv[0]),
    )

    total = data.get("SUMMARY") or data.get("SUM") or {}

    dart = pick_langs(data, ("Dart",))
    golang = pick_langs(data, ("Go",))
    py = pick_langs(data, ("Python",))
    ts = pick_langs(data, ("TypeScript", "TSX", "JavaScript", "JSX"))
    shell = pick_langs(data, ("Bourne Shell", "Bash", "Shell"))
    yaml = pick_langs(data, ("YAML",))
    scripting = dart + golang + py + ts + shell

    print(title)
    print(
        "总文件:",
        total.get("nFiles"),
        " code行:",
        total.get("code"),
        " blank:",
        total.get("blank"),
        " comment:",
        total.get("comment"),
    )

    print(
        "  └ 重点分项（code）： 「核心语言」（Dart+Go+Py+TS/JS+Shell）="
        f"{scripting:,}"
    )
    print(f"       Dart={dart:,} · Go={golang:,} · Python={py:,} · TS/JS系={ts:,} · Shell={shell:,} · YAML={yaml:,}")

    top = langs[:14]
    if top:
        print("  语言 Top（按 code）：")
        for name, blob in top:
            print(
                f"    {name:18}"
                f" files={blob.get('nFiles', 0)!s:>5}"
                f" code={blob.get('code', 0)!s:>9}"
            )


def main() -> None:
    out_dir = REPO / "tmp"
    prod_list = out_dir / "cloc_prod_files.txt"
    test_list = out_dir / "cloc_test_files.txt"

    prod_paths, test_paths = collect_files()
    write_list(prod_paths, prod_list)
    write_list(test_paths, test_list)

    print("口径：cloc 「code」计数（剔除空行与本语言注释）；范围见脚本 ROOTS 与 SKIP_SEGMENTS。\n")

    prod_data = run_cloc(prod_list)
    test_data = run_cloc(test_list)

    (out_dir / "cloc_prod_raw.json").write_text(json.dumps(prod_data, indent=2), encoding="utf-8")
    (out_dir / "cloc_test_raw.json").write_text(json.dumps(test_data, indent=2), encoding="utf-8")

    print("# 拆分前文件数（互斥）：")
    print(f"生产：{len(prod_paths)} 个文件")
    print(f"测试：{len(test_paths)} 个文件\n")

    summarize_block("[生产代码]", prod_data)
    print()
    summarize_block("[测试代码]", test_data)

    psum = prod_data.get("SUMMARY") or prod_data.get("SUM") or {}
    tsum = test_data.get("SUMMARY") or test_data.get("SUM") or {}
    total_code = int(psum.get("code") or 0) + int(tsum.get("code") or 0)

    print()
    print("=" * 54)
    print(f"两端云树干合计「code」行：{total_code:,}")
    print("（生产 + 测试；未含 docs/specs/openspec/node_modules/ref/artifacts 等）")


if __name__ == "__main__":
    main()
