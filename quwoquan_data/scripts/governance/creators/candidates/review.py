"""Apply auditable human review records to isolated governance candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import RUNTIME_ROOT  # noqa: E402
from governance.creators.candidates.store import CandidateRepository  # noqa: E402
from governance.creators.candidates.state import STATUSES  # noqa: E402

DEFAULT_GOVERNANCE_ROOT = RUNTIME_ROOT / "governance"


def load_review_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"review file not found: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("reviews")
        if not isinstance(rows, list):
            raise ValueError(f"{path}: expected a JSON list or {{\"reviews\": [...]}}")
        return [dict(row) for row in rows]

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: expected object")
        rows.append(row)
    return rows


def apply_review_rows(
    repository: CandidateRepository,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("actorType") or "human") != "human":
            raise ValueError("candidate review actorType must be human")
        output.append(
            repository.review(
                str(row.get("candidateId") or "").strip(),
                decision=str(row.get("decision") or "").strip(),
                reviewer=str(row.get("reviewer") or "").strip(),
                decision_id=str(row.get("decisionId") or "").strip(),
                reason=str(row.get("reason") or ""),
                reviewed_at=str(row.get("reviewedAt") or "").strip() or None,
            )
        )
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="候选治理人工审核 checkpoint")
    parser.add_argument("--root", type=Path, default=DEFAULT_GOVERNANCE_ROOT)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--reviews", type=Path, help="人工审核 JSON/NDJSON")
    action.add_argument("--list-status", choices=sorted(STATUSES), help="列出指定状态候选")
    parser.add_argument("--kind", help="列表时按候选 kind 过滤")
    args = parser.parse_args(argv)

    repository = CandidateRepository(args.root)
    if args.reviews:
        reviewed = apply_review_rows(repository, load_review_rows(args.reviews))
        print(f"已应用人工审核: {len(reviewed)}")
        return 0

    candidates = repository.list_candidates(status=args.list_status, kind=args.kind)
    for candidate in candidates:
        print(
            json.dumps(
                {
                    "candidateId": candidate.get("candidateId"),
                    "kind": candidate.get("kind"),
                    "naturalKey": candidate.get("naturalKey"),
                    "status": candidate.get("status"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    print(f"候选数: {len(candidates)}", file=sys.stderr)
    return 0
