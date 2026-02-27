---
name: /submit-with-gate
id: submit-with-gate
category: Workflow
description: 提交（自动 G4 卡点：审计 → gate → commit → push）
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 5

端云全栈提交：**按变更范围自动审计 → gate 门禁 → 通过则提交推送**。

## 前置条件

- 工作区为 quwoquan 仓库根目录
- 已配置 git 与远程 `origin`

## 执行流程

### 第一步：获取当前状态

```bash
git branch --show-current
git status -sb
```

若无待提交改动，提示「当前没有可提交的改动」并结束。

---

### 第二步：确定变更范围

根据 `git status` 分析变更涉及的范围：
- `quwoquan_app/` 变更 → 执行端侧审计
- `quwoquan_service/` 变更 → 执行云侧审计
- 两者都有变更 → 执行全栈审计
- `specs/` 或 `changes/` 变更 → 执行特性树一致性检查（含 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md` 层级与分解遵从）

---

### 第三步：执行审计（按变更范围）

**3.1 端侧审计（如涉及 quwoquan_app/）**

```bash
cd quwoquan_app && flutter analyze
```

硬编码视觉字面量检查（仅检查本次变更的文件）：
```bash
git diff --name-only HEAD -- quwoquan_app/ | grep "\.dart$" | while read f; do
  # 对每个变更文件执行硬编码检查
done
```

**3.2 云侧审计（如涉及 quwoquan_service/）**

```bash
cd quwoquan_service && make gate
```

包含：
- metadata 一致性验证
- DDD 层级导入约束
- codegen 产物一致性
- 契约测试

**3.3 特性树审计（如涉及 specs/ 或 changes/）**

```bash
make verify
```

---

### 第四步：审计不通过 → 修复计划

1. **不执行任何提交**
2. 生成修复计划：
   - 每条违规：文件路径、行号、当前代码、违反规则、修复建议
   - 端侧违规引用 `02-dart-coding`
   - 云侧违规引用 `01-arch-constraints`
3. 等待用户批准后自动修复
4. 修复后重新执行审计直至通过

---

### 第五步：审计通过 → 提交推送

**5.1 总结变更**
```bash
git diff --stat HEAD
```

**5.2 分类提交**

根据变更范围生成 commit message（约定式 `feat:`/`fix:`/`chore:`）。
如同时涉及端云，优先使用描述业务变更的消息。

```bash
git add -A
git commit -m "<message>"
```

**5.3 推送**
```bash
git push origin <CURRENT_BRANCH>
```

**5.4 合入主干（如非 main 分支）**
```bash
git checkout main
git merge <CURRENT_BRANCH> -m "Merge branch '<CURRENT_BRANCH>'"
git push origin main
git checkout <CURRENT_BRANCH>
```

---

## 与原 /submit-with-audit 的关系

| 维度 | /submit-with-audit（旧） | /submit-with-gate（新） |
|------|------------------------|----------------------|
| 范围 | 仅端侧 quwoquan_app | 端云全栈 |
| 审计 | Flutter analyze + 硬编码检查 | 端侧语义 + 云侧 ArchUnit + metadata 同步 + 特性树 |
| 门禁 | 无 make gate | 包含 make gate / make gate-full |
| 位置 | quwoquan_app/.cursor/commands/ | 根目录 .cursor/commands/（全栈统一） |

端侧 `/submit-with-audit` 和 `/semantic-audit` 已废弃，统一使用 `/submit-with-gate`。
