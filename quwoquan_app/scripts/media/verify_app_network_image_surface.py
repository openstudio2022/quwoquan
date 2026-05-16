#!/usr/bin/env python3
from pathlib import Path
import re, sys, yaml
ROOT = Path(__file__).resolve().parents[3]
allow_path = ROOT / "specs/gates/app_network_image_policy_allowlist.yaml"
allowed = {}
if allow_path.exists():
    data = yaml.safe_load(allow_path.read_text()) or {}
    for item in data.get("allowed", []):
        allowed[item["path"]] = int(item.get("maxCount", 0))
pattern = re.compile(r"\bImage\.network\s*\(|\bNetworkImage\s*\(")
violations = []
for path in (ROOT / "quwoquan_app/lib").rglob("*.dart"):
    rel = path.relative_to(ROOT / "quwoquan_app/lib").as_posix()
    if rel == "core/widgets/app_image.dart":
        continue
    count = len(pattern.findall(path.read_text(errors="ignore")))
    max_count = allowed.get(rel, 0)
    if count > max_count:
        violations.append(f"{rel}: {count} > allowlist {max_count}")
if violations:
    print("[app-network-image] FAIL")
    print("\n".join(violations))
    sys.exit(2)
print("[app-network-image] OK")
