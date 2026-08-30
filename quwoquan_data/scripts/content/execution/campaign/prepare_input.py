"""`prepare-campaign` 结构化重复参数的单一解码边界。"""
from __future__ import annotations

import argparse

from content.execution.campaign.lane import normalize_workloads


def parse_requested_workloads(args: argparse.Namespace) -> dict[str, int] | None:
    rows = tuple(getattr(args, "workload_rows", ()) or ())
    if not rows:
        return None
    parsed: dict[str, int] = {}
    for raw in rows:
        carrier, separator, quota_text = str(raw).partition("=")
        carrier = carrier.strip()
        if not separator or not quota_text.strip():
            raise ValueError("--workload must use CARRIER=QUOTA")
        if carrier in parsed:
            raise ValueError(f"duplicate --workload carrier: {carrier}")
        try:
            quota = int(quota_text)
        except ValueError as exc:
            raise ValueError(f"invalid --workload quota: {raw}") from exc
        parsed[carrier] = quota
    return normalize_workloads(parsed)


def parse_source_selection(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    rows = tuple(getattr(args, "source_selection_rows", ()) or ())
    if not rows:
        raise ValueError(
            "handoff phase requires at least one --source-selection "
            "CARRIER=MODE:PROVIDER[,PROVIDER...]"
        )
    selection: dict[str, dict[str, object]] = {}
    for raw in rows:
        carrier, separator, remainder = str(raw).partition("=")
        carrier = carrier.strip()
        mode, mode_separator, providers_text = remainder.partition(":")
        if not separator or not mode_separator or not carrier:
            raise ValueError(
                f"--source-selection must use CARRIER=MODE:PROVIDER[,...]: {raw}"
            )
        if carrier in selection:
            raise ValueError(f"duplicate --source-selection carrier: {carrier}")
        providers = [item.strip() for item in providers_text.split(",") if item.strip()]
        selection[carrier] = {"mode": mode.strip(), "providers": providers}
    return selection


__all__ = ["parse_requested_workloads", "parse_source_selection"]
