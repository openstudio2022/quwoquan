"""object_path_map 派生器的实现包。

唯一稳定入口是 ``quwoquan_ops/gate/object_path_map.py``（薄壳 re-export）；
本包按职责切分：

- ``constants``：规则标识、真相源路径、层规则与命名表（W5 同源声明的载体）。
- ``roster``：ContractGraph 对象 roster 与别名派生。
- ``topology``：service/context 物理拓扑派生。
- ``identity``：端云物理路径 → 身份/层/目标路径的派生函数族。
- ``claims``：端侧对象归属裁决与云侧 kind 规则防漂移。
- ``scan``：端云物理树扫描。
- ``views``：对象聚合视图与现状基线。
- ``render``：manifest/基线报告渲染与 context 口径差异。
- ``entry``：CLI main。
"""
from __future__ import annotations

import sys
from pathlib import Path

_GATE_ROOT = Path(__file__).resolve().parents[1]
if str(_GATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_GATE_ROOT))

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from .constants import *  # noqa: E402,F401,F403
from .constants import (  # noqa: E402,F401
    required_app_layers,
    required_cloud_layers,
    derive_app_l10n_cross_cutting_root,
)
from .roster import ObjectRoster, object_aliases  # noqa: E402,F401
from .topology import (  # noqa: E402,F401
    app_service_for_context,
    app_service_segment,
    context_to_service,
    service_context_segments,
    service_domains,
)
from .identity import (  # noqa: E402,F401
    derive_app_cross_cutting_root,
    derive_app_cross_cutting_shape_root,
    derive_app_cross_cutting_target_path,
    derive_app_is_composition_root,
    derive_app_is_entry_file,
    derive_app_layer,
    derive_app_target_path,
    derive_app_target_shape_identity,
    derive_app_test_non_object_identity,
    derive_app_test_target_path,
    derive_app_test_target_shape_identity,
    derive_cloud_source_identity,
    derive_cloud_test_identity,
    derive_page_physical_owner,
)
from .claims import (  # noqa: E402,F401
    check_cloud_layer_rule_mirror,
    derive_app_object_claim,
)
from .scan import load_page_claims, scan_app, scan_cloud  # noqa: E402,F401
from .views import build_baseline, build_object_view  # noqa: E402,F401
from .render import (  # noqa: E402,F401
    MANIFEST_COLUMNS,
    build_context_diff,
    render_baseline_report,
    render_manifest,
)
from .entry import main  # noqa: E402,F401
