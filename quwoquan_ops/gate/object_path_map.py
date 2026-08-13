#!/usr/bin/env python3
"""端云 business object → 物理文件的唯一派生器（derivation，不是注册表）。

本工具只读受版本控制的真相源，交叉派生「business object → 端云物理文件」映射、
迁移目标清单与现状基线；不写入、不维护任何 registry / inventory / 台账。全部产物
落在 `.qwq_output/env/repo/runs/object-path-map/`，删除后可凭真相源完全重建，符合
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#req-001`（禁止第二真相源，状态必须
由物理路径与运行证据派生）。

实现单轨落在 ``object_path_map_lib/`` 包内（constants / roster / topology /
identity / claims / scan / views / render / entry）；本文件是稳定模块入口，
`from quwoquan_ops.gate import object_path_map` 的全部公开符号由这里 re-export。

真相源（只读）
--------------
1. `quwoquan_service/generated/contract_graph.json`
   对象 roster：`objects[].{id,domain,kind,sourcePath}`、
   `businessObjectMaps[].boundedContexts[].contextId`，以及真实 App 消费边界
   `operations[].clientContract`。
2. `quwoquan_service/services/*/contracts/domain.yaml`
   与 `quwoquan_service/control-plane/*/contracts/domain.yaml`：service → domain。
3. `quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`
   页面 `source_path` 是 presentation 物理 owner 的唯一权威信号；`object_ids`
   只表达页面参与对象，不把参与对象提升为页面物理 owner。
4. 物理扫描：`quwoquan_app/lib/**`、`quwoquan_app/test/**`、
   `quwoquan_service/{services,control-plane}/*/internal/**`、
   `quwoquan_service/{services,control-plane}/*/tests/**`。

W5 同源声明
-----------
规划中的 W5 会在 `quwoquan_service/internal/metadata/load/load.go` 增加派生式
evidence loader。该 loader 必须与本模块同源，复用同一套规则；Go 侧不得另写一份。
可复用的规则表达集中在下列常量与函数（`RULE_ID` 变更即视为规则变更；实现位于
`object_path_map_lib/constants.py` 等包内模块，经本入口 re-export）：

- 常量：`RULE_ID`、`CLOUD_LAYERS`、`APP_LAYERS`、`APP_TO_CLOUD_LAYER_EQUIVALENCE`、
  `REQUIRED_CLOUD_LAYERS_BY_KIND`、`CLOUD_EXTERNAL_REFERENCE_REQUIRED`、
  `CLOUD_EXTERNAL_REFERENCE_EITHER`、`CLOUD_TEST_LAYERS`、
  `CLOUD_TEST_SUPPORT_ROOT`、`APP_OPERATION_REQUIRED_LAYERS`、
  `APP_PAGE_OWNER_REQUIRED_LAYERS`、`APP_CLIENT_INVARIANT_REQUIRED_LAYERS`、
  `FORBIDDEN_APP_LAYERS_BY_KIND`、`APP_PROCESS_PORT_NAMING`、
  `APP_APPEND_PORT_NAMING`、`APP_SESSION_PORT_NAMING`、
  `APP_LAYER_BY_SEGMENT`、`APP_LAYER_ALIASES`、`APP_CROSS_CUTTING_ROOTS`、
  `APP_CROSS_CUTTING_SEGMENTS`、`APP_CROSS_CUTTING_STRIPPED_PREFIXES`、
  `APP_DESIGN_SYSTEM_SEGMENTS`、`APP_L10N_CONFIG_PATH`、`APP_ENTRY_FILE_RE`、
  `APP_COMPOSITION_ROOT_SEGMENT`、
  `APP_COMPOSITION_ROOT_TARGET_PREFIX`、`APP_TARGET_SHAPE_SEGMENTS`、
  `APP_TEST_TARGET_SHAPE_SEGMENTS`、`ALIAS_TRIM_SUFFIXES`、
  `CLAIM_METHOD_CONFIDENCE`。
- 函数：`derive_cloud_source_identity`、`derive_cloud_test_identity`、
  `object_aliases`、`derive_app_object_claim`、`derive_app_layer`、
  `derive_app_target_shape_identity`、`derive_app_test_target_shape_identity`、
  `derive_app_cross_cutting_shape_root`、`derive_app_l10n_cross_cutting_root`、
  `derive_app_is_entry_file`、`derive_app_is_composition_root`、
  `derive_app_target_path`、`derive_app_test_target_path`、
  `derive_app_cross_cutting_root`、`derive_app_cross_cutting_target_path`、
  `derive_page_physical_owner`、`required_app_layers`、`required_cloud_layers`。
- 对象身份入口：`ObjectRoster`（含 `alias_index`、`scope_names`、`by_key`）。

派生幂等
--------
`derive(derive(p)) == derive(p)`：已经处于目标形态的路径，派生结果必须等于它自己。
目标形态由 `derive_app_target_shape_identity`
（`lib/service/<service>/<context>/<object>/<layer>/`）、
`derive_app_test_target_shape_identity`
（`test/<layer>/service/<service>/<context>/<object>/`）与
`derive_app_cross_cutting_shape_root`（`APP_CROSS_CUTTING_ROOTS` 的三个根）精确识别，
命中后一切基于旧命名的启发式让位：身份与层由固定物理位置决定，目标路径即自身。
本不变量由 `test_object_path_map__derivation__local_contract_test.py` 断言；它是四条
domain 流与 W1b 边搬边跑派生器/门禁的前提，破坏它会持续产生假归属与假违规。

`REQUIRED_CLOUD_LAYERS_BY_KIND` 是 `quwoquan_ops/gate/verify_service_architecture.py`
中 `Verification.verify_kind_aware_object_implementation` 的 `required_layers` 镜像。
`check_cloud_layer_rule_mirror` 在每次运行时用 AST 比对两者，一旦漂移直接失败，避免
出现第二套云侧 kind 规则。

用法
----
    python3 quwoquan_ops/gate/object_path_map.py

幂等：输出目录固定、内容全排序、不含时间戳与绝对路径，连续两次运行产物逐字节一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.object_path_map_lib import *  # noqa: E402,F401,F403
from quwoquan_ops.gate.object_path_map_lib import (  # noqa: E402,F401
    MANIFEST_COLUMNS,
    ObjectRoster,
    app_service_for_context,
    app_service_segment,
    build_baseline,
    build_context_diff,
    build_object_view,
    check_cloud_layer_rule_mirror,
    context_to_service,
    derive_app_cross_cutting_root,
    derive_app_cross_cutting_shape_root,
    derive_app_cross_cutting_target_path,
    derive_app_is_composition_root,
    derive_app_is_entry_file,
    derive_app_l10n_cross_cutting_root,
    derive_app_layer,
    derive_app_object_claim,
    derive_app_target_path,
    derive_app_target_shape_identity,
    derive_app_test_non_object_identity,
    derive_app_test_target_path,
    derive_app_test_target_shape_identity,
    derive_cloud_source_identity,
    derive_cloud_test_identity,
    derive_page_physical_owner,
    load_page_claims,
    main,
    object_aliases,
    render_baseline_report,
    render_manifest,
    required_app_layers,
    required_cloud_layers,
    scan_app,
    scan_cloud,
    service_context_segments,
    service_domains,
)

if __name__ == "__main__":
    raise SystemExit(main())
