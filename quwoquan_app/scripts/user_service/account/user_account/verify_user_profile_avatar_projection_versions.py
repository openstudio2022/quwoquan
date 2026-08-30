#!/usr/bin/env python3
"""校验 user_profile read-model projection 的头像 URL 都显式携带版本字段。

范围：
  - quwoquan_service/services/user-service/contracts/account/user_account/projections/*.yaml
  - 跳过 *_request.yaml（请求 DTO，不属于 read-model）

规则：
  - 只要 projection 暴露以下头像 URL 字段之一，就必须同时暴露对应版本字段：
      avatarUrl -> avatarVersion
      likerAvatarUrl -> likerAvatarVersion
      actorAvatarUrl -> actorAvatarVersion
      displayAvatarUrl -> displayAvatarVersion

目的：
  防止新增/改造头像 projection 时只传 URL、不传版本，导致 App 侧缓存失效链路再次漏掉。
"""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = REPO_ROOT
PROJECTIONS_DIR = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "user-service"
    / "contracts"
    / "account"
    / "user_account"
    / "projections"
)

URL_TO_VERSION_FIELD = {
    "avatarUrl": "avatarVersion",
    "likerAvatarUrl": "likerAvatarVersion",
    "actorAvatarUrl": "actorAvatarVersion",
    "displayAvatarUrl": "displayAvatarVersion",
}


def projection_field_names(path: Path) -> set[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return set()
    client_projection = data.get("client_projection")
    if not isinstance(client_projection, dict):
        return set()
    fields = client_projection.get("fields")
    if not isinstance(fields, list):
        return set()
    result: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip()
        if name:
            result.add(name)
    return result


def main() -> int:
    if not PROJECTIONS_DIR.is_dir():
        print(
            f"verify_user_profile_avatar_projection_versions: missing {PROJECTIONS_DIR}",
            file=sys.stderr,
        )
        return 1

    errors: list[str] = []
    checked = 0

    for path in sorted(PROJECTIONS_DIR.glob("*.yaml")):
        if path.name.endswith("_request.yaml"):
            continue
        fields = projection_field_names(path)
        required_pairs = [
            (url_field, version_field)
            for url_field, version_field in URL_TO_VERSION_FIELD.items()
            if url_field in fields
        ]
        if not required_pairs:
            continue
        checked += 1
        for url_field, version_field in required_pairs:
            if version_field not in fields:
                errors.append(
                    f"{path.relative_to(ROOT)}: exposes {url_field} but misses {version_field}"
                )

    if errors:
        print("verify_user_profile_avatar_projection_versions: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "verify_user_profile_avatar_projection_versions: OK "
        f"({checked} avatar projections checked)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
