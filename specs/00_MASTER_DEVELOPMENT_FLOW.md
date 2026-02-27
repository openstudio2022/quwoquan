# 端云一体化开发主线（唯一主线文档）

> **本文档是整个项目开发的唯一主线**。所有 rules、commands、specs 从此文档索引。
> 不要看其它文档来理解开发流程 — 本文档即全貌。

---

## 一、开发流水线（5 个阶段 × 自动卡点）

```
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │  Plan    │───▶│  Create  │───▶│ Implement│───▶│  Verify  │───▶│  Submit  │
  │(需求澄清) │    │(特性创建) │    │ (实施)   │    │ (验收)   │    │ (提交)   │
  └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘
       │               │               │               │               │
   ┌───┴───┐       ┌───┴───┐       ┌───┴───┐       ┌───┴───┐       ┌───┴───┐
   │ AUTO  │       │ AUTO  │       │ AUTO  │       │ AUTO  │       │ AUTO  │
   │ GATE  │       │ GATE  │       │ GATE  │       │ GATE  │       │ GATE  │
   │  G0   │       │  G1   │       │  G2   │       │  G3   │       │  G4   │
   └───────┘       └───────┘       └───────┘       └───────┘       └───────┘
```

每个阶段结束时 AI Agent **自动执行**对应卡点，不需要人为触发。

---

## 二、各阶段详解

### 阶段 1：Plan（需求澄清与任务规划）

**入口**：用户提出需求（ask/plan 模式自动激活约束）

**AI Agent 必须做的事**：
1. 确认需求属于哪个特性树节点（`specs/feature-tree/`）
2. 确认涉及哪些业务对象（查 `contracts/metadata/`）
3. 确认涉及哪些扩展场景（S01~S20，见附录 A）
4. 生成任务拆解，强制顺序：metadata → codegen → 业务逻辑 → 测试
5. **特性树分解遵从**：节点归属与新建须符合 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`（L4 默认叶子，L5 仅当 L4 需 subtask 分解时使用）

**自动卡点 G0**：
```
✓ 需求已映射到特性树节点
✓ 涉及的业务对象已在 metadata 注册（或标记为需新建）
✓ 任务拆解遵循 metadata-first 顺序
✓ 如涉及新实体/字段/事件 → 任务首项必须是更新 metadata
✓ 特性树分解符合层级定义（见 01_FEATURE_TREE_LEVEL_DEFINITIONS.md 一、二）
```

**使用命令**：`/opsx-explore`（思考）→ `/opsx-ff`（创建特性）

---

### 阶段 2：Create（特性创建与 metadata 就绪）

**入口**：`/opsx-ff` 或 `/qwq-extend`

**AI Agent 必须做的事**：
1. 创建/更新特性目录，**仅使用四类文档**：`spec.md`、`design.md`、`tasks.md`、`acceptance.yaml`；禁止在节点下生成 analysis-*.md、README、独立规划书等（详见 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`）。**design 须遵循设计原则**：业界最佳实践与标杆对比、多备选方案对比、选定最优或可演进到最优；若采用轻量方案，design 与 tasks 中必须写明未来演进与遗留带规划任务。
2. **特性树层级与分解**：新建节点路径与层级须符合 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`；`acceptance.yaml` 的 `level` 使用统一取值（L2_feature / L3_subfeature / L4_object_task / L5 或 L5_subtask）；同步更新对应 L1 的 `tree.yaml` 及 `tree_index.yaml`（若使用）。
3. 如需新建业务对象 → 执行 `/qwq-extend new-aggregate|entity|service`
4. 如需扩展已有对象 → 执行 `/qwq-extend add-field|capability|event|...`
5. 更新 metadata YAML（5 文件一组）
6. **自动执行** `make verify`

**自动卡点 G1**：
```bash
# /opsx-ff 和 /qwq-extend 命令执行完毕后自动运行：
make verify-metadata           # 或 make verify：metadata 内部一致性（quwoquan_service 当前为 verify-metadata）
make codegen                   # 从 metadata 生成 Go 骨架代码
make codegen-app               # 从 metadata 生成端侧代码
# 若涉及 rec-model-service（推荐平台下模型服务，Python）：
make codegen-rec-model-python  # 生成 Pydantic 模型与 FastAPI 路由骨架至 services/rec-model-service/generated
```
失败 → 停止，输出错误 + 修复建议，修复后重新执行。

---

### 阶段 3：Implement（实施）

**入口**：`/opsx-apply`

**AI Agent 必须做的事**：
1. 按 `tasks.md` 逐项实施（任务与特性树节点对应：L4 节点下 task 对应 L4 范围；若有 L5 子节点，子任务可分组或由 L5 节点 tasks 承载，见 `01_FEATURE_TREE_LEVEL_DEFINITIONS.md` 八、8.3）
2. 仅在非 codegen 区域手写业务逻辑（domain_service / application_service / feature pages）
3. 遵从 DDD 层级约束（domain 禁止 import infrastructure）
4. 遵从设计系统（Dart 禁止硬编码字面量）
5. 遵从 runtime 统一能力（禁止绕过 runtime/errors、runtime/config 等）
6. **每完成一个 task 自动执行**契约测试

**自动卡点 G2**（每个 task 完成后）：
```bash
# /opsx-apply 每完成一个 task 后自动运行：
make build                     # 编译通过
make test-contract             # 契约测试通过（真实数据库）
# 端侧变更时追加：
flutter test test/cloud/ test/components/ test/ui/  # L1a+L1b+L1c
```
失败 → 停止当前 task，输出错误 + 修复建议。

**结构约束**（rules 实时强制）：

| 端 | 约束 | 规则来源 |
|----|------|---------|
| Go | domain 禁止 import application/adapters/infrastructure | `01-arch-constraints` |
| Go | 禁止直接 import 数据库驱动（仅 infrastructure 允许） | `01-arch-constraints` |
| Go | 必须使用 runtime/errors、runtime/config、runtime/messaging | `01-arch-constraints` |
| Go | codegen 文件（`DO NOT EDIT`）禁止手动修改 | `01-arch-constraints` |
| Dart | 禁止硬编码 fontSize/EdgeInsets/Color/BorderRadius | `02-dart-coding` |
| Dart | 禁止相对路径 import，必须用 package: | `02-dart-coding` |
| Dart | Feature 禁止直接 import 其他 Feature 内部文件 | `02-dart-coding` |
| 端云 | Go struct / Dart DTO / OpenAPI / Migration 必须与 metadata 一致 | `01-arch-constraints` |

---

### 阶段 4：Verify（验收）

**入口**：`/opsx-verify` 或 `/fullstack-audit`

**AI Agent 必须做的事**：
1. 确认所有 tasks.md 任务已完成
2. 确认 acceptance.yaml A1~A8 全部满足
3. **特性树一致性**：tree.yaml ↔ 目录 ↔ 四类文档；acceptance 的 level 与 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md` 约定一致
4. **自动执行** 全栈审计 + 门禁

**自动卡点 G3**：
```bash
# /opsx-verify 或 /opsx-archive 自动运行全量门禁：
make gate-full
```

`make gate-full` 内含（全部必须通过）：

| 检查项 | 说明 |
|-------|------|
| `verify_metadata_internal` | metadata YAML 内部交叉引用 |
| `verify_arch_constraints` | DDD 导入 + 数据库隔离 + runtime 统一 |
| `verify_codegen_hashes` | codegen 产物 hash 比对（防手改） |
| `verify_dart_semantic` | 硬编码字面量 + 包引用 + Feature 隔离 |
| `verify_feature_tree` | tree.yaml ↔ 目录 + acceptance 完整性；特性树层级与分解须符合 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md` |
| `flutter analyze` | Dart 静态分析 |
| `go build ./...` | Go 编译 |
| `make test-contract` | 契约测试（真实数据库） |
| `flutter test test/cloud/ test/components/ test/ui/` | L1a+L1b+L1c 端侧测试（路径规则见 `03-testing.mdc §3`） |

---

### 阶段 5：Submit（提交合入）

**入口**：`/submit-with-gate`

**AI Agent 必须做的事**：
1. 分析 `git status` 确定变更范围
2. **自动执行** 按变更范围的针对性审计
3. 通过后自动 commit → push → merge main

**自动卡点 G4**：
```
git status → 分析变更范围
├── quwoquan_app/ 变更 → 端侧审计（flutter analyze + 硬编码检查）
├── quwoquan_service/ 变更 → 云侧审计 + make gate
├── contracts/ 变更 → metadata 验证 + codegen hash
├── specs/ 变更 → 特性树一致性（含 01_FEATURE_TREE_LEVEL_DEFINITIONS.md 层级与分解遵从）
└── 多范围同时变更 → make gate-full 全量
     │
     ▼
 通过 → git add -A → commit → push → merge main
 失败 → 生成修复计划 → 自动修复 → 重审
```

---

## 三、命令速查

| 阶段 | 命令 | 作用 | 自动卡点 |
|------|------|------|---------|
| Plan | `/opsx-explore` | 自由探索，不写代码 | G0（约束检查） |
| Create | `/opsx-ff` | 创建特性（特性树 + acceptance + tasks） | G1（verify + codegen） |
| Create | `/qwq-extend <scenario>` | 对象级扩展（20 个场景） | G1（verify + codegen） |
| Implement | `/opsx-apply` | 按 tasks.md 逐项实施 | G2（build + test-contract per task） |
| **Implement→Submit** | **`/opsx-deliver`** | **Apply 条件就绪后，验收驱动完成开发 → 验证 → 归档 → 提交入库** | G2 → G3 → G4 |
| Verify | `/opsx-verify` | 验证实现匹配制品 | G3（gate-full） |
| Verify | `/fullstack-audit` | 独立调用全栈审计 | G3（全维度审计） |
| Submit | `/submit-with-gate` | 提交合入 | G4（按范围审计 + commit） |
| Archive | `/opsx-archive` | 归档完成的特性 | G3（gate-full before archive） |

单独调用门禁（随时可用）：

```bash
make verify          # metadata 一致性
make build           # 全量编译
make test-contract   # 契约测试
make gate            # 本地门禁（verify + build + test-contract）
make gate-full       # CI 门禁（gate + 端侧 + 集成测试）
```

---

## 四、规则集（4 条）

| 规则 | 作用域 | 守护内容 |
|------|--------|---------|
| `00-fullstack-development-flow` | 全局 alwaysApply | **本文档的 rules 版本**：开发流程 + 自动卡点 + 约束总纲 |
| `01-arch-constraints` | 全局 alwaysApply | DDD 导入 + 数据库隔离 + runtime 统一 + codegen 保护 + 扩展场景 |
| `02-dart-coding` | `**/*.dart` | 设计系统 + 编码标准 + 状态管理 |
| `03-testing` | 测试文件 | 端云契约测试标准 |

---

## 五、核心约束

### 5.1 metadata-first（元数据先行）

```
任何新实体/字段/事件/接口：
  ① 更新 metadata YAML → ② make verify → ③ make codegen → ④ 手写业务逻辑 → ⑤ make gate
```

禁止跳过 ①②③ 直接编码。

### 5.2 DDD 单向依赖

```
domain ← application ← adapters ← infrastructure
  ↑                                      ↓
  └─────── 禁止反向 import ──────────────┘
```

### 5.3 runtime 统一

| 能力 | 必须使用 | 禁止 |
|------|---------|------|
| 错误处理 | `runtime/errors.AppError` | 自定义 error 返回 HTTP |
| 配置 | `runtime/config` | `os.Getenv` 读业务配置 |
| 消息 | `runtime/messaging.MessageEnvelope` | 自定义 MQ 结构 |
| HTTP | `runtime/http` + `runtime/observability` | 自实现中间件 |

### 5.4 设计系统（Dart）

禁止硬编码 `fontSize`/`EdgeInsets`/`BorderRadius`/`Color(0x)`，必须用 `AppTypography`/`AppSpacing`/`AppColors`。

### 5.5 codegen 保护

`// Code generated ... DO NOT EDIT.` 标记的文件禁止手动修改。`make gate` 通过 hash 比对检测。

---

## 六、20 个扩展场景速查

### 0→1（新建）

| # | 场景 | 命令 |
|---|------|------|
| S01 | 新建聚合根 | `/qwq-extend new-aggregate --name --service --storage` |
| S02 | 新建聚合成员 | `/qwq-extend new-member --aggregate --name` |
| S03 | 新建独立实体 | `/qwq-extend new-entity --name --service --storage` |
| S04 | 新建服务 | `/qwq-extend new-service --name --port` |
| S05 | 新建 API 端点 | `/qwq-extend new-endpoint --service --entity --method --path` |
| S06 | 新建领域事件 | `/qwq-extend new-event --aggregate --name --channel` |
| S07 | 新建投影 | `/qwq-extend new-projection --name --source-events` |
| S08 | 新建向量实体 | `/qwq-extend new-vector --name --source --field` |
| S09 | 新建 Skill | `/qwq-extend new-skill --name --trigger-scenes` |
| S10 | 新建端侧 Feature | `/qwq-extend new-feature --name --pages` |

### 1→N（扩展）

| # | 场景 | 命令 |
|---|------|------|
| S11 | 新增字段 | `/qwq-extend add-field --entity --name --type --classification` |
| S12 | 新增能力 | `/qwq-extend add-capability --entity --capability` |
| S13 | 新增事件消费者 | `/qwq-extend add-consumer --event --consumer` |
| S14 | 新增索引 | `/qwq-extend add-index --entity --fields --unique` |
| S15 | 新增 API 操作 | `/qwq-extend add-endpoint --service --route --method` |
| S16 | 新增投影字段 | `/qwq-extend add-projection-field --projection --field` |
| S17 | 变更存储 | `/qwq-extend migrate-storage --entity --from --to` |
| S18 | 新增缓存 | `/qwq-extend add-cache --entity --ttl` |
| S19 | 新增 Tool | `/qwq-extend add-tool --skill --tool` |
| S20 | 新增测试场景 | `/qwq-extend add-test --entity --scenario` |

每个场景执行后自动运行 G1 卡点（verify + codegen）。

---

## 七、Runtime 实现路线（P0→P3）

详细任务见 `specs/runtime_gap_analysis_and_plan.md`。

| 阶段 | 核心产出 | Gate 条件 |
|------|---------|----------|
| **P0** | metadata 校验 + codegen + Registry + Repository + 拦截链 + 测试基础设施 | Post + UserProfile CRUD 端到端 + 契约测试可运行 |
| **P1** | Event Store + CQRS + 实时推荐 + SSE | 信息流推荐端到端 + 实时偏好反馈 |
| **P2** | 小趣上下文 + 主动能力 + Skill 框架 | 小趣按场景主动建议 + Skill 运行 |
| **P3** | Skill 生态 + Agent 全自主 + SLI 回流 | 生态 Skill 可接入 + Agent 自主 |

```
P0(底座) → P1(推荐+实时) → P2(助手+Skill) → P3(生态+自主)
```

---

## 八、目录结构

```
quwoquan/
├── .cursor/
│   ├── rules/                          # 4 条规则
│   │   ├── 00-fullstack-development-flow.mdc   # 开发流程 + 自动卡点
│   │   ├── 01-arch-constraints.mdc             # 结构约束 + 扩展场景
│   │   ├── 02-dart-coding.mdc                  # Dart 编码标准
│   │   └── 03-testing.mdc                      # 测试标准
│   └── commands/                       # 命令
│       ├── opsx-ff.md                  # 特性创建（含自动 G1）
│       ├── opsx-apply.md               # 特性实施（含自动 G2）
│       ├── opsx-archive.md             # 特性归档（含自动 G3）
│       ├── opsx-explore.md             # 自由探索
│       ├── qwq-extend.md              # 对象级扩展（含自动 G1）
│       ├── fullstack-audit.md          # 独立审计
│       └── submit-with-gate.md         # 提交（含自动 G4）
│
├── specs/
│   ├── 00_MASTER_DEVELOPMENT_FLOW.md   # ← 本文档（唯一主线）
│   ├── runtime_framework_spec.md       # runtime 框架技术规范（附录）
│   ├── runtime_framework_design.md     # runtime 框架设计（附录）
│   ├── runtime_gap_analysis_and_plan.md # runtime 开发计划（附录）
│   ├── runtime_extension_catalog.md    # 扩展场景详解（附录）
│   └── feature-tree/                   # 特性树（四类文档标准见 00_FEATURE_TREE_STANDARD.md）
│
├── quwoquan_service/
│   ├── runtime/                        # 横切 runtime
│   ├── services/                       # 领域服务
│   └── contracts/metadata/             # 元数据（单一事实源）
│
└── quwoquan_app/
    └── lib/                            # Flutter 端
```

---

## 附录引用

| 需要了解 | 查阅 |
|---------|------|
| runtime 框架的完整技术规范 | `specs/runtime_framework_spec.md` |
| runtime 框架的设计细节 | `specs/runtime_framework_design.md` |
| runtime 各模块的 Gap 和开发任务 | `specs/runtime_gap_analysis_and_plan.md` |
| 20 个扩展场景的详细步骤 | `specs/runtime_extension_catalog.md` |
| 特性树结构 | `specs/feature-tree/` |
| **特性树文档标准（四类文档）** | `specs/feature-tree/00_FEATURE_TREE_STANDARD.md` |
| **L1-L5 层级定义与卡点落实** | `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md` |
| 元数据目录结构 | `contracts/metadata/DESIGN.md` |
