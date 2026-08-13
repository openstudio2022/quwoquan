"""页面对象契约门禁实现包。

唯一稳定入口是 ``quwoquan_app/scripts/runtime/page/verify_page_object_contract.py``
（薄壳 re-export）；本包按职责切分：

- ``context``：路径常量、正则、YAML/字符串小工具。
- ``dart_scan``：Dart library/part/import 扫描（持有可 monkeypatch 的 ``APP``）。
- ``mount_rules``：parent/mount evidence 与 root shell 判定规则。
- ``metadata_sources``：metadata 对象/切片、Router 源码与 owner/parent 图校验。
- ``cli``：主流程 ``main``。
"""
from __future__ import annotations

from . import context, dart_scan  # noqa: F401
from .cli import main  # noqa: F401
from .context import (  # noqa: F401
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
    _load_yaml,
    _nonempty_string,
    _snake_case,
    _string_list,
    yaml,
)
from .dart_scan import (  # noqa: F401
    _all_dart_type_tokens,
    _dart_code_without_comments_and_strings,
    _dart_library_owner,
    _dart_library_parts,
    _dart_library_text,
    _direct_app_dart_closure,
    _direct_app_import_libraries,
    _direct_constructor_sites,
    _mounts_entry_widget,
    _resolve_app_dart_uri,
)
from .metadata_sources import (  # noqa: F401
    _effective_route_ids,
    _generated_route_paths,
    _metadata_objects_and_slices,
    _router_sources,
    _source_experience_owners,
    _validate_owner_bindings,
    _validate_parent_graph,
)
from .mount_rules import (  # noqa: F401
    _declared_parent_mount_closures,
    _is_route_less_root_shell,
    _page_source_ownership_errors,
    _parent_mount_evidence_errors,
    _root_shell_mount_errors,
    _root_shell_surface_owner_errors,
    _surface_route_membership_error,
)
