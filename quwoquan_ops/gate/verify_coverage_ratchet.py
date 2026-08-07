#!/usr/bin/env python3
"""代码分支/行/语句覆盖率棘轮门禁，按 ContractGraph 对象身份计量。

覆盖率与架构违规的方向相反：架构基线记录「违规条目集合」并要求只减不增，覆盖率
基线记录「已达成的覆盖率」并要求只增不减。两者共用同一套 ratchet 语义：

* 现状低于基线（超出容差）→ BLOCK，说明这次改动稀释了被测代码。
* 现状显著高于基线（超出 slack）→ BLOCK，要求 `--write-baseline` 把基线收紧，
  避免基线长期停留在远低于现实的水位，退化成摆设。
* 仓库里出现基线没有登记的单元 → BLOCK；基线里留着仓库已不存在的单元 → BLOCK。
* 基线只接受 `measuredFromGreenTests: true`；红测试不得形成或改写 tracked baseline。

为什么 App 必须按对象计量
--------------------------

仓库级或 domain 级平均数无法回答「某个对象是否可准出」：同一 domain 内高覆盖对象
会把零覆盖对象完全淹没。因此 App 覆盖率单元是 production 的 canonical
``domain/context/object`` 身份，名册从
`quwoquan_service/generated/contract_graph.json` 与 `object_path_map.scan_app` 实时派生，
本文件不复制任何 domain/object 名单：

``app:<domain>/<context>/<object>``
    端侧业务对象。每个 `lib/**` 生产文件的归属直接复用
    `object_path_map.scan_app` 的唯一 `objectId`，本文件不实现第二套路径反推。

``app:cross-cutting/<root>``
    仅接收已经物理位于 `APP_CROSS_CUTTING_ROOTS` 的 canonical 横切源码；runtime 与
    design system 分别计量。旧位置、只能反推到 domain/context、歧义或无主源码都
    立即 BLOCK，不能靠计数基线继续容忍。

``cloud:<domain>``
    云侧旧诊断桶。`domain` 取 `object_path_map.service_domains()` 里确实由 Go 实现的
    service 的 domain，并断言它落在同一个 roster 内。一个 domain 可以由多个
    service 承载（`ops` = `product-ops-service` + `control-plane/platform-ops`），
    此时按 domain 合并 coverprofile：**采集单元是 service，计量单元是 domain。**
    这不满足对象级合同，因此 Cloud scope 在 canonical object source owner 单轨闭合前
    始终 ``GATE_BLOCK``，不会采集或写入 domain baseline。

新增对象源码、canonical 横切根或 service 会立刻以「未登记单元」的形式阻断，
必须由绿测试实测进基线；删掉的会以「陈旧单元」阻断。名册跟着契约与源码走，
不需要人工维护。

覆盖率维度
----------

``app:*`` 三个轴，`line` / `branch` 来自 lcov，`file` 来自磁盘上的对象/横切单元：

* ``line``：lcov 的 `LF`/`LH`。
* ``branch``：lcov 的 `BRDA` 明细。**分支只能从 BRDA 数**——Flutter 3.44 的
  `--branch-coverage` 只写 `BRDA:<line>,<block>,<branch>,<taken>`，不写
  `BRF`/`BRH` 汇总行。照 `BRF`/`BRH` 解析会得到恒为 0 的分母，把「测不出分支」
  伪装成「没有分支」。若某天产出里同时出现 `BRF`/`BRH`，与 BRDA 计数不一致即
  阻断，避免同一个维度出现两套口径。
* ``file``：**被测试真正加载到的文件数 / 磁盘上该桶的生产文件数**。
  这一轴不可省：lcov 只记录被某个测试 import 过的文件，从未被 import 的库根本
  不进 `LF` 分母。没有 `file` 轴时，删掉一个覆盖 import 少的测试会让分母变小、
  `line` 反而上升——覆盖率下降却能骗过棘轮。`file` 的分母来自磁盘，堵住这条路。

``cloud:*`` 只有 ``statement``：Go 没有分支覆盖。它也不需要 `file` 轴，因为
`-coverpkg` 把该 service 的 `internal/...` 与 `cmd/...` 全部计入分母，一行没跑到的
文件会以 `count 0` 的块如实出现在 coverprofile 里。

不可测与假 0
------------

一个对象可能确实没有任何测试加载过它的文件，此时 `line` / `branch` 的分母是 0。
**分母为 0 时禁止写 0%**：0% 会被当成「已达标的下限」，此后无论怎么退化都过得去
（仓库里已经出过这个事故：某个 ratchet 对文件缺失静默返回 0，文件搬走后该桶永久
达标）。这里改为把该维度显式登记成 `unmeasured` 并写明原因，且**可测性在任一方向
发生变化都 BLOCK**：

* 基线可测、现状不可测 → BLOCK（测试被删或 import 被摘掉）。
* 基线不可测、现状可测 → BLOCK，要求 `--write-baseline` 登记真实数字。

`file` 轴只在该桶磁盘上一个生产文件都没有时才不可测（例如只有云侧实现、端侧没有
代码的域）；只要有文件，`0/N` 就是**实测事实**而非猜测，照实登记。

采集范围（scope）也逐字段写进基线并比对：改了采集命令却没重新采集时按 scope 漂移
阻断，而不是拿两次不可比的数字做大小比较。

用法
----
    # 复用已落盘的覆盖率产物求值（产物缺失 → BLOCK）
    python3 quwoquan_ops/gate/verify_coverage_ratchet.py

    # 先跑测试采集覆盖率，再求值（门禁在 gate_repo.sh 中的用法）
    python3 quwoquan_ops/gate/verify_coverage_ratchet.py --collect --scope app
    python3 quwoquan_ops/gate/verify_coverage_ratchet.py --collect --scope cloud

    # 只处理单个对象或云侧领域单元
    python3 quwoquan_ops/gate/verify_coverage_ratchet.py --collect \
      --unit app:circle/circle_management/gathering

    # 覆盖率提升后收紧基线（只重写本次求值到的单元分区）
    python3 quwoquan_ops/gate/verify_coverage_ratchet.py --collect --write-baseline

`--write-baseline` 必须搭配 `--collect` 且测试全绿：基线里的 provenance 只有本次
真跑过测试才说得出口。求值路径没有 warn-only、没有关闭开关、没有环境变量旁路、没有
「产物缺失就放行」的分支——求值不到数据一律 BLOCK，因为「测不出来」与
「覆盖率归零」对准出的意义相同。
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm  # noqa: E402
from quwoquan_ops.gate import verify_app_architecture as vaa  # noqa: E402

RULE_ID = "coverage-ratchet/v4"
BASELINE_SCHEMA = "coverage-ratchet-baseline/v2"

BASELINE_PATH = ROOT / "quwoquan_ops" / "policies" / "gates" / "coverage_baseline.json"

#: 覆盖率产物落在可删除的 repo 级运行缓存下（`.qwq_output` 只存可重建输出）。
COVERAGE_CACHE_DIR = (
    ROOT / ".qwq_output" / "env" / "repo" / "local" / "coverage" / "cache"
)

APP_ROOT = ROOT / "quwoquan_app"
SERVICE_ROOT = ROOT / "quwoquan_service"

APP_UNIT_PREFIX = "app:"
CLOUD_UNIT_PREFIX = "cloud:"
APP_CROSS_CUTTING_UNIT_PREFIX = f"{APP_UNIT_PREFIX}cross-cutting/"

KIND_FLUTTER_LCOV = "flutter_lcov"
KIND_GO_COVERPROFILE = "go_coverprofile"

#: 每种 kind 必须提供的覆盖率维度。端侧行/分支/触达三轴，云侧只有语句覆盖。
METRICS_BY_KIND = {
    KIND_FLUTTER_LCOV: ("branch", "file", "line"),
    KIND_GO_COVERPROFILE: ("statement",),
}

#: 端侧采集范围。全量 `flutter test --coverage` 在本机 10 分钟以上，L0 提交门禁
#: 承担不起；`test/local_contract` 是 App 的 canonical L0 套件，也是
#: `gate_repo.sh` 里已经在跑的那一份。
APP_TEST_TARGET = "test/local_contract"

#: 云侧被测包集合，与 `services/<name>/Makefile` 的 `SERVICE_PACKAGE` 同形。
SERVICE_PACKAGE_PATTERNS = ("internal", "cmd", "tests")
#: `-coverpkg` 只统计生产代码，测试包自身不计入分母。
SERVICE_COVERPKG_PATTERNS = ("internal", "cmd")
#: api_integration 需要真实环境，不属于 L0 采集范围。
SERVICE_EXCLUDED_PACKAGE_MARKER = "/tests/api_integration"
#: 与根 Makefile 的 `GO_TEST_PACKAGE_PARALLELISM` 默认值一致：限制 package 并发，
#: 避免每个 test binary 各占满 GOMAXPROCS 把带 deadline 的用例饿死。它只影响调度，
#: 不影响覆盖率数值，因此不进 scope 比对。
SERVICE_GO_TEST_PACKAGE_PARALLELISM = 4

METRIC_STATUS_UNMEASURED = "unmeasured"
ARTIFACT_RECEIPT_SCHEMA = "coverage-artifact-provenance/v3"
ARTIFACT_RECEIPT_FIELDS = {
    "schema",
    "ruleId",
    "target",
    "headCommit",
    "headTree",
    "artifactRef",
    "artifactDigest",
    "sourceTreeDigest",
    "testTreeDigest",
    "attributionDigest",
    "configDigest",
    "toolchainDigest",
    "collectionScopeDigest",
    "testsGreen",
}
ARTIFACT_RECEIPT_DIGEST_FIELDS = {
    "artifactDigest",
    "sourceTreeDigest",
    "testTreeDigest",
    "attributionDigest",
    "configDigest",
    "toolchainDigest",
    "collectionScopeDigest",
}
SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")

# ContractGraph 目前没有一条可安全复用的 cloud production source -> object owner
# 映射。domain 聚合只能作为迁移诊断，不能冒充 L2 DEC-002 要求的对象级准出。
CLOUD_OBJECT_COVERAGE_GAP = (
    "OPEN-001: Cloud coverage 仍按 domain 聚合，尚无 canonical object source owner；"
    "domain baseline 不构成对象级准出证据"
)


class CoverageError(RuntimeError):
    """采集或解析失败；一律阻断，不降级成 0 覆盖率或跳过。"""


class RedTestRun(CoverageError):
    """测试没全绿。

    红着的套件测出来的覆盖率既不是准出证据，也不能形成 tracked baseline；产物
    receipt 可以保留 ``testsGreen=false`` 供诊断，但所有复用和写基线路径都阻断。
    """


# ---------------------------------------------------------------------------
# 单元发现（名册全部从 ContractGraph 派生，本文件不写任何 domain 名单）
# ---------------------------------------------------------------------------


def _has_go_sources(directory: Path) -> bool:
    """目录里是否真的有会进入 ``-coverpkg`` 的 production Go 代码。

    并非每个带 `contracts/domain.yaml` 的 service 都是 Go 实现（推荐服务是
    Python 模型服务，`go list` 对它返回空集）。只含 ``tests/**``、``*_test.go``
    或工具样例的目录也不能成为覆盖目标；否则 test-only service 会凭测试代码制造
    一个没有 production statement 分母的假 target。
    """
    return any(
        path.is_file() and not path.is_symlink() and not path.name.endswith("_test.go")
        for root_name in SERVICE_COVERPKG_PATTERNS
        for path in (directory / root_name).rglob("*.go")
    )


@functools.lru_cache(maxsize=1)
def go_collection_targets() -> dict[str, str]:
    """Go 采集目标：``service 相对根 → domain``。

    真相源是 `object_path_map.service_domains()`（扫 `contracts/domain.yaml`，
    同时覆盖 `services/*` 与 `control-plane/*`），再按「有没有 Go 代码」收窄。
    """
    return {
        relative: domain
        for relative, (_owner, domain) in sorted(opm.service_domains().items())
        if _has_go_sources(ROOT / relative)
    }


def app_object_unit(domain: str, context: str, object_name: str) -> str:
    """返回 canonical App 对象计量单元，不维护对象清单。"""
    return f"{APP_UNIT_PREFIX}{domain}/{context}/{object_name}"


def app_cross_cutting_unit(root: str) -> str:
    """返回 canonical 横切根的独立计量单元。"""
    if root not in opm.APP_CROSS_CUTTING_ROOTS:
        raise CoverageError(f"未知 App canonical cross-cutting root {root!r}")
    return f"{APP_CROSS_CUTTING_UNIT_PREFIX}{root}"


def expected_app_capability_units(
    roster: opm.ObjectRoster,
    pages: Sequence[dict],
) -> tuple[str, ...]:
    """派生必须拥有 App production coverage unit 的对象。

    端侧对象义务只有两条 machine-readable 真相源：ContractGraph 中真实存在
    ``clientContract`` 的 operation，以及已经物理归位到 canonical presentation
    路径的 page owner。页面的参与对象不能冒充物理 owner；纯云对象也不能因为存在于
    ContractGraph 就被强制造一个 App 单元。
    """
    object_ids = set(roster.app_client_contract_operations)
    for page in pages:
        physical_owner = opm.derive_page_physical_owner(
            str(page.get("path") or ""), roster
        )
        if physical_owner is not None:
            object_ids.add(physical_owner)
    return tuple(
        sorted(
            app_object_unit(
                roster.objects[object_id]["domain"],
                roster.objects[object_id]["context"],
                roster.objects[object_id]["objectName"],
            )
            for object_id in object_ids
        )
    )


def app_units(roster: opm.ObjectRoster) -> list[str]:
    """从当前 production source 的唯一对象/横切归属派生 App 单元。

    ``AppAttribution`` 对任一非唯一对象或非 canonical 横切源码 fail closed，因此
    返回的每个单元都至少拥有一个真实生产文件，纯云对象不会靠空目录冒充 App 单元。
    """
    return sorted(AppAttribution(roster).files_by_unit)


def cloud_buckets(roster: opm.ObjectRoster) -> list[str]:
    """云侧领域桶；每个 domain 必须落在 roster 内，否则名册与契约已经漂移。"""
    domains = sorted(set(go_collection_targets().values()))
    unknown = [domain for domain in domains if domain not in roster.domains]
    if unknown:
        raise CoverageError(
            f"service domain 不在 ContractGraph roster 内: {unknown}；"
            "先修 contracts/domain.yaml 或重新 codegen contract_graph.json"
        )
    return domains


def cloud_unit(domain: str) -> str:
    return f"{CLOUD_UNIT_PREFIX}{domain}"


@functools.lru_cache(maxsize=1)
def _roster() -> opm.ObjectRoster:
    return vaa.load_roster()


@functools.lru_cache(maxsize=1)
def discover_app_units() -> tuple[str, ...]:
    return tuple(app_units(_roster()))


@functools.lru_cache(maxsize=1)
def discover_cloud_units() -> tuple[str, ...]:
    return tuple(cloud_unit(domain) for domain in cloud_buckets(_roster()))


@functools.lru_cache(maxsize=1)
def discover_units() -> tuple[str, ...]:
    return discover_app_units() + discover_cloud_units()


def unit_kind(unit: str) -> str:
    if unit.startswith(APP_UNIT_PREFIX):
        return KIND_FLUTTER_LCOV
    if unit.startswith(CLOUD_UNIT_PREFIX):
        return KIND_GO_COVERPROFILE
    raise CoverageError(f"无法识别的单元 {unit!r}")


def unit_bucket(unit: str) -> str:
    prefix = APP_UNIT_PREFIX if unit.startswith(APP_UNIT_PREFIX) else CLOUD_UNIT_PREFIX
    return unit[len(prefix) :]


def cloud_services_for(domain: str) -> list[str]:
    return sorted(
        relative
        for relative, mapped in go_collection_targets().items()
        if mapped == domain
    )


def unit_scope(unit: str) -> str:
    """人类可读且逐字段可比的采集范围描述；与实际执行的命令同源派生。

    端侧把归属规则标识 (`object_path_map.RULE_ID`) 写进 scope：反推规则一变，
    同一份 lcov 的分桶结果就不可比，必须重采而不是继续比大小。
    """
    if unit.startswith(APP_UNIT_PREFIX):
        return (
            f"quwoquan_app: flutter test --coverage --branch-coverage {APP_TEST_TARGET}"
            f"; unit={unit_bucket(unit)} attribution={opm.RULE_ID}"
        )
    services = cloud_services_for(unit_bucket(unit))
    if not services:
        raise CoverageError(f"{unit}: 没有任何 Go service 承载该 domain")
    packages = " ".join(
        f"./{relative[len(SERVICE_ROOT.name) + 1 :]}/{pattern}/..."
        for relative in services
        for pattern in SERVICE_PACKAGE_PATTERNS
    )
    return (
        f"quwoquan_service: go test -covermode=atomic {packages} "
        f"(excluding {SERVICE_EXCLUDED_PACKAGE_MARKER})"
    )


# ---------------------------------------------------------------------------
# 采集（采集目标 ≠ 计量单元：端侧一次跑出全部桶，云侧按 service 跑）
# ---------------------------------------------------------------------------

APP_COLLECTION_TARGET = "app"


def collection_targets(units: Sequence[str]) -> list[str]:
    """把计量单元折叠成去重后的采集目标。

    18 个端侧桶共享同一次 `flutter test --coverage`；云侧一个 domain 可能横跨
    多个 service，各自跑一次 `go test`。
    """
    targets: list[str] = []
    for unit in units:
        if unit.startswith(APP_UNIT_PREFIX):
            candidates = [APP_COLLECTION_TARGET]
        else:
            candidates = cloud_services_for(unit_bucket(unit))
        for candidate in candidates:
            if candidate not in targets:
                targets.append(candidate)
    return targets


def artifact_path(target: str) -> Path:
    if target == APP_COLLECTION_TARGET:
        return COVERAGE_CACHE_DIR / "app.lcov.info"
    return COVERAGE_CACHE_DIR / f"{target.replace('/', '__')}.coverprofile"


def artifact_receipt_path(target: str) -> Path:
    path = artifact_path(target)
    return path.with_name(path.name + ".receipt.json")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_json_digest(payload: object) -> str:
    return _sha256_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _sha256_file(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CoverageError(f"覆盖率输入不是安全普通文件: {_display(path)}")
    return _sha256_bytes(path.read_bytes())


def _tree_digest(paths: Iterable[Path], *, label: str) -> str:
    files = sorted({Path(path) for path in paths}, key=lambda path: path.as_posix())
    if not files:
        raise CoverageError(f"{label} 没有任何受管输入")
    manifest: list[dict[str, str]] = []
    for path in files:
        if path.is_symlink():
            raise CoverageError(f"{label} 含符号链接输入: {path}")
        resolved = path.resolve()
        if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():
            raise CoverageError(f"{label} 含不安全输入: {path}")
        manifest.append(
            {
                "path": resolved.relative_to(ROOT.resolve()).as_posix(),
                "digest": _sha256_bytes(resolved.read_bytes()),
            }
        )
    return _sha256_bytes(
        json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _provenance_tree_files(
    root: Path, *, excluded_directory_names: frozenset[str] = frozenset()
) -> list[Path]:
    """返回会影响采集的普通文件/符号链接；输出目录不进入测试输入摘要。"""
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if (path.is_file() or path.is_symlink())
        and not (excluded_directory_names & set(path.relative_to(root).parts[:-1]))
    )


LOCAL_DEPENDENCY_EXCLUDED_DIRECTORY_NAMES = frozenset(
    {".dart_tool", ".git", "build", "coverage", "failures"}
)


def _app_local_path_dependency_roots() -> list[Path]:
    """从 resolver lock 派生 App 实际使用的全部本地 path package 根。

    这里不从 ``vendor/plugins`` 目录形状猜依赖，也不维护 package 名单。lock 中的
    ``source: path`` 是本次 Flutter resolver 真正选择的闭包；路径必须仍位于仓库内，
    否则 receipt 无法由仓库内容复核。
    """
    lock_path = APP_ROOT / "pubspec.lock"
    if not lock_path.is_file() or lock_path.is_symlink():
        raise CoverageError(f"App path dependency closure 缺少安全 lock: {_display(lock_path)}")
    try:
        document = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CoverageError(f"App pubspec.lock 无法解析: {error}") from error
    packages = document.get("packages") if isinstance(document, dict) else None
    if not isinstance(packages, dict):
        raise CoverageError("App pubspec.lock 缺少 packages mapping")

    roots: set[Path] = set()
    repository_root = ROOT.resolve()
    for name, entry in packages.items():
        if not isinstance(entry, dict) or entry.get("source") != "path":
            continue
        description = entry.get("description")
        if not isinstance(description, dict):
            raise CoverageError(f"App path dependency {name!r} description 非 object")
        raw_path = description.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise CoverageError(f"App path dependency {name!r} 缺少 path")
        candidate = (
            APP_ROOT / raw_path
            if description.get("relative") is True
            else Path(raw_path)
        )
        if candidate.is_symlink():
            raise CoverageError(f"App path dependency {name!r} 根不得是符号链接: {candidate}")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(repository_root) or not resolved.is_dir():
            raise CoverageError(
                f"App path dependency {name!r} 不在仓库内或目录不存在: {candidate}"
            )
        roots.add(resolved)
    return sorted(roots, key=lambda path: path.as_posix())


def _required_safe_files(paths: Sequence[Path], *, label: str) -> list[Path]:
    missing = [path for path in paths if not path.is_file() or path.is_symlink()]
    if missing:
        raise CoverageError(
            f"{label} 缺少安全普通文件: " + ", ".join(_display(path) for path in missing)
        )
    return list(paths)


def _app_source_closure_files() -> list[Path]:
    """返回会影响 App 覆盖产物的 production/package source closure。"""
    source = sorted((APP_ROOT / "lib").rglob("*.dart"))
    source += _required_safe_files(
        (
            APP_ROOT / ".flutter-version",
            APP_ROOT / "pubspec.yaml",
            APP_ROOT / "pubspec.lock",
        ),
        label="App source closure",
    )
    for dependency_root in _app_local_path_dependency_roots():
        source += _provenance_tree_files(
            dependency_root,
            excluded_directory_names=LOCAL_DEPENDENCY_EXCLUDED_DIRECTORY_NAMES,
        )
    return sorted(set(source), key=lambda path: path.as_posix())


def _app_collection_inputs() -> tuple[list[Path], list[Path]]:
    source = _app_source_closure_files()
    # Golden/fixture 也是测试输入；只排除 Flutter golden 失败时生成的 diff 输出。
    tests = _provenance_tree_files(
        APP_ROOT / APP_TEST_TARGET,
        excluded_directory_names=frozenset({"failures"}),
    )
    tests += _provenance_tree_files(
        APP_ROOT / "test/support",
        excluded_directory_names=frozenset({"failures"}),
    )
    return source, tests


def _service_collection_inputs(target: str) -> tuple[list[Path], list[Path]]:
    service_root = ROOT / target
    if target not in go_collection_targets():
        raise CoverageError(f"未知覆盖率采集目标 {target!r}")
    source_candidates = [
        path
        for root_name in SERVICE_COVERPKG_PATTERNS
        for path in _provenance_tree_files(service_root / root_name)
    ]
    source = sorted(
        path for path in source_candidates if not path.name.endswith("_test.go")
    )
    tests = sorted(
        path
        for root_name in SERVICE_COVERPKG_PATTERNS
        for path in _provenance_tree_files(service_root / root_name)
        if path.name.endswith("_test.go")
    )
    tests += sorted(
        path
        for path in _provenance_tree_files(service_root / "tests")
        if SERVICE_EXCLUDED_PACKAGE_MARKER not in path.as_posix()
    )
    return source, tests


def _collection_config_inputs(target: str) -> list[Path]:
    if target == APP_COLLECTION_TARGET:
        required = _required_safe_files(
            (
                APP_ROOT / ".flutter-version",
                APP_ROOT / "pubspec.yaml",
                APP_ROOT / "pubspec.lock",
            ),
            label="App coverage config",
        )
        optional = (
            APP_ROOT / "analysis_options.yaml",
            APP_ROOT / "dart_test.yaml",
            APP_ROOT / "test/flutter_test_config.dart",
        )
    else:
        if target not in go_collection_targets():
            raise CoverageError(f"未知覆盖率采集目标 {target!r}")
        required = _required_safe_files(
            (SERVICE_ROOT / "go.mod", SERVICE_ROOT / "go.sum"),
            label="Go coverage config",
        )
        optional = ()
    return required + [
        path for path in optional if path.is_file() or path.is_symlink()
    ]


def _attribution_inputs() -> list[Path]:
    return [
        ROOT / opm.CONTRACT_GRAPH_PATH,
        ROOT / opm.PAGE_OBJECT_CONTRACT_PATH,
        Path(opm.__file__).resolve(),
        Path(vaa.__file__).resolve(),
    ]


def _collection_scope_digest(target: str) -> str:
    if target == APP_COLLECTION_TARGET:
        command = [
            "flutter",
            "test",
            "--coverage",
            "--branch-coverage",
            "--coverage-path=<artifact>",
            "--reporter=compact",
            APP_TEST_TARGET,
        ]
        scopes = [unit_scope(unit) for unit in discover_app_units()]
    else:
        domain = go_collection_targets().get(target)
        if not domain:
            raise CoverageError(f"未知覆盖率采集目标 {target!r}")
        command = [
            "go",
            "test",
            "-count=1",
            f"-p={SERVICE_GO_TEST_PACKAGE_PARALLELISM}",
            "-covermode=atomic",
            "-coverprofile=<artifact>",
            "-coverpkg=<internal,cmd>",
            "<go-list-without-api-integration>",
        ]
        scopes = [unit_scope(cloud_unit(domain))]
    payload = {
        "ruleId": RULE_ID,
        "target": target,
        "command": command,
        "scopes": scopes,
        "gateSourceDigest": _sha256_file(Path(__file__).resolve()),
    }
    return _sha256_bytes(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def _identity_command(command: Sequence[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        list(command), cwd=cwd, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise CoverageError(
            f"provenance identity command 失败 ({' '.join(command)}, "
            f"exit={completed.returncode}): {_tail(completed.stderr)}"
        )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if not output:
        raise CoverageError(
            f"provenance identity command 无输出: {' '.join(command)}"
        )
    return output


def _git_head_identity() -> dict[str, str]:
    identity = {
        "headCommit": _identity_command(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=ROOT
        ),
        "headTree": _identity_command(
            ["git", "rev-parse", "--verify", "HEAD^{tree}"], cwd=ROOT
        ),
    }
    malformed = sorted(
        key
        for key, value in identity.items()
        if GIT_OBJECT_RE.fullmatch(value) is None
    )
    if malformed:
        raise CoverageError(
            "HEAD provenance 非 canonical git object id: " + ", ".join(malformed)
        )
    return identity


def _toolchain_digest(target: str) -> str:
    identity: dict[str, object] = {
        "pythonImplementation": platform.python_implementation(),
        "pythonVersion": platform.python_version(),
    }
    if target == APP_COLLECTION_TARGET:
        identity["flutter"] = _identity_command(
            ["flutter", "--version", "--machine"], cwd=APP_ROOT
        )
        identity["dart"] = _identity_command(["dart", "--version"], cwd=APP_ROOT)
    else:
        identity["go"] = _identity_command(["go", "version"], cwd=SERVICE_ROOT)
        identity["goEnvironment"] = _identity_command(
            ["go", "env", "GOVERSION", "GOOS", "GOARCH", "CGO_ENABLED"],
            cwd=SERVICE_ROOT,
        )
    return _canonical_json_digest(identity)


def current_collection_identity(target: str) -> dict[str, str]:
    if target == APP_COLLECTION_TARGET:
        source, tests = _app_collection_inputs()
    else:
        source, tests = _service_collection_inputs(target)
    return {
        **_git_head_identity(),
        "sourceTreeDigest": _tree_digest(source, label=f"{target} production source"),
        "testTreeDigest": _tree_digest(tests, label=f"{target} tests"),
        "attributionDigest": _tree_digest(
            _attribution_inputs(), label="coverage attribution"
        ),
        "configDigest": _tree_digest(
            _collection_config_inputs(target), label=f"{target} collection config"
        ),
        "toolchainDigest": _toolchain_digest(target),
        "collectionScopeDigest": _collection_scope_digest(target),
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _write_artifact_receipt(
    target: str,
    *,
    tests_green: bool,
    identity: dict[str, str] | None = None,
) -> dict:
    path = artifact_path(target)
    if not path.is_file() or path.is_symlink():
        raise CoverageError(f"覆盖率采集没有安全产物: {_display(path)}")
    payload: dict[str, object] = {
        "schema": ARTIFACT_RECEIPT_SCHEMA,
        "ruleId": RULE_ID,
        "target": target,
        "artifactRef": _display(path),
        "artifactDigest": _sha256_file(path),
        **(identity or current_collection_identity(target)),
        "testsGreen": tests_green,
    }
    _write_json_atomic(artifact_receipt_path(target), payload)
    return payload


def receipt_digest(payload: dict) -> str:
    """Receipt 的内容寻址 identity；不依赖 JSON 缩进或字段顺序。"""
    return _canonical_json_digest(payload)


def _validate_receipt_payload(
    payload: object,
    *,
    expected_target: str | None = None,
    require_green: bool,
) -> dict:
    if not isinstance(payload, dict) or set(payload) != ARTIFACT_RECEIPT_FIELDS:
        raise CoverageError("覆盖率 provenance receipt fields mismatch")
    if payload.get("schema") != ARTIFACT_RECEIPT_SCHEMA:
        raise CoverageError("覆盖率 provenance receipt schema mismatch")
    if payload.get("ruleId") != RULE_ID:
        raise CoverageError("覆盖率 provenance receipt ruleId mismatch")
    target = payload.get("target")
    if not isinstance(target, str) or not target:
        raise CoverageError("覆盖率 provenance receipt target 非法")
    if expected_target is not None and target != expected_target:
        raise CoverageError(
            f"覆盖率 provenance receipt target 漂移: {target!r} != {expected_target!r}"
        )
    try:
        expected_artifact_ref = _display(artifact_path(target))
    except (KeyError, ValueError, CoverageError) as error:
        raise CoverageError(f"覆盖率 provenance receipt target 不可复核: {target!r}") from error
    if payload.get("artifactRef") != expected_artifact_ref:
        raise CoverageError("覆盖率 provenance receipt artifactRef mismatch")
    malformed_digests = sorted(
        key
        for key in ARTIFACT_RECEIPT_DIGEST_FIELDS
        if SHA256_DIGEST_RE.fullmatch(str(payload.get(key) or "")) is None
    )
    if malformed_digests:
        raise CoverageError(
            "覆盖率 provenance digest 非 canonical sha256（"
            + ", ".join(malformed_digests)
            + "）"
        )
    malformed_git = sorted(
        key
        for key in ("headCommit", "headTree")
        if GIT_OBJECT_RE.fullmatch(str(payload.get(key) or "")) is None
    )
    if malformed_git:
        raise CoverageError(
            "覆盖率 provenance git identity 非 canonical object id（"
            + ", ".join(malformed_git)
            + "）"
        )
    if not isinstance(payload.get("testsGreen"), bool):
        raise CoverageError("覆盖率 provenance testsGreen 必须是 boolean")
    if require_green and payload.get("testsGreen") is not True:
        raise CoverageError("覆盖率产物来自未全绿测试，不构成准出证据")
    return payload


def validate_artifact_receipt(target: str) -> dict:
    path = artifact_path(target)
    receipt_path = artifact_receipt_path(target)
    if not path.is_file():
        raise CoverageError(f"缺少覆盖率产物 {_display(path)}；先跑一次 --collect")
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise CoverageError(
            f"覆盖率产物缺少 provenance receipt {_display(receipt_path)}；"
            "旧产物不可复用，必须重新 --collect"
        )
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoverageError(f"覆盖率 provenance receipt 无法读取: {error}") from error
    payload = _validate_receipt_payload(
        payload, expected_target=target, require_green=False
    )
    expected = {
        "schema": ARTIFACT_RECEIPT_SCHEMA,
        "ruleId": RULE_ID,
        "target": target,
        "artifactRef": _display(path),
        "artifactDigest": _sha256_file(path),
        **current_collection_identity(target),
    }
    drifted = sorted(key for key, value in expected.items() if payload.get(key) != value)
    if drifted:
        raise CoverageError(
            "覆盖率产物 provenance 已陈旧（" + ", ".join(drifted) +
            "）；当前源码/测试/归属/采集范围必须重新 --collect"
        )
    if payload.get("testsGreen") is not True:
        raise CoverageError("覆盖率产物来自未全绿测试，不构成准出证据")
    return payload


def _run(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _tail(text: str, *, limit: int = 40) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:]) + ("\n" if lines else "")


def collect_app(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    completed = _run(
        [
            "flutter",
            "test",
            "--coverage",
            "--branch-coverage",
            f"--coverage-path={destination}",
            "--reporter=compact",
            APP_TEST_TARGET,
        ],
        cwd=APP_ROOT,
    )
    if not destination.is_file():
        raise CoverageError(f"flutter test 未产出 lcov: {destination}")
    if completed.returncode != 0:
        raise RedTestRun(
            f"flutter test 失败（exit={completed.returncode}）；覆盖率必须来自绿的测试。\n"
            f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
        )


def collect_service(service_relative: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    inside_module = service_relative[len(SERVICE_ROOT.name) + 1 :]
    listed = _run(
        ["go", "list"]
        + [f"./{inside_module}/{pattern}/..." for pattern in SERVICE_PACKAGE_PATTERNS],
        cwd=SERVICE_ROOT,
    )
    if listed.returncode != 0:
        raise CoverageError(
            f"go list 失败（{service_relative}, exit={listed.returncode}）\n"
            f"{_tail(listed.stderr)}"
        )
    packages = [
        line.strip()
        for line in listed.stdout.splitlines()
        if line.strip() and SERVICE_EXCLUDED_PACKAGE_MARKER not in line
    ]
    if not packages:
        raise CoverageError(f"{service_relative}: go list 没有返回任何可测包")
    coverpkg = ",".join(
        f"./{inside_module}/{pattern}/..." for pattern in SERVICE_COVERPKG_PATTERNS
    )
    completed = _run(
        [
            "go",
            "test",
            "-count=1",
            f"-p={SERVICE_GO_TEST_PACKAGE_PARALLELISM}",
            "-covermode=atomic",
            f"-coverprofile={destination}",
            f"-coverpkg={coverpkg}",
        ]
        + packages,
        cwd=SERVICE_ROOT,
    )
    if not destination.is_file():
        raise CoverageError(
            f"{service_relative}: go test 未产出 coverprofile: {destination}"
        )
    if completed.returncode != 0:
        raise RedTestRun(
            f"go test 失败（{service_relative}, exit={completed.returncode}）；"
            "覆盖率必须来自绿的测试。\n"
            f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
        )


def collect(target: str) -> None:
    destination = artifact_path(target)
    receipt = artifact_receipt_path(target)
    receipt.unlink(missing_ok=True)
    before = current_collection_identity(target)
    red_error: RedTestRun | None = None
    try:
        if target == APP_COLLECTION_TARGET:
            collect_app(destination)
        else:
            collect_service(target, destination)
    except RedTestRun as error:
        red_error = error
    after = current_collection_identity(target)
    if before != after:
        destination.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        raise CoverageError(
            f"{target}: 覆盖率采集期间源码/测试/归属/采集范围发生漂移"
        )
    _write_artifact_receipt(target, tests_green=red_error is None, identity=before)
    if red_error is not None:
        raise red_error


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

#: lcov 的行汇总记录。
LCOV_LINE_SUMMARY_RE = re.compile(r"^(LF|LH):(\d+)\s*$")
#: lcov 的可选分支汇总记录，仅用于与 BRDA 计数交叉校验。
LCOV_BRANCH_SUMMARY_RE = re.compile(r"^(BRF|BRH):(\d+)\s*$")
#: lcov 的分支明细：`BRDA:<line>,<block>,<branch>,<taken>`，`taken` 为 `-` 表示
#: 该分支所在的代码块从未被求值。
LCOV_BRANCH_DETAIL_RE = re.compile(r"^BRDA:\d+,\d+,[^,]+,(?P<taken>-|\d+)\s*$")

#: go coverprofile 的块记录：`file.go:l.c,l.c numStmt count`。
GO_BLOCK_RE = re.compile(
    r"^(?P<block>.+:\d+\.\d+,\d+\.\d+)\s+(?P<statements>\d+)\s+(?P<count>\d+)\s*$"
)


def parse_lcov(text: str) -> dict[str, dict[str, tuple[int, int]]]:
    """解析 lcov，返回 ``{源文件: {"line": (covered,total), "branch": (...)}}``。

    行取 `LF`/`LH` 汇总；分支只数 `BRDA` 明细（Flutter 不写 `BRF`/`BRH`）。
    产出里同时给出 `BRF`/`BRH` 时与 BRDA 计数交叉校验，不一致即阻断——同一个
    维度不允许存在两套口径。
    """
    records: dict[str, dict[str, tuple[int, int]]] = {}
    source: str | None = None
    lines_found = lines_hit = 0
    branches_found = branches_hit = 0
    declared: dict[str, int] = {}

    def flush() -> None:
        if source is None:
            return
        if "BRF" in declared and declared["BRF"] != branches_found:
            raise CoverageError(
                f"{source}: BRF={declared['BRF']} 与 BRDA 计数 {branches_found} 不一致"
            )
        if "BRH" in declared and declared["BRH"] != branches_hit:
            raise CoverageError(
                f"{source}: BRH={declared['BRH']} 与 BRDA 命中数 {branches_hit} 不一致"
            )
        previous = records.get(source)
        if previous is None:
            records[source] = {
                "line": (lines_hit, lines_found),
                "branch": (branches_hit, branches_found),
            }
            return
        records[source] = {
            metric: (
                max(previous[metric][0], value[0]),
                max(previous[metric][1], value[1]),
            )
            for metric, value in {
                "line": (lines_hit, lines_found),
                "branch": (branches_hit, branches_found),
            }.items()
        }

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("SF:"):
            flush()
            source = stripped[len("SF:") :]
            lines_found = lines_hit = branches_found = branches_hit = 0
            declared = {}
            continue
        if source is None:
            continue
        line_summary = LCOV_LINE_SUMMARY_RE.match(stripped)
        if line_summary:
            if line_summary.group(1) == "LF":
                lines_found = int(line_summary.group(2))
            else:
                lines_hit = int(line_summary.group(2))
            continue
        branch_summary = LCOV_BRANCH_SUMMARY_RE.match(stripped)
        if branch_summary:
            declared[branch_summary.group(1)] = int(branch_summary.group(2))
            continue
        branch_detail = LCOV_BRANCH_DETAIL_RE.match(stripped)
        if branch_detail:
            branches_found += 1
            if branch_detail.group("taken") not in {"-", "0"}:
                branches_hit += 1
    flush()
    if not records:
        raise CoverageError("lcov 中没有任何 SF: 记录")
    return records


def parse_go_coverprofile(text: str) -> dict[str, tuple[int, int]]:
    """解析 go coverprofile，返回 ``{"statement": (covered, total)}``。

    首行是 `mode: atomic`。其后每行一个基本块，同一个块可能出现多次（不同测试
    二进制各写一份），按块去重并对计数求和，与 `go tool cover -func` 同口径。
    """
    lines = text.splitlines()
    if not lines or not lines[0].startswith("mode:"):
        raise CoverageError("go coverprofile 缺少 `mode:` 首行")
    blocks: dict[str, tuple[int, int]] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        match = GO_BLOCK_RE.match(stripped)
        if match is None:
            raise CoverageError(f"go coverprofile 无法解析的块记录: {stripped!r}")
        block = match.group("block")
        statements = int(match.group("statements"))
        count = int(match.group("count"))
        previous_statements, previous_count = blocks.get(block, (statements, 0))
        blocks[block] = (previous_statements, previous_count + count)
    if not blocks:
        raise CoverageError("go coverprofile 没有任何块记录")
    total = sum(statements for statements, _ in blocks.values())
    covered = sum(statements for statements, count in blocks.values() if count > 0)
    return {"statement": (covered, total)}


# ---------------------------------------------------------------------------
# 端侧归属（全部经 object_path_map，不写第二套规则）
# ---------------------------------------------------------------------------

LIB_PREFIX = "lib/"


class AppAttribution:
    """`lib/**` 生产文件 → canonical 对象/横切单元及磁盘文件名册。"""

    def __init__(self, roster: opm.ObjectRoster) -> None:
        page_claims, pages = opm.load_page_claims()
        rows, _findings = opm.scan_app(roster, page_claims)
        self.unit_of: dict[str, str] = {}
        self.files_by_unit: dict[str, set[str]] = {}
        unowned: list[dict] = []
        repository_prefix = f"{opm.APP_LIB_ROOT.as_posix()}/"
        for row in rows:
            if row.get("role") != "production":
                continue
            path = str(row.get("path") or "")
            if not path.startswith(repository_prefix):
                raise CoverageError(f"App production source path 非 canonical repo path: {path!r}")
            library_relative = path[len(repository_prefix) :]
            object_id = str(row.get("objectId") or "")
            unit: str | None = None
            if object_id:
                record = roster.objects.get(object_id)
                if record is None:
                    raise CoverageError(
                        f"{path}: object_path_map 返回未知 objectId {object_id!r}"
                    )
                unit = app_object_unit(
                    record["domain"], record["context"], record["objectName"]
                )
            elif row.get("status") == "canonical_cross_cutting":
                root = str(row.get("crossCuttingRoot") or "")
                unit = app_cross_cutting_unit(root)
            else:
                unowned.append(row)
                continue
            previous = self.unit_of.get(library_relative)
            if previous is not None and previous != unit:
                raise CoverageError(
                    f"{path}: 同一 production source 被归入多个 coverage unit: "
                    f"{previous!r}, {unit!r}"
                )
            self.unit_of[library_relative] = unit
            self.files_by_unit.setdefault(unit, set()).add(library_relative)

        if unowned:
            examples = [
                (
                    f"{row.get('path')} "
                    f"(status={row.get('status')}, method={row.get('method')})"
                )
                for row in unowned[:20]
            ]
            suffix = f"\n  ... 另有 {len(unowned) - len(examples)} 个" if len(unowned) > len(examples) else ""
            raise CoverageError(
                "App production source 没有唯一 canonical object owner，且也不在 "
                "canonical cross-cutting root；必须先修归属，禁止登记 allowance：\n  "
                + "\n  ".join(examples)
                + suffix
            )
        missing_capability_units = sorted(
            set(expected_app_capability_units(roster, pages)) - set(self.files_by_unit)
        )
        if missing_capability_units:
            raise CoverageError(
                "App capability object 没有 owned production coverage unit；"
                "clientContract operation / canonical page owner 不能被空 baseline 放行：\n  "
                + "\n  ".join(missing_capability_units[:20])
                + (
                    f"\n  ... 另有 {len(missing_capability_units) - 20} 个"
                    if len(missing_capability_units) > 20
                    else ""
                )
            )
        if not self.files_by_unit:
            raise CoverageError("App 没有任何可计量的 production source unit")

    def known(self, source: str) -> bool:
        """lcov 的 `SF:` 路径是否属于本次派生覆盖到的 `lib/**` 生产文件。"""
        if not source.startswith(LIB_PREFIX):
            return False
        library_relative = source[len(LIB_PREFIX) :]
        return library_relative in self.unit_of


def _measure_app_unit(
    unit: str,
    lcov: dict[str, dict[str, tuple[int, int]]],
    attribution: AppAttribution,
) -> dict[str, dict]:
    try:
        on_disk = attribution.files_by_unit[unit]
    except KeyError as error:
        raise CoverageError(f"{unit}: 没有 production source 计量单元") from error
    reached = 0
    line_covered = line_total = 0
    branch_covered = branch_total = 0
    for source, values in lcov.items():
        library_relative = source[len(LIB_PREFIX) :] if source.startswith(LIB_PREFIX) else source
        if attribution.unit_of.get(library_relative) != unit:
            continue
        reached += 1
        line_covered += values["line"][0]
        line_total += values["line"][1]
        branch_covered += values["branch"][0]
        branch_total += values["branch"][1]
    return {
        "file": _metric(
            reached,
            len(on_disk),
            unmeasured_reason="该 App 单元在 lib/** 下没有任何生产文件",
        ),
        "line": _metric(
            line_covered,
            line_total,
            unmeasured_reason=(
                f"{APP_TEST_TARGET} 没有任何测试加载该 App 单元的 lib 文件"
                f"（磁盘 {len(on_disk)} 个，lcov 触达 {reached} 个）"
            ),
        ),
        "branch": _metric(
            branch_covered,
            branch_total,
            unmeasured_reason=(
                f"{APP_TEST_TARGET} 触达的该 App 单元文件里没有任何可判定分支"
                f"（磁盘 {len(on_disk)} 个，lcov 触达 {reached} 个）"
            ),
        ),
    }


def _metric(covered: int, total: int, *, unmeasured_reason: str) -> dict:
    """把 ``covered/total`` 折成 metric 条目；分母为 0 时如实标不可测，不写 0%。"""
    if total <= 0:
        return {"status": METRIC_STATUS_UNMEASURED, "reason": unmeasured_reason}
    return {"covered": covered, "total": total, "percent": percent(covered, total)}


def percent(covered: int, total: int) -> float:
    return round(covered * 100.0 / total, 2)


def _display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _read_artifact(target: str) -> tuple[str, dict]:
    path = artifact_path(target)
    receipt = validate_artifact_receipt(target)
    return path.read_text(encoding="utf-8", errors="replace"), receipt


def measure(units: Sequence[str]) -> tuple[dict[str, dict[str, dict]], dict]:
    """读取落盘产物，折算成 ``{unit: {metric: entry}}`` 与全局附加事实。"""
    measured: dict[str, dict[str, dict]] = {}
    unit_receipts: dict[str, list[dict]] = {}
    app_units = [unit for unit in units if unit.startswith(APP_UNIT_PREFIX)]
    if app_units:
        attribution = AppAttribution(_roster())
        app_text, app_receipt = _read_artifact(APP_COLLECTION_TARGET)
        lcov = parse_lcov(app_text)
        unknown = sorted(source for source in lcov if not attribution.known(source))
        if unknown:
            raise CoverageError(
                "lcov 里有不属于当前 canonical 对象/横切单元的源文件"
                "（归属派生器与产物不同源）：\n  "
                + "\n  ".join(unknown[:20])
            )
        for unit in app_units:
            measured[unit] = _measure_app_unit(unit, lcov, attribution)
            unit_receipts[unit] = [app_receipt]

    for unit in units:
        if unit.startswith(APP_UNIT_PREFIX):
            continue
        blocks: dict[str, tuple[int, int]] = {}
        receipts: list[dict] = []
        for service_relative in cloud_services_for(unit_bucket(unit)):
            artifact_text, receipt = _read_artifact(service_relative)
            covered, total = parse_go_coverprofile(artifact_text)["statement"]
            blocks[service_relative] = (covered, total)
            receipts.append(receipt)
        covered = sum(value[0] for value in blocks.values())
        total = sum(value[1] for value in blocks.values())
        if total <= 0:
            raise CoverageError(
                f"{unit}: statement 分母为 0，采集没有真正生效"
            )
        measured[unit] = {"statement": _metric(covered, total, unmeasured_reason="")}
        unit_receipts[unit] = receipts
    return measured, {"unitReceipts": unit_receipts}


# ---------------------------------------------------------------------------
# 基线
# ---------------------------------------------------------------------------

POLICY_NUMERIC_KEYS = (
    "tolerance_percentage_points",
    "ratchet_slack_percentage_points",
    "granularity_units",
)
POLICY_REASON_KEYS = (
    "tolerance_reason",
    "ratchet_slack_reason",
    "granularity_units_reason",
)
BASELINE_TOP_LEVEL_FIELDS = {
    "_governance",
    "schema",
    "ruleId",
    "policy",
    "receipts",
    "units",
}
BASELINE_GOVERNANCE_FIELDS = {"owner", "reason", "expires_when"}
BASELINE_UNIT_FIELDS = {
    "kind",
    "scope",
    "measuredFromGreenTests",
    "receiptDigests",
    "metrics",
}


def _validate_baseline_metric(unit: str, metric: str, entry: object) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{BASELINE_PATH}: {unit}/{metric} 必须是 object")
    if entry.get("status") == METRIC_STATUS_UNMEASURED:
        if set(entry) != {"status", "reason"} or not str(entry.get("reason") or "").strip():
            raise ValueError(
                f"{BASELINE_PATH}: {unit}/{metric} unmeasured 必须只含 status/reason"
            )
        return
    if set(entry) != {"covered", "total", "percent"}:
        raise ValueError(
            f"{BASELINE_PATH}: {unit}/{metric} measured fields mismatch"
        )
    covered = entry.get("covered")
    total = entry.get("total")
    value = entry.get("percent")
    if (
        not isinstance(covered, int)
        or isinstance(covered, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total <= 0
        or covered < 0
        or covered > total
        or not isinstance(value, (int, float))
        or isinstance(value, bool)
        or float(value) != percent(covered, total)
    ):
        raise ValueError(f"{BASELINE_PATH}: {unit}/{metric} measured value 非自洽实测值")


def _validate_baseline_receipt_registry(receipts: object) -> dict[str, dict]:
    if not isinstance(receipts, dict):
        raise ValueError(f"{BASELINE_PATH}: receipts 必须是 object")
    validated: dict[str, dict] = {}
    for declared_digest, payload in receipts.items():
        if SHA256_DIGEST_RE.fullmatch(str(declared_digest or "")) is None:
            raise ValueError(f"{BASELINE_PATH}: receipt key 非 canonical sha256")
        try:
            receipt = _validate_receipt_payload(
                payload, expected_target=None, require_green=True
            )
        except CoverageError as error:
            raise ValueError(f"{BASELINE_PATH}: receipt {declared_digest}: {error}") from error
        actual_digest = receipt_digest(receipt)
        if declared_digest != actual_digest:
            raise ValueError(
                f"{BASELINE_PATH}: receipt {declared_digest} 内容摘要伪造，"
                f"实测 {actual_digest}"
            )
        validated[declared_digest] = receipt
    return validated


def _validate_unit_receipt_refs(
    unit: str,
    entry: dict,
    receipt_registry: dict[str, dict],
) -> None:
    refs = entry.get("receiptDigests")
    if (
        not isinstance(refs, list)
        or not refs
        or refs != sorted(set(refs))
        or any(SHA256_DIGEST_RE.fullmatch(str(ref or "")) is None for ref in refs)
    ):
        raise ValueError(
            f"{BASELINE_PATH}: {unit}.receiptDigests 必须是非空、去重、有序 sha256 列表"
        )
    missing = sorted(set(refs) - set(receipt_registry))
    if missing:
        raise ValueError(
            f"{BASELINE_PATH}: {unit}.receiptDigests 引用缺失 receipt: {missing}"
        )
    actual_targets = sorted(receipt_registry[ref]["target"] for ref in refs)
    expected_targets = sorted(collection_targets([unit]))
    if actual_targets != expected_targets:
        raise ValueError(
            f"{BASELINE_PATH}: {unit}.receiptDigests target 绑定伪造；"
            f"baseline={actual_targets}, expected={expected_targets}"
        )


def load_baseline() -> dict:
    if not BASELINE_PATH.is_file():
        raise FileNotFoundError(BASELINE_PATH)
    document = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{BASELINE_PATH}: baseline 必须是 object")
    if set(document) != BASELINE_TOP_LEVEL_FIELDS:
        missing = sorted(BASELINE_TOP_LEVEL_FIELDS - set(document))
        extra = sorted(set(document) - BASELINE_TOP_LEVEL_FIELDS)
        if "receipts" in missing:
            raise ValueError(
                f"{BASELINE_PATH}: baseline 缺少可复核 receipt provenance；"
                "旧 measuredFromGreenTests 布尔值不得冒充绿测试来源"
            )
        raise ValueError(
            f"{BASELINE_PATH}: baseline fields mismatch; missing={missing}, extra={extra}"
        )
    if document.get("schema") != BASELINE_SCHEMA:
        raise ValueError(
            f"{BASELINE_PATH}: schema 必须是 {BASELINE_SCHEMA}，"
            f"实测 {document.get('schema')!r}"
        )
    if document.get("ruleId") != RULE_ID:
        raise ValueError(
            f"{BASELINE_PATH}: ruleId 必须是 {RULE_ID}，实测 {document.get('ruleId')!r}"
        )
    governance = document.get("_governance")
    if not isinstance(governance, dict) or set(governance) != BASELINE_GOVERNANCE_FIELDS:
        raise ValueError(f"{BASELINE_PATH}: _governance fields mismatch")
    for key in BASELINE_GOVERNANCE_FIELDS:
        if not str(governance.get(key) or "").strip():
            raise ValueError(f"{BASELINE_PATH}: _governance.{key} 不得为空")
    policy = document.get("policy") or {}
    if not isinstance(policy, dict) or set(policy) != set(POLICY_NUMERIC_KEYS) | set(
        POLICY_REASON_KEYS
    ):
        raise ValueError(f"{BASELINE_PATH}: policy fields mismatch")
    for key in POLICY_NUMERIC_KEYS:
        value = policy.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{BASELINE_PATH}: policy.{key} 必须是非负数，实测 {value!r}")
    for key in POLICY_REASON_KEYS:
        if not str(policy.get(key) or "").strip():
            raise ValueError(f"{BASELINE_PATH}: policy.{key} 必须写明理由")
    receipt_registry = _validate_baseline_receipt_registry(document.get("receipts"))
    units = document.get("units")
    if not isinstance(units, dict):
        raise ValueError(f"{BASELINE_PATH}: units 必须是 object")
    for unit, entry in units.items():
        if not isinstance(unit, str) or not isinstance(entry, dict):
            raise ValueError(f"{BASELINE_PATH}: unit entry 非法: {unit!r}")
        if set(entry) != BASELINE_UNIT_FIELDS:
            raise ValueError(f"{BASELINE_PATH}: {unit} fields mismatch")
        try:
            expected_kind = unit_kind(unit)
        except CoverageError as error:
            raise ValueError(f"{BASELINE_PATH}: {error}") from error
        if entry.get("kind") != expected_kind:
            raise ValueError(f"{BASELINE_PATH}: {unit}.kind 与单元不一致")
        if not str(entry.get("scope") or "").strip():
            raise ValueError(f"{BASELINE_PATH}: {unit}.scope 不得为空")
        if entry.get("measuredFromGreenTests") is not True:
            raise ValueError(
                f"{BASELINE_PATH}: {unit}.measuredFromGreenTests 必须是 true；"
                "红测试或旧暂定基线不得复用"
            )
        _validate_unit_receipt_refs(unit, entry, receipt_registry)
        metrics = entry.get("metrics")
        expected_metrics = set(METRICS_BY_KIND[expected_kind])
        if not isinstance(metrics, dict) or set(metrics) != expected_metrics:
            raise ValueError(f"{BASELINE_PATH}: {unit}.metrics 维度不完整")
        for metric, metric_entry in metrics.items():
            _validate_baseline_metric(unit, metric, metric_entry)
    referenced_receipts = {
        digest for entry in units.values() for digest in entry["receiptDigests"]
    }
    unreferenced = sorted(set(receipt_registry) - referenced_receipts)
    if unreferenced:
        raise ValueError(
            f"{BASELINE_PATH}: receipts 含未被任何 baseline entry 引用的条目: {unreferenced}"
        )
    return document


def unit_entry(
    metrics: dict[str, dict],
    unit: str,
    *,
    receipts: Sequence[dict],
) -> dict:
    validated_receipts = [
        _validate_receipt_payload(receipt, expected_target=None, require_green=True)
        for receipt in receipts
    ]
    receipt_refs = sorted(receipt_digest(receipt) for receipt in validated_receipts)
    registry = {
        receipt_digest(receipt): receipt for receipt in validated_receipts
    }
    provisional = {"receiptDigests": receipt_refs}
    _validate_unit_receipt_refs(unit, provisional, registry)
    return {
        "kind": unit_kind(unit),
        "scope": unit_scope(unit),
        "measuredFromGreenTests": True,
        "receiptDigests": receipt_refs,
        "metrics": {
            metric: dict(metrics[metric])
            for metric in sorted(METRICS_BY_KIND[unit_kind(unit)])
        },
    }


def write_baseline(
    measured: dict[str, dict],
    *,
    units: Sequence[str],
    unit_receipts: dict[str, Sequence[dict]],
    known_units: Sequence[str] | None = None,
) -> dict:
    """把本次绿产物写回基线，并为每个 entry 绑定可复核 receipt。"""
    missing_receipts = sorted(set(units) - set(unit_receipts))
    extra_receipts = sorted(set(unit_receipts) - set(units))
    if missing_receipts or extra_receipts:
        raise CoverageError(
            "baseline provenance 与求值单元不一致；"
            f"missing={missing_receipts}, extra={extra_receipts}"
        )
    try:
        payload = load_baseline()
    except FileNotFoundError as error:
        raise CoverageError(
            "缺少 tracked coverage baseline；不得由局部采集凭空创建 governance/policy"
        ) from error
    except (ValueError, json.JSONDecodeError) as error:
        # v1 -> v2 不能保留没有 receipt 的历史数字，也不能局部抹掉另一 family。
        # 只有所有已知单元同次真实绿采集后，才允许整体迁移。
        if set(units) != set(discover_units()):
            raise CoverageError(
                "现有 coverage baseline 缺少可复核 receipt provenance；"
                "禁止局部迁移或沿用旧数字，须在 Cloud 对象 owner 闭合后全量重采"
            ) from error
        raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise CoverageError("现有 coverage baseline 不是 JSON object") from error
        payload = {
            "_governance": raw.get("_governance", {}),
            "schema": BASELINE_SCHEMA,
            "ruleId": RULE_ID,
            "policy": raw.get("policy", {}),
            "receipts": {},
            "units": {},
        }
    payload.setdefault("receipts", {})
    payload.setdefault("units", {})
    payload["schema"] = BASELINE_SCHEMA
    payload["ruleId"] = RULE_ID

    if known_units is not None:
        includes_app = any(unit.startswith(APP_UNIT_PREFIX) for unit in units)
        includes_cloud = any(unit.startswith(CLOUD_UNIT_PREFIX) for unit in units)
        known = set(known_units)
        for unit in list(payload["units"]):
            in_selected_family = (
                includes_app and unit.startswith(APP_UNIT_PREFIX)
            ) or (includes_cloud and unit.startswith(CLOUD_UNIT_PREFIX))
            if in_selected_family and unit not in known:
                payload["units"].pop(unit)
    for unit in units:
        receipts = list(unit_receipts[unit])
        for receipt in receipts:
            validated = _validate_receipt_payload(
                receipt, expected_target=None, require_green=True
            )
            payload["receipts"][receipt_digest(validated)] = dict(validated)
        payload["units"][unit] = unit_entry(
            measured[unit], unit, receipts=receipts
        )

    referenced_receipts = {
        digest
        for entry in payload["units"].values()
        for digest in entry["receiptDigests"]
    }
    payload["receipts"] = {
        digest: payload["receipts"][digest]
        for digest in sorted(referenced_receipts)
    }
    reserved = {
        "_governance",
        "schema",
        "ruleId",
        "policy",
        "receipts",
        "units",
    }
    ordered = {
        "_governance": payload["_governance"],
        "schema": BASELINE_SCHEMA,
        "ruleId": RULE_ID,
        "policy": payload["policy"],
        "receipts": payload["receipts"],
    }
    # baseline schema 不接受计数 allowance 或其他附加字段；所有 production
    # source 必须进入对象/cross-cutting 单元，否则在归属阶段立即 BLOCK。
    for key in list(payload):
        if key not in reserved:
            payload.pop(key)
    ordered["units"] = {unit: payload["units"][unit] for unit in sorted(payload["units"])}
    _write_json_atomic(BASELINE_PATH, ordered)
    return ordered


# ---------------------------------------------------------------------------
# 求值
# ---------------------------------------------------------------------------


def thresholds(policy: dict, total: int) -> tuple[float, float]:
    """返回该分母下生效的 ``(容差, slack)``，含「一个可数单位」的粒度下限。

    领域桶的分母跨三个数量级：`content` 有上万行，`notification` 只有几十个分支。
    固定的 pp 阈值在小桶上等于噪声放大器——动一个分支就是好几个百分点。因此阈值
    取「配置 pp」与「`granularity_units` 个可数单位折算出的 pp」的较大者：测不出
    比一个语句/分支更细的差别，就不该拿比它更细的阈值去阻断。
    """
    unit_pp = 100.0 / total
    granularity = float(policy["granularity_units"]) * unit_pp
    return (
        max(float(policy["tolerance_percentage_points"]), granularity),
        max(float(policy["ratchet_slack_percentage_points"]), granularity),
    )


def diff(
    measured: dict[str, dict[str, dict]],
    baseline: dict,
    units: Sequence[str],
    *,
    known_units: Sequence[str] | None = None,
) -> list[str]:
    """返回阻断原因列表；空列表表示通过。"""
    policy = baseline.get("policy") or {}
    recorded_units = baseline.get("units") or {}
    failures: list[str] = []
    try:
        receipt_registry = _validate_baseline_receipt_registry(
            baseline.get("receipts")
        )
    except ValueError as error:
        return [f"baseline provenance 无法复核: {error}"]

    for unit in units:
        recorded = recorded_units.get(unit)
        if recorded is None:
            failures.append(
                f"{unit}: 未登记单元（仓库里存在，基线里没有）；用 --write-baseline 登记"
            )
            continue
        try:
            _validate_unit_receipt_refs(unit, recorded, receipt_registry)
        except ValueError as error:
            failures.append(f"{unit}: baseline provenance 无法复核: {error}")
            continue
        if recorded.get("kind") != unit_kind(unit):
            failures.append(
                f"{unit}: kind 漂移，基线 {recorded.get('kind')!r} != 现状 {unit_kind(unit)!r}"
            )
            continue
        if recorded.get("scope") != unit_scope(unit):
            failures.append(
                f"{unit}: 采集范围漂移，基线与现状不可比；\n"
                f"    baseline: {recorded.get('scope')}\n"
                f"    current : {unit_scope(unit)}"
            )
            continue
        if not recorded.get("measuredFromGreenTests", False):
            failures.append(
                f"{unit}: 基线是暂定值（measuredFromGreenTests=false，采集时测试没全绿）；"
                "测试已绿则用 --collect --write-baseline 重新采集"
            )
            continue
        recorded_metrics = recorded.get("metrics") or {}
        for metric in METRICS_BY_KIND[unit_kind(unit)]:
            if metric not in recorded_metrics:
                failures.append(f"{unit}/{metric}: 基线缺少该维度")
                continue
            failures += _diff_metric(
                unit, metric, measured[unit][metric], recorded_metrics[metric], policy
            )

    if known_units is not None:
        includes_app = any(unit.startswith(APP_UNIT_PREFIX) for unit in units)
        includes_cloud = any(unit.startswith(CLOUD_UNIT_PREFIX) for unit in units)
        recorded_in_scope = {
            unit
            for unit in recorded_units
            if (includes_app and unit.startswith(APP_UNIT_PREFIX))
            or (includes_cloud and unit.startswith(CLOUD_UNIT_PREFIX))
        }
        stale = sorted(recorded_in_scope - set(known_units))
        failures += [
            f"{unit}: 基线里的陈旧单元（仓库里已不存在）；用 --write-baseline 收敛"
            for unit in stale
        ]
    return failures


def _diff_metric(
    unit: str,
    metric: str,
    current: dict,
    recorded: dict,
    policy: dict,
) -> list[str]:
    """比对单个维度；可测性在任一方向变化都阻断，绝不把不可测折成 0%。"""
    current_unmeasured = current.get("status") == METRIC_STATUS_UNMEASURED
    recorded_unmeasured = recorded.get("status") == METRIC_STATUS_UNMEASURED
    if current_unmeasured and recorded_unmeasured:
        return []
    if current_unmeasured:
        return [
            f"{unit}/{metric}: 基线有实测值 {recorded.get('percent')}%，现在测不出来了"
            f"（{current.get('reason')}）；测不出与归零对准出等价，不得放行"
        ]
    if recorded_unmeasured:
        return [
            f"{unit}/{metric}: 基线登记为不可测，现在可测了（{current['percent']:.2f}%，"
            f"{current['covered']}/{current['total']}）；用 --write-baseline 登记真实数字"
        ]
    floor = float(recorded["percent"])
    value = float(current["percent"])
    if metric == "file":
        # file 轴专门堵住「删掉覆盖差的测试 import，让 lcov 分母缩水」的路径。
        # 一个小桶可能只有两三个文件；若沿用两个可数单位的粒度下限，删掉其中
        # 一个会落在 50%~100% 的容差内，恰好把这条防线架空。
        tolerance = float(policy["tolerance_percentage_points"])
        slack = float(policy["ratchet_slack_percentage_points"])
    else:
        tolerance, slack = thresholds(policy, int(current["total"]))
    if value < floor - tolerance:
        return [
            f"{unit}/{metric}: 覆盖率下降 {value:.2f}% < 基线 {floor:.2f}% "
            f"- 容差 {tolerance:.2f}pp（{current['covered']}/{current['total']}）"
        ]
    if value > floor + slack:
        return [
            f"{unit}/{metric}: 覆盖率已升到 {value:.2f}%，超出基线 {floor:.2f}% "
            f"+ slack {slack:.2f}pp；用 --write-baseline 收紧基线"
            f"（{current['covered']}/{current['total']}）"
        ]
    return []


def summarize(measured: dict[str, dict[str, dict]], units: Sequence[str]) -> dict:
    return {
        "ruleId": RULE_ID,
        "units": {
            unit: {
                metric: dict(measured[unit][metric])
                for metric in sorted(measured[unit])
            }
            for unit in units
        },
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def known_units_for(units: Sequence[str]) -> tuple[str, ...]:
    """返回所选 family 的完整当前名册，用于陈旧 baseline 检查。"""
    known: tuple[str, ...] = ()
    if any(unit.startswith(APP_UNIT_PREFIX) for unit in units):
        known += discover_app_units()
    if any(unit.startswith(CLOUD_UNIT_PREFIX) for unit in units):
        known += discover_cloud_units()
    return known


def resolve_units(scope: str, requested: Iterable[str] | None) -> list[str]:
    if requested:
        selected = tuple(dict.fromkeys(requested))
        invalid = sorted(
            unit
            for unit in selected
            if not unit.startswith((APP_UNIT_PREFIX, CLOUD_UNIT_PREFIX))
        )
        if invalid:
            raise ValueError(f"无法识别的单元 {invalid}")
        known = known_units_for(selected)
        unknown = sorted(set(selected) - set(known))
        if unknown:
            raise ValueError(f"未知单元 {unknown}；可用单元 {known}")
        return [unit for unit in known if unit in set(selected)]
    if scope == "app":
        return list(discover_app_units())
    if scope in {"cloud", "service"}:
        return list(discover_cloud_units())
    return list(discover_units())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "代码覆盖率棘轮门禁（App 按对象只增不减；Cloud 对象 owner 未闭合时阻断）"
        )
    )
    parser.add_argument(
        "--scope",
        choices=("all", "app", "cloud", "service"),
        default="all",
        help="求值范围；`--unit` 优先于 `--scope`",
    )
    parser.add_argument(
        "--unit",
        action="append",
        default=None,
        help=(
            "只处理该单元（可重复），例如 "
            "app:circle/circle_management/gathering / cloud:tag"
        ),
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="先跑测试采集覆盖率再求值；不带该参数时复用已落盘产物",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="用本次实测值重写基线；未求值的单元分区原样保留",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)

    try:
        units = resolve_units(arguments.scope, arguments.unit)
    except (ValueError, CoverageError) as error:
        print(f"verify_coverage_ratchet: BLOCK: {error}", file=sys.stderr)
        return 2

    if any(unit.startswith(CLOUD_UNIT_PREFIX) for unit in units):
        # 现有 domain coverprofile 仍可用于本地诊断，但不能作为 DEC-002 的对象级
        # baseline。对象 source owner 未单轨前 fail closed，也禁止 --collect 写假绿。
        print(
            f"verify_coverage_ratchet: GATE_BLOCK: {CLOUD_OBJECT_COVERAGE_GAP}",
            file=sys.stderr,
        )
        return 2

    if arguments.write_baseline and not arguments.collect:
        # 基线里的 `measuredFromGreenTests` 只有本次真的跑过测试才说得出口；
        # 复用旧产物写基线等于凭空断言 provenance。
        print(
            "verify_coverage_ratchet: BLOCK: --write-baseline 必须搭配 --collect，"
            "基线只能由本次实跑的测试写入",
            file=sys.stderr,
        )
        return 2

    if arguments.collect:
        for target in collection_targets(units):
            try:
                print(f"verify_coverage_ratchet: collecting {target} ...", flush=True)
                collect(target)
            except RedTestRun as error:
                print(
                    f"verify_coverage_ratchet: BLOCK: {target}: {error}",
                    file=sys.stderr,
                )
                return 1
            except CoverageError as error:
                print(
                    f"verify_coverage_ratchet: BLOCK: {target}: {error}", file=sys.stderr
                )
                return 1

    try:
        measured, extras = measure(units)
    except CoverageError as error:
        print(f"verify_coverage_ratchet: BLOCK: {error}", file=sys.stderr)
        return 1

    if arguments.write_baseline:
        try:
            write_baseline(
                measured,
                units=units,
                unit_receipts=extras["unitReceipts"],
                known_units=known_units_for(units),
            )
        except (CoverageError, ValueError, json.JSONDecodeError) as error:
            print(f"verify_coverage_ratchet: GATE_BLOCK: {error}", file=sys.stderr)
            return 2
        print(f"verify_coverage_ratchet: wrote baseline -> {_display(BASELINE_PATH)}")
        print(json.dumps(summarize(measured, units), ensure_ascii=False, sort_keys=True))
        return 0

    try:
        baseline = load_baseline()
    except FileNotFoundError:
        print(
            "verify_coverage_ratchet: BLOCK: missing "
            f"{BASELINE_PATH} (run once with --collect --write-baseline)",
            file=sys.stderr,
        )
        return 2
    except (ValueError, json.JSONDecodeError) as error:
        print(f"verify_coverage_ratchet: FAIL load baseline: {error}", file=sys.stderr)
        return 1

    failures = diff(
        measured,
        baseline,
        units,
        known_units=known_units_for(units),
    )
    if failures:
        print("verify_coverage_ratchet: BLOCK: coverage ratchet", file=sys.stderr)
        for entry in failures:
            print(f"  {entry}", file=sys.stderr)
        print(
            "  覆盖率只增不减：新增代码必须带测试。修不动时补测试，"
            "不要下调基线；覆盖率真的提升了就用 --write-baseline 收紧。",
            file=sys.stderr,
        )
        return 1

    print(f"verify_coverage_ratchet: OK ({len(units)} unit(s))")
    print(json.dumps(summarize(measured, units), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
