---
name: /design
id: design
category: Workflow
description: 设计基线（SDD 第二阶段：prd 完成后 → 方案决策 + 元数据基线 + codegen）
---

> SDD 主流程：explore → prd → **design** → dev → commit → deploy

## 阶段准入自检（Design Gate）

进入本阶段前，AI Agent **必须自检**以下问题。任何未澄清项 → 输出 `GATE_BLOCK`，暂停执行。

| # | 自检问题 | 通过条件 |
|---|---------|---------|
| D1 | spec.md 是否存在且稳定（不再有重大需求变更）？ | 目标节点的 spec.md 已写入 |
| D2 | acceptance.yaml A1~An 是否已定义（即使 status=pending）？ | 至少有 3 条可测量验收标准 |
| D3 | 设计约束是否已识别？ | 能列出 DDD 分层、metadata 范围、端云对齐要求 |
| D4 | 是否有 ≥2 个方案可供比较？ | 即使其中一个是"轻量方案/不做" |
| D5 | 与其他特性/服务的依赖是否已识别和解决？ | 无未解决的阻塞依赖 |
| D6 | 上游规格是否包含对标输入或已明确无需对标？ | 能说明参考对象、借鉴点与适用边界 |
| D7 | 是否完成 `A1~An ↔ T1~T4` 证据矩阵设计？ | 每条核心验收项都能落到测试责任 |
| D8 | 若涉实时性，是否定义一致性、顺序、幂等、重试、重连与弱网降级？ | 核心协议与恢复策略清晰 |
| D9 | 是否定义并发、容量、弹性、灰度、回滚与观测方案？ | 发布与增长风险可控 |
| D10 | 若涉及 operation / surface / route / path template，是否已明确 metadata 分层与 codegen 汇聚方案？ | 不再依赖代码 override 表或手写字符串常量 |

**任一未通过 → 输出 GATE_BLOCK：**

```
GATE_BLOCK（Design 准入未满足）：
□ D1: spec.md 不存在 → 先执行 /prd 完成需求规格
□ D3: 设计约束未明确 → 请先识别技术约束和业务约束
（列出所有未通过项）
```

---

## 两种执行模式

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| **create**（默认）| design.md、tasks.md 不存在 | 创建设计文档 + 元数据基线 + 代码生成 |
| **update** | design.md 已存在 | diff 现有设计，追加新决策变更，补充元数据变更，重新 codegen |

update 模式**不覆盖**已有内容：design 追加新决策，tasks 追加新任务（不改已完成标记），acceptance 追加新 An（不改已有编号）。

---

## 执行步骤

### 步骤 1：撰写 design.md

**设计原则**（强制）：
- 必须包含 ≥2 个方案对比，每个方案须标注优点、缺点、适用条件
- 必须有明确的选型决策，并给出理由
- 若采用轻量方案，**必须**写明未来演进路径
- 遵从业界最佳实践：先调研标杆，再权衡约束
- 必须先评审上游 `spec.md + acceptance.yaml` 是否足以支撑设计；若不足，先补阻断项

内容结构：

```markdown
# <特性标题> 设计方案

## 设计动因
<为什么需要设计这个，解决 spec.md 中哪些约束>

## 上游输入评审
<spec 是否清晰、acceptance 是否可测、哪些内容仍然阻断设计；若涉及 operation/surface/route，必须评审 metadata 承载边界是否清晰>

## 对标输入分析
<对标对象、借鉴点、不借鉴点、适用边界、当前差距>

## 方案对比

### 方案 A：<名称>
**优点**：...
**缺点**：...
**适用条件**：...

### 方案 B：<名称>
...

## 选型决策
**选定方案**：<方案 X>
**理由**：<简明理由>

## 关键设计决策
- 决策 1：...（已定，不变）
- 决策 2：...

## 元数据唯一源分层
<service.yaml 承载什么；ui_config.yaml / ui_surfaces.yaml 承载什么；禁止哪些代码位置再维护第二份表>

## TDD / ATDD 策略
<A1~An 如何先验收、各 Story 如何先写失败测试，再实现再重构>

## Story 与测试层映射
<L4 Story 如何划分；每个 Story 对应哪些 T1~T4 测试层>

## 角色职责与多重防护网
<产品负责规格与体验目标，架构负责方案与弹性，开发负责 TDD 落地，测试负责多层证据，发布负责灰度与回滚>

## 实时性与弱网设计
<时延目标、一致性模型、重试、断线恢复、弱网降级、可恢复提示>

## 并发性能与容量设计
<峰值假设、热点、防抖/限流、降级、扩容余量、性能预算>

## 灰度发布与回滚设计
<5/25/50/100 放量、观测指标、回滚阈值、人工/自动回滚条件>

## 未来演进
- 演进点 1：...（触发条件 / 时机）

## 遗留带规划任务
（若有取舍，记录未来要做的事，与 tasks.md「未来演进任务」对应）
```

---

### 步骤 2：撰写 tasks.md

**强制顺序**：metadata → codegen → 先写测试（Red）→ 业务逻辑（Green）→ 重构 → 补齐证据/发布约束

**语义要求**：`tasks.md` 描述的是 Story 的工程执行清单，不是新的树层级。

```markdown
# <特性> 任务列表

## 当前交付任务
- [ ] T1: [metadata] 创建/更新 contracts/metadata/{domain}/{entity}/*.yaml
- [ ] T2: [codegen] make verify-metadata && make codegen && make codegen-app
- [ ] T3: [测试] 为当前 Story 补齐 T1/T2/T3/T4 最小失败测试与验收证据骨架
- [ ] T4: [业务逻辑] 实现 domain service
- [ ] T5: [业务逻辑] 实现 application service
- [ ] T6: [业务逻辑] 实现 HTTP handler
- [ ] T7: [业务逻辑] 实现 Dart Repository + UI
- [ ] T8: [测试] 让先行测试转绿并补齐弱网/并发/体验/灰度证据

## 搁置任务（不在本次交付范围，但已识别，有重启条件）
<!-- 格式：- [ ] <描述>（重启条件：<条件>） -->

## 未来演进任务
<!-- 与 design.md 未来演进对应 -->
```

---

### 步骤 3：元数据基线执行

根据 Design Gate 识别的元数据意图，直接执行对应操作（无需用户另行运行 `/extend`）：

| 意图 | 对应操作 | 产出 |
|------|----------|------|
| 新建聚合根 | 创建 `contracts/metadata/{domain}/{agg}/` + 5 个 YAML 骨架 | aggregate/fields/storage/events/service |
| 新建独立实体 | 同上 | entity/fields/storage/events/service |
| 新建微服务 | 创建 `contracts/metadata/{domain}/` + `services/{name}-service/` | 完整服务骨架 |
| 新增 API 端点 | 更新 `service.yaml` api_routes | 新路由声明 |
| 新增字段 | 更新 `fields.yaml` | 字段定义 |
| 新增领域事件 | 更新 `events.yaml` | 事件声明 |
| 新增 ReadModel 投影 | 创建 `{entity}/projections/{name}.yaml` | 投影声明 |
| 新增错误码层 | 创建 `errors.yaml`（含 code/l10n_key/user_message.zh/en/go_const/dart_const） | 错误码声明；云侧用 generated.AppErrorFrom*，端侧用 *ErrorCode.fromCode().toDisplayMessage(l10n)；禁止硬编码 |
| 新增行为采集层 | 创建 `behaviors.yaml` | 行为事件 + 推荐特征 + 训练样本 |
| 新增隐私策略层 | 创建 `privacy.yaml` | PII 日志策略 + 数据生命周期 |
| 新增端侧配置层 | 创建 `ui_config.yaml` | tab/布局/feature flags/空状态 |
| 新增 surface / route 契约层 | 更新 `ui_config.yaml` 或创建 `ui_surfaces.yaml` | `surface_id/route_id/path_template/binds_operations` |
| 新增三层测试契约 | 创建 `tests/mock.yaml + contract.yaml + e2e.yaml` | 测试场景声明 |
| 新增向量能力 | 更新 `aggregate.yaml` + 创建 `_vectors/{name}.yaml` | 向量索引声明 |
| 新增缓存层 | 更新 `aggregate.yaml` + `storage.yaml` | Redis 缓存配置 |
| 修改 PA 输出契约字段 | 使用 `/extend pa-contract`（见 S26）更新 AssistantTurnOutput + prompt 模板 + output_contracts.json | 类型化 DTO 同步更新，版本≤2 |
| 无元数据变更 | 跳过本步骤 | — |

多意图组合：一个特性可包含多个意图，按上表顺序逐一执行（统一在步骤 4 一次性验证）。

**骨架内容标准**：从同类已有 YAML 继承结构，预填已知字段，留 TODO 标记待补充项，禁止空文件。

**设计阶段新增硬要求**：
- 若 `acceptance.yaml.non_functional_acceptance.realtime.enabled=true`，必须设计顺序一致性、幂等、重试、重连与弱网体验
- 若存在高增长或热点场景，必须设计容量假设、限流/降级、扩容与观测方案
- 若有对标对象，必须写清“借鉴什么、不借鉴什么、当前差距如何收敛”
- 若发现 Repository、Router、decoder context 仍依赖硬编码字符串，必须在 design 中给出 metadata 收口位置与 semantic gate 方案

---

### 步骤 4：G1 — Verify + Codegen（自动执行，一次性）

步骤 1+2+3 全部完成后，AI Agent **必须立即自动执行**：

```bash
make verify-metadata           # metadata 内部一致性（含新增 YAML 格式校验）
make codegen                   # 云侧代码生成（Go struct/repo/routes/errors）
make codegen-app               # 端侧代码生成（Dart DTO/错误码/行为tracker/ui配置）
# 若涉及 rec-model-service：
# make codegen-rec-model-python  # Python 特征 schema 生成
```

**任一失败 → 停止 + 输出错误 + 修复建议 → 修复后重跑步骤 4。**

---

### 步骤 5：输出设计完成摘要

```
设计基线完成：<feature-path>

design.md：
  方案：<N 个对比，选定方案 X>
  关键决策：<N 条>
  未来演进：<N 条>

tasks.md：
  当前交付任务：<N 条>
  顺序：metadata → codegen → 测试先行 → 业务逻辑 → 重构/证据补齐

元数据变更：
  ✓ <变更1>（如：新建 contracts/metadata/content/post/errors.yaml）
  ...

代码生成：
  ✓ make verify-metadata PASS
  ✓ make codegen PASS  → <生成文件列表>
  ✓ make codegen-app PASS  → <生成文件列表>

下一步：/dev <feature-path>（逐 task 按 TDD 实施）
      或 /deliver <feature-path>（验收驱动 + TDD 一气呵成）
```

---

## 与其他命令的关系

| 命令 | 职责 | 时机 |
|------|------|------|
| `/prd` | 需求规格基线（spec + acceptance 草稿） | design 前 |
| `/design` | **设计决策 + metadata 基线 + codegen** | prd 完成后 |
| `/extend` | 实施阶段增量扩展（新增字段/事件/端点等） | dev 过程中发现需要扩展时 |
| `/dev` | 逐 task 实施，每 task 后 G2 卡点 | design 完成后 |
| `/deliver` | 验收驱动：dev + commit 一气呵成 | design 完成后（推荐） |
