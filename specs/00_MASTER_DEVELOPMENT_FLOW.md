# 端云一体化开发主线（Journey / Scenario 版）

> 本文档是整个项目开发的唯一主线。正式交付围绕 `L3_scenario` 实施，正式组合验收围绕 `L2_journey` 收口，正式测试只使用 `T1~T4`。

## 一、主流程

### 标准链路

```text
explore → prd → design → dev → verify → commit → deploy
                 └──────────── deliver（= dev + commit，dev 内含 verify/archive 闭环）────────────┘
```

AI Agent 执行 `/dev` 任务时，默认采用增强闭环：

```text
任务级 plan mode 审视 → 实施 → 自修复 → verify 等价检查 → archive 等价回写 → 等待 /commit
```

### 快捷链路

```text
explore → baseline → dev → verify → commit → deploy
```

仅适用于：需求边界、验收、商用约束已稳定，且方案明显收敛到现有模式或单一路径的场景。

### 原型链路

```text
try → land → commit → deploy
```

### 三层治理与流程映射

| 层级 | 作用 | 对应阶段 |
|------|------|---------|
| `L1_capability` | 能力边界、关键旅程、NFR、发布治理 | explore / prd / design / baseline / deploy |
| `L2_journey` | 端到端用户旅程、跨场景组合验收、发布 guardrails | explore / prd / design / baseline / verify / deploy |
| `L3_scenario` | 单环节场景、异常边界、最小实施与验证单元 | prd / design / baseline / dev / verify / commit |

## 二、非协商原则

- `spec-first`：先有规格，再有设计，再有实现。
- `acceptance-first`：先定义 `L2_journey` 与 `L3_scenario` 的验收，再进入实现。
- `metadata-first`：契约、字段、错误码、route、surface、operation 一律先改 metadata，再 codegen，再改业务逻辑。
- `env-seed-first`：涉及页面数据、Repository、人工 beta 或端云测试时，必须先补 `contracts/metadata/**/test_fixtures` 与 `_shared/test_fixtures/app_{alpha,beta,gamma}_seed_manifest.json`，再实现业务逻辑。
- `test-first`：进入 `/dev`、`/deliver`、`/try` 后默认执行 `Red → Green → Refactor`。
- `benchmark-driven`：对标必须落到“借鉴 / 不借鉴 / 适用边界 / 当前差距 / 收敛计划”。
- `commercial-ready-before-dev`：凡是用户可见、可灰度、可分享、可被小趣消费的能力，必须通过 `/prd` + `/design` 或 `/baseline` 冻结 `SLO/KPI`、权限边界、数据生命周期、迁移灰度与回滚方案。
- `single-source`：`tree_index.yaml`、`spec.md`、`design.md`、`acceptance.yaml`、`plan.yaml`、`specs/changelog/CR-*.yaml`、metadata 各自有唯一真相源。
- 缺少对标输入、真实网络条件、容量假设、权限边界或回滚条件时，直接 `GATE_BLOCK`。
- `dev-autonomy`：AI Agent 执行 `/dev` 时必须先进入任务级 plan mode，完整审视 spec/design/plan/acceptance/CR，自动补齐缺口后再实施。
- `full-commercial-closure`：`/dev` 不得以“完成部分切片”作为结束条件，必须把目标 scenario 所需的前后端、metadata/codegen、四层测试、验收证据与商用条件闭环到可归档状态。

## 三、阶段 Gate

### 3.1 `/explore`

必须完成：

- 映射需求归属的 `L1/L2/L3`
- 识别涉及的业务对象、metadata、扩展场景
- 识别对标输入、NFR、权限边界、数据生命周期、迁移与发布风险
- 判断本次增量是否需要新建或续写 `specs/changelog/CR-*.yaml`
- 输出初步 plan slice 方向，顺序必须是 `metadata -> codegen -> 业务逻辑 -> 测试`

输出要求：

- 已澄清事实
- 仍待澄清问题
- 建议归属的 `L1_capability / L2_journey / L3_scenario`
- 初步 plan slice 方向
- 受影响的 CR 范围
- `EXPLORE_READY` 或 `GATE_BLOCK`

禁止：

- 在 `/explore` 阶段实现代码
- 使用 `L4/L5` 表示树层级

### 3.2 `/prd`（G0）

进入 `/prd` 前必须同时满足：

- 目标用户、核心问题、范围边界、Out of Scope 清晰
- `L1/L2/L3` 与涉及业务对象已明确
- `journey_acceptance` / `scenario_acceptance` 可量化且映射 `T1~T4`
- 对标输入与不可打折的交互基线明确
- `SLO/KPI`、弱网、并发、性能、容量目标明确
- 若涉及小趣、权限、可见性或删除撤销，必须冻结权限边界、保留策略与撤销时效
- 若涉及创作、编辑、升级、删除、分享，必须冻结数据生命周期合同
- 若与已有 Journey/Scenario 重叠，必须冻结覆盖矩阵与优先级
- 若可灰度上线，必须冻结迁移方案、feature flag、观测指标与回滚条件
- 若涉及 `API path / operation / surface / route / decoder context`，必须明确 metadata 唯一真相源

产出物：

- `spec.md`
- `acceptance.yaml`
- 关联或新建 `specs/changelog/CR-*.yaml`
- 商用基线：`SLO/KPI`、权限边界、生命周期、覆盖矩阵、迁移灰度回滚

`spec.md` 最少包含：

- 背景与动机、目标用户、功能范围、Out of Scope
- 约束、对标输入与吸收结论、角色分工
- 既有 Journey/Scenario 覆盖矩阵、数据生命周期合同、权限与分享边界
- 非功能目标、迁移灰度与回滚要求、验收重点

任一项未满足：`GATE_BLOCK`

### 3.3 `/design`（G1）

进入 `/design` 前必须同时满足：

- `spec.md` 与 `acceptance.yaml` 已稳定，足以支撑设计
- 至少有 2 个方案可比较，且权衡清晰
- 选定方案覆盖 metadata/codegen、模型或字段演进、数据迁移/回填、feature flag、观测与回滚
- 若涉及小趣或私密内容，权限、撤销、保留模型已冻结
- `T1~T4` 证据矩阵已形成，`plan.yaml` 已能表达切片顺序与退出条件

自动执行 G1：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

产出物：

- `design.md`
- `plan.yaml`
- metadata / codegen 基线
- 测试证据矩阵
- 灰度发布设计

`design.md` 最少包含：

- 上游规格评审、方案对比与选型
- metadata/codegen 方案、字段演进与数据迁移方案
- feature flag、观测、SLO 验证与回滚方案
- `T1~T4` 证据矩阵与 plan slices
- 环境包配置、seed manifest、人工 beta 数据预置与生产禁 seed 边界

### 3.4 `/baseline`（G0 + G1）

进入 `/baseline` 前必须同时满足：

- `/explore` 已完成，且 `L1/L2/L3` 与涉及业务对象已明确
- `/prd` 的进入条件全部满足
- 需求边界、验收、商用约束足够稳定，不需要先单独冻结一次 `spec.md`
- 方案已明显收敛到现有模式或单一可行路径，不存在需要单独评审的重大架构分叉
- 已能直接形成 `design.md`、`plan.yaml` 与 `T1~T4` 证据矩阵

自动执行 G0 + G1：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

产出物：

- `spec.md`
- `acceptance.yaml`
- `design.md`
- `plan.yaml`
- 关联或新建 `specs/changelog/CR-*.yaml`
- metadata / codegen 基线
- 测试证据矩阵
- 灰度发布设计

若在执行中发现方案并未真正收敛：停止 `/baseline`，退回标准链路 `/prd` → `/design`。

### 3.5 `/dev`（G2）

进入 `/dev` 前必须满足：

- `design.md` 已冻结
- codegen 已通过
- `plan.yaml` 已就绪
- `acceptance.yaml` 可测量且映射 `T1~T4`
- 当前要实施的 slice 已绑定先行失败测试
- 对应 CR 已存在且明确受影响节点

每次会话实施顺序：

```text
1. 进入任务级 plan mode，读取 `spec.md`、`design.md`、`plan.yaml`、`acceptance.yaml` 与对应 CR
2. 审视前后端、metadata/codegen、权限、生命周期、灰度/回滚、观测与 `T1~T4` 缺口
3. 若规格、设计、切片、验收或商用条件存在缺口，先自动修复相关文档与计划
4. 派生覆盖全部未完成 slices 的会话 todo（仅本次会话有效）
5. 逐条 todo 执行 Red → Green → Refactor
6. 补齐目标 scenario 所需的前后端功能、配置、观测、权限、非功能验证与四层测试证据
7. 回填 `acceptance.yaml`、`plan.yaml` 与 CR 证据
8. 执行 verify 等价检查并修复所有 BLOCKING 项
9. 验证通过后自动执行 archive 等价回写
10. 停在待 `/commit` 状态
```

每完成一组 slice：

```bash
make -C quwoquan_service build
make -C quwoquan_service test-contract
```

若涉及 Flutter 变更，追加：

```bash
cd quwoquan_app && flutter test test/cloud/ test/components/ test/ui/ test/smoke/
make verify-app-mock-isolation
```

禁止：

- 只完成部分 slice、部分端或部分测试后就宣布 `/dev` 完成
- 明知验收、商用条件、灰度回滚、观测或四层测试未闭环，仍停止等待下一条指令
- 把原本应在 `/dev` 内自动修复的问题推迟到 `/commit`

### 3.6 `/verify`（G3）

- 检查 `L3_scenario` 完成度与 `scenario_acceptance` 闭环
- 检查 `L2_journey` 的组合验收是否因本次增量受影响
- 检查 `plan.yaml` 覆盖率、CR 影响项、`T1~T4` 证据
- 执行 `make gate-full`
- 当 `/dev` 已完成 verify 等价检查时，`/verify` 可作为显式复核或返工后的独立重跑命令

### 3.7 `/commit`（G4）

- 只提交已完成的 slice 与对应 CR 范围
- 提交前必须执行端侧 `T1/T2` 与仓库 `make gate`

```bash
cd quwoquan_app && flutter test test/cloud/ test/components/ test/ui/ test/smoke/
make verify-app-mock-isolation
make gate
```

- 若改动 **正式构建**（`app_pipeline`、上架脚本、`main_prod`、`APP_DATA_SOURCE`）：须审阅 **与 [`specs/gates/mock_data_cloud_integration_policy.md`](gates/mock_data_cloud_integration_policy.md) §5.1 R5 一致**（`--dart-define=APP_DATA_SOURCE=remote` 或等价约定）。
- 门禁、验收、证据、CR 更新状态全部闭环后才可提交

### 3.8 `/deploy`（G5）

- 先 integration，再灰度 prod
- 必须完成 `T3/T4`、SLO 卡点、观测确认与回滚演练
- 发布对象是 release batch / CR 范围，不再只看单个 Scenario
- 未达到 SLO 或回滚条件不清时不得放量
- **多环境统一口径**（alpha / beta / gamma / prod-gray / prod、波次推进）：[`deploy/shared/environment_matrix.md`](../deploy/shared/environment_matrix.md)

### 3.9 `/try`

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
- `L2_journey` 主要收口 `T3/T4`
- `L3_scenario` 主要收口 `T1/T2`，必要时补 `T3`
- `/deploy`、`/verify`、`/deliver`、`/commit` 文档只使用 `T1~T4`

## 五、单一真相源

- 特性树索引：`specs/feature-tree/tree_index.yaml`
- 规格：`spec.md`
- 设计：`design.md`
- 验收：`acceptance.yaml`
- 实施计划：`plan.yaml`
- 增量变更：`specs/changelog/CR-*.yaml`
- 契约与生成：`contracts/metadata/*`

禁止：

- 维护第二套树 taxonomy
- 维护第二套 operation/surface/route/path 规则表
- 用会话 todo 替代正式治理文档
- 让 `specs/changelog/` 长成第二套特性树

## 六、与命令文档的关系

以下文档必须与本主线保持一致：

- `.cursor/commands/explore.md`
- `.cursor/commands/baseline.md`
- `.cursor/commands/prd.md`
- `.cursor/commands/design.md`
- `.cursor/commands/dev.md`
- `.cursor/commands/verify.md`
- `.cursor/commands/archive.md`
- `.cursor/commands/commit.md`
- `.cursor/commands/deliver.md`
- `.cursor/commands/deploy.md`
- `.cursor/commands/try.md`
- `.cursor/commands/land.md`
