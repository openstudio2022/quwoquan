#!/usr/bin/env python3
"""禁止阶段名进入稳定可执行路径、schema key 与测试标识（零容忍、无 allowlist）。

`m2 / m8 / m9 / m11 / b10 / phase0 / part3` 这类阶段名把「第几期做的」固化进永久
标识：读到 `m9_p0_replay_cases.json` 的人无从判断它覆盖什么行为，只能去翻当时的
排期。REQ-007 明令稳定可执行路径、schema key 和测试标识禁止阶段名；本门禁把这条
规则变成可执行扫描。

spec: specs/feature-tree/runtime/runtime-control-plane-foundation/
      domain-onboarding-acceptance-governance/spec.md#req-007 / #gwt-004

扫描面（`quwoquan_service` 树，调用方可用 `--scan-root` 显式覆盖）：

1. 路径面：全部源码文件的相对路径分段。
2. 测试标识面：`*_test.go` 顶层 func 名与 `*_test.py` 顶层 def 名。
3. 测试 JSON 面：`tests/**` 下 JSON fixture 的 key 与字符串值。
4. 契约 schema key 面：`contracts/**` 与 `services/*/contracts/**` YAML 的映射 key。

判定：标识 token 化（先按非字母数字切分，再按 CamelCase 边界切分）后，
任一 token 匹配 `^(m|b|phase|part)[0-9]{1,2}$`（大小写不敏感）即违规。
阶段序号现实中不超过两位数（m2..m11、b10、phase0、partN），三位以上数字
是量级/容量语义（`M10000` 活动规模、`part100` 之类不存在），不在判定内。

刻意避开的合法形态（由判定规则本身排除，不设 allowlist）：

* sha256 / hex 片段（digest、asset id、releases 文件名）：≥4 位纯 hex 粗段
  整体跳过；`b10`（3 字符）不满足跳过条件，仍会被拦。
* ULID / base32 假 id（`01J8DAILY...`）：无分隔符，不构成独立 token。
* 连续大写缩写（`M3U8`、`HTTP2`、`B2B`）：整体成段，不匹配「前缀+纯数字」。
* 版本号（`v2`）与外部格式名（`utf8`、`h264`）：前缀不在闭集或带非数字尾巴。
* 历史说明文字（注释、markdown）：不属于可执行标识，不在扫描面。
* `t1..tN`：特性树子句锚点（specs 树、spec_ref 注释）是合法语法，且与
  recommendation 契约的价值分层 wire key（`valueTierWeights.T1..T4`，tier 语义）
  同形，无法零误报区分，因此 `t` 前缀不纳入扫描闭集；REQ-007 对 t1..t4 的
  约束由特性树语法门禁承载。

空扫描 fail-closed：扫描根缺失或任一扫描面命中 0 个受检对象即阻断。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import (  # noqa: E402
    ScanRootUnusable,
    repository_root,
    require_nonempty,
    require_scan_root,
)

__all__ = ["ScanRootUnusable", "main", "scan", "stage_tokens", "tokenize"]

#: 阶段名 token 闭集：`m2 / b10 / phase0 / part7`（序号 1..2 位数字）。
STAGE_TOKEN_RE = re.compile(r"^(?:m|b|phase|part)[0-9]{1,2}$")

#: 粗分段：非字母数字即边界（`_`、`-`、`.`、`/`、空白、中文等）。
COARSE_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")

#: ≥4 位纯 hex 的粗段是 digest/asset id 片段，整体跳过；阶段名 `b10` 只有
#: 3 字符，不会被误跳过（m/phase/part 含非 hex 字母，天然不受影响）。
HEX_SEGMENT_RE = re.compile(r"^[0-9a-fA-F]{4,}$")

#: CamelCase 细分段。顺序关键：先取「大写开头的词」，再取「连续大写数字缩写」
#: （`M3U8`、`HTTP2`、`B2B` 整体成段，`M2Contract` 中的 `M2` 恰好单独成段），
#: 最后取小写词（`m9`、`phase0`）。
CAMEL_TOKEN_RE = re.compile(r"[A-Z][a-z]+[0-9]*|[A-Z0-9]+(?![a-z])|[a-z]+[0-9]*")

GO_TEST_FUNC_RE = re.compile(r"^func\s+([A-Za-z0-9_]+)\s*\(", re.MULTILINE)
PY_TEST_DEF_RE = re.compile(r"^def\s+([A-Za-z0-9_]+)\s*\(", re.MULTILINE)

#: 可丢弃/第三方目录不属于稳定可执行路径。
SKIP_DIRS = {".qwq_output", ".git", "node_modules", "vendor", "__pycache__"}


def tokenize(identifier: str) -> list[str]:
    tokens: list[str] = []
    for coarse in COARSE_SPLIT_RE.split(identifier):
        if not coarse or HEX_SEGMENT_RE.match(coarse):
            continue
        tokens.extend(match.group(0) for match in CAMEL_TOKEN_RE.finditer(coarse))
    return tokens


def stage_tokens(identifier: str) -> list[str]:
    return [token for token in tokenize(identifier) if STAGE_TOKEN_RE.match(token.lower())]


def _iter_source_files(scan_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in scan_root.rglob("*"):
        if not path.is_file():
            continue
        if SKIP_DIRS.intersection(path.relative_to(scan_root).parts):
            continue
        files.append(path)
    return files


def _scan_paths(scan_root: Path, files: list[Path]) -> list[str]:
    violations: list[str] = []
    seen_segments: set[tuple[str, str]] = set()
    for path in files:
        relative = path.relative_to(scan_root)
        for index, segment in enumerate(relative.parts):
            hits = stage_tokens(segment)
            if not hits:
                continue
            location = "/".join(relative.parts[: index + 1])
            key = (location, segment)
            if key in seen_segments:
                continue
            seen_segments.add(key)
            violations.append(
                f"path: {location} 含阶段名 token {sorted(set(hits))}"
            )
    return violations


def _scan_test_identifiers(scan_root: Path, files: list[Path]) -> list[str]:
    violations: list[str] = []
    test_files = [
        path
        for path in files
        if path.name.endswith("_test.go") or path.name.endswith("_test.py")
    ]
    require_nonempty(test_files, "测试标识面", root=scan_root)
    for path in test_files:
        pattern = GO_TEST_FUNC_RE if path.suffix == ".go" else PY_TEST_DEF_RE
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            name = match.group(1)
            hits = stage_tokens(name)
            if hits:
                violations.append(
                    f"test-identifier: {path.relative_to(scan_root)} :: {name} "
                    f"含阶段名 token {sorted(set(hits))}"
                )
    return violations


def _walk_json(node: object, path: str, violations: list[str], where: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            hits = stage_tokens(key_text)
            if hits:
                violations.append(
                    f"json-key: {where} :: {path}/{key_text} 含阶段名 token {sorted(set(hits))}"
                )
            _walk_json(value, f"{path}/{key_text}", violations, where)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk_json(item, f"{path}[{index}]", violations, where)
    elif isinstance(node, str):
        hits = stage_tokens(node)
        if hits:
            violations.append(
                f"json-value: {where} :: {path} = {node!r} 含阶段名 token {sorted(set(hits))}"
            )


def _scan_test_json(scan_root: Path, files: list[Path]) -> list[str]:
    import json

    violations: list[str] = []
    json_files = [
        path
        for path in files
        if path.suffix == ".json"
        and "tests" in path.relative_to(scan_root).parts
    ]
    require_nonempty(json_files, "测试 JSON fixture 面", root=scan_root)
    for path in json_files:
        where = path.relative_to(scan_root).as_posix()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            violations.append(f"json-parse: {where} 解析失败: {error}")
            continue
        _walk_json(document, "", violations, where)
    return violations


def _walk_yaml_keys(node: object, path: str, violations: list[str], where: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            hits = stage_tokens(key_text)
            if hits:
                violations.append(
                    f"schema-key: {where} :: {path}/{key_text} 含阶段名 token {sorted(set(hits))}"
                )
            _walk_yaml_keys(value, f"{path}/{key_text}", violations, where)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk_yaml_keys(item, f"{path}[{index}]", violations, where)


def _scan_contract_schema_keys(scan_root: Path, files: list[Path]) -> list[str]:
    violations: list[str] = []
    yaml_files = [
        path
        for path in files
        if path.suffix in {".yaml", ".yml"}
        and "contracts" in path.relative_to(scan_root).parts
    ]
    require_nonempty(yaml_files, "契约 schema key 面", root=scan_root)
    for path in yaml_files:
        where = path.relative_to(scan_root).as_posix()
        try:
            documents = list(
                yaml.safe_load_all(path.read_text(encoding="utf-8"))
            )
        except (OSError, yaml.YAMLError) as error:
            violations.append(f"schema-parse: {where} 解析失败: {error}")
            continue
        for document in documents:
            _walk_yaml_keys(document, "", violations, where)
    return violations


def scan(scan_root: Path) -> list[str]:
    require_scan_root(scan_root, "阶段名标识")
    files = require_nonempty(
        _iter_source_files(scan_root), "阶段名标识扫描", root=scan_root
    )
    violations: list[str] = []
    violations.extend(_scan_paths(scan_root, files))
    violations.extend(_scan_test_identifiers(scan_root, files))
    violations.extend(_scan_test_json(scan_root, files))
    violations.extend(_scan_contract_schema_keys(scan_root, files))
    return sorted(violations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-root",
        type=Path,
        default=None,
        help="显式扫描根；缺省为仓库根下的 quwoquan_service",
    )
    args = parser.parse_args(argv)
    scan_root = args.scan_root or repository_root() / "quwoquan_service"

    violations = scan(scan_root)
    if violations:
        print(
            f"[verify] FAIL: 稳定可执行路径 / schema key / 测试标识发现 "
            f"{len(violations)} 处阶段名（m2/b10/t3/phase0/partN 等把排期固化进"
            f"永久标识；按覆盖的行为重命名，禁止旧路径 shim）：",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("[verify] OK: 稳定可执行路径、schema key 与测试标识不含阶段名")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
