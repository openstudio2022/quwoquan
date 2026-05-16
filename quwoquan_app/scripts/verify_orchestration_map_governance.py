#!/usr/bin/env python3
"""Gate script: Map<String, dynamic> governance in orchestration layer.

Scans orchestration/, phases/, state/, and pipelines/ for raw Map<String, dynamic>
usage. Each occurrence must be annotated with an ASSISTANT_WEAK_TYPE comment or
be in an allowlisted LLM serde boundary. Unannotated occurrences are reported
as BLOCKING.

Run:
    python3 scripts/verify_orchestration_map_governance.py

Exit 0 = pass, exit 1 = violations found.
"""

import os
import re
import sys

SCAN_DIRS = [
    "lib/assistant/orchestration/state",
    "lib/assistant/orchestration/phases",
    "lib/assistant/orchestration/pipelines",
]

ALLOWLIST_FILES = {
    # Core engine: LLM serde boundary — template/message assembly, response parsing
    "assistant_pipeline_engine.dart",
    # Observability: JSON payload construction at serde boundary
    "observability_payload_builder.dart",
    # LLM serde boundary: template/message assembly for model interaction
    "bootstrap_phase.dart",
    "understand_phase.dart",
    "evidence_digest_phase.dart",
    "retrieval_design_phase.dart",
    # Serialization/deserialization layer for persisted session state
    "finalize_runner.dart",
    # Typed DTO with Map fields at LLM serde boundary (documented)
    "synthesis_draft.dart",
}

WEAK_TYPE_ANNOTATION = re.compile(
    r"ASSISTANT_WEAK_TYPE|LLM serde boundary|@Deprecated"
)
MAP_PATTERN = re.compile(r"Map<String,\s*dynamic>")
DOC_COMMENT = re.compile(r"^\s*///?")

BASE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "quwoquan_app")
if not os.path.isdir(BASE_DIR):
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def scan():
    violations = []
    for scan_dir in SCAN_DIRS:
        full_dir = os.path.join(BASE_DIR, scan_dir)
        if not os.path.isdir(full_dir):
            continue
        for fname in sorted(os.listdir(full_dir)):
            if not fname.endswith(".dart"):
                continue
            if fname in ALLOWLIST_FILES:
                continue
            fpath = os.path.join(full_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for i, line in enumerate(lines, start=1):
                if not MAP_PATTERN.search(line):
                    continue
                if DOC_COMMENT.match(line):
                    continue
                context_start = max(0, i - 15)
                context_end = min(len(lines), i + 3)
                context = "".join(lines[context_start:context_end])
                if WEAK_TYPE_ANNOTATION.search(context):
                    continue
                violations.append(f"  {scan_dir}/{fname}:{i}: {line.rstrip()}")
    return violations


def main():
    violations = scan()
    if not violations:
        print("Map<String,dynamic> governance: PASS")
        print(f"  Scanned: {', '.join(SCAN_DIRS)}")
        sys.exit(0)
    print(f"Map<String,dynamic> governance: {len(violations)} violation(s)")
    for v in violations:
        print(v)
    print()
    print("Each Map<String,dynamic> in orchestration/ must either:")
    print("  1. Be in an allowlisted LLM serde boundary file")
    print("  2. Have a nearby ASSISTANT_WEAK_TYPE annotation comment")
    print("  3. Be marked @Deprecated (transitional)")
    sys.exit(1)


if __name__ == "__main__":
    main()
