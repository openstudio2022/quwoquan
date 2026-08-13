"""Canonical execution target-selection contracts."""
from __future__ import annotations

from pathlib import Path

import yaml


def _coverage_file(path: Path) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "普陀区",
                        "leaves": [
                            {
                                "name": "测试实体甲",
                                "canonicalName": "测试实体甲",
                                "entityType": "地点/景区",
                                "geoTagRef": "Topic/地理/行政区/中国/test-region-a/舟山市/普陀区",
                                "typeTagRefs": ["Entity/地点/景区/5A景区"],
                                "selectionPriority": 1,
                            }
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path
