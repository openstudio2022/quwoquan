"""canonical coverage 常量、异常与最小共享 helper。

本模块承载原单文件门禁的全部顶层常量（路径、单元前缀、policy、receipt 字段、
正则）、`CoverageError` / `RedTestRun` 异常，以及被多个模块共享的 `_display` /
`_tail` 两个最小 helper。除路径推导按新目录层级调整外，内容与拆分前逐字一致。
"""

from __future__ import annotations

import re
from pathlib import Path

# 拆分为包后本文件多了一层目录：parents[3] 与拆分前单文件的 parents[2] 指向
# 同一个仓库根。
ROOT = Path(__file__).resolve().parents[3]

# 包命名空间（等价于拆分前的单文件模块命名空间）；`_display` 对 ROOT 的
# call-time 解析必须经它进行，测试才能通过 monkeypatch 改写 ROOT。
import quwoquan_ops.gate.canonical_coverage as cc  # noqa: E402

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
        "对象级全量绿采集及其 canonical receipt provenance。App 采集覆盖 "
        f"{APP_TEST_TARGET} 全部测试，并以 BRDA 明细计算分支。"
    ),
    "expires_when": (
        "覆盖率规则由新的当前规格整体替代并原子硬切时；不得保留旧格式或迁移别名。"
    ),
    "measure": (
        "从 ContractGraph 与 object_path_map 实时派生 App/Cloud object unit，并把 "
        "App design_system/l10n/runtime 与 Cloud cmd/shared_runtime 五个物理根分别"
        "归入显式 cross-cutting unit；App 执行 "
        f"{APP_TEST_TARGET} 下全部 *_test.dart，file covered 是 lcov 出现的归属"
        "production file 数、file total 是磁盘全部归属 production file 数，line "
        "按 DA 明细复算 LF/LH，branch 按 (line,block,branch) 去重 BRDA 明细复算"
        "命中与总数。Go Cloud 对各服务 internal/cmd 及仓库 cmd/runtime/"
        "internal/platform 生成 atomic coverprofile，并以 block statement weight "
        "累计 covered/total；Python Cloud 对 internal/cmd 使用受管解释器 trace，"
        "以 trace._find_executable_linenos 的可执行行集合为 total、正计数交集为"
        "covered。每个数值必须绑定同次全绿且八轴 current identity 匹配的 "
        "canonical receipt。"
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

#: 端侧采集目标名（采集目标 ≠ 计量单元：端侧一次跑出全部桶）。
APP_COLLECTION_TARGET = "app"


class CoverageError(RuntimeError):
    """采集或解析失败；一律阻断，不降级成 0 覆盖率或跳过。"""


class RedTestRun(CoverageError):
    """测试没全绿。

    红着的套件测出来的覆盖率既不是准出证据，也不能形成 tracked baseline；产物
    receipt 可以保留 ``testsGreen=false`` 供诊断，但所有复用和写基线路径都阻断。
    """


def _display(path: Path) -> str:
    try:
        return path.relative_to(cc.ROOT).as_posix()
    except ValueError:
        return str(path)


def _tail(text: str, *, limit: int = 40) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:]) + ("\n" if lines else "")
