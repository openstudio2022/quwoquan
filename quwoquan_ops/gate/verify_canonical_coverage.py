#!/usr/bin/env python3
"""唯一 canonical coverage rule，按 ContractGraph 对象身份计量。

覆盖率与架构违规的方向相反：架构基线记录「违规条目集合」并要求只减不增，覆盖率
基线记录「已达成的覆盖率」并要求只增不减。canonical rule 只有一套语义：

* 现状低于基线（超出容差）→ BLOCK，说明这次改动稀释了被测代码。
* 现状显著高于基线（超出 slack）→ BLOCK，要求 `--write-baseline` 把基线收紧，
  避免基线长期停留在远低于现实的水位，退化成摆设。
* 仓库里出现基线没有登记的单元 → BLOCK；基线里留着仓库已不存在的单元 → BLOCK。
* 基线只接受 `measuredFromGreenTests: true`；红测试不得形成或改写 tracked baseline。

为什么端云都必须按对象计量
--------------------------

仓库级或 domain 级平均数无法回答「某个对象是否可准出」：同一 domain 内高覆盖对象
会把零覆盖对象完全淹没。因此覆盖率单元是 production 的 canonical
``service/context/object`` 身份，名册从
`quwoquan_service/generated/contract_graph.json` 与 `object_path_map.scan_app` 实时派生，
本文件不复制任何 domain/object 名单：

``app:<service>/<context>/<object>``
    端侧业务对象。每个 `lib/**` 生产文件的归属直接复用
    `object_path_map.scan_app` 的唯一 `objectId`，本文件不实现第二套路径反推。

``app:cross-cutting/<root>``
    仅接收已经物理位于 `APP_CROSS_CUTTING_ROOTS` 的 canonical 横切源码；runtime 与
    design system 分别计量。旧位置、只能反推到 domain/context、歧义或无主源码都
    立即 BLOCK，不能靠计数基线继续容忍。

``cloud:<service>/<context>/<object>``
    云侧业务对象。对象身份只从
    ``services|control-plane/<service>/internal/<context>/<object>/<layer>`` 的物理路径
    反推，并与 ContractGraph roster 交叉验证；同一 domain 的不同 service 不再合桶。

``cloud:cross-cutting/cmd`` / ``cloud:cross-cutting/shared_runtime``
    组合根 ``cmd/**`` 与仓库级 ``runtime/**``、``internal/platform/**`` 没有业务对象
    身份，分别进入显式横切单元；它们不能被悄悄丢出分母，也不能冒充某个对象覆盖率。

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

``cloud:*`` 只有 ``statement``：Go 由 ``-coverpkg`` 产出全分母的
coverprofile，Python 由标准库 ``trace`` 对每个 production 文件的可执行行求全分母。
两者都把未运行的 production source 保留为分子 0，因此不需要额外
``file`` 轴；任一对象的 statement 分母或分子为 0 都直接 BLOCK。

不可测与假 0
------------

一个对象可能确实没有任何测试加载过它的文件，此时 `line` / `branch` 的分母是 0。
**分母为 0 时禁止写 0%**：0% 会被当成「已达标的下限」，此后无论怎么退化都过得去
（仓库里已经出过这个事故：旧门禁对文件缺失静默返回 0，文件搬走后该桶永久
达标）。当前采集会把该维度显式登记成 `unmeasured` 并写明原因，但这种状态只用于
解释阻断，**绝不能进入 baseline 或成为可比结果**：

* 基线可测、现状不可测 → BLOCK（测试被删或 import 被摘掉）。
* 旧基线不可测、现状可测 → BLOCK，要求由全绿采集登记真实数字。
* 基线与现状都不可测 → 仍然 BLOCK；两个未知不能相互证明覆盖率达标。

`file` 轴只在该桶磁盘上一个生产文件都没有时才不可测（例如只有云侧实现、端侧没有
代码的域）；只要有文件，`0/N` 就是**实测事实**而非猜测，作为当前阻断原因照实
报告，但同样禁止写入 baseline。

采集范围（scope）也逐字段写进基线并比对：改了采集命令却没重新采集时按 scope 漂移
阻断，而不是拿两次不可比的数字做大小比较。

端侧分片采集
------------

一次 `flutter test --coverage --branch-coverage test/local_contract` 要把全部测试
文件的覆盖率累积在同一个采集进程里，本机内存 + swap 撑不住而被 OS 杀死。因此端侧
采集按测试文件切成若干片顺序执行，再把各片 lcov 合并成一份 `app.lcov.info`：

* **确定性切分**：`app_test_files()` 按 posix 路径排序枚举全部
  ``*_test.dart``，`app_shard_plan()` 只依赖 ``(排序后的文件清单, 片数)`` 做连续
  均分。同样的输入必然切出同样的片，覆盖率数字不会随分片抖动；每个测试文件恰好
  出现在一片里，既不重复也不遗漏，分片不构成任何跳过名单。
* **语义等价合并**：合并在 `DA`/`BRDA` 明细层做并集与命中数累加，`LF`/`LH` 由
  合并后的 `DA` 重新推导——这与全量运行内部把各 test isolate 的 hitmap 合并成
  一份是同一套算术。某个文件只在 A 片被触达时，它照样进入合并结果，不会被 B 片
  的缺席抹掉。每片自身声明的 `LF`/`LH` 必须与它自己的 `DA` 明细自洽，否则阻断，
  杜绝同一维度出现两套口径。
* **可断点续跑**：每片的 lcov 与状态落在 `.qwq_output` 的可删除缓存里，状态绑定
  分片方案与本次采集 identity；只有**绿且未漂移**的片可以复用，红片与陈旧片一律
  重跑。中间产物删掉后仍能凭受版本控制的真相源重建。
* **红片照样阻断**：任一片非零退出即 `RedTestRun`，产物 receipt 记
  ``testsGreen=false``，`--write-baseline` 与求值路径全部拒绝。分片不是绕过全绿
  要求的后门；`measuredFromGreenTests` 仍然表示「本次数字来自全部分片都绿的实跑」。

片数是纯粹的机器容量旋钮，不进 `unit_scope` 也不进 `collectionScopeDigest`：合并
结果与全量运行语义等价，换一台内存更大的机器改片数不该让基线变得不可比。

用法
----
    # 复用已落盘的覆盖率产物求值（产物缺失 → BLOCK）
    python3 quwoquan_ops/gate/verify_canonical_coverage.py

    # 先跑测试采集覆盖率，再求值（门禁在 gate_repo.sh 中的用法）
    python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope app
    python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope cloud

    # 内存吃紧时切得更细（默认片数由测试文件数派生）
    python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope app \
      --app-shards 20

    # 只处理单个对象或云侧领域单元
    python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect \
      --unit app:circle/circle_management/gathering

    # 覆盖率提升后收紧基线（只重写本次求值到的单元分区）
    python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --write-baseline

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

RULE_ID = "canonical-coverage-rule"
BASELINE_SCHEMA = "canonical-coverage-baseline"

BASELINE_PATH = (
    ROOT / "quwoquan_ops" / "policies" / "gates" / "canonical_coverage_baseline.json"
)
RETIRED_BASELINE_PATH = (
    ROOT / "quwoquan_ops" / "policies" / "gates" / "coverage_baseline.json"
)

#: 覆盖率产物落在可删除的 repo 级运行缓存下（`.qwq_output` 只存可重建输出）。
COVERAGE_CACHE_DIR = (
    ROOT / ".qwq_output" / "env" / "repo" / "local" / "coverage" / "cache"
)

APP_ROOT = ROOT / "quwoquan_app"
SERVICE_ROOT = ROOT / "quwoquan_service"

APP_UNIT_PREFIX = "app:"
CLOUD_UNIT_PREFIX = "cloud:"
APP_CROSS_CUTTING_UNIT_PREFIX = f"{APP_UNIT_PREFIX}cross-cutting/"
CLOUD_CROSS_CUTTING_UNIT_PREFIX = f"{CLOUD_UNIT_PREFIX}cross-cutting/"
CLOUD_CROSS_CUTTING_ROOTS = ("cmd", "shared_runtime")

#: 仓库级 shared runtime 不是业务 service 目录，但必须以独立采集目标进入分母。
#: 该值只用于产物 identity，不对应一个可以被 package/deploy 的物理 service。
SHARED_RUNTIME_COLLECTION_TARGET = "quwoquan_service/shared-runtime"
SHARED_RUNTIME_PACKAGE_PATTERNS = ("runtime", "internal/platform", "cmd")
SHARED_RUNTIME_COVERPKG_PATTERNS = ("runtime", "internal/platform", "cmd")

KIND_FLUTTER_LCOV = "flutter_lcov"
KIND_CLOUD_STATEMENT = "cloud_statement"

#: 每种 kind 必须提供的覆盖率维度。端侧行/分支/触达三轴，云侧只有语句覆盖。
METRICS_BY_KIND = {
    KIND_FLUTTER_LCOV: ("branch", "file", "line"),
    KIND_CLOUD_STATEMENT: ("statement",),
}

#: 端侧采集范围。全量 `flutter test --coverage` 在本机 10 分钟以上，L0 提交门禁
#: 承担不起；`test/local_contract` 是 App 的 canonical L0 套件，也是
#: `gate_repo.sh` 里已经在跑的那一份。
APP_TEST_TARGET = "test/local_contract"

#: `flutter test <dir>` 收集测试文件的后缀，与 package:test 的默认约定一致。
APP_TEST_FILE_SUFFIX = "_test.dart"

#: 单片最多承载多少个测试文件；默认片数由此派生，不写死片数。这是纯粹的机器容量
#: 旋钮：它只决定一次 `flutter test` 进程里累积多少覆盖率，不决定哪些测试被执行。
#:
#: 取值依据是本机实测的 dart/flutter_tester 进程树峰值 RSS：20 个测试文件 2.37 GiB、
#: 40 个 2.84 GiB，即约 2.0 GiB 固定开销（并发 tester 进程）加每个测试文件约 23 MiB
#: 的覆盖率累积。按这条线外推，全量 786 个文件一次跑完需要约 20 GiB——这正是全量
#: 采集被 OS 杀掉的原因。50 个文件一片把单片峰值压到约 3.2 GiB；内存更紧或更宽裕时
#: 用 `--app-shards` 覆盖，不要改这个常数去迁就某一台机器。
APP_SHARD_MAX_TEST_FILES = 50

#: 分片中间产物目录名（在 `COVERAGE_CACHE_DIR` 下，可整体删除后重建）。
APP_SHARD_DIRECTORY_NAME = "app-shards"
APP_SHARD_STATE_SCHEMA = "canonical-coverage-app-shard-state"

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

#: Python Cloud service 与 Go service 共用对象级 ``statement`` 轴，但采集
#: 必须来自它自己的 canonical local_contract Python 环境，不能因
#: ``go list`` 为空而整个丢出 Cloud 分母。
PYTHON_SERVICE_TEST_TARGET = "tests/local_contract"
PYTHON_TRACE_ARTIFACT_SCHEMA = "canonical-coverage-python-trace"
PYTHON_TRACE_SOURCE_ROOTS = ("internal", "cmd")
PYTHON_MANAGED_ENV_RELATIVE = Path(".cache/quwoquan/python-envs/rec-model/bin/python")
PYTHON_COVERAGE_TOOLCHAIN_LOCK = Path("resources/coverage-toolchain.lock")
PYTHON_COVERAGE_TOOLCHAIN_MARKER = "coverage-toolchain.sha256"
PYTHON_EXACT_REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;]+)$"
)

METRIC_STATUS_UNMEASURED = "unmeasured"
ARTIFACT_RECEIPT_SCHEMA = "canonical-coverage-receipt"

CANONICAL_BASELINE_GOVERNANCE = {
    "owner": "runtime-control-plane-foundation",
    "reason": (
        "唯一 canonical coverage baseline；只接受 App、Cloud、Python、Ops "
        "对象级全量绿采集及其 canonical receipt provenance。"
    ),
    "expires_when": (
        "覆盖率规则由新的当前规格整体替代并原子硬切时；不得保留旧格式或迁移别名。"
    ),
}
CANONICAL_POLICY = {
    "tolerance_percentage_points": 0.3,
    "tolerance_reason": "只吸收同一测试调度的微小覆盖率噪声，不吸收真实回归。",
    "improvement_slack_percentage_points": 3.0,
    "improvement_slack_reason": "覆盖率提升超过3pp时要求整体刷新唯一canonical baseline。",
    "granularity_units": 2.0,
    "granularity_units_reason": "小对象按两个可数语句、分支或文件提供测量粒度下限。",
}
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


def _has_python_sources(directory: Path) -> bool:
    """目录里是否有真实 production Python 代码。"""
    return any(
        path.is_file() and not path.is_symlink() and path.name != "__init__.py"
        for root_name in PYTHON_TRACE_SOURCE_ROOTS
        for path in (directory / root_name).rglob("*.py")
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


@functools.lru_cache(maxsize=1)
def python_collection_targets() -> dict[str, str]:
    """Python 采集目标：同样从 service domain 真相源派生。"""
    targets = {
        relative: domain
        for relative, (_owner, domain) in sorted(opm.service_domains().items())
        if _has_python_sources(ROOT / relative)
    }
    mixed = sorted(set(targets) & set(go_collection_targets()))
    if mixed:
        raise CoverageError(
            "同一 Cloud service 同时含 Go/Python production source，必须先声明唯一"
            f" coverage collection owner: {mixed}"
        )
    return targets


def cloud_collection_targets() -> dict[str, str]:
    """返回全部可执行 Cloud 采集目标，不因实现语言漏掉对象。"""
    return {**go_collection_targets(), **python_collection_targets()}


def _collection_target_language(target: str) -> str:
    if target == SHARED_RUNTIME_COLLECTION_TARGET or target in go_collection_targets():
        return "go"
    if target in python_collection_targets():
        return "python"
    raise CoverageError(f"未知覆盖率采集目标 {target!r}")


def app_object_unit(domain: str, context: str, object_name: str) -> str:
    """返回 canonical App ``service/context/object`` 单元，不维护 service 清单。"""
    service = opm.app_service_for_context(domain, context)
    return f"{APP_UNIT_PREFIX}{service}/{context}/{object_name}"


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


def cloud_object_unit(service_name: str, context: str, object_name: str) -> str:
    """返回 canonical Cloud ``service/context/object`` 单元。"""
    service = opm.app_service_segment(service_name)
    return f"{CLOUD_UNIT_PREFIX}{service}/{context}/{object_name}"


def cloud_cross_cutting_unit(root: str) -> str:
    """返回 Cloud 组合根/共享 runtime 的显式横切单元。"""
    if root not in CLOUD_CROSS_CUTTING_ROOTS:
        raise CoverageError(f"未知 Cloud cross-cutting root {root!r}")
    return f"{CLOUD_CROSS_CUTTING_UNIT_PREFIX}{root}"


@functools.lru_cache(maxsize=1)
def _roster() -> opm.ObjectRoster:
    return vaa.load_roster()


@functools.lru_cache(maxsize=1)
def discover_app_units() -> tuple[str, ...]:
    return tuple(app_units(_roster()))


@functools.lru_cache(maxsize=1)
def discover_cloud_units() -> tuple[str, ...]:
    return tuple(sorted(CloudAttribution(_roster()).files_by_unit))


@functools.lru_cache(maxsize=1)
def discover_units() -> tuple[str, ...]:
    return discover_app_units() + discover_cloud_units()


def unit_kind(unit: str) -> str:
    if unit.startswith(APP_UNIT_PREFIX):
        return KIND_FLUTTER_LCOV
    if unit.startswith(CLOUD_UNIT_PREFIX):
        return KIND_CLOUD_STATEMENT
    raise CoverageError(f"无法识别的单元 {unit!r}")


def unit_bucket(unit: str) -> str:
    prefix = APP_UNIT_PREFIX if unit.startswith(APP_UNIT_PREFIX) else CLOUD_UNIT_PREFIX
    return unit[len(prefix) :]


def _service_target_for_segment(service_segment: str) -> str:
    matches = sorted(
        relative
        for relative in cloud_collection_targets()
        if opm.app_service_segment(Path(relative).name) == service_segment
    )
    if len(matches) != 1:
        raise CoverageError(
            f"Cloud service segment {service_segment!r} 必须唯一命中采集目标，实测 {matches}"
        )
    return matches[0]


def cloud_collection_targets_for_unit(unit: str) -> list[str]:
    """返回 Cloud 单元所依赖的真实采集产物。"""
    bucket = unit_bucket(unit)
    if bucket == "cross-cutting/cmd":
        targets = [
            relative
            for relative in cloud_collection_targets()
            if any(
                path.is_file()
                and not path.is_symlink()
                and not path.name.endswith("_test.go")
                for suffix in (
                    ("*.go",)
                    if _collection_target_language(relative) == "go"
                    else ("*.py",)
                )
                for path in (ROOT / relative / "cmd").rglob(suffix)
            )
        ]
        if any(
            path.is_file()
            and not path.is_symlink()
            and not path.name.endswith("_test.go")
            for path in (SERVICE_ROOT / "cmd").rglob("*.go")
        ):
            targets.append(SHARED_RUNTIME_COLLECTION_TARGET)
        return sorted(targets)
    if bucket == "cross-cutting/shared_runtime":
        return [SHARED_RUNTIME_COLLECTION_TARGET]
    parts = bucket.split("/")
    if len(parts) != 3 or any(not part for part in parts):
        raise CoverageError(f"Cloud 对象单元不是 service/context/object: {unit!r}")
    return [_service_target_for_segment(parts[0])]


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
    targets = cloud_collection_targets_for_unit(unit)
    target_kinds = sorted({_collection_target_language(target) for target in targets})
    return (
        "quwoquan_service: canonical local_contract statement coverage; "
        f"unit={unit_bucket(unit)} targets={','.join(targets)} "
        f"collectors={','.join(target_kinds)} "
        f"attribution={opm.RULE_ID} (excluding {SERVICE_EXCLUDED_PACKAGE_MARKER})"
    )


# ---------------------------------------------------------------------------
# 采集（采集目标 ≠ 计量单元：端侧一次跑出全部桶，云侧按 service 跑）
# ---------------------------------------------------------------------------

APP_COLLECTION_TARGET = "app"


def collection_targets(units: Sequence[str]) -> list[str]:
    """把计量单元折叠成去重后的采集目标。

    端侧对象共享同一次 `flutter test --coverage`；云侧对象只读取 owning service
    的产物，cmd/shared-runtime 横切单元读取对应的全部真实采集目标。
    """
    targets: list[str] = []
    for unit in units:
        if unit.startswith(APP_UNIT_PREFIX):
            candidates = [APP_COLLECTION_TARGET]
        else:
            candidates = cloud_collection_targets_for_unit(unit)
        for candidate in candidates:
            if candidate not in targets:
                targets.append(candidate)
    return targets


def artifact_path(target: str) -> Path:
    if target == APP_COLLECTION_TARGET:
        return COVERAGE_CACHE_DIR / "app.lcov.info"
    if target in python_collection_targets():
        return COVERAGE_CACHE_DIR / f"{target.replace('/', '__')}.python-trace.json"
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
        raise CoverageError(
            f"App path dependency closure 缺少安全 lock: {_display(lock_path)}"
        )
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
            raise CoverageError(
                f"App path dependency {name!r} 根不得是符号链接: {candidate}"
            )
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
            f"{label} 缺少安全普通文件: "
            + ", ".join(_display(path) for path in missing)
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
    if target == SHARED_RUNTIME_COLLECTION_TARGET:
        source_candidates = [
            path
            for root_name in SHARED_RUNTIME_COVERPKG_PATTERNS
            for path in _provenance_tree_files(SERVICE_ROOT / root_name)
        ]
        source = sorted(
            path for path in source_candidates if not path.name.endswith("_test.go")
        )
        tests = sorted(
            path for path in source_candidates if path.name.endswith("_test.go")
        )
        if not source or not tests:
            raise CoverageError(
                "shared runtime coverage 必须同时拥有 production source 与 tests"
            )
        return source, tests
    language = _collection_target_language(target)
    service_root = ROOT / target
    if language == "python":
        source = sorted(
            path
            for root_name in PYTHON_TRACE_SOURCE_ROOTS
            for path in _provenance_tree_files(service_root / root_name)
        )
        tests = _provenance_tree_files(service_root / PYTHON_SERVICE_TEST_TARGET)
        if not source or not tests:
            raise CoverageError(
                f"{target}: Python coverage 必须同时拥有 production source 与 "
                f"{PYTHON_SERVICE_TEST_TARGET}"
            )
        return source, tests
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
        language = _collection_target_language(target)
        if language == "python":
            service_root = ROOT / target
            required = _required_safe_files(
                (
                    service_root / "Makefile",
                    service_root / "pyproject.toml",
                    service_root / PYTHON_COVERAGE_TOOLCHAIN_LOCK,
                ),
                label="Python coverage config",
            )
            optional = tuple(sorted(service_root.rglob("requirements*.txt")))
        else:
            required = _required_safe_files(
                (SERVICE_ROOT / "go.mod", SERVICE_ROOT / "go.sum"),
                label="Go coverage config",
            )
            optional = ()
    return required + [path for path in optional if path.is_file() or path.is_symlink()]


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
        language = _collection_target_language(target)
        scopes = [
            unit_scope(unit)
            for unit in discover_cloud_units()
            if target in cloud_collection_targets_for_unit(unit)
        ]
        if language == "python":
            command = [
                "<managed-python>",
                "-B",
                "<stdlib-trace-runner>",
                "-q",
                PYTHON_SERVICE_TEST_TARGET,
                "--artifact=<artifact>",
            ]
        else:
            package_shape = (
                "<runtime,internal/platform,cmd>"
                if target == SHARED_RUNTIME_COLLECTION_TARGET
                else "<internal,cmd>"
            )
            command = [
                "go",
                "test",
                "-count=1",
                f"-p={SERVICE_GO_TEST_PACKAGE_PARALLELISM}",
                "-covermode=atomic",
                "-coverprofile=<artifact>",
                f"-coverpkg={package_shape}",
                "<go-list-without-api-integration>",
            ]
    payload = {
        "ruleId": RULE_ID,
        "target": target,
        "command": command,
        "scopes": scopes,
        "gateSourceDigest": _sha256_file(Path(__file__).resolve()),
    }
    return _sha256_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
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
        raise CoverageError(f"provenance identity command 无输出: {' '.join(command)}")
    return output


def _python_collection_executable(target: str) -> Path:
    """返回 Recommendation Makefile 声明的受管 Python 环境。"""
    if target not in python_collection_targets():
        raise CoverageError(f"{target}: 不是 Python coverage target")
    executable = Path.home() / PYTHON_MANAGED_ENV_RELATIVE
    if not executable.exists() or not os.access(executable, os.X_OK):
        raise CoverageError(
            f"{target}: 缺少受管 Python 测试环境 {executable}；先执行 "
            f"make -C {target} prepare-test-python"
        )
    return executable


def _canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_python_coverage_toolchain_lock(text: str) -> dict[str, str]:
    """解析只允许 exact ``name==version`` 的 coverage toolchain lock。"""
    locked: dict[str, str] = {}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PYTHON_EXACT_REQUIREMENT_RE.fullmatch(line)
        if match is None:
            raise CoverageError(
                f"Python coverage toolchain lock 第 {number} 行不是 exact requirement: "
                f"{line!r}"
            )
        name = _canonical_distribution_name(match.group("name"))
        if name in locked:
            raise CoverageError(
                f"Python coverage toolchain lock 重复 dependency: {name}"
            )
        locked[name] = match.group("version")
    if "pytest" not in locked:
        raise CoverageError("Python coverage toolchain lock 缺少 exact pytest==version")
    return locked


PYTHON_TOOLCHAIN_PROBE = r"""
import hashlib
import importlib
import importlib.metadata
import json
import pathlib
import sys
import trace

trace_path = pathlib.Path(trace.__file__).resolve()
pytest_path = pathlib.Path(importlib.import_module("pytest").__file__).resolve()
print(json.dumps({
    "basePrefix": sys.base_prefix,
    "pythonExecutable": sys.executable,
    "pythonVersion": sys.version,
    "pytestPath": str(pytest_path),
    "pytestVersion": importlib.metadata.version("pytest"),
    "traceDigest": "sha256:" + hashlib.sha256(trace_path.read_bytes()).hexdigest(),
    "tracePath": str(trace_path),
}, sort_keys=True, separators=(",", ":")))
"""


def _python_toolchain_state(target: str) -> dict[str, object]:
    """验证并返回会完整进入 ``toolchainDigest`` 的 Python runner 身份。"""
    executable = _python_collection_executable(target)
    service_root = ROOT / target
    lock_path = service_root / PYTHON_COVERAGE_TOOLCHAIN_LOCK
    if not lock_path.is_file() or lock_path.is_symlink():
        raise CoverageError(f"{target}: 缺少安全 coverage toolchain lock: {lock_path}")
    locked = _parse_python_coverage_toolchain_lock(
        lock_path.read_text(encoding="utf-8")
    )
    lock_digest = _sha256_file(lock_path)
    marker_path = executable.parent.parent / PYTHON_COVERAGE_TOOLCHAIN_MARKER
    if not marker_path.is_file() or marker_path.is_symlink():
        raise CoverageError(
            f"{target}: 缺少受管 coverage toolchain marker: {marker_path}"
        )
    marker = marker_path.read_text(encoding="utf-8").strip()
    if marker != lock_digest.removeprefix("sha256:"):
        raise CoverageError(f"{target}: coverage toolchain marker 与 tracked lock 漂移")
    try:
        probe = json.loads(
            _identity_command(
                [str(executable), "-B", "-c", PYTHON_TOOLCHAIN_PROBE],
                cwd=service_root,
            )
        )
    except json.JSONDecodeError as error:
        raise CoverageError(
            f"{target}: Python coverage toolchain probe 非 JSON"
        ) from error
    required_probe_fields = {
        "basePrefix",
        "pythonExecutable",
        "pythonVersion",
        "pytestPath",
        "pytestVersion",
        "traceDigest",
        "tracePath",
    }
    if not isinstance(probe, dict) or set(probe) != required_probe_fields:
        raise CoverageError(
            f"{target}: Python coverage toolchain probe fields mismatch"
        )
    if Path(str(probe["pythonExecutable"])) != executable:
        raise CoverageError(
            f"{target}: collection Python executable 漂移: "
            f"{probe['pythonExecutable']!r} != {str(executable)!r}"
        )
    expected_pytest = locked["pytest"]
    if probe["pytestVersion"] != expected_pytest:
        raise CoverageError(
            f"{target}: pytest version 漂移: "
            f"expected={expected_pytest!r}, actual={probe['pytestVersion']!r}"
        )
    pytest_path = Path(str(probe["pytestPath"]))
    if (
        not pytest_path.is_absolute()
        or not pytest_path.is_file()
        or pytest_path.is_symlink()
        or not pytest_path.resolve().is_relative_to(executable.parent.parent.resolve())
    ):
        raise CoverageError(
            f"{target}: pytest 不是受管 rec-model environment 文件: {pytest_path}"
        )
    trace_path = Path(str(probe["tracePath"]))
    base_prefix = Path(str(probe["basePrefix"])).resolve()
    if (
        not trace_path.is_absolute()
        or not trace_path.is_file()
        or trace_path.is_symlink()
        or not trace_path.resolve().is_relative_to(base_prefix)
    ):
        raise CoverageError(
            f"{target}: trace module 不是 collection Python 的安全 stdlib 文件: "
            f"{trace_path}"
        )
    actual_trace_digest = _sha256_file(trace_path)
    if probe["traceDigest"] != actual_trace_digest:
        raise CoverageError(f"{target}: trace module bytes 在 probe 期间漂移")
    freeze_lines = sorted(
        line.strip()
        for line in _identity_command(
            [str(executable), "-m", "pip", "freeze", "--all"],
            cwd=service_root,
        ).splitlines()
        if line.strip()
    )
    frozen: dict[str, str] = {}
    for line in freeze_lines:
        match = PYTHON_EXACT_REQUIREMENT_RE.fullmatch(line)
        if match is None:
            raise CoverageError(
                f"{target}: pip freeze 含非 exact dependency，不能形成 toolchain identity: "
                f"{line!r}"
            )
        name = _canonical_distribution_name(match.group("name"))
        if name in frozen:
            raise CoverageError(f"{target}: pip freeze 重复 dependency: {name}")
        frozen[name] = match.group("version")
    drifted = {
        name: {"expected": version, "actual": frozen.get(name)}
        for name, version in locked.items()
        if frozen.get(name) != version
    }
    if drifted:
        raise CoverageError(
            f"{target}: coverage toolchain lock 与 pip freeze 漂移: {drifted}"
        )
    return {
        "lockDigest": lock_digest,
        "lockedRequirements": locked,
        "pipFreeze": freeze_lines,
        "pythonExecutable": probe["pythonExecutable"],
        "pythonResolvedExecutable": str(executable.resolve()),
        "pythonVersion": probe["pythonVersion"],
        "pytestPath": probe["pytestPath"],
        "pytestVersion": probe["pytestVersion"],
        "traceDigest": actual_trace_digest,
        "tracePath": str(trace_path),
    }


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
        key for key, value in identity.items() if GIT_OBJECT_RE.fullmatch(value) is None
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
    elif _collection_target_language(target) == "python":
        identity["coverageToolchain"] = _python_toolchain_state(target)
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


def _write_text_atomic(path: Path, text: str) -> None:
    """整份替换落盘；半截产物会被 receipt 的 artifactDigest 当成合法输入。"""
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
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


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
        raise CoverageError(
            f"覆盖率 provenance receipt target 不可复核: {target!r}"
        ) from error
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
    drifted = sorted(
        key for key, value in expected.items() if payload.get(key) != value
    )
    if drifted:
        raise CoverageError(
            "覆盖率产物 provenance 已陈旧（"
            + ", ".join(drifted)
            + "）；当前源码/测试/归属/采集范围必须重新 --collect"
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


def app_test_files() -> tuple[str, ...]:
    """按 canonical 顺序枚举 `APP_TEST_TARGET` 下全部测试文件（相对 App 根）。

    这份清单必须与 `flutter test <APP_TEST_TARGET>` 自己会收集的集合一致：
    package:test 取该目录下所有 ``*_test.dart``，并跳过点开头的隐藏路径。排序用
    posix 路径字节序，使分片方案只由磁盘内容决定，不受文件系统遍历顺序影响。
    """
    root = APP_ROOT / APP_TEST_TARGET
    if not root.is_dir() or root.is_symlink():
        raise CoverageError(f"App 测试根不是安全目录: {_display(root)}")
    files: list[str] = []
    for path in root.rglob(f"*{APP_TEST_FILE_SUFFIX}"):
        relative = path.relative_to(APP_ROOT)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            raise CoverageError(f"App 测试文件不是安全普通文件: {_display(path)}")
        files.append(relative.as_posix())
    if not files:
        raise CoverageError(
            f"{APP_TEST_TARGET} 下没有任何 {APP_TEST_FILE_SUFFIX}；采集范围为空即 BLOCK"
        )
    return tuple(sorted(files))


def default_app_shard_count(test_files: Sequence[str]) -> int:
    """按测试文件数派生默认片数，避免把片数写死成会随仓库增长而失效的常数。"""
    return max(1, -(-len(test_files) // APP_SHARD_MAX_TEST_FILES))


def app_shard_plan(
    test_files: Sequence[str], shard_count: int
) -> tuple[tuple[str, ...], ...]:
    """把已排序的测试文件切成 ``shard_count`` 段连续分片。

    切分只是 ``(排序后的文件清单, shard_count)`` 的纯函数：同样输入必然得到同样
    分片，覆盖率数字不会因为分片而抖动。前 ``remainder`` 片各多承载一个文件，
    保证片间大小相差不超过 1；连续切分让同一目录的测试尽量落在同一片，减少单片
    需要加载的库数量。每个文件恰好出现一次——分片是全集的划分，不是筛选。
    """
    if shard_count < 1:
        raise CoverageError(f"分片数必须 >= 1，实测 {shard_count}")
    if shard_count > len(test_files):
        raise CoverageError(
            f"分片数 {shard_count} 超过测试文件数 {len(test_files)}；空片没有意义"
        )
    size, remainder = divmod(len(test_files), shard_count)
    plan: list[tuple[str, ...]] = []
    cursor = 0
    for index in range(shard_count):
        span = size + (1 if index < remainder else 0)
        plan.append(tuple(test_files[cursor : cursor + span]))
        cursor += span
    return tuple(plan)


def app_shard_directory() -> Path:
    return COVERAGE_CACHE_DIR / APP_SHARD_DIRECTORY_NAME


def _app_shard_artifact_paths(index: int, shard_count: int) -> tuple[Path, Path]:
    """返回该片的 ``(lcov, state)`` 路径；片数进文件名，换片数即换一组文件。"""
    stem = f"shard-{index:04d}-of-{shard_count:04d}"
    directory = app_shard_directory()
    return directory / f"{stem}.lcov.info", directory / f"{stem}.state.json"


def _reusable_shard_lcov(
    lcov_path: Path, state_path: Path, expected_state: dict[str, object]
) -> str | None:
    """只有「绿 + 未漂移 + 字节未被改动」的片才允许跳过重跑。

    任何一项对不上都返回 ``None`` 让调用方重跑该片：断点续跑是省时间的手段，
    不能变成让陈旧或红的片混进合并结果的路径。
    """
    if not state_path.is_file() or state_path.is_symlink():
        return None
    if not lcov_path.is_file() or lcov_path.is_symlink():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("testsGreen") is not True:
        return None
    if any(payload.get(key) != value for key, value in expected_state.items()):
        return None
    if payload.get("lcovDigest") != _sha256_file(lcov_path):
        return None
    return lcov_path.read_text(encoding="utf-8", errors="replace")


def _run_app_shard(destination: Path, test_files: Sequence[str]) -> str:
    """跑一片测试；返回失败摘要，空串表示该片全绿。

    产不出 lcov（例如该片自己被 OOM 杀掉）不是「红测试」而是采集失败，必须以
    `CoverageError` 阻断：把它当成红测试会让 receipt 记下一份不完整的产物。
    """
    completed = _run(
        [
            "flutter",
            "test",
            "--coverage",
            "--branch-coverage",
            f"--coverage-path={destination}",
            "--reporter=compact",
            *test_files,
        ],
        cwd=APP_ROOT,
    )
    if not destination.is_file():
        raise CoverageError(
            f"flutter test 未产出 lcov: {_display(destination)}"
            f"（exit={completed.returncode}）\n"
            f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
        )
    if completed.returncode != 0:
        return (
            f"exit={completed.returncode}\n"
            f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
        )
    return ""


def collect_app(
    destination: Path,
    *,
    shards: int | None = None,
    identity: dict[str, str] | None = None,
) -> None:
    """分片采集端侧行/分支覆盖率，合并成与全量运行语义等价的单份 lcov。

    分片只改变执行方式：所有测试文件都会被执行一次，合并按 `DA`/`BRDA` 明细取
    并集并累加命中数。任一片红都在跑完全部分片后抛 `RedTestRun`——与全量运行
    「跑完所有测试再以非零码退出」同形，产物照样落盘供诊断，但 receipt 会记
    ``testsGreen=false``，复用与写基线两条路径都被拒绝。
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()

    test_files = app_test_files()
    shard_count = default_app_shard_count(test_files) if shards is None else shards
    plan = app_shard_plan(test_files, shard_count)
    plan_digest = _canonical_json_digest([list(shard) for shard in plan])
    identity_digest = _canonical_json_digest(
        identity
        if identity is not None
        else current_collection_identity(APP_COLLECTION_TARGET)
    )

    directory = app_shard_directory()
    directory.mkdir(parents=True, exist_ok=True)
    expected_names = {
        path.name
        for index in range(shard_count)
        for path in _app_shard_artifact_paths(index, shard_count)
    }
    for path in directory.iterdir():
        # 只清理本目录里不属于当前分片方案的可重建中间产物。
        if path.name not in expected_names and path.is_file():
            path.unlink()

    merged: dict[str, dict] = {}
    red: list[str] = []
    for index, shard_files in enumerate(plan):
        lcov_path, state_path = _app_shard_artifact_paths(index, shard_count)
        expected_state: dict[str, object] = {
            "schema": APP_SHARD_STATE_SCHEMA,
            "ruleId": RULE_ID,
            "shardIndex": index,
            "shardCount": shard_count,
            "planDigest": plan_digest,
            "shardDigest": _canonical_json_digest(list(shard_files)),
            "collectionIdentityDigest": identity_digest,
        }
        text = _reusable_shard_lcov(lcov_path, state_path, expected_state)
        if text is None:
            state_path.unlink(missing_ok=True)
            lcov_path.unlink(missing_ok=True)
            print(
                f"verify_canonical_coverage: app shard {index + 1}/{shard_count}"
                f" ({len(shard_files)} test file(s)) ...",
                flush=True,
            )
            failure = _run_app_shard(lcov_path, shard_files)
            text = lcov_path.read_text(encoding="utf-8", errors="replace")
            _write_json_atomic(
                state_path,
                {
                    **expected_state,
                    "lcovDigest": _sha256_file(lcov_path),
                    "testsGreen": not failure,
                },
            )
            if failure:
                red.append(f"shard {index + 1}/{shard_count}: {failure}")
        else:
            print(
                f"verify_canonical_coverage: app shard {index + 1}/{shard_count}"
                " reused (green, unchanged)",
                flush=True,
            )
        merge_lcov_records(merged, parse_lcov_records(text))

    if not merged:
        raise CoverageError(
            f"分片采集没有产出任何 lcov 记录（{shard_count} 片）；采集没有真正生效"
        )
    _write_text_atomic(destination, render_lcov(merged))
    if red:
        raise RedTestRun(
            f"flutter test 分片失败（{len(red)}/{shard_count} 片红）；"
            "覆盖率必须来自绿的测试。\n" + "\n".join(red)
        )


PYTHON_TRACE_RUNNER = r"""
import json
import os
import pathlib
import sys
import trace

import pytest

schema, destination, test_target = sys.argv[1:4]
service_root = pathlib.Path.cwd().resolve()
sources = sorted(
    path.resolve()
    for root_name in ("internal", "cmd")
    for path in (service_root / root_name).rglob("*.py")
    if path.is_file() and not path.is_symlink()
)
tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.base_prefix])
exit_code = int(tracer.runfunc(pytest.main, ["-q", test_target]))
counts = tracer.results().counts
files = {}
for source in sources:
    executable = set(trace._find_executable_linenos(str(source)))
    covered = {
        line
        for (filename, line), count in counts.items()
        if count > 0 and pathlib.Path(filename).resolve() == source
    }
    relative = source.relative_to(service_root).as_posix()
    files[relative] = {
        "coveredStatements": len(covered & executable),
        "totalStatements": len(executable),
    }
payload = {"schema": schema, "files": files}
output = pathlib.Path(destination)
output.parent.mkdir(parents=True, exist_ok=True)
temporary = output.with_name(output.name + ".tmp")
temporary.write_text(
    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    + "\n",
    encoding="utf-8",
)
os.replace(temporary, output)
raise SystemExit(exit_code)
"""


def collect_python_service(service_relative: str, destination: Path) -> None:
    """用标准库 trace 跑 Python service 的 canonical local_contract。"""
    executable = _python_collection_executable(service_relative)
    service_root = ROOT / service_relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    completed = _run(
        [
            str(executable),
            "-B",
            "-c",
            PYTHON_TRACE_RUNNER,
            PYTHON_TRACE_ARTIFACT_SCHEMA,
            str(destination),
            PYTHON_SERVICE_TEST_TARGET,
        ],
        cwd=service_root,
    )
    if not destination.is_file():
        raise CoverageError(
            f"{service_relative}: Python trace 未产出 statement artifact: {destination}"
        )
    if completed.returncode != 0:
        raise RedTestRun(
            f"pytest 失败（{service_relative}, exit={completed.returncode}）；"
            "覆盖率必须来自绿的测试。\n"
            f"{_tail(completed.stdout)}{_tail(completed.stderr)}"
        )


def collect_service(service_relative: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    if service_relative == SHARED_RUNTIME_COLLECTION_TARGET:
        package_patterns = SHARED_RUNTIME_PACKAGE_PATTERNS
        coverpkg_patterns = SHARED_RUNTIME_COVERPKG_PATTERNS
    else:
        if service_relative not in go_collection_targets():
            raise CoverageError(f"未知覆盖率采集目标 {service_relative!r}")
        inside_module = service_relative[len(SERVICE_ROOT.name) + 1 :]
        package_patterns = tuple(
            f"{inside_module}/{pattern}" for pattern in SERVICE_PACKAGE_PATTERNS
        )
        coverpkg_patterns = tuple(
            f"{inside_module}/{pattern}" for pattern in SERVICE_COVERPKG_PATTERNS
        )
    listed = _run(
        ["go", "list"] + [f"./{pattern}/..." for pattern in package_patterns],
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
    coverpkg = ",".join(f"./{pattern}/..." for pattern in coverpkg_patterns)
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


def collect(target: str, *, app_shards: int | None = None) -> None:
    destination = artifact_path(target)
    receipt = artifact_receipt_path(target)
    receipt.unlink(missing_ok=True)
    before = current_collection_identity(target)
    red_error: RedTestRun | None = None
    try:
        if target == APP_COLLECTION_TARGET:
            collect_app(destination, shards=app_shards, identity=before)
        elif _collection_target_language(target) == "python":
            collect_python_service(target, destination)
        else:
            collect_service(target, destination)
    except RedTestRun as error:
        red_error = error
    after = current_collection_identity(target)
    if before != after:
        destination.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        raise CoverageError(f"{target}: 覆盖率采集期间源码/测试/归属/采集范围发生漂移")
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
#: lcov 的行明细：`DA:<line>,<count>`（可选第三段 checksum）。
LCOV_LINE_DETAIL_RE = re.compile(r"^DA:(?P<line>\d+),(?P<count>\d+)(?:,[^,]*)?\s*$")
#: lcov 的分支明细：`BRDA:<line>,<block>,<branch>,<taken>`，`taken` 为 `-` 表示
#: 该分支所在的代码块从未被求值。
LCOV_BRANCH_DETAIL_RE = re.compile(
    r"^BRDA:(?P<line>\d+),(?P<block>\d+),(?P<branch>[^,]+),(?P<taken>-|\d+)\s*$"
)

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


# ---------------------------------------------------------------------------
# lcov 明细层：分片合并的唯一算术
# ---------------------------------------------------------------------------
#
# `parse_lcov` 消费的是汇总口径（`LF`/`LH` + `BRDA` 计数），它回答「这份产物的
# 覆盖率是多少」。分片合并回答的是另一个问题：「怎么把 N 份产物拼成一份，使它
# 与全量运行产出的那一份等价」。这必须在明细层做——把两片的 `LF`/`LH` 相加会
# 把同一个文件的分母重复计数，把后一片直接覆盖前一片会丢掉只在前片被触达的文件。


def _lcov_file_record() -> dict:
    return {"lines": {}, "branches": {}}


def parse_lcov_records(text: str) -> dict[str, dict]:
    """把 lcov 拆成可合并的明细：``{源文件: {"lines": ..., "branches": ...}}``。

    ``lines`` 是 ``{行号: 命中次数}``，``branches`` 是
    ``{(行号, block, branch): 命中次数 | None}``，``None`` 对应 `taken` 为 `-`
    的「该分支所在代码块从未被求值」。

    每个 `SF:` 块自己声明的 `LF`/`LH`（以及 lcov 可选的 `BRF`/`BRH`）必须与它
    自己的明细自洽，否则阻断：合并后的汇总行由明细重新推导，若输入的汇总行本来
    就与明细不一致，同一维度就出现了两套口径，合并结果无从取舍。

    空文本返回空 dict：某一片的测试可能一个 `lib/**` 文件都没加载到（例如只测
    跨 package 的 generated contracts），此时 `flutter test` 产出的是零字节
    lcov。这是分片下的真实情况，不是采集失败——合并结果整体为空才是失败。
    """
    records: dict[str, dict] = {}
    source: str | None = None
    lines: dict[int, int] = {}
    branches: dict[tuple[int, str, str], int | None] = {}
    declared: dict[str, int] = {}

    def flush() -> None:
        if source is None:
            return
        _assert_lcov_summaries_match_details(source, declared, lines, branches)
        merge_lcov_file_record(
            records.setdefault(source, _lcov_file_record()),
            {"lines": lines, "branches": branches},
        )

    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("SF:"):
            flush()
            source = stripped[len("SF:") :]
            lines = {}
            branches = {}
            declared = {}
            continue
        if source is None:
            continue
        line_detail = LCOV_LINE_DETAIL_RE.match(stripped)
        if line_detail:
            number = int(line_detail.group("line"))
            lines[number] = lines.get(number, 0) + int(line_detail.group("count"))
            continue
        line_summary = LCOV_LINE_SUMMARY_RE.match(stripped)
        if line_summary:
            declared[line_summary.group(1)] = int(line_summary.group(2))
            continue
        branch_summary = LCOV_BRANCH_SUMMARY_RE.match(stripped)
        if branch_summary:
            declared[branch_summary.group(1)] = int(branch_summary.group(2))
            continue
        branch_detail = LCOV_BRANCH_DETAIL_RE.match(stripped)
        if branch_detail:
            key = (
                int(branch_detail.group("line")),
                branch_detail.group("block"),
                branch_detail.group("branch"),
            )
            taken = branch_detail.group("taken")
            branches[key] = _merge_branch_taken(
                branches.get(key), None if taken == "-" else int(taken)
            )
            continue
    flush()
    return records


def _assert_lcov_summaries_match_details(
    source: str,
    declared: dict[str, int],
    lines: dict[int, int],
    branches: dict[tuple[int, str, str], int | None],
) -> None:
    found = len(lines)
    hit = sum(1 for count in lines.values() if count > 0)
    branch_found = len(branches)
    branch_hit = sum(1 for taken in branches.values() if taken)
    for label, declared_key, derived in (
        ("LF", "LF", found),
        ("LH", "LH", hit),
        ("BRF", "BRF", branch_found),
        ("BRH", "BRH", branch_hit),
    ):
        if declared_key in declared and declared[declared_key] != derived:
            raise CoverageError(
                f"{source}: {label}={declared[declared_key]} 与明细推导值 {derived} 不一致；"
                "分片合并要求汇总行与 DA/BRDA 明细同源"
            )


def _merge_branch_taken(current: int | None, incoming: int | None) -> int | None:
    """合并同一个分支的 `taken`。

    `-`（None）表示「这一片没有求值过该分支」，与 `0`（求值过但没走到）不同：
    只要任一片给出了数字，合并结果就是数字之和；全部是 `-` 才继续是 `-`。这与
    `parse_lcov` 的命中判定（`-` 和 `0` 都算未命中）自洽，也不会让某一片的
    「没求值」抹掉另一片的实测命中。
    """
    if current is None:
        return incoming
    if incoming is None:
        return current
    return current + incoming


def merge_lcov_file_record(target: dict, incoming: dict) -> None:
    """把单个源文件的明细并入 ``target``（行命中累加，分支按上面的规则合并）。"""
    target_lines: dict[int, int] = target["lines"]
    for number, count in incoming["lines"].items():
        target_lines[number] = target_lines.get(number, 0) + count
    target_branches: dict[tuple[int, str, str], int | None] = target["branches"]
    for key, taken in incoming["branches"].items():
        target_branches[key] = _merge_branch_taken(target_branches.get(key), taken)


def merge_lcov_records(target: dict[str, dict], incoming: dict[str, dict]) -> None:
    """把一份 lcov 的全部明细并入 ``target``，按源文件取并集。

    「并集」是这里的关键：某个文件只在 A 片被触达时，它必须留在合并结果里；
    B 片没提到它不代表它没有覆盖率。同理某个文件在两片各覆盖了不同的行，合并
    后两批行都在分母里、都在分子里。
    """
    for source, record in incoming.items():
        merge_lcov_file_record(target.setdefault(source, _lcov_file_record()), record)


def _lcov_branch_sort_key(key: tuple[int, str, str]) -> tuple:
    line, block, branch = key
    return (line, _lcov_identifier_sort_key(block), _lcov_identifier_sort_key(branch))


def _lcov_identifier_sort_key(value: str) -> tuple[int, int, str]:
    return (0, int(value), "") if value.isdigit() else (1, 0, value)


def iter_lcov_lines(records: dict[str, dict]) -> Iterable[str]:
    """按 Flutter 产出的记录形状渲染合并结果：``SF / DA* / LF / LH / BRDA*``。

    `LF`/`LH` 由合并后的 `DA` 重新推导，不沿用任何一片的汇总行；不写
    `BRF`/`BRH`，与 Flutter 3.44 的原生产出保持同形，`parse_lcov` 因此对
    「全量运行的 lcov」与「分片合并的 lcov」走完全相同的代码路径。
    """
    for source in sorted(records):
        record = records[source]
        lines: dict[int, int] = record["lines"]
        yield f"SF:{source}\n"
        for number in sorted(lines):
            yield f"DA:{number},{lines[number]}\n"
        yield f"LF:{len(lines)}\n"
        yield f"LH:{sum(1 for count in lines.values() if count > 0)}\n"
        branches: dict[tuple[int, str, str], int | None] = record["branches"]
        for key in sorted(branches, key=_lcov_branch_sort_key):
            line, block, branch = key
            taken = branches[key]
            yield f"BRDA:{line},{block},{branch},{'-' if taken is None else taken}\n"
        yield "end_of_record\n"


def render_lcov(records: dict[str, dict]) -> str:
    return "".join(iter_lcov_lines(records))


def parse_go_coverprofile_files(text: str) -> dict[str, tuple[int, int]]:
    """解析 Go coverprofile，返回逐文件 ``{source: (covered, total)}``。

    首行是 `mode: atomic`。其后每行一个基本块，同一个块可能出现多次（不同测试
    二进制各写一份），按块去重并对计数求和，再按 source 聚合。逐文件明细是
    Cloud 对象归属的前提；先聚合成 service/domain 总数会永久丢失对象边界。
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
    files: dict[str, list[int]] = {}
    for block, (statements, count) in blocks.items():
        source, separator, _coordinates = block.rpartition(":")
        if not separator or not source:
            raise CoverageError(f"go coverprofile block 缺少 source path: {block!r}")
        totals = files.setdefault(source, [0, 0])
        totals[1] += statements
        if count > 0:
            totals[0] += statements
    return {source: (values[0], values[1]) for source, values in files.items()}


def parse_go_coverprofile(text: str) -> dict[str, tuple[int, int]]:
    """解析 Go coverprofile 的全产物 statement 汇总；兼容公共解析入口。"""
    files = parse_go_coverprofile_files(text)
    return {
        "statement": (
            sum(covered for covered, _total in files.values()),
            sum(total for _covered, total in files.values()),
        )
    }


def parse_python_trace_files(
    text: str,
    target: str,
) -> dict[str, tuple[int, int]]:
    """解析标准库 trace 产物并锚定到 ``quwoquan_service`` 相对路径。"""
    if target not in python_collection_targets():
        raise CoverageError(f"{target}: 不是 Python coverage target")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise CoverageError(f"{target}: Python trace artifact 不是 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"schema", "files"}:
        raise CoverageError(f"{target}: Python trace artifact fields mismatch")
    if payload.get("schema") != PYTHON_TRACE_ARTIFACT_SCHEMA:
        raise CoverageError(
            f"{target}: Python trace schema 必须是 {PYTHON_TRACE_ARTIFACT_SCHEMA}"
        )
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise CoverageError(f"{target}: Python trace artifact 没有 production files")
    service_relative = Path(target).relative_to(SERVICE_ROOT.name).as_posix()
    parsed: dict[str, tuple[int, int]] = {}
    for relative, entry in sorted(files.items()):
        relative_path = Path(str(relative))
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or not relative_path.parts
            or relative_path.suffix != ".py"
        ):
            raise CoverageError(
                f"{target}: Python trace source path 非 canonical: {relative!r}"
            )
        if not isinstance(entry, dict) or set(entry) != {
            "coveredStatements",
            "totalStatements",
        }:
            raise CoverageError(
                f"{target}: Python trace source fields mismatch: {relative!r}"
            )
        covered = entry.get("coveredStatements")
        total = entry.get("totalStatements")
        if (
            not isinstance(covered, int)
            or isinstance(covered, bool)
            or not isinstance(total, int)
            or isinstance(total, bool)
            or covered < 0
            or total < 0
            or covered > total
        ):
            raise CoverageError(
                f"{target}: Python trace statement 计数非法: {relative!r}"
            )
        source = f"{service_relative}/{relative_path.as_posix()}"
        parsed[source] = (covered, total)
    return parsed


class CloudAttribution:
    """Cloud production source → 对象/横切单元的唯一物理归属。"""

    def __init__(self, roster: opm.ObjectRoster) -> None:
        self.unit_of: dict[str, str] = {}
        self.files_by_unit: dict[str, set[str]] = {}
        service_domains = opm.service_domains()
        for target, domain in sorted(cloud_collection_targets().items()):
            owner, declared_domain = service_domains[target]
            if declared_domain != domain or domain not in roster.domains:
                raise CoverageError(
                    f"{target}: service domain 与 ContractGraph roster 漂移"
                )
            service_root = ROOT / target
            language = _collection_target_language(target)
            suffix = "*.go" if language == "go" else "*.py"
            for path in sorted((service_root / "internal").rglob(suffix)):
                if (
                    language == "go" and path.name.endswith("_test.go")
                ) or path.is_symlink():
                    continue
                identity = opm.derive_cloud_source_identity(
                    path.relative_to(service_root / "internal").parts
                )
                if identity is None:
                    raise CoverageError(
                        f"{_display(path)}: Cloud production source 不是 "
                        "internal/<context>/<object>/<layer>"
                    )
                context, object_name, _layer = identity
                record = roster.by_key.get((domain, context, object_name))
                if record is None:
                    raise CoverageError(
                        f"{_display(path)}: 物理对象 {domain}.{context}.{object_name} "
                        "不在 ContractGraph roster"
                    )
                self._add(
                    path,
                    cloud_object_unit(owner, context, object_name),
                )
            for path in sorted((service_root / "cmd").rglob(suffix)):
                if (
                    not (language == "go" and path.name.endswith("_test.go"))
                    and not path.is_symlink()
                ):
                    self._add(path, cloud_cross_cutting_unit("cmd"))

        for path in sorted((SERVICE_ROOT / "cmd").rglob("*.go")):
            if not path.name.endswith("_test.go") and not path.is_symlink():
                self._add(path, cloud_cross_cutting_unit("cmd"))
        for root_name in ("runtime", "internal/platform"):
            for path in sorted((SERVICE_ROOT / root_name).rglob("*.go")):
                if not path.name.endswith("_test.go") and not path.is_symlink():
                    self._add(path, cloud_cross_cutting_unit("shared_runtime"))

        if not self.files_by_unit:
            raise CoverageError("Cloud 没有任何可计量的 production source unit")

    def _add(self, path: Path, unit: str) -> None:
        source = path.relative_to(SERVICE_ROOT).as_posix()
        previous = self.unit_of.get(source)
        if previous is not None and previous != unit:
            raise CoverageError(
                f"{_display(path)}: 同一 Cloud source 被归入多个 coverage unit: "
                f"{previous!r}, {unit!r}"
            )
        self.unit_of[source] = unit
        self.files_by_unit.setdefault(unit, set()).add(source)

    def canonical_source(self, coverprofile_source: str) -> str | None:
        """把 module/绝对 coverprofile path 规范为相对 ``quwoquan_service``。"""
        module_prefix = f"{SERVICE_ROOT.name}/"
        if coverprofile_source.startswith(module_prefix):
            relative = coverprofile_source[len(module_prefix) :]
        elif coverprofile_source in self.unit_of:
            relative = coverprofile_source
        else:
            candidate = Path(coverprofile_source)
            if not candidate.is_absolute():
                return None
            try:
                relative = (
                    candidate.resolve().relative_to(SERVICE_ROOT.resolve()).as_posix()
                )
            except ValueError:
                return None
        return relative if relative in self.unit_of else None


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
                raise CoverageError(
                    f"App production source path 非 canonical repo path: {path!r}"
                )
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
            suffix = (
                f"\n  ... 另有 {len(unowned) - len(examples)} 个"
                if len(unowned) > len(examples)
                else ""
            )
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
        library_relative = (
            source[len(LIB_PREFIX) :] if source.startswith(LIB_PREFIX) else source
        )
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


def _measure_cloud_unit(
    unit: str,
    profiles: Sequence[tuple[str, dict[str, tuple[int, int]]]],
    attribution: CloudAttribution,
) -> dict[str, dict]:
    """只累计属于该 Cloud 对象/横切单元的逐文件 statement。"""
    covered = total = 0
    for target, files in profiles:
        unknown = sorted(
            source for source in files if attribution.canonical_source(source) is None
        )
        if unknown:
            raise CoverageError(
                f"{target}: coverprofile 含无 canonical 对象/横切 owner 的 source:\n  "
                + "\n  ".join(unknown[:20])
            )
        for source, (file_covered, file_total) in files.items():
            canonical = attribution.canonical_source(source)
            if canonical is not None and attribution.unit_of[canonical] == unit:
                covered += file_covered
                total += file_total
    if total <= 0:
        raise CoverageError(
            f"{unit}: statement 分母为 0；物理 source owner 与采集范围漂移"
        )
    if covered <= 0:
        raise CoverageError(
            f"{unit}: statement 实测 0/{total}；对象没有任何 production statement "
            "被 canonical local_contract 执行，禁止把 0% 登记成可准出基线"
        )
    return {"statement": _metric(covered, total, unmeasured_reason="")}


def _require_app_unit_measured(unit: str, metrics: dict[str, dict]) -> None:
    """App 任何不可测轴或 0/N 都不能进入 canonical baseline。"""
    failures: list[str] = []
    for metric in METRICS_BY_KIND[KIND_FLUTTER_LCOV]:
        entry = metrics[metric]
        if entry.get("status") == METRIC_STATUS_UNMEASURED:
            failures.append(f"{metric}=unmeasured ({entry.get('reason')})")
        elif int(entry.get("covered", 0)) <= 0:
            failures.append(f"{metric}=0/{entry.get('total')}")
    if failures:
        raise CoverageError(f"{unit}: App coverage 不可准出：" + "; ".join(failures))


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
                "（归属派生器与产物不同源）：\n  " + "\n  ".join(unknown[:20])
            )
        for unit in app_units:
            measured[unit] = _measure_app_unit(unit, lcov, attribution)
            _require_app_unit_measured(unit, measured[unit])
            unit_receipts[unit] = [app_receipt]

    cloud_units = [unit for unit in units if unit.startswith(CLOUD_UNIT_PREFIX)]
    if cloud_units:
        attribution = CloudAttribution(_roster())
    for unit in cloud_units:
        profiles: list[tuple[str, dict[str, tuple[int, int]]]] = []
        receipts: list[dict] = []
        for target in cloud_collection_targets_for_unit(unit):
            artifact_text, receipt = _read_artifact(target)
            if _collection_target_language(target) == "python":
                files = parse_python_trace_files(artifact_text, target)
            else:
                files = parse_go_coverprofile_files(artifact_text)
            profiles.append((target, files))
            receipts.append(receipt)
        measured[unit] = _measure_cloud_unit(unit, profiles, attribution)
        unit_receipts[unit] = receipts
    return measured, {"unitReceipts": unit_receipts}


# ---------------------------------------------------------------------------
# 基线
# ---------------------------------------------------------------------------

POLICY_NUMERIC_KEYS = (
    "tolerance_percentage_points",
    "improvement_slack_percentage_points",
    "granularity_units",
)
POLICY_REASON_KEYS = (
    "tolerance_reason",
    "improvement_slack_reason",
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
        raise ValueError(
            f"{BASELINE_PATH}: {unit}/{metric} 不得把 unmeasured 写入 baseline；"
            "未采集不是绿测试覆盖结果"
        )
    if set(entry) != {"covered", "total", "percent"}:
        raise ValueError(f"{BASELINE_PATH}: {unit}/{metric} measured fields mismatch")
    covered = entry.get("covered")
    total = entry.get("total")
    value = entry.get("percent")
    if (
        not isinstance(covered, int)
        or isinstance(covered, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total <= 0
        or covered <= 0
        or covered > total
        or not isinstance(value, (int, float))
        or isinstance(value, bool)
        or float(value) != percent(covered, total)
    ):
        raise ValueError(
            f"{BASELINE_PATH}: {unit}/{metric} measured value 非自洽实测值"
        )


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
            raise ValueError(
                f"{BASELINE_PATH}: receipt {declared_digest}: {error}"
            ) from error
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
    if RETIRED_BASELINE_PATH.is_file():
        raise ValueError(
            f"{RETIRED_BASELINE_PATH}: 旧 coverage baseline 已硬切退休；"
            "删除旧输入后仅生成 canonical baseline"
        )
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
    if (
        not isinstance(governance, dict)
        or set(governance) != BASELINE_GOVERNANCE_FIELDS
    ):
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
            raise ValueError(
                f"{BASELINE_PATH}: policy.{key} 必须是非负数，实测 {value!r}"
            )
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
    kind = unit_kind(unit)
    expected_metrics = set(METRICS_BY_KIND[kind])
    if not isinstance(metrics, dict) or set(metrics) != expected_metrics:
        actual_metrics = (
            sorted(metrics) if isinstance(metrics, dict) else type(metrics).__name__
        )
        raise CoverageError(
            f"{unit}: baseline metrics 维度不完整；"
            f"expected={sorted(expected_metrics)}, actual={actual_metrics}"
        )
    for metric, entry in metrics.items():
        try:
            _validate_baseline_metric(unit, metric, entry)
        except ValueError as error:
            raise CoverageError(str(error)) from error
    validated_receipts = [
        _validate_receipt_payload(receipt, expected_target=None, require_green=True)
        for receipt in receipts
    ]
    receipt_refs = sorted(receipt_digest(receipt) for receipt in validated_receipts)
    registry = {receipt_digest(receipt): receipt for receipt in validated_receipts}
    provisional = {"receiptDigests": receipt_refs}
    _validate_unit_receipt_refs(unit, provisional, registry)
    return {
        "kind": kind,
        "scope": unit_scope(unit),
        "measuredFromGreenTests": True,
        "receiptDigests": receipt_refs,
        "metrics": {
            metric: dict(metrics[metric])
            for metric in sorted(METRICS_BY_KIND[kind])
        },
    }


def write_baseline(
    measured: dict[str, dict],
    *,
    units: Sequence[str],
    unit_receipts: dict[str, Sequence[dict]],
    known_units: Sequence[str] | None = None,
) -> dict:
    """以全单元同次绿产物整体写入唯一 baseline。"""
    if RETIRED_BASELINE_PATH.is_file():
        raise CoverageError(
            f"{RETIRED_BASELINE_PATH}: 旧 coverage baseline 已硬切退休；"
            "禁止 alias、fallback、dual-read 或原位改名"
        )
    all_units = set(discover_units())
    if set(units) != all_units:
        raise CoverageError(
            "canonical coverage baseline 只能由 App、Cloud、Python、Ops "
            "全单元同次全绿采集整体写入；禁止 scope/unit 分区更新"
        )
    if known_units is not None and set(known_units) != all_units:
        raise CoverageError(
            "canonical coverage baseline roster 与当前全单元名册不一致"
        )
    missing_receipts = sorted(set(units) - set(unit_receipts))
    extra_receipts = sorted(set(unit_receipts) - set(units))
    if missing_receipts or extra_receipts:
        raise CoverageError(
            "baseline provenance 与求值单元不一致；"
            f"missing={missing_receipts}, extra={extra_receipts}"
        )
    if BASELINE_PATH.exists():
        try:
            load_baseline()
        except (ValueError, json.JSONDecodeError) as error:
            raise CoverageError(
                "非 canonical coverage baseline 已硬切退休；"
                "禁止兼容读取、别名或迁移旧数字"
            ) from error
    payload = {
        "_governance": dict(CANONICAL_BASELINE_GOVERNANCE),
        "schema": BASELINE_SCHEMA,
        "ruleId": RULE_ID,
        "policy": dict(CANONICAL_POLICY),
        "receipts": {},
        "units": {},
    }
    for unit in units:
        receipts = list(unit_receipts[unit])
        for receipt in receipts:
            validated = _validate_receipt_payload(
                receipt, expected_target=None, require_green=True
            )
            payload["receipts"][receipt_digest(validated)] = dict(validated)
        payload["units"][unit] = unit_entry(measured[unit], unit, receipts=receipts)

    referenced_receipts = {
        digest
        for entry in payload["units"].values()
        for digest in entry["receiptDigests"]
    }
    payload["receipts"] = {
        digest: payload["receipts"][digest] for digest in sorted(referenced_receipts)
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
    ordered["units"] = {
        unit: payload["units"][unit] for unit in sorted(payload["units"])
    }
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
        max(float(policy["improvement_slack_percentage_points"]), granularity),
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
        receipt_registry = _validate_baseline_receipt_registry(baseline.get("receipts"))
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
        return [
            f"{unit}/{metric}: 基线与现状都不可测（{current.get('reason')}）；"
            "两个 unmeasured 不能相互证明覆盖率达标，必须由全绿采集产生实测值"
        ]
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
    if int(recorded.get("covered", 0)) <= 0:
        return [
            f"{unit}/{metric}: 基线是非法 0/{recorded.get('total')}；"
            "未触达 production 代码不能成为可准出下限，须由全绿采集重建"
        ]
    if int(current.get("covered", 0)) <= 0:
        return [
            f"{unit}/{metric}: 现状实测 0/{current.get('total')}；"
            "未触达 production 代码不得借粒度容差通过棘轮"
        ]
    floor = float(recorded["percent"])
    value = float(current["percent"])
    if metric == "file":
        # file 轴专门堵住「删掉覆盖差的测试 import，让 lcov 分母缩水」的路径。
        # 一个小桶可能只有两三个文件；若沿用两个可数单位的粒度下限，删掉其中
        # 一个会落在 50%~100% 的容差内，恰好把这条防线架空。
        tolerance = float(policy["tolerance_percentage_points"])
        slack = float(policy["improvement_slack_percentage_points"])
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
            "唯一 canonical coverage rule（App/Cloud 按 service/context/object 计量）"
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
            "app:circle_service/circle_management/gathering / "
            "cloud:circle_service/circle_management/gathering"
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
        help="仅用 App/Cloud/Python/Ops 全单元同次全绿实测值整体写入唯一 baseline",
    )
    parser.add_argument(
        "--app-shards",
        type=int,
        default=None,
        help=(
            "端侧采集切成几片顺序执行（默认由测试文件数派生）。"
            "纯容量旋钮：所有测试文件都会被执行一次，合并结果与全量运行等价，"
            "因此片数不进 scope，也不能用来跳过任何测试"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)

    try:
        units = resolve_units(arguments.scope, arguments.unit)
    except (ValueError, CoverageError) as error:
        print(f"verify_canonical_coverage: BLOCK: {error}", file=sys.stderr)
        return 2

    if arguments.write_baseline and not arguments.collect:
        # 基线里的 `measuredFromGreenTests` 只有本次真的跑过测试才说得出口；
        # 复用旧产物写基线等于凭空断言 provenance。
        print(
            "verify_canonical_coverage: BLOCK: --write-baseline 必须搭配 --collect，"
            "基线只能由本次实跑的测试写入",
            file=sys.stderr,
        )
        return 2

    if arguments.app_shards is not None and arguments.app_shards < 1:
        print(
            "verify_canonical_coverage: BLOCK: --app-shards 必须 >= 1；"
            "分片是执行方式，不是跳过测试的手段",
            file=sys.stderr,
        )
        return 2

    if arguments.collect:
        for target in collection_targets(units):
            try:
                print(f"verify_canonical_coverage: collecting {target} ...", flush=True)
                collect(target, app_shards=arguments.app_shards)
            except RedTestRun as error:
                print(
                    f"verify_canonical_coverage: BLOCK: {target}: {error}",
                    file=sys.stderr,
                )
                return 1
            except CoverageError as error:
                print(
                    f"verify_canonical_coverage: BLOCK: {target}: {error}",
                    file=sys.stderr,
                )
                return 1

    try:
        measured, extras = measure(units)
    except CoverageError as error:
        print(f"verify_canonical_coverage: BLOCK: {error}", file=sys.stderr)
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
            print(f"verify_canonical_coverage: GATE_BLOCK: {error}", file=sys.stderr)
            return 2
        print(f"verify_canonical_coverage: wrote baseline -> {_display(BASELINE_PATH)}")
        print(
            json.dumps(summarize(measured, units), ensure_ascii=False, sort_keys=True)
        )
        return 0

    try:
        baseline = load_baseline()
    except FileNotFoundError:
        print(
            "verify_canonical_coverage: BLOCK: missing "
            f"{BASELINE_PATH} (run once with --collect --write-baseline)",
            file=sys.stderr,
        )
        return 2
    except (ValueError, json.JSONDecodeError) as error:
        print(f"verify_canonical_coverage: FAIL load baseline: {error}", file=sys.stderr)
        return 1

    failures = diff(
        measured,
        baseline,
        units,
        known_units=known_units_for(units),
    )
    if failures:
        print("verify_canonical_coverage: BLOCK: canonical coverage rule", file=sys.stderr)
        for entry in failures:
            print(f"  {entry}", file=sys.stderr)
        print(
            "  覆盖率只增不减：新增代码必须带测试。修不动时补测试，"
            "不要下调基线；覆盖率真的提升了就用 --write-baseline 收紧。",
            file=sys.stderr,
        )
        return 1

    print(f"verify_canonical_coverage: OK ({len(units)} unit(s))")
    print(json.dumps(summarize(measured, units), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
