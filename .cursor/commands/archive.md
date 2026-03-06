---
name: /archive
id: archive
category: Workflow
description: 归档特性（自动 G3 全量门禁 + 回写特性树状态）
---

> SDD 主流程：... → dev → **archive** → commit → deploy

## 前置条件检查（执行前必须满足）

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 目标节点四类文档齐全 | spec.md、design.md、tasks.md、acceptance.yaml 均存在 |
| 2 | tasks 已完成 | tasks.md 中**当前交付任务**均已标记完成（搁置/演进任务可保留 `[ ]`） |
| 3 | acceptance 无 pending | acceptance.yaml 所有 A1~An 的 status ≠ `pending`（须为 implemented/waived/deferred） |
| 4 | acceptance tests 链接有效 | status=`implemented` 的 An 的 `tests[]` 文件在仓库中存在（gate 自动验证） |
| 5 | 基线漂移已处理 | `/verify` 漂移报告中无 BLOCKING 项（D1 SPEC_DRIFT、D2 IMPL_DRIFT、D3 DESIGN_DRIFT 已解决） |
| 6 | gate-full 通过 | `make gate-full` 全部通过，含特性树一致性检查 |

**若不满足**：不执行归档；输出补全列表：

```
前置条件不满足，请先完成以下项后再执行 /archive：

□ [ ] 四类文档齐全：spec.md、design.md、tasks.md、acceptance.yaml（见 00_FEATURE_TREE_STANDARD.md）
□ [ ] tasks 当前交付任务已完成：tasks.md 中当前交付任务全部 [x]；未完成项请先执行 /dev
□ [ ] acceptance 无 pending：所有 A1~An status 改为 implemented/waived/deferred
□ [ ] acceptance tests 链接有效：status=implemented 的 An 的 tests[].file 已写入实际测试文件路径
□ [ ] 漂移已处理：执行 /verify，解决所有 BLOCKING 漂移项（SPEC/IMPL/DESIGN drift）
□ [ ] gate-full 通过：执行 make gate-full，修复所有失败项

补全后重新执行：/verify → /archive
```

---

## 步骤

### 1. 完成度与漂移检查

1. 确认目标节点具备四类文档（标准见 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`）
2. 校验 `tasks.md` 当前交付任务全部 `[x]`（搁置/演进任务可保留 `[ ]`）
3. 校验 `acceptance.yaml` 所有 A1~An status ≠ pending
4. 读取 `acceptance.yaml` 中 `tests[]`，逐一确认文件存在
5. 确认已执行 `/verify` 并无 BLOCKING 漂移项

### 2. 自动 G3 卡点：全量门禁

AI Agent **必须自动执行**：

```bash
make gate-full
```

包含：
- metadata 一致性验证
- DDD 结构约束 + codegen hash 比对
- 端侧语义审计（flutter analyze + 硬编码检查）
- 云侧契约测试
- 特性树一致性（四类文档存在性 + acceptance status 不含 pending + tests[] 文件存在）

**任一失败 → 停止归档 → 输出错误 + 修复建议 → 修复后重跑。**

### 3. 归档（回写 tree_index + acceptance）

G3 通过后，AI Agent **必须回写以下两处**：

**3a. 更新 `acceptance.yaml` 顶层**：

```yaml
archived: true
archived_at: <ISO8601 当前时间>
```

**3b. 更新 `specs/feature-tree/tree_index.yaml`**：

```yaml
status: completed
```

（若节点在 tree_index 中找不到 → 输出 WARNING 并提示手动添加。）

4. 生成归档报告：

```
归档报告：<feature-path>

| 维度         | 结果                                  |
|--------------|---------------------------------------|
| 当前交付任务 | N/N 完成                             |
| 验收项       | implemented N，waived N，deferred N   |
| 漂移         | SPEC 0，IMPL 0，DESIGN 0，TASK N(warning) |
| 门禁         | make gate-full PASS                  |
| 搁置任务     | N 项，重启条件已记录                   |
| 演进任务     | N 项，已在 design.md 映射             |

下一步：/commit（提交代码入库）
```

---

## 与其他命令的关系

| 命令 | 职责 | 与 /archive 关系 |
|------|------|----------------|
| `/verify` | 漂移检测 + gate-full | archive 的前置（推荐先 verify 再 archive） |
| `/archive` | **归档**：G3 + 回写状态 | 独立归档，不提交代码 |
| `/commit` | 归档 + 提交入库 | commit 的阶段 1 等价于 archive |
| `/deliver` | dev + archive + commit 一气呵成 | deliver 的阶段 3 等价于 archive |
