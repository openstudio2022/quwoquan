"""垂类架构防回退门实现包：taxonomy 派生、退役残影、债务棘轮与报告。

包内模块职责：

- ``constants``：路径、正则、扫描集合与基线 schema 常量的唯一定义处。
- ``models``：``HitSummary`` 命中摘要与 ``Snapshot`` 全仓快照 dataclass。
- ``fsscan``：文件枚举、注释剥离、行归一、digest 与 YAML/JSON 读取基元。
- ``taxonomy``：domain taxonomy 垂类词派生与服务 domain owner 扫描。
- ``retired_travel``：已退役 travel-service 残影与五类调用方依赖扫描。
- ``scans``：垂类分叉 / contentVertical / taxonomy 消费者扫描与快照组装。
- ``baseline``：债务基线 YAML 解析与校验。
- ``report``：棘轮比对、报告输出与 CLI ``main`` 入口。
"""

from __future__ import annotations

import sys
from pathlib import Path

_GATE_ROOT = Path(__file__).resolve().parents[1]
if str(_GATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_GATE_ROOT))

from repository_root import repository_root  # noqa: E402

_REPO_ROOT = repository_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from .baseline import load_baseline  # noqa: E402
from .constants import (  # noqa: E402
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
    TAXONOMY_FILENAME_RE,
    TEXT_SUFFIXES,
    TRAVEL_DEPENDENCY_AREAS,
    TRAVEL_DOMAIN,
    VERTICAL_WORD_STOPLIST,
)
from .models import HitSummary, Snapshot  # noqa: E402
from .report import evaluate, main  # noqa: E402
from .retired_travel import (  # noqa: E402
    scan_app_travel_contract_ghosts,
    scan_contract_graph_travel_ghosts,
    scan_materialized_travel_owners,
    scan_travel_dependencies,
)
from .scans import (  # noqa: E402
    build_snapshot,
    scan_content_vertical_usage,
    scan_platform_vertical_branches,
    scan_taxonomy_runtime_consumers,
)
from .taxonomy import (  # noqa: E402
    load_vertical_terms,
    scan_service_domains,
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
