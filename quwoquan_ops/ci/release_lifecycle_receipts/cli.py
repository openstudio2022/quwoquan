"""release lifecycle receipts 的 CLI 参数与主入口。

原单文件 ``render_release_lifecycle_receipts.py`` 拆分出的 CLI 子模块；
``render_*`` 与 ``validate_manifest`` 均为薄入口模块属性（可被测试
monkeypatch），消费点经 ``_pkg.`` 访问。``--help`` 文案沿用薄入口 docstring。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

import quwoquan_ops.ci.render_release_lifecycle_receipts as _pkg

from .receipt_codec import _load_json, _parse_binding


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=_pkg.__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    readiness = subparsers.add_parser("rollback-readiness")
    readiness.add_argument("--manifest", required=True, type=Path)
    readiness.add_argument("--service", required=True)
    readiness.add_argument("--from-candidate-digest", required=True)
    readiness.add_argument("--current-ledger-readback", required=True, type=Path)
    readiness.add_argument("--rollback-drill-readback", required=True, type=Path)
    readiness.add_argument("--backup-validation", required=True, type=Path)
    readiness.add_argument("--archive-prefix", required=True)
    readiness.add_argument(
        "--rollback-drill-max-age-seconds", required=True, type=int
    )
    readiness.add_argument("--output", required=True, type=Path)

    outcome = subparsers.add_parser("prod-outcome")
    outcome.add_argument("--manifest", required=True, type=Path)
    outcome.add_argument("--service", required=True)
    outcome.add_argument("--from-candidate-digest", required=True)
    outcome.add_argument("--stage-report", action="append", default=[])
    outcome.add_argument("--stage-readback", action="append", default=[])
    outcome.add_argument("--archive-prefix", required=True)
    outcome.add_argument("--hard-deadline-epoch", required=True, type=int)
    outcome.add_argument("--rollback-budget-seconds", required=True, type=int)
    outcome.add_argument("--output-dir", required=True, type=Path)

    soak = subparsers.add_parser("prod-soak-request")
    soak.add_argument("--manifest", required=True, type=Path)
    soak.add_argument("--service", required=True)
    soak.add_argument("--full-readback", required=True, type=Path)
    soak.add_argument("--slo-observation", required=True, type=Path)
    soak.add_argument("--alerts-observation", required=True, type=Path)
    soak.add_argument("--health-report", required=True, type=Path)
    soak.add_argument("--credential-evidence", required=True, type=Path)
    soak.add_argument("--credential-policy", required=True, type=Path)
    soak.add_argument("--governance-receipt", required=True, type=Path)
    soak.add_argument("--soak-policy", required=True, type=Path)
    soak.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest = _load_json(args.manifest, "ReleaseEvidenceManifest")
        if args.command == "rollback-readiness":
            result = _pkg.render_rollback_readiness(
                manifest=manifest,
                service=args.service,
                from_candidate_digest=args.from_candidate_digest,
                current_ledger_path=args.current_ledger_readback,
                current_ledger=_load_json(
                    args.current_ledger_readback, "current hosted ledger"
                ),
                rollback_drill_path=args.rollback_drill_readback,
                rollback_drill=_load_json(
                    args.rollback_drill_readback, "rollback drill readback"
                ),
                backup_validation_path=args.backup_validation,
                backup_validation=_load_json(
                    args.backup_validation, "backup recovery validation"
                ),
                archive_prefix=args.archive_prefix,
                rollback_drill_max_age_seconds=args.rollback_drill_max_age_seconds,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        elif args.command == "prod-outcome":
            report_paths = _parse_binding(args.stage_report, "stage report")
            readback_paths = _parse_binding(args.stage_readback, "stage readback")
            result = _pkg.render_prod_outcome(
                manifest=manifest,
                service=args.service,
                from_candidate_digest=args.from_candidate_digest,
                reports={
                    stage: (path, _load_json(path, f"{stage} report"))
                    for stage, path in report_paths.items()
                },
                readbacks={
                    stage: (path, _load_json(path, f"{stage} readback"))
                    for stage, path in readback_paths.items()
                },
                archive_prefix=args.archive_prefix,
                hard_deadline_epoch=args.hard_deadline_epoch,
                rollback_budget_seconds=args.rollback_budget_seconds,
            )
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for key, filename in (
                ("environment", "prod.json"),
                ("rollout", "rollout.json"),
                ("rollback", "rollback.json"),
            ):
                (args.output_dir / filename).write_text(
                    json.dumps(
                        result[key], ensure_ascii=False, indent=2, sort_keys=True
                    )
                    + "\n",
                    encoding="utf-8",
                )
        else:
            result = _pkg.render_prod_soak_request(
                manifest=manifest,
                service=args.service,
                full_readback=_load_json(args.full_readback, "full hosted readback"),
                slo=_load_json(args.slo_observation, "Prometheus soak observation"),
                slo_path=args.slo_observation,
                alerts=_load_json(
                    args.alerts_observation, "Alertmanager soak observation"
                ),
                alerts_path=args.alerts_observation,
                health=_load_json(args.health_report, "prod health report"),
                health_path=args.health_report,
                credential_evidence=_load_json(
                    args.credential_evidence, "prod credential evidence"
                ),
                credential_policy=yaml.safe_load(
                    args.credential_policy.read_text(encoding="utf-8")
                ),
                credential_policy_path=args.credential_policy,
                governance=_load_json(
                    args.governance_receipt, "release governance receipt"
                ),
                governance_path=args.governance_receipt,
                soak_policy=yaml.safe_load(
                    args.soak_policy.read_text(encoding="utf-8")
                ),
                soak_policy_path=args.soak_policy,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"render_release_lifecycle_receipts: FAIL: {error}")
        return 2
