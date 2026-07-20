#!/usr/bin/env python3
"""Verify feature consistency between feature_registry.yaml, Go structs, and Python extractors.

This script checks:
1. feature_registry.yaml vs Go CandidateInput/UserFeatureVector;
2. immutable impression snapshots vs the active feature registry;
3. request-scoped PIT joining without mutable projection lookups;
4. training/serving feature vectors and context features remain aligned.

Exit 0 = all consistent, Exit 1 = gaps found.
"""

import ast
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SERVICE_ROOT = SCRIPT_DIR.parents[2]

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
    context_features = [f["name"] for f in scenario.get("context_features", [])]
    labels = [l["name"] for l in scenario.get("labels", [])]
    return {
        "user": user_features,
        "item": item_features,
        "context": context_features,
        "labels": labels,
    }


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


def scan_go_function_map_keys(filepath: Path, function_name: str) -> list[str]:
    """Extract literal map keys from one Go feature snapshot function."""
    if not filepath.exists():
        return []
    content = filepath.read_text()
    match = re.search(
        rf"func {re.escape(function_name)}\(.*?(?=\nfunc |\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return []
    return re.findall(r'"([A-Za-z][A-Za-z0-9]*)"\s*:', match.group(0))


def extract_python_string_list(filepath: Path, variable_name: str) -> list[str]:
    """Read a literal Python string-list constant without importing the module."""
    if not filepath.exists():
        return []
    tree = ast.parse(filepath.read_text())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == variable_name
            for target in node.targets
        ):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            return []
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
    return []


def check_sample_joiner_key():
    """Verify the joiner is request-scoped and consumes immutable online snapshots."""
    joiner_path = SCRIPT_DIR / "sample_joiner.py"
    if not joiner_path.exists():
        return []
    content = joiner_path.read_text()
    issues = []
    for identity_field in ("requestId", "userId", "targetId"):
        if identity_field not in content:
            issues.append(
                f"sample_joiner.py missing request-scoped identity '{identity_field}'"
            )
    for snapshot_field in (
        "featureSnapshotAt",
        "userFeatureSnapshot",
        "itemFeatureSnapshot",
    ):
        if snapshot_field not in content:
            issues.append(
                f"sample_joiner.py missing immutable online snapshot field '{snapshot_field}'"
            )
    for mutable_projection in ("rm_recommend_feature", "rm_discovery_feed"):
        if mutable_projection in content:
            issues.append(
                f"sample_joiner.py must not read mutable projection '{mutable_projection}'"
            )
    if "build_training_samples(events, args.scenario)" not in content:
        issues.append(
            "sample_joiner.py main path does not consume build_training_samples"
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
    """Check active registry features are captured by the immutable Go snapshot."""
    issues = []
    registry = load_feature_registry()
    if not registry:
        return issues

    learning_go = SERVICE_ROOT / "runtime" / "recommendation" / "learning.go"
    snapshot_item_fields = set(
        scan_go_function_map_keys(learning_go, "trainingItemFeatures")
    )
    snapshot_user_fields = set(
        scan_go_function_map_keys(learning_go, "trainingUserFeatures")
    )
    registry_items = set(registry.get("item", []))
    registry_users = set(registry.get("user", []))
    if snapshot_item_fields != registry_items:
        missing = sorted(registry_items - snapshot_item_fields)
        extra = sorted(snapshot_item_fields - registry_items)
        if missing:
            issues.append(
                f"trainingItemFeatures missing active registry fields: {missing}"
            )
        if extra:
            issues.append(
                f"trainingItemFeatures exposes unregistered fields: {extra}"
            )
    if snapshot_user_fields != registry_users:
        missing = sorted(registry_users - snapshot_user_fields)
        extra = sorted(snapshot_user_fields - registry_users)
        if missing:
            issues.append(
                f"trainingUserFeatures missing active registry fields: {missing}"
            )
        if extra:
            issues.append(
                f"trainingUserFeatures exposes unregistered fields: {extra}"
            )

    scorer_go = SERVICE_ROOT / "runtime" / "recommendation" / "scorer.go"
    candidate_fields = set(scan_go_struct_fields(scorer_go, "CandidateInput"))
    expected_candidate_fields = registry_items - {"tagCount"}
    if candidate_fields != expected_candidate_fields:
        missing = sorted(expected_candidate_fields - candidate_fields)
        extra = sorted(candidate_fields - expected_candidate_fields)
        if missing:
            issues.append(f"CandidateInput missing registry fields: {missing}")
        if extra:
            issues.append(f"CandidateInput exposes unregistered fields: {extra}")

    joiner_path = SCRIPT_DIR / "sample_joiner.py"
    if not joiner_path.exists():
        return issues
    joiner_content = joiner_path.read_text()

    for label in registry.get("labels", []):
        if label not in joiner_content:
            issues.append(f"Registry label '{label}' not found in sample_joiner.py")

    return issues


def check_context_feature_registry():
    """Ensure training, online scoring, and PIT samples use one context surface."""
    issues = []
    registry = load_feature_registry()
    if not registry:
        return issues
    expected = set(registry.get("context", []))
    consumers = (
        (
            "train.py",
            SCRIPT_DIR / "train.py",
            "CONTEXT_NUMERIC_FEATURES",
        ),
        (
            "train_multiobjective.py",
            SCRIPT_DIR / "train_multiobjective.py",
            "CONTEXT_NUMERIC_FEATURES",
        ),
        (
            "content_feed.py",
            SERVICE_ROOT / "services" / "rec-model-service" / "models" / "content_feed.py",
            "CONTEXT_NUMERIC",
        ),
    )
    for label, path, variable in consumers:
        actual = set(extract_python_string_list(path, variable))
        if actual != expected:
            issues.append(
                f"{label} {variable}={sorted(actual)} != context registry={sorted(expected)}"
            )

    for label, path in (
        ("sample_joiner.py", SCRIPT_DIR / "sample_joiner.py"),
        (
            "RemoteModelScorer",
            SERVICE_ROOT / "runtime" / "recommendation" / "scorer.go",
        ),
    ):
        content = path.read_text() if path.exists() else ""
        for feature in expected:
            if feature not in content:
                issues.append(f"{label} missing context feature '{feature}'")
    return issues


RETIRED_SKEWED_ITEM_FEATURES = ("bodyLength", "aspectRatio", "hasCover")


def check_n3_feature_skew_contract():
    """Guard the single training/online feature surface closed by N3-3."""
    issues = []
    registry = load_feature_registry()
    registry_items = set(registry.get("item", [])) if registry else set()
    for feature in RETIRED_SKEWED_ITEM_FEATURES:
        if feature in registry_items:
            issues.append(
                f"Retired skewed item feature '{feature}' returned to feature_registry"
            )
    if "publishHour" not in registry_items:
        issues.append("feature_registry item features missing online-backed publishHour")

    scorer_go = SERVICE_ROOT / "runtime" / "recommendation" / "scorer.go"
    candidate_fields = set(scan_go_struct_fields(scorer_go, "CandidateInput"))
    if "publishHour" not in candidate_fields:
        issues.append("CandidateInput missing publishHour")
    for feature in RETIRED_SKEWED_ITEM_FEATURES:
        if feature in candidate_fields:
            issues.append(
                f"CandidateInput still exposes retired skewed feature '{feature}'"
            )

    ranker_extractors = (
        ("train.py", SCRIPT_DIR / "train.py"),
        ("train_multiobjective.py", SCRIPT_DIR / "train_multiobjective.py"),
        ("train_embedding.py", SCRIPT_DIR / "train_embedding.py"),
        (
            "content_feed.py",
            SERVICE_ROOT / "services" / "rec-model-service" / "models" / "content_feed.py",
        ),
        (
            "transformer.py",
            SERVICE_ROOT / "services" / "rec-model-service" / "features" / "transformer.py",
        ),
    )
    retired_usage_patterns = {
        "bodyLength": re.compile(r"""["']bodyLength["']\s*,"""),
        "aspectRatio": re.compile(r"""["']aspectRatio["']\s*,"""),
        "hasCover": re.compile(r"""\.get\(["']hasCover["']\)"""),
    }
    for label, path in ranker_extractors:
        if not path.exists():
            issues.append(f"N3-3 feature extractor missing: {label}")
            continue
        content = path.read_text(encoding="utf-8")
        if "publishHour" not in content:
            issues.append(f"{label} missing publishHour")
        for feature, pattern in retired_usage_patterns.items():
            if pattern.search(content):
                issues.append(f"{label} still consumes retired feature '{feature}'")

    for label, path in (
        ("sample_joiner.py", SCRIPT_DIR / "sample_joiner.py"),
        ("generate_seed_data.py", SCRIPT_DIR / "generate_seed_data.py"),
    ):
        content = path.read_text(encoding="utf-8")
        for feature in RETIRED_SKEWED_ITEM_FEATURES:
            if re.search(rf"""["']{re.escape(feature)}["']\s*:""", content):
                issues.append(f"{label} still emits retired feature '{feature}'")

    return issues


# W7 交集特征三方一致强校验（B8 收口）：registry 声明的交集特征必须同时进入
# ① 三个 Python 特征抽取器（serving + 两个训练脚本，经共享 helper 段）
# ② Go 曝光时不可变训练快照（joiner 只透传，不再重算）
# ③ Go UserFeatureVector / CandidateInput（wire 单点注入）
INTERSECTION_USER_FEATURES = [
    "sharedFolloweesCount", "sharedCircleCount", "coCommentedCount",
    "coVisitedEntityCount", "followeeInObjectActive", "followeeViewingActive",
    "affinityIntersectionScore",
]
INTERSECTION_ITEM_FEATURES = [
    "intersectionFactStrength", "intersectionFreshness",
    "affinityIntersectionScore", "intersectionConfidenceLabel",
    "intersectionClass",
]


def check_intersection_features():
    """Strict tri-source alignment for intersection features (W7/B8)."""
    issues = []
    extractor_files = [
        ("train.py", SCRIPT_DIR / "train.py"),
        ("train_multiobjective.py", SCRIPT_DIR / "train_multiobjective.py"),
        (
            "content_feed.py",
            SERVICE_ROOT / "services" / "rec-model-service" / "models" / "content_feed.py",
        ),
    ]
    for label, path in extractor_files:
        if not path.exists():
            issues.append(f"intersection check: {label} missing at {path}")
            continue
        content = path.read_text()
        if "_append_intersection_features" not in content:
            issues.append(
                f"{label} missing _append_intersection_features (intersection features not wired)"
            )
            continue
        for feat in INTERSECTION_USER_FEATURES + INTERSECTION_ITEM_FEATURES:
            if feat not in content:
                issues.append(f"{label} missing intersection feature '{feat}'")

    learning_go = SERVICE_ROOT / "runtime" / "recommendation" / "learning.go"
    if learning_go.exists():
        snapshot_content = learning_go.read_text()
        for feat in INTERSECTION_USER_FEATURES:
            if feat not in snapshot_content:
                issues.append(
                    f"trainingUserFeatures missing user intersection feature '{feat}'"
                )
    joiner_path = SCRIPT_DIR / "sample_joiner.py"
    if joiner_path.exists():
        joiner_content = joiner_path.read_text()
        if "featureLagSeconds" not in joiner_content:
            issues.append(
                "sample_joiner.py missing featureLagSeconds (PIT leakage metric, B9)"
            )

    feature_go = SERVICE_ROOT / "runtime" / "recommendation" / "feature.go"
    go_user_fields = scan_go_struct_fields(feature_go, "UserFeatureVector")
    for feat in INTERSECTION_USER_FEATURES:
        if go_user_fields and feat not in go_user_fields:
            issues.append(
                f"UserFeatureVector missing intersection field '{feat}' (wire drift)"
            )

    scorer_go = SERVICE_ROOT / "runtime" / "recommendation" / "scorer.go"
    go_item_fields = scan_go_struct_fields(scorer_go, "CandidateInput")
    for feat in INTERSECTION_ITEM_FEATURES:
        if go_item_fields and feat not in go_item_fields:
            issues.append(
                f"CandidateInput missing intersection field '{feat}' (wire drift)"
            )

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
        "likeLevel", "shareLevel", "eventLevel",
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

    # Context time features must be identical in online scoring and PIT samples.
    issues.extend(check_context_feature_registry())

    # N3-3: training/online item feature skew must remain single-track.
    issues.extend(check_n3_feature_skew_contract())

    # W7: strict intersection feature tri-source alignment
    issues.extend(check_intersection_features())

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
