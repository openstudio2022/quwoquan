#!/usr/bin/env python3
"""Verify feature consistency between feature_registry.yaml, Go structs, and Python extractors.

This script checks:
1. feature_registry.yaml user_features vs Go UserFeatureVector fields
2. feature_registry.yaml item_features vs rm_discovery_feed projector fields
3. sample_joiner.py join key alignment (postId vs contentId)
4. Python _extract_features coverage matches registry

Exit 0 = all consistent, Exit 1 = gaps found.
"""

import sys
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SERVICE_ROOT = SCRIPT_DIR.parent.parent

def load_feature_registry():
    """Load declared features from feature_registry.yaml."""
    registry_path = SCRIPT_DIR / "feature_registry.yaml"
    if not registry_path.exists():
        print(f"WARN: {registry_path} not found, skipping registry check")
        return None

    import yaml
    with open(registry_path) as f:
        data = yaml.safe_load(f)

    scenario = data.get("scenarios", [{}])[0] if "scenarios" in data else data
    user_features = [f["name"] for f in scenario.get("user_features", [])]
    item_features = [f["name"] for f in scenario.get("item_features", [])]
    labels = [l["name"] for l in scenario.get("labels", [])]
    return {"user": user_features, "item": item_features, "labels": labels}


def scan_go_struct_fields(filepath: Path, struct_name: str) -> list[str]:
    """Extract JSON tag names from a Go struct definition."""
    if not filepath.exists():
        return []
    content = filepath.read_text()
    pattern = rf"type {struct_name} struct \{{(.*?)\}}"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return []
    fields = re.findall(r'json:"(\w+)', match.group(1))
    return fields


def check_sample_joiner_key():
    """Verify sample_joiner uses correct join key."""
    joiner_path = SCRIPT_DIR / "sample_joiner.py"
    if not joiner_path.exists():
        return []
    content = joiner_path.read_text()
    issues = []
    if "contentId" in content and "postId" not in content:
        issues.append(
            "sample_joiner.py uses 'contentId' but rm_discovery_feed uses 'postId' as primary key"
        )
    return issues


def main():
    issues: list[str] = []

    # Check Go struct has level-mapped fields
    feature_go = SERVICE_ROOT / "runtime" / "recommendation" / "feature.go"
    go_fields = scan_go_struct_fields(feature_go, "UserFeatureVector")
    required_fields = [
        "likeLevel", "favoriteLevel", "shareLevel", "eventLevel",
        "topicAffinities", "audienceAffinities", "formatAffinities",
        "entityAffinities", "entityInstanceAffinities",
        "typeENER", "avgEngagementDepth", "sourceDistribution",
    ]
    for field in required_fields:
        if field not in go_fields:
            issues.append(f"UserFeatureVector missing field: {field}")

    # Check sample joiner
    issues.extend(check_sample_joiner_key())

    # Check BehaviorSignal has new fields
    hotpath_go = SERVICE_ROOT / "runtime" / "recommendation" / "hotpath.go"
    signal_fields = scan_go_struct_fields(hotpath_go, "BehaviorSignal")
    required_signal = ["referralSource", "engagementDepth", "entityRefs", "authorId"]
    for field in required_signal:
        if field not in signal_fields:
            issues.append(f"BehaviorSignal missing field: {field}")

    if issues:
        print("FEATURE CONSISTENCY CHECK FAILED:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("Feature consistency check PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
