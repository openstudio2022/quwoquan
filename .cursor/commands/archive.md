---
name: /archive
id: archive
category: Workflow
description: 兼容归档入口（/dev 验证通过后默认自动归档；本命令仅用于手动补归档或修复）
---

> 标准流：`/dev` 在验证通过后自动完成 archive 等价回写，随后等待 `/commit`。本命令仅用于兼容记录流程、手动补归档或修复回写。

## 使用场景

- `/dev` 已完成，但因中断或记录流程导致归档未回写
- 需要单独修复 `acceptance.yaml.archived` 或 `tree_index.status`
- `/land` 需要复用归档等价逻辑

标准交付流中，**无需单独执行 `/archive`**。

---

## 前置条件检查（执行前必须满足）

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 目标节点四类文档齐全 | spec.md、design.md、plan.yaml、acceptance.yaml 均存在 |
| 2 | plan 已收口 | plan.yaml 中目标 slice 均已完成 |
| 3 | acceptance 无 pending | acceptance.yaml 所有 A1~An 的 status ≠ `pending`（须为 implemented/waived/deferred） |
| 4 | acceptance tests 链接有效 | status=`implemented` 的 An 的 `tests[]` 文件在仓库中存在（gate 自动验证） |
| 5 | 基线漂移已处理 | `/verify` 漂移报告中无 BLOCKING 项（D1 SPEC_DRIFT、D2 IMPL_DRIFT、D3 DESIGN_DRIFT 已解决） |
| 6 | gate-full 通过 | `make gate-full` 全部通过，含特性树一致性检查 |
| 7 | 非功能验收已闭环 | 实时性 / 弱网 / 并发 / 容量 / 弹性 / 对标体验等要求已有证据 |
| 8 | 灰度生产条件已闭环 | 观测指标、放量步进、回滚阈值已写入并可执行 |

**若不满足**：不执行归档；输出补全列表：

```
前置条件不满足，请先完成以下项后再执行 /archive：

□ [ ] 四类文档齐全：spec.md、design.md、plan.yaml、acceptance.yaml（见 00_FEATURE_TREE_STANDARD.md）
□ [ ] plan 当前交付切片已完成：plan.yaml 中目标 slice 已完成；未完成项请先执行 /dev
□ [ ] acceptance 无 pending：所有 A1~An status 改为 implemented/waived/deferred
□ [ ] acceptance tests 链接有效：status=implemented 的 An 的 tests[].file 已写入实际测试文件路径
□ [ ] 漂移已处理：执行 /verify，解决所有 BLOCKING 漂移项（SPEC/IMPL/DESIGN drift）
□ [ ] gate-full 通过：执行 make gate-full，修复所有失败项
□ [ ] 非功能验收闭环：补齐实时性/弱网/并发/弹性/体验证据
□ [ ] 灰度生产闭环：补齐 SLO、放量、回滚条件与观测项

补全后重新执行：/dev（自动 verify + archive）或 `/verify` → `/archive`
```

---

## 步骤

### 1. 完成度与漂移检查

1. 确认目标节点具备四类文档（标准见 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`）
2. 校验 `plan.yaml` 目标 slices 已完成
3. 校验 `acceptance.yaml` 所有 A1~An status ≠ pending
4. 校验 `acceptance.yaml` 中核心验收项已声明 `test_layers`（`T1~T4`）
5. 读取 `acceptance.yaml` 中 `tests[]`，逐一确认文件存在
6. 确认已执行 `/verify` 并无 BLOCKING 漂移项
7. 若存在 `non_functional_acceptance`，校验其实时性 / 弱网 / 并发 / 弹性 / 灰度字段已补齐
8. 校验 `design.md` 中灰度发布、回滚、观测与容量策略已落表

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
- 非功能验收完整性（实时性 / 弱网 / 并发 / 弹性 / 体验 / 灰度）

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
| 当前交付切片 | N/N 完成                             |
| 验收项       | implemented N，waived N，deferred N   |
| 漂移         | SPEC 0，IMPL 0，DESIGN 0，TASK N(warning) |
| 门禁         | make gate-full PASS                  |
| 非功能验收   | realtime/weak-network/perf/elasticity PASS |
| 灰度条件     | steps/SLO/rollback READY             |
| 计划切片     | N 项，已在 plan.yaml 映射             |
| CR           | revision N，delta 已记录               |

下一步：/commit（提交代码入库）
```

---

## 与其他命令的关系

| 命令 | 职责 | 与 /archive 关系 |
|------|------|----------------|
| `/verify` | 漂移检测 + gate-full | 手动补归档时的常见前置；标准流通常由 `/dev` 内置完成 |
| `/archive` | **兼容补归档**：G3 + 回写状态 | 非标准流程，仅修复时使用 |
| `/commit` | 提交入库 | commit 以前提是 `/dev` 已自动归档；发现缺口时可兜底执行 archive 等价逻辑 |
| `/deliver` | dev + commit 一气呵成 | deliver 复用 `/dev` 的自动 verify / archive，不单独调用 archive |
