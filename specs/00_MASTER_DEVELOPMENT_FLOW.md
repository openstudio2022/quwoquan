# 端云一体化开发主线（三层目录版）

> 本文档是整个项目开发的唯一主线。正式交付围绕 `L3_story` 运作，正式测试只使用 `T1~T4`。

## 一、主流程

### 标准链路

```text
explore → prd → design → dev → commit → deploy
                 └────── deliver（= dev + commit）──────┘
```

### 原型链路

```text
try → land → commit → deploy
```

### 三层治理与流程映射

| 层级 | 作用 | 对应阶段 |
|------|------|---------|
| `L1_capability` | 能力边界、关键旅程、NFR、发布治理 | explore / prd / design / deploy |
| `L2_feature` | 稳定业务特性容器 | explore / prd / design |
| `L3_story` | 最小交付、最小验收、最小归档单元 | prd / design / dev / verify / commit |

## 二、非协商原则

- `spec-first`：先有规格，再有设计，再有实现。
- `acceptance-first`：先定义 `A1~An` 和 `T1~T4`，再进入实现。
- `metadata-first`：契约、字段、错误码、route、surface、operation 一律先改 metadata，再 codegen，再改业务逻辑。
- `test-first`：进入 `/dev`、`/deliver`、`/try` 后默认执行 `Red → Green → Refactor`。
- `benchmark-driven`：对标必须落到“借鉴 / 不借鉴 / 适用边界 / 当前差距 / 收敛计划”。
- `commercial-ready-before-dev`：凡是用户可见、可灰度、可分享、可被小趣消费的能力，`/prd` 与 `/design` 必须冻结 `SLO/KPI`、权限边界、数据生命周期、迁移灰度与回滚方案。
- `single-source`：`tree_index.yaml`、`spec.md`、`design.md`、`tasks.md`、`acceptance.yaml`、metadata 各自有唯一真相源。
- 缺少对标输入、真实网络条件、容量假设、权限边界或回滚条件时，直接 `GATE_BLOCK`。

## 三、阶段 Gate

### 3.1 `/explore`

必须完成：

- 映射需求归属的 `L1/L2/L3`
- 识别涉及的业务对象、metadata、扩展场景
- 识别对标输入、NFR、权限边界、数据生命周期、迁移与发布风险
- 输出初步 Task 方向，顺序必须是 `metadata -> codegen -> 业务逻辑 -> 测试`

输出要求：

- 已澄清事实
- 仍待澄清问题
- 建议归属的 `L1/L2/L3`
- 初步 Task 方向
- `EXPLORE_READY` 或 `GATE_BLOCK`

禁止：

- 在 `/explore` 阶段实现代码
- 使用 `L4/L5` 表示树层级

### 3.2 `/prd`（G0）

进入 `/prd` 前必须同时满足：

- 目标用户、核心问题、范围边界、Out of Scope 清晰
- `L1/L2/L3` 与涉及业务对象已明确
- `A1~An` 可量化且映射 `T1~T4`
- 对标输入与不可打折的交互基线明确
- `SLO/KPI`、弱网、并发、性能、容量目标明确
- 若涉及小趣、权限、可见性或删除撤销，必须冻结权限边界、保留策略与撤销时效
- 若涉及创作、编辑、升级、删除、分享，必须冻结数据生命周期合同
- 若与已有 Story 重叠，必须冻结覆盖矩阵与优先级
- 若可灰度上线，必须冻结迁移方案、feature flag、观测指标与回滚条件
- 若涉及 `API path / operation / surface / route / decoder context`，必须明确 metadata 唯一真相源

产出物：

- `spec.md`
- `acceptance.yaml`
- 商用基线：`SLO/KPI`、权限边界、生命周期、覆盖矩阵、迁移灰度回滚

`spec.md` 最少包含：

- 背景与动机、目标用户、功能范围、Out of Scope
- 约束、对标输入与吸收结论、角色分工
- 既有 Story 覆盖矩阵、数据生命周期合同、权限与分享边界
- 非功能目标、迁移灰度与回滚要求、验收重点

任一项未满足：`GATE_BLOCK`

### 3.3 `/design`（G1）

进入 `/design` 前必须同时满足：

- `spec.md` 与 `acceptance.yaml` 已稳定，足以支撑设计
- 至少有 2 个方案可比较，且权衡清晰
- 选定方案覆盖 metadata/codegen、模型或字段演进、数据迁移/回填、feature flag、观测与回滚
- 若涉及小趣或私密内容，权限、撤销、保留模型已冻结
- `T1~T4` 证据矩阵已形成，当前 task 已绑定 Red 测试
- `tasks.md` 顺序明确，且遵循 `metadata -> codegen -> 业务逻辑 -> 测试`

自动执行 G1：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

产出物：

- `design.md`
- `tasks.md`
- metadata / codegen 基线
- 测试证据矩阵
- 灰度发布设计

`design.md` 最少包含：

- 上游规格评审、方案对比与选型
- metadata/codegen 方案、字段演进与数据迁移方案
- feature flag、观测、SLO 验证与回滚方案
- `T1~T4` 证据矩阵与任务拆解

### 3.4 `/dev`（G2/G3）

进入 `/dev` 前必须满足：

- `design.md` 已冻结
- codegen 已通过
- `tasks.md` 已就绪
- `acceptance.yaml` 可测量且映射 `T1~T4`
- 当前 task 已绑定先行失败测试

每完成一个 task：

```bash
make -C quwoquan_service build
make -C quwoquan_service test-contract
```

全部 task 完成后必须执行：

```bash
make gate-full
```

收口要求：

- `T1~T4` 证据齐全
- 非功能验收齐全
- 已达到 gray-release ready
- 自动回写归档状态

### 3.5 `/verify`

- 检查 `L3_story` 完成度与 `acceptance.yaml` 闭环
- 执行 `make gate-full`
- 作为标准流程的独立复核或补救入口

### 3.6 `/commit`（G4）

- 只提交已完成的 `L3_story`
- 提交前必须执行端侧 `L1` 与仓库 `L2` 门禁

```bash
cd quwoquan_app && flutter test test/cloud/ test/components/ test/ui/
make gate
```

- 门禁、验收、证据、归档状态全部闭环后才可提交

### 3.7 `/deploy`（G5）

- 先 integration，再灰度 prod
- 必须完成 `T3/T4`、SLO 卡点、观测确认与回滚演练
- 未达到 SLO 或回滚条件不清时不得放量

### 3.8 `/try`

- 不要求创建特性树节点
- 其余约束一条不豁免
- 至少验证一个高风险维度：弱网 / 回滚 / 重连 / 并发 / 对标差异
- 验证成功后执行 `/land`

## 四、测试层统一口径

| 测试层 | 作用 |
|--------|------|
| `T1` | 契约与静态校验 |
| `T2` | 模块与交互验证 |
| `T3` | 端云集成验证 |
| `T4` | 端到端旅程验证 |

规则：

- 特性树层级不用 `L3/L4` 表示测试
- `/deploy`、`/verify`、`/deliver`、`/commit` 文档只使用 `T1~T4`

## 五、单一真相源

- 特性树索引：`specs/feature-tree/tree_index.yaml`
- 规格：`spec.md`
- 设计：`design.md`
- 任务：`tasks.md` / `tasks.yaml`
- 验收：`acceptance.yaml`
- 契约与生成：`contracts/metadata/*`

禁止：

- 维护第二套树 taxonomy
- 维护第二套 operation/surface/route/path 规则表
- 用测试执行桶替代正式测试治理语言

## 六、与命令文档的关系

以下文档必须与本主线保持一致：

- `.cursor/commands/explore.md`
- `.cursor/commands/prd.md`
- `.cursor/commands/design.md`
- `.cursor/commands/dev.md`
- `.cursor/commands/verify.md`
- `.cursor/commands/commit.md`
- `.cursor/commands/deliver.md`
- `.cursor/commands/deploy.md`
- `.cursor/commands/try.md`
- `.cursor/commands/land.md`
