#!/usr/bin/env python3
"""交集 gamma-local remote smoke 一键执行器（R-IX08 凭证收口）。

content-service 强制 verified principal（JWT），smoke 测试自身不签发凭证。
本脚本先从 metadata fixture 幂等应用交集社交图、对象卡和推荐频道 seed，再经
canonical 本地签发通道（`quwoquan_ops.cli.lib.local_environment_auth`，
user-service acceptance-session 本地 go run，token 只存于签发进程内存与
测试子进程环境，不落 argv/报告/日志文件）签出 acceptance token，最后运行
`test/api_integration/ui/intersection/intersection_remote_smoke__api_integration_test.dart`。

前置：gamma-local 栈 content-service healthy（默认 http://127.0.0.1:19220）。
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
SEED_BOX_ROOT = REPO_ROOT / "quwoquan_service" / "services" / "seed-box" / "scripts"
REQUIRED_SEEDS = (
    (
        "content-social-graph-seed-report.json",
        SEED_BOX_ROOT / "apply_content_social_graph_seed.py",
        True,
    ),
    (
        "content-object-cards-seed-report.json",
        SEED_BOX_ROOT / "apply_content_object_cards_seed.py",
        True,
    ),
    (
        "content-moment-channel-seed-report.json",
        SEED_BOX_ROOT / "apply_content_moment_channel_seed.py",
        False,
    ),
)


def _apply_required_seeds(viewer_id: str, report_root: Path) -> int:
    report_root.mkdir(parents=True, exist_ok=True)
    for report_name, script, requires_viewer in REQUIRED_SEEDS:
        command = [
            sys.executable,
            str(script),
            "--report",
            str(report_root / report_name),
        ]
        if requires_viewer:
            command.extend(["--viewer-id", viewer_id])
        completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if completed.returncode != 0:
            print(
                f"[intersection-smoke] seed failed: {script.name} "
                f"(exit={completed.returncode})",
                file=sys.stderr,
            )
            return completed.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:19220",
        help="content-service 直连地址（默认 gamma-local 19220）",
    )
    parser.add_argument(
        "--viewer-id",
        default="fixture_user_current",
        help="acceptance viewer（须与交集 seed 的 viewer 一致）",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT))
    from quwoquan_ops.cli.lib.local_environment_auth import (
        open_local_acceptance_session,
    )
    from quwoquan_ops.cli.lib.output_paths import env_run_dir

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
    seed_status = _apply_required_seeds(args.viewer_id, report_root)
    if seed_status != 0:
        return seed_status

    session = open_local_acceptance_session(
        args.base_url,
        environment="gamma",
        target_name="gamma-local",
        subject=args.viewer_id,
    )
    print(
        f"[intersection-smoke] acceptance session ready: "
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
