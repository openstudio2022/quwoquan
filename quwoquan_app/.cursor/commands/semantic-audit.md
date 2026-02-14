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

---

## 3) 被 /submit-with-audit 调用且检查不通过时

若本检查在「提交前流程」中被调用且**未通过**（flutter analyze 有 error 或 Python 脚本发现硬编码），须输出**修改项及修改建议规划**，便于后续自动修复：

- **每条修改项**包含：`文件:行号`、当前代码片段、违反的规则（引用 01-core / 06-semantic）、**建议修改**（具体改为 `AppTypography` / `AppSpacing` / `AppColors` 等语义 API 的写法）。
- 不执行提交；等待用户批准后，由执行流程按规划自动修改并验证编译，再提示用户再次执行提交命令。
