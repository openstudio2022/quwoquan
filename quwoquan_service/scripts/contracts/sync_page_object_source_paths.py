#!/usr/bin/env python3
"""把 ``page_object_contract.yaml`` 的 App 相对路径收敛回磁盘真相。

覆盖 ``source_path`` 与 ``route_registration_evidence`` / ``mount_evidence``：
端侧 ``quwoquan_app/lib`` 已从「技术角色分层」收敛为
``lib/service/<service>/<context>/<object>/<layer>/`` 的对象树。页面文件每被搬走一次，
``page_object_contract.yaml`` 的路径就失效一条：

- ``quwoquan_app/scripts/runtime/page/verify_page_object_contract.py`` 直接 BLOCK。
- ``quwoquan_ops/gate/object_path_map.py`` 的 ``page_object_contract`` 认领
  **无声失效**，退化成别名启发式或 ``context_only``。

本工具是该 YAML 的唯一写入口：搬迁流不要手改契约，跑一次本工具即可。
定位不唯一时一律报错退出，绝不代替业务猜测。

用法::

    # 只检测，不落盘（CI / gate 用）
    python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --check

    # 搬完页面后一条命令收敛 + 门禁分类（运行报告落 .qwq_output，可删可重建）
    python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --with-gate

    # 把需人工裁决的 REVIEW 项也视为失败
    python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --check --fail-on-review

退出码：``0`` 无待处理 drift；``1`` 存在需人工裁决项；``2`` 工具/契约自身错误。
``--with-gate`` 只读消费门禁输出用于分类，退出码不受门禁影响，也绝不修改门禁。

实现单轨落在同目录 ``page_object_source_paths/`` 包内；本文件只是稳定 CLI
入口，并为既有消费者 re-export 包 API（含私有 ``_`` 符号）。
"""
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md

from __future__ import annotations

import sys
from pathlib import Path

# 仓库禁止源码树出现 __pycache__；入口可能被无 -B 的方式直接执行，
# 导入实现包前先关闭字节码写入。
sys.dont_write_bytecode = True

_PACKAGE_PARENT = str(Path(__file__).resolve().parent)
if _PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, _PACKAGE_PARENT)

from page_object_source_paths import (  # noqa: E402
    APP_DIR_NAME,
    CONTRACT_REL,
    EVIDENCE_FIELDS,
    GATE_FAILURE_CLASSES,
    GIT_RENAME_MAX_HOPS,
    REPORT_DIR_NAME,
    REPOSITORY_ROOT,
    ContractError,
    ManualDecision,
    ReviewFinding,
    SourcePathFix,
    SyncReport,
    _atomic_write,
    _consumed_dart_identifiers,
    _consumed_public_behavior_symbols,
    _dart_library_text,
    _dart_source_tokens,
    _default_report_dir,
    _entry_widget,
    _expected_document,
    _field_region,
    _importable,
    _is_application_public_path,
    _load_disk_scan_paths,
    _load_shape_resolver,
    _looks_like_object_presentation,
    _matching_paren_end,
    _page_block_range,
    _page_library_evidence,
    _parse_dart_uri_directives,
    _public_behavior_symbols,
    _public_instance_behavior_symbols,
    _public_named_declarations,
    _rename_target_in_commit,
    _resolve_app_dart_uri,
    _run_git,
    classify_gate_failures,
    contract_pages,
    defines_entry_widget,
    git_rename_target,
    lib_basename_candidates,
    load_contract,
    main,
    object_presentation_participant_findings,
    page_scan_set_findings,
    references_widget,
    render_markdown_report,
    render_report,
    replace_page_path,
    resolve_moved_path,
    run_page_quality_gates,
    sync,
    write_run_report,
)

if __name__ == "__main__":
    raise SystemExit(main())
