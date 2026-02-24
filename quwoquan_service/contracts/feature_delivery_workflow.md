# 特性粒度交付工作流（Ask/Plan → Implement → Verify → Merge）

目标：把“contracts-first、端云一体、DDD、横切能力开箱即用、TDD/验收、自动化门禁”做成可重复的交付流程，使 AI agent 能最大化自动完成，最终由人复核即可。

---

## 1. Ask 阶段（澄清与范围界定）

输出必须包含：
- 特性目标（用户价值）
- 涉及的领域边界（Bounded Context）：哪些服务/对象/接口
- 风险与非目标（不做什么）
- 验收口径草案（见 §3）

---

## 2. Plan 阶段（以 contracts 为起点的交付计划）

输出必须落到仓库产物（不可只停留在对话里）：

### 2.0 特性目录（必需）

- 在仓库根创建特性目录：`changes/<date>-<slug>/`
- 更新全量特性台账：`changes/feature_catalog.yaml`
- 绑定 OpsX：填写 `opsx_change_id` 与 `opsx_specs`
- 补齐映射文件：`traceability.yaml`（服务/对象/API/横切能力/测试）

### 2.1 Contracts Delta（必需）

- 修改/新增 `contracts/openapi/*.yaml`（先契约）
- 如涉及：错误码、headers、endpoint 归因、隐私分级、事件 envelope、SLO 等，必须同步更新对应 `contracts/*.md`

### 2.2 Specs（必需）

- 更新对应 `specs/<service>/spec.md` 的场景与约束

### 2.3 Tasks（必需）

- 在 `tasks.md` 中以“特性粒度”补充任务，并引用 `tasks.md` 的 **§0 全服务统一能力**（不重复造轮子）

---

## 3. 验收标准（TDD：先验收/先测试）

每个特性必须产出“验收标准清单”，并对应测试层级：
- mock 自动化测试（端侧 mock 与服务 stub）
- 单元测试（领域规则、边界、错误码映射）
- 契约测试（OpenAPI/Schema 校验 + 示例/Golden）
- 集成测试（Docker Compose + 冒烟链路）
- 用户验收自动化（UAT case 自动执行或可复跑脚本）

验收模板与质量门禁见：`contracts/acceptance_criteria.md`。

---

## 4. Implement 阶段（DDD + 横切能力开箱即用）

强制要求：
- DDD 分层与依赖方向：`contracts/ddd_fullstack_guidelines.md`
- 横切能力通过 `runtime/*` 与平台模板自动接入，不允许服务各自实现一套
- 隐私/安全开关通过 `sys.*` 系统配置实现，默认关闭匿名化/加密，见 `contracts/privacy_and_security.md`

端云一体：
- 端侧必须支持 mock/remote 一键切换（Repository/DataSource 注入）
- remote 调用必须注入 headers（traceId/requestId/pageId 等）

---

## 5. Verify 阶段（自动化门禁）

本地与 CI 必须执行统一门禁：
- `make gate`（仓库根快门禁）
- `make gate-full`（仓库根全量门禁，含测试）
- `scripts/verify_feature_traceability.sh`
- `scripts/verify_contract_metadata.sh`
- CI/CD 质量门禁见：`contracts/ci_cd_automation.md`

---

## 6. Merge 阶段（禁止不遵从代码入库）

必须通过：
- contracts 校验 + `make gate` + 测试套件
- 隐私/安全门禁（secret scan/SCA/SAST）

建议：将 gate 与测试作为必需检查项（CI required checks），未通过不得合入主分支。

