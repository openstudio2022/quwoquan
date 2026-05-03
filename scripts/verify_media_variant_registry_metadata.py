#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
fields = (ROOT / "quwoquan_service/contracts/metadata/content/post/fields.yaml").read_text()
required = ["dominantColor", "lqip", "contentProfile", "derivativePolicyVersion", "accessPolicy", "originalAccess"]
missing = [name for name in required if f"name: {name}" not in fields]
service = (ROOT / "quwoquan_service/contracts/metadata/content/post/service.yaml").read_text()
if "RequestOriginalImageAccess" not in service:
    missing.append("RequestOriginalImageAccess")
if missing:
    print("[media-variant-registry] FAIL missing: " + ", ".join(missing))
    sys.exit(2)
print("[media-variant-registry] OK")
