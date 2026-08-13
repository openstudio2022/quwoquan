"""Compile object-declared external capabilities and environment bindings.

There is deliberately no provider or capability registry. Capability identity,
ports and conformance semantics come from object ``operations.yaml`` files;
environment selection comes from each service's environment config;
implementation paths are discovered from source. The compiled receipt and
generated Go descriptors are derived artifacts only.

实现单轨落在 ``external_provider_governance_lib/`` 包内（constants / models /
derived_sources / validation / compilation / go_descriptors）；本文件是稳定
模块与 CLI 入口：

- ``from quwoquan_ops.cli.lib import external_provider_governance`` 与
  ``from quwoquan_ops.cli.lib.external_provider_governance import X`` 的全部
  公开符号与被测私有符号由这里 re-export；
- ``python3 quwoquan_ops/cli/lib/external_provider_governance.py --go-bindings``
  仍是 quwoquan_service Makefile 消费的唯一 codegen CLI（该路径是
  ``make``/CI 的契约，不可移动）。

包内实现对可被测试 patch 的符号（``SERVICES_ROOT`` / ``_service_roots``）
一律经由本模块命名空间在调用时读取，保持与拆分前单文件相同的
mock.patch 语义。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

if __name__ == "__main__":
    # 以脚本方式执行时，包内子模块的 `import quwoquan_ops.cli.lib.
    # external_provider_governance` 必须解析到当前模块对象，才能与 import
    # 形态共享同一命名空间（含 mock.patch 语义），且避免同一文件被二次加载。
    sys.modules.setdefault(
        "quwoquan_ops.cli.lib.external_provider_governance", sys.modules[__name__]
    )

from quwoquan_ops.cli.lib.external_provider_governance_lib.constants import (  # noqa: E402,F401
    ADAPTER_RE,
    CAPABILITY_RE,
    ENV_KEY_RE,
    ENVIRONMENTS,
    FIRST_PARTY_AUTHORITY_ADAPTER,
    LOCAL_SUBSTITUTE_MARKERS,
    MESSAGE_TRANSPORT_CAPABILITY_ID,
    MESSAGE_TRANSPORT_REMOTE_UAT_PREREQUISITE_SCHEMA,
    MESSAGE_TRANSPORT_REQUIRED_METRICS,
    NONPROD_ENVIRONMENTS,
    PLATFORM_LOCAL_ADAPTERS,
    READY_IMPLEMENTATION_STATUSES,
    RELEASE_ADAPTER_ENVIRONMENTS,
    ROOT,
    SERVICES_ROOT,
    STATES,
    is_local_substitute_adapter,
    is_prod_forbidden_adapter,
    requires_provider_conformance,
)
from quwoquan_ops.cli.lib.external_provider_governance_lib.models import (  # noqa: E402,F401
    ProviderGovernanceIssue,
)
from quwoquan_ops.cli.lib.external_provider_governance_lib.derived_sources import (  # noqa: E402,F401
    _dependency_role,
    _descriptor_output,
    _find_adapter_source,
    _load_yaml,
    _operation_sources,
    _root_record,
    _service_roots,
    _source_owner,
    load_bindings,
    load_conformance_manifest,
    load_registry,
)
from quwoquan_ops.cli.lib.external_provider_governance_lib.validation import (  # noqa: E402,F401
    _binding_record,
    _service_binding_scope,
    binding_issues,
    conformance_manifest_issues,
    registry_issues,
)
from quwoquan_ops.cli.lib.external_provider_governance_lib.compilation import (  # noqa: E402,F401
    compile_governance,
    load_and_compile,
)
from quwoquan_ops.cli.lib.external_provider_governance_lib.go_descriptors import (  # noqa: E402,F401
    _descriptor_roots,
    composition_issues,
    render_go_bindings,
    write_go_bindings,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go-bindings", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    registry = load_registry()
    compiled, issues = compile_governance(
        registry,
        load_bindings(),
        load_conformance_manifest(),
    )
    if args.check and not args.go_bindings:
        parser.error("--check requires --go-bindings")
    if args.go_bindings:
        issues = [*issues, *write_go_bindings(registry, compiled, check=args.check)]
    if args.quiet:
        print(
            "external-provider-governance: "
            f"capabilities={compiled['capabilityCount']} "
            f"adapters={compiled['adapterCount']} issues={len(issues)}"
        )
    else:
        print(json.dumps(compiled, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
