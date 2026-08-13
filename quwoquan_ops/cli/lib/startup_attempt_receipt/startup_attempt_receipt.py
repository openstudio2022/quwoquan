"""startup attempt receipt 的脚本入口（argparse CLI，逐字搬移）。

保持文件名 ``startup_attempt_receipt.py``：
``quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh`` 按文件路径直接
执行本脚本，且 ``verify_dev_up_cli_surface.py`` 与 dev-up 验收测试按
``startup_attempt_receipt.py`` token 扫描 gamma 脚本。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    # 原单文件为 parents[3]；包形态多一层目录，改为 parents[4]，值仍是仓库根。
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import quwoquan_ops.cli.lib.startup_attempt_receipt as _pkg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--attempt-id", default="")
    parser.add_argument("--status", choices=_pkg.STATUSES, required=True)
    parser.add_argument("--workload", default="")
    parser.add_argument("--compose-project", default="")
    parser.add_argument("--candidate-digest", default="")
    parser.add_argument("--configuration-digest", default="")
    parser.add_argument("--provider-runtime-digest", default="")
    parser.add_argument("--observability-log-sink-digest", default="")
    parser.add_argument("--image-transport-tag", default="")
    parser.add_argument("--image-composition-file", default="")
    parser.add_argument("--run-root", default="")
    parser.add_argument("--failure", default="")
    parser.add_argument("--cleanup-failure", default="")
    args = parser.parse_args()
    image_composition = None
    if args.image_composition_file:
        image_composition = _pkg.load_candidate_oci_image_composition(
            Path(args.image_composition_file),
            expected_environment=args.env,
            expected_target=args.target,
            expected_candidate_digest=args.candidate_digest,
        )
    _pkg.transition_startup_attempt(
        env=args.env,
        target=args.target,
        attempt_id=args.attempt_id,
        status=args.status,
        workload=args.workload,
        compose_project=args.compose_project,
        candidate_digest=args.candidate_digest,
        configuration_digest=args.configuration_digest,
        provider_runtime_digest=args.provider_runtime_digest,
        observability_log_sink_digest=args.observability_log_sink_digest,
        image_transport_tag=args.image_transport_tag,
        image_composition=image_composition,
        run_root=args.run_root,
        failure=args.failure,
        cleanup_failure=args.cleanup_failure,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
