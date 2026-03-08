---
name: /submit-with-audit
id: submit-with-audit
category: Workflow
description: 兼容提交流程（根流程以 /commit 为准；本命令仅保留端侧历史兼容）
---

完成代码提交的完整流程：**先执行 semantic-audit 检查 → 不通过则生成修改规划并等待批准后自动修复 → 通过则提交并推送到当前分支、再合入主干**。默认使用**当前分支**进行提交与推送。

> 语义统一说明：仓库根流程以 `/commit` 作为唯一 submit 语义命令；本命令仅用于兼容历史端侧工作流。若与根目录 `/.cursor/commands/commit.md`、`/.cursor/rules/00-fullstack-development-flow.mdc`、`/.cursor/rules/03-testing.mdc` 冲突，以根流程规则为准，并同样受 `T1~T4`、TDD、非功能验收与灰度发布要求约束。

## 前置条件

- 工作区为 quwoquan 仓库根目录（或包含 `quwoquan_app` 的目录）。
- 已配置 git 与远程 `origin`，存在主干分支 `main`。

## 执行流程

### 第一步：获取当前分支与工作区状态

1. 在**仓库根目录**执行：
   ```bash
   git branch --show-current
   git status -sb
   ```
2. 若没有未提交改动且没有未跟踪的待提交文件，提示「当前没有可提交的改动」并结束。
3. 记录当前分支为 `CURRENT_BRANCH`（用于后续提交与推送）。

---

### 第二步：执行 semantic-audit 检查（提交前必须通过）

在 **quwoquan_app** 目录下依次执行以下两项，且**两项均需通过**才算检查通过。

**2.1 Flutter 静态分析（指定文件，与 semantic-audit 一致）**

```bash
cd quwoquan_app && flutter analyze lib/features/home/pages/discovery_page.dart \
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

- **通过**：命令退出码为 0 且无 error。
- **不通过**：存在 error 或退出码非 0。

**2.2 硬编码视觉字面量检查（Python 脚本）**

在 **quwoquan_app** 目录下执行：

```bash
cd quwoquan_app && python3 - <<'PY'
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

- **通过**：输出为 `No hardcoded visual literals found in targeted scope.`
- **不通过**：输出了任意 `文件:行号: 代码行`。

---

### 第三步：若检查不通过 —— 生成修改规划并等待批准

1. **不执行任何提交或推送**。
2. 生成**修改项及修改建议规划**，格式如下：
   - **修改项列表**（每条包含）：
     - 文件路径与行号
     - 当前代码片段（违规行）
     - 违反的规则（来自 01-core-coding-standards、06-semantic-consistency-audit）
     - **建议修改**：具体改为使用 `AppTypography` / `AppSpacing` / `AppColors` 等语义 API 的示例或说明。
   - 若为 **flutter analyze** 报错：按报错文件与信息逐条列出，并给出修复建议。
   - 若为 **硬编码字面量**：按脚本输出的每个 `文件:行号` 读取上下文，给出替换为语义常量的具体建议。
3. 明确告知用户：
   - 「当前不满足提交前检查，**不会提交**。」
   - 「请确认是否批准按上述规划自动修改。批准后我将执行修改、再次运行 semantic-audit 并确保 `flutter build` 通过，然后请您**再次执行本提交命令**以完成提交。」
4. **等待用户明确回复批准**（例如「批准」「执行修改」「按规划改」等）。未批准前不进行自动修改。

---

### 第四步：用户批准后 —— 自动修改并验证

仅在用户已对「修改规划」明确批准后执行：

1. 按第三步中的规划逐项修改代码（优先使用 `AppTypography`、`AppSpacing`、`AppColors`、`DesignSemanticConstants`、`UITextConstants` 等）。
2. 修改完成后，重新执行**第二步**的 2.1 与 2.2；若仍不通过，继续修复直至通过。
3. 在 quwoquan_app 下执行编译验证：
   ```bash
   cd quwoquan_app && flutter build apk --debug
   ```
   若失败则修复直至通过（或改为 `flutter build ios --debug` 等与当前开发环境一致的目标）。
4. 告知用户：「修改已完成，语义检查与编译均已通过。请**再次执行 /submit-with-audit 命令**以完成提交、推送与合入主干。」  
   **本次不自动执行 commit/push/merge**，由用户再次运行本命令后进入第五步。

---

### 第五步：检查通过 —— 总结改动、提交、推送、合入主干

仅在**第二步两项检查均通过**时执行（若刚完成第四步的修复，需用户再次执行本命令后才会进入第五步）。

**5.1 总结自上次提交后的变化**

在仓库根目录执行：

```bash
git diff --stat HEAD
git status -sb
```

用自然语言简要总结：修改了哪些模块/文件、主要变更类型（例如：设计系统扩展、图片编辑 Pro、发现/圈子/创建页等），用于生成 commit message。

**5.2 提交**

1. 添加待提交内容（默认仅 quwoquan_app，排除无关目录如 social_content_app 的本地配置）：
   ```bash
   git add quwoquan_app/
   ```
2. 根据 5.1 的总结生成一条清晰的 commit message（建议使用约定式：`feat:`/`fix:`/`chore:` 等）。
3. 执行提交：
   ```bash
   git commit -m "<生成的 message>"
   ```

**5.3 推送到远程当前分支**

```bash
git push origin <CURRENT_BRANCH>
```

**5.4 合入主干并推送**

1. 若 `CURRENT_BRANCH` 已是 `main`：仅需确认 `main` 已推送（5.3 即完成），并说明「当前分支为 main，已推送，无需额外合入。」
2. 若 `CURRENT_BRANCH` 不是 `main`：
   ```bash
   git checkout main
   git merge <CURRENT_BRANCH> -m "Merge branch '<CURRENT_BRANCH>'"
   git push origin main
   git checkout <CURRENT_BRANCH>
   ```
3. 报告结果：已提交到 `<CURRENT_BRANCH>`、已推送到 `origin/<CURRENT_BRANCH>`、已合入并推送 `main`。

---

## 小结表

| 阶段           | 条件               | 动作 |
|----------------|--------------------|------|
| 第二步         | 检查不通过         | 生成修改规划，不提交，等待用户批准 |
| 第四步         | 用户已批准         | 自动修改 → 再跑检查与编译 → 提示用户再次执行本命令 |
| 第五步         | 检查通过（或用户再次执行且通过） | 总结改动 → commit → push 当前分支 → merge 到 main 并 push |

执行本命令时，**始终从第一步开始**；若上次因检查不通过而停在「等待批准」，用户批准后先完成第四步，再提示用户再次运行本命令以进入第五步。
