"""Revalidate one private dependency projection after an external build command."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection_verify import (
    load_dependency_projection_cas_readback,
    revalidate_dependency_projection_cas,
    write_dependency_projection_cas_readback,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection-root", required=True, type=Path)
    parser.add_argument("--expectation", required=True, type=Path)
    parser.add_argument("--expectation-digest", required=True)
    parser.add_argument("--readback-output", required=True, type=Path)
    parser.add_argument(
        "--phase",
        choices=("prebuild", "postbuild"),
        default="postbuild",
    )
    parser.add_argument(
        "--environment-owner",
        choices=("production", "patrol"),
        default="production",
    )
    return parser


def _shell_exports(*, phase: str, path: Path, digest: str) -> str:
    label = phase.upper()
    return "\n".join(
        (
            f"export QWQ_DEPENDENCY_PROJECTION_{label}_READBACK_REF="
            + shlex.quote(str(path)),
            f"export QWQ_DEPENDENCY_PROJECTION_{label}_READBACK_DIGEST="
            + shlex.quote(digest),
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        readback = revalidate_dependency_projection_cas(
            projection_root=args.projection_root,
            evidence_path=args.expectation,
            expected_digest=args.expectation_digest,
            command_environment_owner=args.environment_owner,
            command_environment=dict(os.environ),
        )
        evidence = write_dependency_projection_cas_readback(
            readback=readback,
            evidence_path=args.readback_output,
        )
        loaded = load_dependency_projection_cas_readback(
            evidence_path=evidence.evidence_path,
            expected_digest=evidence.evidence_digest,
            expected_expectation_digest=args.expectation_digest,
        )
        if loaded.manifest != evidence.manifest:
            raise ValueError(
                "APP.DEPENDENCY.projection_expectation_invalid: "
                "post-build readback differs after reload"
            )
        print(
            _shell_exports(
                phase=args.phase,
                path=evidence.evidence_path,
                digest=evidence.evidence_digest,
            )
        )
        return 0
    except (OSError, TypeError, ValueError) as error:
        detail = str(error) or type(error).__name__
        if not detail.startswith("APP.DEPENDENCY"):
            detail = f"APP.DEPENDENCY.projection_expectation_invalid: {detail}"
        print(detail, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
