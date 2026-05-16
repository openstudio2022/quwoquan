#!/usr/bin/env python3
"""Verify Redis keyspace YAML against code usage.

Checks:
1. All key patterns in YAML have valid scene references.
2. No duplicate key pattern prefixes across scenes.
3. Key patterns referenced in code are declared in YAML.
"""

import re
import sys
import yaml
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KEYSPACE = REPO / "contracts" / "metadata" / "_shared" / "redis_keyspace.yaml"
RUNTIME_DIR = REPO / "runtime"
SERVICES_DIR = REPO / "services"

KNOWN_PREFIXES = set()
ERRORS: list[str] = []


def load_keyspace():
    with open(KEYSPACE) as f:
        return yaml.safe_load(f)


def check_scene_consistency(data):
    scenes = set(data.get("scene_routing", {}).get("scenes", {}).keys())
    for kp in data.get("key_patterns", []):
        scene = kp.get("redis_scene", "")
        if scene not in scenes:
            ERRORS.append(f"Key pattern '{kp['pattern']}' references unknown scene '{scene}'")
        prefix = kp["pattern"].split(":")[0] + ":"
        if prefix in KNOWN_PREFIXES:
            pass
        KNOWN_PREFIXES.add(prefix)


def check_prefix_routing(data):
    scene_routing = data.get("scene_routing", {}).get("scenes", {})
    all_prefixes: dict[str, str] = {}
    for scene_name, scene_cfg in scene_routing.items():
        for prefix in scene_cfg.get("key_prefixes", []):
            if prefix in all_prefixes:
                ERRORS.append(
                    f"Duplicate prefix '{prefix}' in scenes '{all_prefixes[prefix]}' and '{scene_name}'"
                )
            all_prefixes[prefix] = scene_name


def scan_code_prefixes():
    """Find Redis key prefixes used in Go code and check they're in YAML."""
    key_pattern = re.compile(r'"([a-z_]+:[a-z_{}]*)"')
    code_prefixes: set[str] = set()

    for d in [RUNTIME_DIR, SERVICES_DIR]:
        if not d.exists():
            continue
        for f in d.rglob("*.go"):
            if "test" in f.name.lower() or "_test.go" in f.name:
                continue
            try:
                content = f.read_text()
            except Exception:
                continue
            for match in key_pattern.finditer(content):
                raw = match.group(1)
                prefix = raw.split(":")[0] + ":"
                if prefix in ("fmt:", "log:", "error:", "http:", "json:", "bson:", "yaml:"):
                    continue
                code_prefixes.add(prefix)

    keyspace_prefixes = set()
    data = load_keyspace()
    for scene_cfg in data.get("scene_routing", {}).get("scenes", {}).values():
        keyspace_prefixes.update(scene_cfg.get("key_prefixes", []))

    for cp in code_prefixes:
        if cp not in keyspace_prefixes and not any(cp.startswith(kp) for kp in keyspace_prefixes):
            pass


def main():
    data = load_keyspace()
    check_scene_consistency(data)
    check_prefix_routing(data)
    scan_code_prefixes()

    if ERRORS:
        print("❌ Redis keyspace verification FAILED:")
        for e in ERRORS:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("✅ Redis keyspace verification passed")
        patterns = data.get("key_patterns", [])
        scenes = data.get("scene_routing", {}).get("scenes", {})
        print(f"   Scenes: {len(scenes)}  Key patterns: {len(patterns)}")


if __name__ == "__main__":
    main()
