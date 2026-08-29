#!/usr/bin/env python3
"""交集 gamma-local remote smoke 一键执行器（R-IX08 凭证收口）。

Owner: tools/gamma（人工烟测工具，非领域 gate，非 App environments 副本）。
跨环境正式验收 runner 归 Ops service_ops；本文件保持 tools 口袋，禁止迁入
scripts/service/ 或 *_service/environments/。

content-service 强制 verified principal（JWT），smoke 测试自身不签发凭证。
本脚本从 canonical Data readiness/import receipt 选择 release-bound author，
再经 candidate-bound 非生产身份池和公开 OTP/LoginWithPhone 恢复真实测试账号，
token 只存于测试进程环境，不落 argv/报告/日志文件，最后运行
`test/api_integration/service/content_service/content/intersection_visit_state/intersection_remote_smoke__api_integration_test.dart`。

前置：gamma-local 栈 content-service healthy，并显式传入 topology
`origins.contentService`。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT

SMOKE_TEST = (
    "test/api_integration/service/content_service/content/intersection_visit_state/"
    "intersection_remote_smoke__api_integration_test.dart"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        required=True,
        help="由 topology target origins.contentService 投影的直连地址",
    )
    parser.add_argument(
        "--release-readiness",
        default=os.environ.get("DATA_RELEASE_READINESS_RECEIPT", "").strip(),
        help=(
            "canonical Data release-readiness.json；缺失时返回 GATE_BLOCK，"
            "不允许独立 viewer/seed identity"
        ),
    )
    args = parser.parse_args()

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from quwoquan_ops.cli.lib.output_paths import env_run_dir
    from quwoquan_ops.cli.lib.release_video_delivery import (
        ReleaseVideoDeliveryError,
        load_release_content_identity,
        resolve_readiness_path,
    )

    try:
        identity = load_release_content_identity(
            resolve_readiness_path(args.release_readiness),
            expected_environment="gamma",
        )
        discovery_query = next(
            (
                query
                for query in identity["receipt"].get("feedQueries") or []
                if isinstance(query, dict) and query.get("name") == "discovery_work"
            ),
            None,
        )
        discovery_post_ids = {
            str(value).strip()
            for value in (discovery_query or {}).get("matchedPostIds") or []
            if str(value).strip()
        }
        release_authors = sorted(
            {
                str(binding.get("authorId") or "").strip()
                for binding in identity["postBindings"]
                if binding.get("postId") in discovery_post_ids
                and str(binding.get("authorId") or "").strip()
            }
        )
        if not release_authors:
            raise ReleaseVideoDeliveryError(
                "canonical Data readiness/import receipt has no release-bound discovery author"
            )
    except (ReleaseVideoDeliveryError, ValueError) as exc:
        print(f"[intersection-smoke] GATE_BLOCK: {exc}", file=sys.stderr)
        return 2

    configured_run_root = os.environ.get("QWQ_RUN_ROOT", "").strip()
    report_root = (
        Path(configured_run_root)
        if configured_run_root
        else env_run_dir(
            "gamma",
            "intersection-remote-smoke",
            target="gamma-local",
        )
    )
    report_root.mkdir(parents=True, exist_ok=True)

    access_token = os.environ.get("QWQ_TEST_DATA_ACCESS_TOKEN", "").strip()
    owner_id = os.environ.get("QWQ_TEST_DATA_OWNER_ID", "").strip()
    persona_id = os.environ.get("QWQ_TEST_DATA_PERSONA_ID", "").strip()
    if not access_token or not owner_id or not persona_id:
        print(
            "[intersection-smoke] GATE_BLOCK: typed test-data actor binding is missing",
            file=sys.stderr,
        )
        return 2
    print(
        f"[intersection-smoke] acceptance session ready: "
        f"release={identity['releaseId']} import={identity['importRunId']} "
        f"owner={owner_id} persona={persona_id}"
    )

    command = [
        "flutter",
        "test",
        SMOKE_TEST,
        "--no-pub",
        "--dart-define=RUN_LOCAL_GAMMA_REMOTE_SMOKE=true",
        f"--dart-define=LOCAL_GAMMA_CONTENT_BASE_URL={args.base_url}",
        f"--dart-define=APP_CURRENT_USER_ID={persona_id}",
    ]
    child_environment = os.environ.copy()
    child_environment["LOCAL_GAMMA_ACCEPTANCE_TOKEN"] = access_token
    completed = subprocess.run(
        command,
        cwd=APP_ROOT,
        env=child_environment,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
