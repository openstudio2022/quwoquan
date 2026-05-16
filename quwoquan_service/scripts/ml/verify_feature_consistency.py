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

    scenarios = data.get("scenarios", {})
    if isinstance(scenarios, dict):
        scenario = scenarios.get("content_feed") or next(iter(scenarios.values()), {})
    else:
        scenario = scenarios[0] if scenarios else {}
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
    if "targetId" not in content:
        issues.append(
            "sample_joiner.py missing 'targetId' — expected as the join key against rm_discovery_feed"
        )
    return issues


def _count_extract_features_dims(filepath: Path) -> int | None:
    """Count the number of features appended in _extract_features."""
    if not filepath.exists():
        return None
    content = filepath.read_text()
    append_count = content.count("features.append(")
    extend_matches = re.findall(r"features\.extend\(\[([^\]]+)\]", content)
    for m in extend_matches:
        append_count += len([x.strip() for x in m.split(",") if x.strip()])
    return append_count


def _extract_content_type_map(filepath: Path) -> dict | None:
    """Extract CONTENT_TYPE_MAP from a Python file."""
    if not filepath.exists():
        return None
    content = filepath.read_text()
    match = re.search(r'CONTENT_TYPE_MAP\s*=\s*\{([^}]+)\}', content)
    if not match:
        return None
    pairs = re.findall(r'"(\w+)":\s*(\d+)', match.group(1))
    return {k: int(v) for k, v in pairs}


def check_feature_dimensions():
    """Ensure train.py, train_multiobjective.py, train_embedding.py, and content_feed.py all have same feature dims."""
    issues = []
    train_py = SCRIPT_DIR / "train.py"
    mo_py = SCRIPT_DIR / "train_multiobjective.py"
    embed_py = SCRIPT_DIR / "train_embedding.py"
    serving_py = SERVICE_ROOT / "services" / "rec-model-service" / "models" / "content_feed.py"

    dims = {}
    for label, path in [("train.py", train_py), ("train_multiobjective.py", mo_py), ("train_embedding.py", embed_py), ("content_feed.py", serving_py)]:
        d = _count_extract_features_dims(path)
        if d is not None:
            dims[label] = d

    ranker_dims = {k: v for k, v in dims.items() if k != "train_embedding.py"}
    values = list(ranker_dims.values())
    if len(set(values)) > 1:
        issues.append(f"Feature dimension mismatch across ranker scripts: {ranker_dims}")

    return issues


def check_content_type_maps():
    """Ensure CONTENT_TYPE_MAP is consistent across Python files."""
    issues = []
    files = [
        ("train.py", SCRIPT_DIR / "train.py"),
        ("train_multiobjective.py", SCRIPT_DIR / "train_multiobjective.py"),
        ("train_embedding.py", SCRIPT_DIR / "train_embedding.py"),
        ("content_feed.py", SERVICE_ROOT / "services" / "rec-model-service" / "models" / "content_feed.py"),
    ]
    maps = {}
    for label, path in files:
        m = _extract_content_type_map(path)
        if m is not None:
            maps[label] = m

    ref_map = None
    for label, m in maps.items():
        if ref_map is None:
            ref_map = m
        elif m != ref_map:
            issues.append(f"CONTENT_TYPE_MAP mismatch: {label}={m} vs reference={ref_map}")

    return issues


def _extract_recall_path_map(filepath: Path) -> dict | None:
    """Extract RECALL_PATH_MAP from a Python file."""
    if not filepath.exists():
        return None
    content = filepath.read_text()
    match = re.search(r'RECALL_PATH_MAP\s*=\s*\{([^}]+)\}', content)
    if not match:
        return None
    pairs = re.findall(r'"(\w+)":\s*(\d+)', match.group(1))
    return {k: int(v) for k, v in pairs}


def check_recall_path_maps():
    """Ensure RECALL_PATH_MAP is consistent across training and serving."""
    issues = []
    files = [
        ("train.py", SCRIPT_DIR / "train.py"),
        ("content_feed.py", SERVICE_ROOT / "services" / "rec-model-service" / "models" / "content_feed.py"),
    ]
    maps = {}
    for label, path in files:
        m = _extract_recall_path_map(path)
        if m is not None:
            maps[label] = m

    ref_map = None
    for label, m in maps.items():
        if ref_map is None:
            ref_map = m
        elif m != ref_map:
            issues.append(f"RECALL_PATH_MAP mismatch: {label}={m} vs reference={ref_map}")

    return issues


def check_feature_version():
    """Ensure feature_registry.yaml version is referenced in Python code."""
    registry_path = SCRIPT_DIR / "feature_registry.yaml"
    if not registry_path.exists():
        return []
    try:
        import yaml
        with open(registry_path) as f:
            data = yaml.safe_load(f)
        registry_version = data.get("version")
        if registry_version is None:
            return []
    except Exception:
        return []

    issues = []
    serving_py = SERVICE_ROOT / "services" / "rec-model-service" / "models" / "content_feed.py"
    if serving_py.exists():
        content = serving_py.read_text()
        version_match = re.search(r'FEATURE_VERSION\s*=\s*(\d+)', content)
        if version_match:
            code_version = int(version_match.group(1))
            if code_version != registry_version:
                issues.append(f"content_feed.py FEATURE_VERSION={code_version} != registry version={registry_version}")
    return issues


def check_item_and_label_registry():
    """Check registry item_features and labels are covered in joiner."""
    issues = []
    registry = load_feature_registry()
    if not registry:
        return issues

    joiner_path = SCRIPT_DIR / "sample_joiner.py"
    if not joiner_path.exists():
        return issues
    joiner_content = joiner_path.read_text()

    ignored_item_features = {"contentId", "itemEmbedding"}

    for feat in registry.get("item", []):
        if feat in ignored_item_features:
            continue
        if feat not in joiner_content:
            issues.append(f"Registry item feature '{feat}' not found in sample_joiner.py")

    for label in registry.get("labels", []):
        if label not in joiner_content:
            issues.append(f"Registry label '{label}' not found in sample_joiner.py")

    return issues


def main():
    issues: list[str] = []

    # Check feature registry YAML consistency
    registry = load_feature_registry()
    if registry:
        feature_go = SERVICE_ROOT / "runtime" / "recommendation" / "feature.go"
        go_user_fields = scan_go_struct_fields(feature_go, "UserFeatureVector")
        for feat in registry["user"]:
            if feat not in go_user_fields:
                issues.append(f"Registry user feature '{feat}' missing from UserFeatureVector Go struct")

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

    # Check feature dimensions across Python scripts
    issues.extend(check_feature_dimensions())

    # Check CONTENT_TYPE_MAP consistency
    issues.extend(check_content_type_maps())

    # Check RECALL_PATH_MAP consistency
    issues.extend(check_recall_path_maps())

    # Check feature_registry.yaml version vs code
    issues.extend(check_feature_version())

    # Check item features and labels in registry vs joiner
    issues.extend(check_item_and_label_registry())

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
