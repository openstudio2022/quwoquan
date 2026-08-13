#!/usr/bin/env python3
"""阻断页面到对象、路由、Surface 与 Query Slice 的契约漂移。

触发范围：页面扫描集、共享路由/Surface、生产 Router 或页面对象契约发生变化。
阻断条件：页面漏登、引用/路径漂移、不可达路由、弱类型展示、无效对象/父级等。
修复方式：回到 ``metadata/_shared/page_object_contract.yaml`` 及其真实装配证据修正，
不得在质量矩阵或 typing inventory 维护第二套对象绑定。脚本已接入 ``make
verify-app-page-horizontal-quality`` 与仓库 App gate。

实现单轨落在 ``page_object_contract/`` 包内（context / dart_scan /
mount_rules / metadata_sources / cli）；本文件是稳定 CLI 入口，并为既有
消费者（page object mount 合约测试等）re-export 包 API。测试对扫描根
``APP`` 的 monkeypatch 目标是 ``dart_scan`` 子模块（本入口以属性暴露）。
"""
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from page_object_contract import *  # noqa: E402,F401,F403
from page_object_contract import (  # noqa: E402,F401
    APP,
    AUTH_REQUIREMENTS,
    BANNED_PRESENTATION_RE,
    CONTRACT,
    DART_IMPORT_STATEMENT_RE,
    DART_PART_OF_RE,
    DART_PART_RE,
    DART_URI_LITERAL_RE,
    GENERATED_ROUTES,
    GENERATED_SURFACES,
    LOCAL_SLICE_RE,
    METADATA,
    NAVIGATION_DIR,
    PAGE_ID_RE,
    PAGE_KINDS,
    PLATFORM_CAPABILITIES,
    ROOT,
    ROUTER_DIR,
    ROUTER_EVIDENCE_PREFIXES,
    ROUTES,
    SERVICES,
    SOURCE_PATH_RE,
    SURFACES,
    TYPE_NAME_RE,
    _all_dart_type_tokens,
    _dart_code_without_comments_and_strings,
    _dart_library_owner,
    _dart_library_parts,
    _dart_library_text,
    _declared_parent_mount_closures,
    _direct_app_dart_closure,
    _direct_app_import_libraries,
    _direct_constructor_sites,
    _effective_route_ids,
    _generated_route_paths,
    _is_route_less_root_shell,
    _load_yaml,
    _metadata_objects_and_slices,
    _mounts_entry_widget,
    _nonempty_string,
    _page_source_ownership_errors,
    _parent_mount_evidence_errors,
    _resolve_app_dart_uri,
    _root_shell_mount_errors,
    _root_shell_surface_owner_errors,
    _router_sources,
    _snake_case,
    _source_experience_owners,
    _string_list,
    _surface_route_membership_error,
    _validate_owner_bindings,
    _validate_parent_graph,
    context,
    dart_scan,
    main,
    yaml,
)

if __name__ == "__main__":
    raise SystemExit(main())
