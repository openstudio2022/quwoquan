#!/usr/bin/env python3
"""垂类架构防回退门。

本门禁只读取物理源码、canonical domain owner metadata 与现存债务基线：

* 禁止新增按内容垂类拆分的 ``services/<vertical>-service``；
* 禁止业务代码新增垂类 ``switch/case`` 或 ``contentVertical ==`` 分叉；
* ``contentVertical`` 使用、``domain_taxonomy.yaml`` 运行时消费者只减不增；
* 已退役 travel-service 目录与 App、Assistant、api-edge、runtime auth、Ops 装配依赖永久保持为零。

基线不是服务/字段/消费者注册表，只保存允许现存命中的路径、计数摘要与退役责任。
删除命中会自动通过；新路径、计数增加或等量替换会阻断。travel-service 已完成日落，
其目录和五类调用方依赖不再接受任何 allowance、正计数或迁移期开关。

实现单轨落在 ``vertical_architecture_ratchet/`` 包内；本文件只是稳定 CLI 入口，
并为既有消费者 re-export 包 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

_BOOTSTRAP = next(
    path
    for path in Path(__file__).resolve().parents
    if (path / "repository_root.py").is_file()
)
if str(_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP))

from repository_root import repository_root  # noqa: E402

DEFAULT_ROOT = repository_root()
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))

from quwoquan_ops.gate.vertical_architecture_ratchet import (  # noqa: E402
    APP_CONTRACT_LOCK,
    APP_GENERATED_MANIFEST,
    APP_TRAVEL_DEPENDENCY_RE,
    BASELINE_SCHEMA,
    CASE_RE,
    CODE_SUFFIXES,
    CONTENT_VERTICAL_COMPARE_RE,
    CONTENT_VERTICAL_RE,
    CONTRACT_GRAPH,
    COPY_PARTS,
    DEFAULT_BASELINE,
    DIGEST_RE,
    DOMAIN_TAXONOMY,
    HitSummary,
    OUTPUT_ROOT,
    PATH_RE,
    REQUIRED_BUCKETS,
    RETIRED_APP_ARTIFACTS,
    RETIRED_APP_OUTPUT_RE,
    RETIRED_OUTPUT_NAME_RE,
    RETIRED_TRAVEL_SERVICE,
    ROOT,
    SERVICE_ROOT,
    SERVICE_TRAVEL_DEPENDENCY_RE,
    SKIP_PARTS,
    Snapshot,
    TAXONOMY_FILENAME_RE,
    TEXT_SUFFIXES,
    TRAVEL_DEPENDENCY_AREAS,
    TRAVEL_DOMAIN,
    VERTICAL_WORD_STOPLIST,
    build_snapshot,
    evaluate,
    load_baseline,
    load_vertical_terms,
    main,
    scan_app_travel_contract_ghosts,
    scan_content_vertical_usage,
    scan_contract_graph_travel_ghosts,
    scan_materialized_travel_owners,
    scan_platform_vertical_branches,
    scan_service_domains,
    scan_taxonomy_runtime_consumers,
    scan_travel_dependencies,
)

__all__ = [
    "APP_CONTRACT_LOCK",
    "APP_GENERATED_MANIFEST",
    "APP_TRAVEL_DEPENDENCY_RE",
    "BASELINE_SCHEMA",
    "CASE_RE",
    "CODE_SUFFIXES",
    "CONTENT_VERTICAL_COMPARE_RE",
    "CONTENT_VERTICAL_RE",
    "CONTRACT_GRAPH",
    "COPY_PARTS",
    "DEFAULT_BASELINE",
    "DEFAULT_ROOT",
    "DIGEST_RE",
    "DOMAIN_TAXONOMY",
    "HitSummary",
    "OUTPUT_ROOT",
    "PATH_RE",
    "REQUIRED_BUCKETS",
    "RETIRED_APP_ARTIFACTS",
    "RETIRED_APP_OUTPUT_RE",
    "RETIRED_OUTPUT_NAME_RE",
    "RETIRED_TRAVEL_SERVICE",
    "ROOT",
    "SERVICE_ROOT",
    "SERVICE_TRAVEL_DEPENDENCY_RE",
    "SKIP_PARTS",
    "Snapshot",
    "TAXONOMY_FILENAME_RE",
    "TEXT_SUFFIXES",
    "TRAVEL_DEPENDENCY_AREAS",
    "TRAVEL_DOMAIN",
    "VERTICAL_WORD_STOPLIST",
    "build_snapshot",
    "evaluate",
    "load_baseline",
    "load_vertical_terms",
    "main",
    "scan_app_travel_contract_ghosts",
    "scan_content_vertical_usage",
    "scan_contract_graph_travel_ghosts",
    "scan_materialized_travel_owners",
    "scan_platform_vertical_branches",
    "scan_service_domains",
    "scan_taxonomy_runtime_consumers",
    "scan_travel_dependencies",
]


if __name__ == "__main__":
    raise SystemExit(main())
