# Runtime 商用准出开发计划（可验收、阶段门禁）

> 目标：开发目标清晰、每阶段结束**必须通过自动化验证**方可验收，不交付半成品。
> 依据：`specs/runtime_gap_analysis_and_plan.md`。

---

## 1. 开发目标确认

### 1.1 总体目标

**Runtime 达到商用准出水准**，使各业务服务可基于统一 runtime 聚焦业务开发，具体包括：

- **P0**：metadata 校验、codegen、EntityRegistry、Repository 框架、读写拦截链、契约测试基础设施、治理/实验/学习基础实现、本地开发环境 → **服务可开始业务开发**。
- **P1**：Event Store、CQRS Projector、实时推荐（Redis 热路径 + 规则引擎）、SSE/Streaming → **信息流推荐端到端可用**。
- **P2**：PageContext、Context Pipeline、Suggested Actions、Skill 框架、实验/学习闭环 → **小趣按场景主动建议 + Skill 可运行**。
- **P3**：Skill 生态、Agent 全自主、SLI 回流 → **商用准出**。

### 1.2 原则（与本计划强约束）

- **每阶段必须自动化验证**：阶段结束时必须执行指定命令（`make verify`、`make gate`、`make test`、`make test-contract` 等），**全部通过**后该阶段才视为可验收；未通过则不得进入下一阶段。
- **不交付半成品**：每个 Task 的验收标准都对应到可执行脚本或测试，避免“需人工反复调试才能用”的状态。
- **P0 不完成不启动 P1**：依赖关系严格按 gap 分析中的 DAG 执行。

### 1.3 权威输入

| 文档 | 用途 |
|------|------|
| `specs/runtime_gap_analysis_and_plan.md` | Gap 全景、更新后开发计划、P0~P3 Task 与 Gate 条件 |
| `specs/runtime_framework_spec.md` | Runtime 框架规范 |
| `specs/runtime_framework_design.md` | 设计细节（含测试基础设施、codegen） |

---

## 2. 阶段总览与门禁

| 阶段 | 目标 | 自动化验收（必须全部通过） | 预估 |
|------|------|---------------------------|------|
| **P0-fix** | 编译通过、spec 与 metadata v3 一致、特性树完整 | 见 §3.1 | 2~3 天 |
| **P0** | 底座可用：校验 + codegen + Registry + Repository + 拦截链 + 测试基础设施 + 治理等 + 本地环境 | 见 §3.2 | 3~4 周 |
| **P1** | CQRS + 实时推荐 + SSE | 见 §3.3 | 3~4 周 |
| **P2** | 小趣上下文 + Skill 框架 + 实验闭环 | 见 §3.4 | 4~5 周 |
| **P3** | Skill 生态 + Agent 全自主 | 见 §3.5 | 3~4 周 |

---

## 3. 各阶段自动化验证与可验收标准

### 3.1 P0-fix 阶段

**目标**：既有代码可编译、spec 与 metadata v3 对齐、特性树补全。

**Task 清单**（见 gap 分析 §5.2）：

- P0-fix-1：修复 `runtime/http` 与 `runtime/observability`（如 `NewHTTPServerMiddleware`）— **若已修复则仅需验证编译**
- P0-fix-2：spec 中 metadata 引用更新为 v3 目录
- **P0-fix-2b**：**根目录与 service 的 verify/gate 脚本适配 metadata v3**（当前 `scripts/verify_contract_metadata.sh` 与 `quwoquan_service/scripts/gate.sh` 仍检查旧扁平文件，须改为遍历 v3 聚合/实体目录并校验必需 YAML 及引用关系）
- P0-fix-3：特性树补全（tree.yaml + 各 L2 的 acceptance/spec/tasks）

**阶段结束必须通过的自动化验证**（用户验收 = 以下全部成功）：

```bash
# 1) 编译
cd quwoquan_service && go build ./runtime/...

# 2) 仓库级 verify（含 metadata/契约/特性树等）
cd <repo_root> && make verify

# 3) 仓库级 gate（含 service gate）
cd <repo_root> && make gate
```

**验收清单**（可勾选）：

- [ ] `go build ./runtime/...` 零错误
- [ ] `make verify` 全绿
- [ ] `make gate` 全绿（若 gate 仍依赖旧 metadata 路径，须在本阶段内修正 gate/脚本以支持 v3，再通过 gate）

**说明**：
- 若 `quwoquan_service/scripts/gate.sh` 仍检查过往版本 metadata 扁平文件，P0-fix 须同步更新为 v3 或由根目录 verify 覆盖，使 gate 通过。
- 若 `make verify` 报缺文件（`engineering_directory_manifest.yaml` 所列），须在 P0-fix 内补全内容，直至 `make verify` 全绿。

---

### 3.2 P0 阶段（底座）

**目标**：metadata 校验工具、codegen、EntityRegistry、Repository 框架、读写拦截链、契约测试基础设施、governance/experiments/learning 实现、本地开发环境；Post + UserProfile 端到端 CRUD 与契约测试可运行。

**Task 清单**（见 gap 分析 §5.3）：P0-1～P0-8。

**阶段结束必须通过的自动化验证**（= P0 Gate，全部通过方可验收）：

```bash
# 1) 编译
cd quwoquan_service && go build ./runtime/... && go build ./tools/...

# 2) metadata 与契约
cd <repo_root> && make verify

# 3) codegen 产出（以 Post、UserProfile 为验证聚合）
cd quwoquan_service && make codegen   # 若已提供 make codegen
# 且生成代码可编译
go build ./internal/...

# 4) 单元测试
cd quwoquan_service && make test

# 5) 契约测试（Post MongoDB + UserProfile PostgreSQL + 缓存/拦截链等）
cd quwoquan_service && make test-contract

# 6) 全仓库门禁
cd <repo_root> && make gate
```

**P0 Gate 验收清单**（与 gap 分析 §6.1 一致，每项须有对应自动化检查）：

- [ ] `go build ./runtime/...` 零错误
- [ ] `make verify` 全绿（含 metadata v3 一致性）
- [ ] `make codegen` 对 Post + UserProfile 生成完整且可编译
- [ ] Post（MongoDB）CRUD 端到端通过（契约测试）
- [ ] UserProfile（PostgreSQL）CRUD 端到端通过（契约测试）
- [ ] Redis 缓存：命中/未命中/过期 三路径通过（契约测试）
- [ ] 读拦截链：SECRET 不暴露、PII 脱敏（契约测试）
- [ ] 写拦截链：必填校验、事件 hook 就绪（契约测试）
- [ ] 契约测试基础设施：embedded-postgres + testcontainers mongo + miniredis 可启动/运行/清理
- [ ] 熔断器 + 限流 + 优雅关闭 有单元测试通过
- [ ] `make test-contract` 一键全绿
- [ ] `docker-compose up`（或 `make dev-up`）本地开发环境就绪（可脚本检测端口/健康）

**说明**：`make test-contract`、`make codegen` 若尚未在 Makefile 中定义，须在 P0 内补齐并纳入本阶段验收。

---

### 3.3 P1 阶段

**目标**：Event Store、Projector、实时推荐（热路径 + 引擎）、SSE/Streaming。

**阶段结束必须通过的自动化验证**（= P1 Gate）：

```bash
cd quwoquan_service && go build ./runtime/...
cd quwoquan_service && make test
cd quwoquan_service && make test-contract
# 若有集成测试/推荐端到端测试
cd quwoquan_service && make test-integration   # 或按实际 target
cd <repo_root> && make verify && make gate
```

**验收清单**（与 gap 分析 §6.2 对齐）：

- [ ] 信息流推荐端到端可用（类 TikTok 实时偏好反馈）
- [ ] SSE 流式推送可用
- [ ] CQRS ReadModel 投影可用
- [ ] 上述能力有自动化测试覆盖，且 `make gate` 通过

---

### 3.4 P2 阶段

**目标**：PageContext、Context Pipeline、Suggested Actions、Skill 框架、experiments + learning 闭环。

**阶段结束必须通过的自动化验证**（= P2 Gate）：

```bash
cd quwoquan_service && go build ./runtime/... && make test
cd quwoquan_service && make test-contract
cd <repo_root> && make verify && make gate
```

**验收清单**（与 gap 分析 §6.3 对齐）：

- [ ] 小趣三层上下文感知
- [ ] Suggested Actions 按页面场景主动建议
- [ ] Skill 框架可运行（内置 Skill 可执行）
- [ ] 对应自动化测试通过，`make gate` 通过

---

### 3.5 P3 阶段

**目标**：Skill 生态、Agent 全自主、SLI/SLO 回流。

**阶段结束必须通过的自动化验证**（= P3 Gate = 商用准出）：

```bash
cd quwoquan_service && go build ./runtime/... && make test
cd quwoquan_service && make test-contract
cd <repo_root> && make verify && make gate
```

**验收清单**（与 gap 分析 §6.4 对齐）：

- [ ] Skill Store 可接入外部 Skill
- [ ] Agent 全自主开发闭环
- [ ] SLI/SLO 回流到 Agent 知识库
- [ ] 全部自动化验证通过

---

## 4. 执行顺序与何时可进入开发

### 4.1 开发目标是否清楚

- **是**。目标为 Runtime 商用准出，分 P0-fix → P0 → P1 → P2 → P3，每阶段有明确交付物和 Gate 条件（见 gap 分析 + 实现计划）。
- **本计划**在每阶段末尾增加了**必须执行的自动化验证命令与验收清单**，确保“通过即可验收、不交付半成品”。

### 4.2 进入开发的条件

- **现在即可进入开发**：从 **P0-fix** 开始执行。
- 每阶段完成标准：**仅当该阶段“自动化验证”全部通过后，该阶段才算完成并可验收**；未通过前不进入下一阶段。

### 4.3 建议执行顺序

1. **P0-fix**（2~3 天）  
   - 按 §3.1 完成 P0-fix-1～P0-fix-3。  
   - 运行 §3.1 的 3 条验证，全部通过后勾选验收清单，再进入 P0。

2. **P0**（3~4 周）  
   - 按 gap 分析 §5.3 与实现计划 P0 的 Task 顺序执行（P0-1 校验 → P0-2 codegen → P0-3 Registry → P0-4 Repository → P0-5 拦截链 → P0-6 测试基础设施 → P0-7 governance 等 → P0-8 本地环境）。  
   - 每完成一个 Task，运行与该 Task 相关的测试或脚本；**阶段结束**时运行 §3.2 全部命令，通过后勾选 P0 Gate 清单，再进入 P1。

3. **P1 → P2 → P3**  
   - 同理：每阶段按对应 Task 开发，**阶段结束**时运行该节的自动化验证，全部通过后再进入下一阶段。

### 4.4 自动化验证的落地要求

- **P0-fix**：若现有 `make gate` 仍依赖旧 metadata 结构，须在本阶段内修改 `quwoquan_service/scripts/gate.sh` 或根目录 `scripts/verify_*.sh`，使 v3 目录被正确校验，并保证 `make verify`、`make gate` 通过。
- **P0**：须在 quwoquan_service 中提供：
  - `make codegen`（或等效命令），
  - `make test-contract`（运行契约测试，含 Post、UserProfile、缓存、拦截链等），
  并在阶段 Gate 中执行。
- **P1/P2/P3**：新增能力均需有对应单元测试或契约/集成测试，并纳入 `make test` 或 `make test-contract`/`make test-integration`，保证 `make gate` 能覆盖到。

---

## 5. 总结

- **开发目标**：Runtime 商用准出，阶段与 Task 以 `runtime_gap_analysis_and_plan.md` 为准。
- **可进入开发**：是，从 P0-fix 开始。
- **每阶段验收**：以本文 §3 中该阶段的**自动化验证命令**与**验收清单**为准；全部通过即该阶段可验收，不交付半成品、不依赖人工反复调试才可用。
- **门禁**：每阶段结束必须通过 `make verify` 与 `make gate`（及该阶段指定的 test/codegen 等），否则不得进入下一阶段。
