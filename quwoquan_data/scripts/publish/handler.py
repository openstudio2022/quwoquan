"""data publish — assemble release package from task outputs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common.paths import release_root, RELEASE_ROOT
from publish.assemble import assemble_release
from publish.gate import gate_publish


def _push_to_service(release_dir: Path, service_url: str) -> bool:
    """Push release NDJSON to the content service bulk import endpoint."""
    try:
        import urllib.request
        import json
    except ImportError:
        print("[publish] urllib not available for push", file=sys.stderr)
        return False

    entities_path = release_dir / "entities" / "entities.ndjson"
    if not entities_path.exists():
        print("[publish] No entities NDJSON to push", file=sys.stderr)
        return False

    url = service_url.rstrip("/") + "/admin/import"
    with open(entities_path, "rb") as f:
        req = urllib.request.Request(
            url,
            data=f.read(),
            headers={"Content-Type": "application/x-ndjson"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read())
                print(f"[publish] Push result: {body}", file=sys.stderr)
                return True
        except Exception as e:
            print(f"[publish] Push failed: {e}", file=sys.stderr)
            return False


def handle_publish(args: argparse.Namespace) -> None:
    """Orchestrate publish: assemble → gate → package → (optional) push."""
    task_id = args.task
    release_id = args.release_id

    print(f"[publish] Task: {task_id} → Release: {release_id}")
    print(f"[publish] Steps: assemble → gate → package")

    root = assemble_release(task_id, release_id)
    print(f"[publish] Assembled to: {root}")

    issues = gate_publish(release_id)
    if issues:
        print(f"[publish] Gate FAILED ({len(issues)} issues):", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(1)

    print(f"[publish] Gate PASSED")

    if getattr(args, "push_to_service", None):
        print(f"[publish] Pushing to service: {args.push_to_service}")
        ok = _push_to_service(root, args.push_to_service)
        if not ok:
            print("[publish] Push failed, but release is assembled", file=sys.stderr)
        else:
            print("[publish] Push succeeded")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("publish", help="Assemble release package")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--release-id", required=True, help="Release identifier")
    p.add_argument(
        "--push-to-service",
        default=None,
        help="Service URL to push release via bulk import API (e.g. http://localhost:18080)",
    )
    p.set_defaults(handler=handle_publish)
