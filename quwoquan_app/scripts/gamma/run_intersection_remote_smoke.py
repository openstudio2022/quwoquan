#!/usr/bin/env python3
"""交集 gamma-local remote smoke 一键执行器（R-IX08 凭证收口）。

content-service 强制 verified principal（JWT），smoke 测试自身不签发凭证。
本脚本从 canonical Data readiness/import receipt 选择 release-bound author，
再经 canonical 本地签发通道（`quwoquan_ops.cli.lib.local_environment_auth`，
user-service acceptance-session 本地 go run，token 只存于签发进程内存与
测试子进程环境，不落 argv/报告/日志文件）签出 acceptance token，最后运行
`test/api_integration/ui/intersection/intersection_remote_smoke__api_integration_test.dart`。

前置：gamma-local 栈 content-service healthy，并显式传入 topology
`origins.contentService`。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPO_ROOT / "quwoquan_app"
SMOKE_TEST = (
    "test/api_integration/ui/intersection/"
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

    sys.path.insert(0, str(REPO_ROOT))
    from quwoquan_ops.cli.lib.local_environment_auth import (
        open_local_acceptance_session,
    )
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
        viewer_id = release_authors[0]
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

    session = open_local_acceptance_session(
        args.base_url,
        environment="gamma",
        target_name="gamma-local",
        subject=viewer_id,
    )
    print(
        f"[intersection-smoke] acceptance session ready: "
        f"release={identity['releaseId']} import={identity['importRunId']} "
        f"owner={session.owner_id} persona={session.persona_id}"
    )

    command = [
        "flutter",
        "test",
        SMOKE_TEST,
        "--no-pub",
        "--dart-define=RUN_LOCAL_GAMMA_REMOTE_SMOKE=true",
        f"--dart-define=LOCAL_GAMMA_CONTENT_BASE_URL={args.base_url}",
        f"--dart-define=APP_CURRENT_USER_ID={session.persona_id}",
    ]
    child_environment = os.environ.copy()
    child_environment["LOCAL_GAMMA_ACCEPTANCE_TOKEN"] = session.access_token
    completed = subprocess.run(
        command,
        cwd=APP_ROOT,
        env=child_environment,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
