"""Argparse surface for Ops App UAT evidence commands."""

from __future__ import annotations

import argparse

from quwoquan_ops.cli.lib.environment_acceptance_fact import ACCEPTANCE_PROFILES


def _add_boolean(
    parser: argparse.ArgumentParser, name: str, *, destination: str
) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(name, dest=destination, action="store_true")
    group.add_argument(
        f"--no-{name.removeprefix('--')}", dest=destination, action="store_false"
    )


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    bind = subparsers.add_parser(
        "app-uat-target-bind",
        help="从显式 ReleaseUatSamplePlan/CAS/readback/candidate/device refs create-once TargetUatBinding",
    )
    for name in (
        "evidence-root",
        "binding-output-root",
        "runtime-binding-ref",
        "runtime-binding-digest",
        "launch-binding-ref",
        "launch-binding-digest",
        "sample-plan-ref",
        "sample-plan-digest",
        "active-cas-ref",
        "active-cas-digest",
        "readback-ref",
        "readback-digest",
        "artifact-class",
        "build-mode",
        "build-profile",
        "provider-identity",
        "provider-class",
        "provider-type",
        "provider-conformance-ref",
        "provider-conformance-digest",
        "device-identity",
        "device-class",
        "runner-identity",
        "runner-source-path",
        "runner-digest",
        "profile",
        "created-at",
    ):
        bind.add_argument(f"--{name}", required=True)
    _add_boolean(bind, "--provider-registered", destination="provider_registered")
    _add_boolean(bind, "--device-registered", destination="device_registered")
    _add_boolean(bind, "--runner-registered", destination="runner_registered")
    _add_boolean(bind, "--non-promotable", destination="non_promotable")

    bundle = subparsers.add_parser(
        "app-uat-bundle",
        help="从显式 plan/binding/raw refs 构建无 verdict 的只读诊断投影",
    )
    for name in (
        "evidence-root",
        "sample-plan-ref",
        "sample-plan-digest",
        "output-ref",
        "generated-at",
    ):
        bundle.add_argument(f"--{name}", required=True)
    bundle.add_argument("--target-binding", action="append", required=True)
    bundle.add_argument("--raw-result", action="append", required=True)

    append = subparsers.add_parser(
        "environment-acceptance-append",
        help="校验全部 direct raw/readiness/predecessor authority 后 create-once 追加 acceptance fact",
    )
    for name in (
        "evidence-root",
        "acceptance-root",
        "environment",
        "target",
        "release-id",
        "release-digest",
        "import-run-id",
        "verify-run-id",
        "sample-plan-ref",
        "sample-plan-digest",
        "data-readiness-ref",
        "data-readiness-digest",
        "created-at",
        "source-fingerprint",
    ):
        append.add_argument(f"--{name}", required=True)
    append.add_argument("--manifest-digest", default="")
    append.add_argument(
        "--acceptance-profile", choices=ACCEPTANCE_PROFILES, required=True
    )
    for name in (
        "consumer-health-ref",
        "consumer-health-digest",
        "active-cas-ref",
        "active-cas-digest",
        "active-cas-readback-ref",
        "active-cas-readback-digest",
        "lifecycle-exit-ref",
        "lifecycle-exit-digest",
        "provider-readiness-ref",
        "provider-readiness-digest",
        "observability-readiness-ref",
        "observability-readiness-digest",
        "rollback-readiness-ref",
        "rollback-readiness-digest",
    ):
        append.add_argument(f"--{name}", default="")
    append.add_argument("--target-binding", action="append", default=[])
    append.add_argument("--required-raw", action="append", default=[])
    append.add_argument("--required-profile", action="append", default=[])
    append.add_argument("--lease-revocation", action="append", default=[])
    append.add_argument("--lock-release", action="append", default=[])
    append.add_argument("--gc-protection", action="append", default=[])
    append.add_argument("--prod-release-facts", default="")
    append.add_argument("--predecessor-ref", default="")
    append.add_argument("--predecessor-digest", default="")
    append.add_argument("--predecessor-fact-id", default="")
