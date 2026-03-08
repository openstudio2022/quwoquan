# 端云一体化开发主线（唯一主线文档）

> **本文档是整个项目开发的唯一主线**。所有 rules、commands、specs 从此文档索引。
> 不要看其它文档来理解开发流程 — 本文档即全貌。
>
> **从属关系（强制）**：任何子域规范（包括但不限于个人助理、推荐、内容、聊天）都只能作为本主线的“子规范补充”，不得覆盖或绕过本主线与特性树标准。若冲突，以本文件与 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md` 为准。

---

## 一、SDD 开发流水线（Spec-Driven Development）

### 标准主流程

```
explore → prd → design → dev → commit → deploy
                      └────── deliver（= dev + commit）──────┘
```

```
  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
  │ explore │─▶│   prd   │─▶│  design  │─▶│   dev   │─▶│ commit  │─▶│ deploy  │
  │ (探索)   │  │(需求规格)│  │ (设计基线)│  │ (实施)  │  │(提交入库)│  │ (部署)  │
  └────┬────┘  └────┬────┘  └────┬─────┘  └────┬────┘  └────┬────┘  └────┬────┘
       │             │            │              │             │             │
    G0 准入       PRD Gate    Design Gate    Dev Gate      G4            G5
    自检（思考）    + G0          + G1        + G2/G3     L1+L2+审计   integration
                                                  │                      → prod
                                                  └─ T1~T4 自验证 + 自动归档
```

### 原型快速通道（豁免特性树分解，所有编码约束完整遵从）

```
try → [验证通过] → land → [人工确认] → commit → deploy
```

每个阶段进入时 AI Agent **自动执行阶段准入自检（Phase Gate）**，每个阶段结束时**自动执行卡点（G0~G5）**，不需要人为触发。

---

## 二、各阶段详解

### 阶段 0：explore（探索）

**入口**：`/explore`（ask/plan 模式自动激活约束）

**AI Agent 必须做的事**：
1. 确认需求属于哪个特性树节点（`specs/feature-tree/`）
2. 确认涉及哪些业务对象（查 `contracts/metadata/`）
3. 确认涉及哪些扩展场景（S01~S25，见附录 A）
4. 对输入做批判性澄清：目标用户、核心问题、边界、风险、未知项、伪需求/跳步判断
5. 主动引导用户补充业界对标输入：产品、原型、截图/视频、公开代码、公开技术文档
6. 形成初步交付拆解，顺序：metadata → codegen → 业务逻辑 → 测试
7. **特性树分解遵从**：节点归属与新建须符合 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`（治理视图默认止于 L4 Story）
8. 涉及部署拓扑时，补充 `deploy/shared/process_domain_mapping.yaml`

**禁止**：在 explore 阶段写任何实现代码。

**阶段输出要求**：
- 明确输出 `EXPLORE_READY` 或 `GATE_BLOCK`
- 若 `GATE_BLOCK`，列出仍待澄清项与建议补充的对标输入

**使用命令**：`/explore`（思考）→ `/prd`（需求规格）

---

### 阶段 1：prd（需求规格）

**入口**：`/prd`

**PRD Gate 自检**（进入前全部通过，否则 GATE_BLOCK）：
- P1: 能用一句话描述目标用户 + 核心问题？
- P2: 特性树 L4 路径已确定？
- P3: 业务对象已识别（已存在/需新建）？
- P4: 至少 3 条可量化验收标准？
- P5: out-of-scope 已明确？
- P6: 是否已说明需要对标的产品、原型、公开代码或公开技术文档？若未提供，是否已明确无需对标？
- P7: 是否已定义四层测试金字塔 `T1~T4` 的验收责任？
- P8: 是否已定义实时性 / 弱网 / 并发 / 容量 / 弹性等非功能目标？
- P9: 是否已定义对标对象、体验目标与不打折的交互基线？
- P10: 是否已定义灰度发布、观测指标与回滚条件？

**AI Agent 必须做的事**：
1. 创建/更新特性树节点，**仅使用四类文档**（禁止生成 analysis-*.md、README、独立规划书等；详见 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`）
2. 撰写 `spec.md`（背景/目标用户/功能范围/Out of Scope/约束/验收重点）
3. 将需求按四层治理视图建模：L1 关键能力、L2 功能特性、L3 子功能或组件、L4 Story
4. 撰写 `acceptance.yaml` 草稿（A1~An，status=pending，至少 3 条 SMART 验收标准，且可映射到 `T1~T4`）
5. 将对标输入沉淀为结构化结论：借鉴点 / 不借鉴点 / 适用边界 / 成本
6. 写入非功能验收基线：实时性 / 弱网 / 并发 / 性能 / 弹性 / gray-release
7. 若涉及部署拓扑，补充 `deploy/shared/process_domain_mapping.yaml`

**自动卡点 G0**：
```
✓ spec.md 已创建（包含 Out of Scope）
✓ acceptance.yaml 已创建，至少 3 条 An（status=pending），并可映射到 `T1~T4`
✓ 特性树节点已在 tree_index.yaml 中注册（status: specified）
✓ 特性树分解符合层级定义（见 01_FEATURE_TREE_LEVEL_DEFINITIONS.md）
```

**使用命令**：`/prd`

---

### 阶段 2：Create（特性创建与 metadata 就绪）

**入口**：`/design`

**Design Gate 自检**（进入前全部通过，否则 GATE_BLOCK）：
- D1: spec.md 已存在且稳定？
- D2: acceptance.yaml A1~An 已定义？
- D3: 设计约束已识别（DDD 分层、metadata 范围）？
- D4: ≥2 个方案可供比较？
- D5: 无未解决的阻塞依赖？
- D6: 是否完成 `A1~An ↔ T1~T4` 证据矩阵设计？
- D7: 若涉实时性，是否定义一致性、顺序、幂等、重试、重连与弱网降级？
- D8: 是否定义并发、容量、弹性、限流、降级、回滚与观测策略？
- D9: 是否完成对标体验吸收结论，并明确当前差距与收敛路径？

**AI Agent 必须做的事**：
1. 先评审上游 `spec.md` 与 `acceptance.yaml` 是否足以支撑设计，不足则阻断进入方案设计
2. 创建/更新 `design.md`（≥2 方案对比、选型决策、未来演进；若轻量方案必须写明演进路径）
3. 创建设计中的对标分析：对标对象、借鉴点、适配边界、当前差距、演进路径
4. 创建/更新 `tasks.md`（顺序：metadata → codegen → 测试先行 → 业务逻辑 → 重构）
5. **特性树层级与分解**：节点路径须符合 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`；acceptance.yaml 的 `level` 使用统一取值（优先 `L4_story`）
6. 如需新建业务对象 → 执行 `/extend new-aggregate|entity|service`（或由 /design 自动调用）
7. 如需扩展已有对象 → 执行 `/extend add-field|capability|event|...`
8. 更新 metadata YAML（5 文件一组）
9. 完成 TDD/ATDD 策略、角色职责、多重防护网、灰度发布与回滚设计

**自动卡点 G1**：
```bash
# /design 执行完毕后自动运行：
make verify-metadata           # metadata 内部一致性
make codegen                   # 从 metadata 生成 Go 骨架代码
make codegen-app               # 从 metadata 生成端侧代码
# 若涉及 rec-model-service：
make codegen-rec-model-python  # 生成 Pydantic 模型与 FastAPI 路由骨架
```
失败 → 停止，输出错误 + 修复建议，修复后重新执行。

**使用命令**：`/design`

---

### 阶段 3：dev（实施）

**入口**：`/dev`（或 `/deliver` 一气呵成）

**Dev Gate 自检**（进入前全部通过，否则 GATE_BLOCK）：
- V1: design.md 已存在且关键设计决策已冻结？
- V2: codegen 已通过？
- V3: 当前 Story 的 tasks.md 任务按正确顺序排列？
- V4: acceptance.yaml An 有明确判定方式并映射到 `T1~T4`？
- V5: 当前 task 是否已绑定先行失败测试（TDD Red）？
- V6: 若为实时性 / 高风险交互，是否已绑定弱网 / 并发 / 恢复类用例？

**AI Agent 必须做的事**：
1. 按 L4 Story 组织实施，`tasks.md` 作为 Story 的工程执行清单
2. 仅在非 codegen 区域手写业务逻辑（domain_service / application_service / feature pages）
3. 遵从 DDD 层级约束、Dart 编码规范、runtime 统一能力、错误码规范
4. 默认执行 `Red → Green → Refactor`
5. **每完成一个 task 自动执行 G2**

**自动卡点 G2**（每个 task 完成后）：
```bash
make build                     # 编译通过
make test-contract             # 契约测试通过（真实数据库）
# 端侧变更时追加：
flutter test test/cloud/ test/components/ test/ui/
```
失败 → 停止当前 task，输出错误 + 修复建议。

**开发收口要求（/dev 完成时自动执行）**：
```bash
make gate-full
```

并必须满足：
- `T1~T4` 四层自验证证据齐全
- 非功能验收（实时性 / 弱网 / 并发 / 弹性 / 体验）齐全
- 已达到 **gray-release ready**
- 自动回写归档状态：`acceptance.yaml.archived=true`、`tree_index.status=completed`

通过后，`/dev` 的状态应为：**已归档、等待 `/commit` 提交**。

**结构约束**（rules 实时强制）：

| 端 | 约束 | 规则来源 |
|----|------|---------|
| Go | domain 禁止 import application/adapters/infrastructure | `01-arch-constraints` |
| Go | 禁止直接 import 数据库驱动（仅 infrastructure 允许） | `01-arch-constraints` |
| Go | 必须使用 runtime/errors、runtime/config、runtime/messaging | `01-arch-constraints` |
| Go | codegen 文件（`DO NOT EDIT`）禁止手动修改 | `01-arch-constraints` |
| Dart | 禁止硬编码 fontSize/EdgeInsets/Color/BorderRadius/width/height | `02-dart-coding` |
| Dart | 禁止相对路径 import，必须用 package: | `02-dart-coding` |
| Dart | Feature 禁止直接 import 其他 Feature 内部文件 | `02-dart-coding` |
| 错误码 | 云侧用 generated.AppErrorFrom*；端侧用 *ErrorCode.fromCode().toDisplayMessage；测试用枚举.code | `01-arch-constraints §3.3` |
| 端云 | Go struct / Dart DTO / OpenAPI / Migration 必须与 metadata 一致 | `01-arch-constraints` |

**使用命令**：`/dev`

---

### 阶段 4：verify（验证，独立复核/兼容入口）

**入口**：`/verify`（特性级）或 `/audit`（代码库级）

**AI Agent 必须做的事**：
1. 复核所有 tasks.md 任务已完成
2. 复核 acceptance.yaml A1~An 全部满足（status 非 pending）
3. 检测漂移（SPEC_DRIFT / IMPL_DRIFT / DESIGN_DRIFT / TASK_DRIFT）
4. 复核自动归档前后的状态一致性
5. **自动执行** 全栈审计 + 门禁

**自动卡点 G3**：
```bash
make gate-full
```

`make gate-full` 内含（全部必须通过）：

| 检查项 | 说明 |
|-------|------|
| `verify_metadata_internal` | metadata YAML 内部交叉引用 |
| `verify_arch_constraints` | DDD 导入 + 数据库隔离 + runtime 统一 |
| `verify_codegen_hashes` | codegen 产物 hash 比对（防手改） |
| `verify_dart_semantic` | 硬编码字面量 + 包引用 + Feature 隔离 |
| `verify_error_code_semantic` | 端侧禁止硬编码错误码字符串，须用 *ErrorCode.fromCode / .code |
| `verify_feature_tree` | tree.yaml ↔ 目录 + acceptance 完整性；特性树层级与分解须符合 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md` |
| `flutter analyze` | Dart 静态分析 |
| `go build ./...` | Go 编译 |
| `make test-contract` | 契约测试（真实数据库） |
| `flutter test test/cloud/ test/components/ test/ui/` | L1a+L1b+L1c 端侧测试（路径规则见 `03-testing.mdc §3`） |

---

### 阶段 5：commit（提交入库）

**入口**：`/commit`

**AI Agent 必须做的事**：
1. 读取 `/dev` 已自动完成的归档结果
2. 分析 `git status` 确定变更范围
3. **提交前必须执行 L1+L2 门禁**（`make gate`）并通过
4. **自动执行** 按变更范围的针对性审计
5. 通过后自动 commit → push → merge main
6. 若因历史流程或异常中断尚未归档，`/commit` 可兼容补归档，但这不是标准流程

**自动卡点 G4**：
```
读取 `/dev` 自动归档结果（若缺失则兼容补归档）→ git status → 分析变更范围
     │
     ▼
 执行 L1+L2 门禁（make gate）─ 必须通过
     │
     ├── quwoquan_app/ 变更 → 端侧审计（L1 + flutter analyze + 硬编码检查）
     ├── quwoquan_service/ 变更 → 云侧审计（L2 + metadata + make gate）
     ├── contracts/ 变更 → metadata 验证 + codegen hash
     ├── specs/ 变更 → 特性树一致性（含 01_FEATURE_TREE_LEVEL_DEFINITIONS.md 层级与分解遵从）
     └── 多范围同时变更 → make gate 全量
          │
          ▼
      通过 → git add -A → commit → push → merge main
      失败 → 生成修复计划 → 自动修复 → 重审
```

**使用命令**：`/commit`

---

### 阶段 6：deploy（部署）

**入口**：`/deploy`

**前置**：commit（G4）已完成，代码已入库 main。目标：从特性到入库（L1/L2 自测通过），再到集成验证（L3/L4），再到生产端到端打通。

**AI Agent 必须做的事**：
1. **G5a：部署到 integration** — 将当前 main 构建物部署到 integration 环境（staging），使 L3/L4 可打该环境
2. **G5b：L3/L4 集成验证** — 在 integration 上执行 L3 API Contract 与 L4 Patrol 测试，全部通过方可进入 G5c
3. **G5c：灰度到 prod** — 按 `deploy/service/config-release/` 规范，执行灰度/滚动发布到生产；SLO 卡点通过则继续，否则回滚

**自动卡点 G5**：
```bash
# G5a：部署到 integration（由 CI/CD 或人工触发，见 deploy/shared/deliver_to_production_runbook.md）
# G5b：L3/L4 集成验证（阻塞）
STAGING_BASE_URL=<integration-api-url> TEST_AUTH_TOKEN=<token> make test-api-contract   # L3
patrol test test/patrol/ --dart-define=ENV=staging --dart-define=STAGING_BASE_URL=...   # L4
# G5c：灰度/滚动发布到 prod
make config-gray-rollout SERVICE=... FROM_IMAGE=... TO_IMAGE=... FROM_CONFIG=... TO_CONFIG=... STEP=25
# 每步后 SLO 卡点：make config-slo-gate ERROR_RATE=... P95_MS=... REDIS_ERROR_RATE=...
```

**灰度发布要求**（见 `deploy/service/config-release/`）：
- 滚动步进：5 → 25 → 50 → 100（%）
- 每步后执行 SLO 卡点：错误率、P95 延迟、Redis 错误率
- 超过阈值 → 暂停或回滚；`high_risk_fields` 变更须审批 + 灰度 + 回滚方案

**使用命令**：`/opsx-deploy`（集成验证 + 灰度到生产）

---

## 三、命令速查（当前正式命令）

| 阶段 | 命令 | 作用 | 自动卡点 |
|------|------|------|---------|
| Explore | `/explore` | 探索思考，不写代码 | G0（约束检查） |
| PRD | `/prd` | 建立需求规格基线（spec + acceptance） | PRD Gate + G0 |
| Design | `/design` | 建立设计基线（design + tasks + metadata + codegen） | Design Gate + G1 |
| Implement | `/dev` | 按 tasks 实施，完成 `T1~T4` 自验证、gray-release ready、自动归档 | G2 + G3 |
| **Implement→Submit** | **`/deliver`** | **验收驱动开发 → 自动归档 → 提交入库** | G2 → G3 → G4 |
| Verify | `/verify` | 特性级漂移检测与复核 | G3（gate-full） |
| Audit | `/audit` | 独立调用全栈审计 | G3（全维度审计） |
| Submit | `/commit` | 读取 `/dev` 自动归档结果后提交合入 | G4（按范围审计 + commit） |
| **Deploy** | **`/deploy`** | **部署到 integration → L3/L4 集成验证 → 灰度到 prod** | G5a → G5b → G5c |
| Archive | `/archive` | 兼容补归档/修复回写，非标准流 | G3（gate-full） |
| Prototype | `/try` | 快速验证想法，豁免特性树前置创建但不豁免工程约束 | G2（每次主要变更后） |
| Prototype | `/land` | 将原型成果回补到标准基线并完成归档语义 | G3（gate-full） |

单独调用门禁（随时可用）：

```bash
make verify          # metadata 一致性
make build           # 全量编译
make test-contract   # 契约测试
make gate            # 本地门禁（verify + build + test-contract）
make gate-full       # 四层自验证 + 非功能验收 + 发布前证据
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

### 5.6 部署拓扑与领域接口解耦

- 部署进程是运维抽象，不是领域抽象
- 对外接口仍按领域服务暴露，禁止被部署态影响
- 同一环境中一个 domain 只能归属一个部署进程
- `integration` 与 `prod` 的 process-domain 映射必须一致

---

## 六、25 个扩展场景速查（/extend）

### 0→1（新建）

| # | 场景 | 命令 |
|---|------|------|
| S01 | 新建聚合根 | `/extend new-aggregate --name --service --storage` |
| S02 | 新建聚合成员 | `/extend new-member --aggregate --name` |
| S03 | 新建独立实体 | `/extend new-entity --name --service --storage` |
| S04 | 新建服务 | `/extend new-service --name --port` |
| S05 | 新建 API 端点 | `/extend new-endpoint --service --entity --method --path` |
| S06 | 新建领域事件 | `/extend new-event --aggregate --name --channel` |
| S07 | 新建投影 | `/extend new-projection --name --source-events` |
| S08 | 新建向量实体 | `/extend new-vector --name --source --field` |
| S09 | 新建 Skill | `/extend new-skill --name --trigger-scenes` |
| S10 | 新建端侧 Feature | `/extend new-feature --name --pages` |

### 1→N（扩展）

| # | 场景 | 命令 |
|---|------|------|
| S11 | 新增字段 | `/extend add-field --entity --name --type --classification` |
| S12 | 新增能力 | `/extend add-capability --entity --capability` |
| S13 | 新增事件消费者 | `/extend add-consumer --event --consumer` |
| S14 | 新增索引 | `/extend add-index --entity --fields --unique` |
| S15 | 新增 API 操作 | `/extend add-endpoint --service --route --method` |
| S16 | 新增投影字段 | `/extend add-projection-field --projection --field` |
| S17 | 变更存储 | `/extend migrate-storage --entity --from --to` |
| S18 | 新增缓存 | `/extend add-cache --entity --ttl` |
| S19 | 新增 Tool | `/extend add-tool --skill --tool` |
| S20 | 新增测试场景 | `/extend add-test --entity --scenario` |

### 横切层扩展（S21-S25）

| # | 场景 | 命令 |
|---|------|------|
| S21 | 新增错误码层 | `/extend add-errors --entity --domain` |
| S22 | 新增端侧 UI 配置层 | `/extend add-ui-config --entity --domain` |
| S23 | 新增行为采集层 | `/extend add-behaviors --entity --domain` |
| S24 | 新增隐私策略层 | `/extend add-privacy --entity --domain` |
| S25 | 新增三层测试契约 | `/extend add-test-contracts --entity --domain` |

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
│   └── commands/                       # SDD 命令集
│       ├── explore.md                  # 探索（G0 准入自检）
│       ├── prd.md                      # 需求规格（PRD Gate + G0）
│       ├── design.md                   # 设计基线（Design Gate + G1）
│       ├── dev.md                      # 实施（Dev Gate + G2/task，收口时自动 G3 + 自动归档）
│       ├── archive.md                  # 兼容补归档/修复（非标准流）
│       ├── commit.md                   # 提交入库（读取 /dev 自动归档结果后执行 G4）
│       ├── deploy.md                   # 部署（G5a→G5b→G5c）
│       ├── deliver.md                  # 全链路：dev+commit
│       ├── verify.md                   # 特性级漂移检测（G3）
│       ├── audit.md                    # 代码库级结构审计
│       ├── try.md                      # 原型模式（豁免特性树）
│       ├── land.md                     # 原型落地基线化（保留归档语义）
│       ├── extend.md                   # 对象级扩展（S01~S25，G1）
│       └── prune.md                    # 清理过期特性树节点
│
├── specs/
│   ├── 00_MASTER_DEVELOPMENT_FLOW.md   # ← 本文档（唯一主线）
│   ├── 01_APP_DIRECTORY_STRUCTURE_BY_DOMAIN.md  # 端侧 lib/ui、lib/cloud 按领域划分
│   ├── 01_APP_DIRECTORY_MIGRATION_TASKS.md      # features→ui 迁移任务清单
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
| **端侧目录结构（按领域 ui/cloud）** | `specs/01_APP_DIRECTORY_STRUCTURE_BY_DOMAIN.md` |
| **端侧 features→ui 迁移任务** | `specs/01_APP_DIRECTORY_MIGRATION_TASKS.md` |
| 元数据目录结构 | `contracts/metadata/DESIGN.md` |
| **Deliver → Prod 端到端流程** | `deploy/shared/deliver_to_production_runbook.md` |
