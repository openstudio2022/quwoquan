---
name: /semantic-audit
id: semantic-audit
category: Quality
description: 执行创作与频道链路语义一致性检查
---

执行全套语义一致性检查，默认先跑“发现/圈子/主页入口 + 创作链路”，再可选跑“全量仓库”。

## 1) 频道与创作链路快速检查（推荐每次提交前执行）

```bash
flutter analyze lib/features/home/pages/discovery_page.dart \
  lib/features/home/pages/home_page.dart \
  lib/components/tab_navigation.dart \
  lib/components/post_list_section.dart \
  lib/features/circles/pages/circles_page.dart \
  lib/features/circles/pages/circle_detail_page.dart \
  lib/features/circles/pages/circle_stats_page.dart \
  lib/features/create/pages/create_page.dart \
  lib/components/media/image/editor/image_editor_page.dart \
  lib/components/media/image/editor/panels/image_editor_operation_panel.dart \
  lib/components/media/image/editor/panels/image_editor_rotate_overlay.dart \
  lib/components/media/image/editor/tool_list/image_editor_tool_entry_chip.dart \
  lib/components/media/image/editor/tool_list/image_editor_pro_tool_list.dart \
  lib/components/media/image/editor/top_bar/image_editor_top_bar.dart \
  lib/components/media/image/editor/bottom_bar/image_editor_bottom_bar.dart \
  lib/core/design_system/spacing/app_spacing.dart \
  lib/core/design_system/typography/app_typography.dart \
  lib/core/constants/design_semantic_constants.dart
```

```bash
python3 - <<'PY'
import pathlib
import re

targets = [
    "lib/features/home/pages/discovery_page.dart",
    "lib/features/home/pages/home_page.dart",
    "lib/features/circles/pages/circles_page.dart",
    "lib/components/tab_navigation.dart",
    "lib/components/post_list_section.dart",
    "lib/features/create/pages/create_page.dart",
]
targets += [str(p) for p in pathlib.Path("lib/components/media/image/editor").rglob("*.dart")]

pattern = re.compile(
    r"fontSize:\s*\d+(\.\d+)?(\.sp)?|"
    r"size:\s*\d+(\.\d+)?(\.sp)?|"
    r"BorderRadius\.circular\(\s*\d+(\.\d+)?\s*\)|"
    r"EdgeInsets\.(all|symmetric|only)\(\s*\d+"
)

found = False
for file in targets:
    p = pathlib.Path(file)
    if not p.exists():
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if pattern.search(line):
            print(f"{file}:{i}: {line.strip()}")
            found = True
if not found:
    print("No hardcoded visual literals found in targeted scope.")
PY
```

## 2) 全量仓库健康度检查（阶段验收时执行）

```bash
flutter analyze
```

若第 2 步出现历史遗留告警，请按“先创作链路、后外围模块”顺序分批治理，避免一次性大改引入回归。
