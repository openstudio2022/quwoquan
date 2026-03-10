# 端云一体化开发主线（三层目录版）

> **本文档是整个项目开发的唯一主线。**
>
> 本主线与特性树三层目录模型绑定：
>
> - `L1_capability`
> - `L2_feature`
> - `L3_story`
>
> `Task` 保持为执行清单，不进入目录层级。

---

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

---

## 二、核心原则

- `spec-first`：先有规格，再有设计，再有实现。
- `acceptance-first`：先定义 `A1~An`，再做实现。
- `test-first`：默认执行 Red → Green → Refactor。
- `metadata-first`：涉及契约、字段、接口、错误码时，先改 metadata，再 codegen，再改业务逻辑。
- `three-level-directory-only`：仓库治理树只接受 `L1/L2_feature/L3_story` 三层目录，不再兼容旧层级。
- `tree-test-decoupling`：树层表达交付对象，测试层只用 `T1~T4`。
- `single-source`：`tree_index.yaml`、四件套、任务文件各自有唯一真相源，不再维护第二套映射表。

---

## 三、各阶段说明

### 3.1 `/explore`

职责：

- 确认需求归属的 `L1_capability`
- 判断是否应建立或更新某个 `L2_feature`
- 判断目标 `L3_story`
- 给出初步 Task 拆解方向
- 识别对标输入、NFR 风险、角色边界、发布风险

输出要求：

- 已澄清事实
- 仍待澄清问题
- 建议归属的 `L1/L2/L3`
- 初步 Task 方向
- `EXPLORE_READY` 或 `GATE_BLOCK`

禁止：

- 在 explore 阶段实现代码
- 使用 `L4/L5` 作为树层级表述

### 3.2 `/prd`

职责：

- 创建或更新 `L3_story`
- 撰写 `spec.md`
- 撰写 `acceptance.yaml`

PRD Gate 要点：

- 是否能说清目标用户和核心问题
- 是否已明确 `L1/L2`
- 是否至少有 3 条可量化验收项
- 是否已明确 Out of Scope
- 是否已明确 `T1~T4` 测试层映射

### 3.3 `/design`

职责：

- 为 `L3_story` 提供方案对比与选型
- 形成 `design.md`
- 形成 Task 执行清单
- 完成 metadata/codegen 基线

Design Gate 要点：

- 上游 `spec.md + acceptance.yaml` 是否足以支撑设计
- 是否至少有 2 个方案
- 是否已识别约束、依赖、测试策略和回滚策略

### 3.4 `/dev`

职责：

- 以 `L3_story` 为唯一实施单位
- 逐项完成 Task
- 执行 Red → Green → Refactor
- 更新 `acceptance.yaml` 中对应验收项的测试证据

Dev Gate 要点：

- `design.md` 已冻结
- codegen 已通过
- `tasks.md` 已就绪
- `acceptance.yaml` 可测量且映射 `T1~T4`

### 3.5 `/verify`

职责：

- 验证 `L3_story` 完成度
- 检查 Task 是否收口
- 检查 `acceptance.yaml` 是否闭环
- 执行 gate

### 3.6 `/commit`

职责：

- 提交已完成的 `L3_story`
- 保证门禁、验收、证据、归档状态已闭环

### 3.7 `/deploy`

职责：

- 部署到 integration / staging
- 执行 `T3` 端云集成验证
- 执行 `T4` 端到端旅程验证
- 满足 SLO 后进入生产放量或发布

注意：

- 不再使用 `L3/L4` 表示测试层
- 测试层统一为 `T1~T4`

---

## 四、测试层统一口径

测试层只有以下四层：

| 测试层 | 作用 |
|--------|------|
| `T1` | 契约与静态校验 |
| `T2` | 模块与交互验证 |
| `T3` | 端云集成验证 |
| `T4` | 端到端旅程验证 |

原则：

- 特性树层级不用 `L3/L4` 表示测试
- deploy、verify、deliver、commit 文档必须只使用 `T1~T4`

---

## 五、门禁要求

### 开发期

- `make verify`：治理文档、特性树、契约与结构校验
- `make codegen`：云侧代码生成
- `make codegen-app`：端侧代码生成
- `make build`：编译校验
- `make test-contract`：契约与服务测试

### 收口期

- `make gate`：本地合入前门禁
- `make gate-full`：完整验证门禁

门禁必须保证：

- 不存在旧层级
- 不存在旧目录深度
- `tree_index.yaml` 与目录一致
- `acceptance.yaml` 结构与 level 合法

---

## 六、目录与真相源

### 唯一真相源

- 特性树索引：`specs/feature-tree/tree_index.yaml`
- 规格：`spec.md`
- 设计：`design.md`
- 任务：`tasks.md` / `tasks.yaml`
- 验收：`acceptance.yaml`

### 禁止

- 维护第二套树 taxonomy
- 在脚手架和门禁中继续保留旧层级
- 用测试执行桶替代正式测试治理语言

---

## 七、与命令文档的关系

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

---

## 八、总结

仓库的正式开发治理模型是：

```text
L1_capability
  └── L2_feature
        └── L3_story
              └── Task（非目录层）
```

开发主线围绕 `L3_story` 运作，测试围绕 `T1~T4` 运作。  
这两套模型从现在开始彻底解耦，不再共享 `L*` 术语。
