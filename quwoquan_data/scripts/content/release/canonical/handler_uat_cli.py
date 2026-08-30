"""Argparse bindings for release UAT authority and exit proof commands."""

from __future__ import annotations

import argparse


def register_uat_parsers(
    commands: argparse._SubParsersAction,
    *,
    owner: object,
) -> None:
    sampling_authority = commands.add_parser(
        "project-uat-sampling-authority",
        help=(
            "从 M1000 external strategy 与 product/quality authenticated "
            "readback exact inputs 只读投影 sampling authority"
        ),
    )
    sampling_authority.add_argument("--artifact-root", required=True)
    sampling_authority.add_argument("--release-id", required=True)
    sampling_authority.add_argument("--release-digest", required=True)
    sampling_authority.add_argument("--strategy-ref", required=True)
    sampling_authority.add_argument("--strategy-digest", required=True)
    sampling_authority.add_argument("--product-readback-ref", required=True)
    sampling_authority.add_argument("--product-readback-digest", required=True)
    sampling_authority.add_argument("--quality-readback-ref", required=True)
    sampling_authority.add_argument("--quality-readback-digest", required=True)
    sampling_authority.add_argument(
        "--output",
        help="可选 canonical JSON 目标；仅 create-once 写入，不覆盖已有字节",
    )
    sampling_authority.set_defaults(
        handler=owner.handle_project_uat_sampling_authority
    )

    prove_m1000 = commands.add_parser(
        "prove-m1000-four-env",
        help=(
            "只读校验 M1000 exact/delta、共同冻结 App 抽样与同一不可变包 "
            "Alpha→Beta→Gamma→Prod fail-closed 准出"
        ),
    )
    prove_m1000.add_argument(
        "--request",
        required=True,
        help="显式列出全部 current-candidate exact-byte evidence 的请求 JSON",
    )
    prove_m1000.add_argument(
        "--artifact-root",
        required=True,
        help="请求中所有相对 evidence ref 的只读根目录",
    )
    prove_m1000.set_defaults(handler=owner.handle_m1000_four_environment_proof)


__all__ = ["register_uat_parsers"]
