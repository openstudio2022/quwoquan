"""Exit gate for download command."""
from __future__ import annotations

from _common.paths import batch_command_root
from _common.io import read_ndjson


def gate_download(task_id: str, batch_id: str) -> list[str]:
    """Check download exit criteria: each entity has >= 2 retained sources from different platforms."""
    issues = []
    sources_dir = batch_command_root(task_id, batch_id, "download") / "sources"

    if not sources_dir.exists():
        issues.append("No sources directory")
        return issues

    entity_dirs = [d for d in sources_dir.iterdir() if d.is_dir()]
    if not entity_dirs:
        issues.append("No entity source directories")

    for ent_dir in entity_dirs:
        source_dirs = [d for d in ent_dir.iterdir() if d.is_dir()]
        md_count = sum(1 for sd in source_dirs if (sd / "source.md").exists())
        if md_count < 2:
            issues.append(f"{ent_dir.name}: only {md_count} sources (need >= 2)")

    return issues
