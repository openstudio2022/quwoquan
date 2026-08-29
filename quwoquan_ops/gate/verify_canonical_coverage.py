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

实现单轨落在 ``canonical_coverage/`` 包内；本文件只是稳定 CLI 入口，并为既有
消费者 re-export 包 API。被 import 时本模块在 ``sys.modules`` 中指向该包，
使对本模块属性的 monkeypatch 与拆分前单文件语义保持一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    path
    for path in Path(__file__).resolve().parents
    if (path / "repository_root.py").is_file()
)
if str(_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP))

from repository_root import repository_root  # noqa: E402

_REPO_ROOT = repository_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

sys.dont_write_bytecode = True

from quwoquan_ops.gate import canonical_coverage as _canonical_coverage  # noqa: E402
from quwoquan_ops.gate.canonical_coverage import (  # noqa: E402
    APP_COLLECTION_TARGET,
    APP_CROSS_CUTTING_UNIT_PREFIX,
    APP_ROOT,
    APP_SHARD_MAX_TEST_FILES,
    APP_TEST_FILE_SUFFIX,
    APP_TEST_TARGET,
    APP_UNIT_PREFIX,
    ARTIFACT_RECEIPT_SCHEMA,
    BASELINE_PATH,
    BASELINE_SCHEMA,
    CANONICAL_BASELINE_GOVERNANCE,
    CANONICAL_POLICY,
    CLOUD_CROSS_CUTTING_UNIT_PREFIX,
    CLOUD_UNIT_PREFIX,
    COVERAGE_CACHE_DIR,
    KIND_CLOUD_STATEMENT,
    KIND_FLUTTER_LCOV,
    METRICS_BY_KIND,
    METRIC_STATUS_UNMEASURED,
    PYTHON_COVERAGE_TOOLCHAIN_LOCK,
    PYTHON_COVERAGE_TOOLCHAIN_MARKER,
    PYTHON_TRACE_ARTIFACT_SCHEMA,
    RETIRED_BASELINE_PATH,
    ROOT,
    RULE_ID,
    SERVICE_ROOT,
    AppAttribution,
    CloudAttribution,
    CoverageError,
    RedTestRun,
    _app_collection_inputs,
    _app_shard_artifact_paths,
    _app_source_closure_files,
    _attribution_inputs,
    _collection_config_inputs,
    _collection_scope_digest,
    _display,
    _git_head_identity,
    _has_go_sources,
    _identity_command,
    _measure_app_unit,
    _measure_cloud_unit,
    _parse_python_coverage_toolchain_lock,
    _python_collection_executable,
    _python_toolchain_state,
    _read_artifact,
    _require_app_unit_measured,
    _roster,
    _run,
    _sha256_bytes,
    _sha256_file,
    _toolchain_digest,
    _tree_digest,
    _write_artifact_receipt,
    app_cross_cutting_unit,
    app_object_unit,
    app_shard_directory,
    app_shard_plan,
    app_test_files,
    app_units,
    artifact_path,
    artifact_receipt_path,
    build_parser,
    cloud_collection_targets_for_unit,
    cloud_cross_cutting_unit,
    collect,
    collect_app,
    collection_targets,
    current_collection_identity,
    default_app_shard_count,
    diff,
    discover_app_units,
    discover_cloud_units,
    discover_units,
    expected_app_capability_units,
    go_collection_targets,
    known_units_for,
    load_baseline,
    main,
    measure,
    merge_lcov_records,
    opm,
    parse_go_coverprofile,
    parse_go_coverprofile_files,
    parse_lcov,
    parse_lcov_records,
    parse_python_trace_files,
    percent,
    python_collection_targets,
    receipt_digest,
    render_lcov,
    resolve_units,
    summarize,
    thresholds,
    unit_bucket,
    unit_entry,
    unit_kind,
    unit_scope,
    vaa,
    validate_artifact_receipt,
    write_baseline,
)

# 既有测试对本模块属性做 monkeypatch 并期望包内实现同步生效（与拆分前单文件的
# 全局查找语义一致）。把 import 名指向包命名空间，使两者是同一个可写命名空间；
# 作为脚本直跑（__main__）时保持本命名空间不变，直接调用 re-export 的 main。
if __name__ != "__main__":
    sys.modules[__name__] = _canonical_coverage


if __name__ == "__main__":
    raise SystemExit(main())
