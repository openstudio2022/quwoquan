"""CLI 参数处理与全域校验编排的 main 入口。"""

from __future__ import annotations

import sys

from test_directory_layout_lib import (
    APP_ROOT,
    CONTROL_PLANE_ROOT,
    DATA_ROOT,
    OPS_TEST_ROOT,
    SERVICE_DOMAIN_ROOT,
    SERVICE_ROOT,
)

from .app_layout import verify_app
from .app_support import app_patrol_user_acceptance_targets
from .common import Failures, rel, verify_no_generated_bridges
from .data import verify_data
from .ops import verify_ops
from .service import (
    verify_all_canonical_files_recognized,
    verify_runtime,
    verify_service,
    verify_service_domain_cross_cutting,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        if argv != ["--list-patrol-user-acceptance-targets"]:
            print(f"[verify] FAIL: unsupported arguments: {' '.join(argv)}", file=sys.stderr)
            return 2
        for path in app_patrol_user_acceptance_targets():
            print(rel(path))
        return 0
    failures = Failures()
    verify_app(failures)
    verify_data(failures)
    verify_ops(failures)
    verify_service(failures)
    verify_runtime(failures)
    verify_service_domain_cross_cutting(failures)
    verify_no_generated_bridges(APP_ROOT, failures)
    verify_no_generated_bridges(DATA_ROOT, failures)
    verify_no_generated_bridges(OPS_TEST_ROOT, failures)
    verify_no_generated_bridges(SERVICE_ROOT, failures)
    verify_no_generated_bridges(CONTROL_PLANE_ROOT, failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "internal", failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "runtime", failures)
    verify_no_generated_bridges(SERVICE_DOMAIN_ROOT / "tools", failures)
    verify_all_canonical_files_recognized(failures)
    return failures.exit_code()
