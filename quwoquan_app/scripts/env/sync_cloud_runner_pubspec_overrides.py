#!/usr/bin/env python3
"""从 App 唯一 override 真相源生成 alpha/mock package resolver 配置。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
SOURCE = APP / "pubspec.yaml"
TARGETS = (
    APP / "packages/quwoquan_cloud_mock",
    APP / "runners/alpha",
)


def main() -> int:
    source = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    overrides = source.get("dependency_overrides")
    if not isinstance(overrides, dict) or not overrides:
        raise ValueError("App dependency_overrides 不能为空")

    for target in TARGETS:
        rebased: dict[str, object] = {}
        for name, descriptor in overrides.items():
            if isinstance(descriptor, dict) and "path" in descriptor:
                absolute = (APP / str(descriptor["path"])).resolve()
                rebased[name] = {
                    **descriptor,
                    "path": Path(os.path.relpath(absolute, target)).as_posix(),
                }
            else:
                rebased[name] = descriptor
        payload = yaml.safe_dump(
            {"dependency_overrides": rebased},
            allow_unicode=True,
            sort_keys=False,
        )
        output = target / "pubspec_overrides.yaml"
        output.write_text(
            "# Generated from quwoquan_app/pubspec.yaml; DO NOT EDIT.\n" + payload,
            encoding="utf-8",
        )
        print(f"generated: {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
