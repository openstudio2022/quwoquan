# CI/CD 与工程自动化统一规范（Commercial-grade）

目标：把“质量、合规与交付”做成**默认自动完成**的工程能力，不让每个服务团队重复建设。

本规范适用于所有服务与平台模块，要求通过统一流水线模板/脚本落地（而非每个服务手写一套）。

---

## 1. 必须自动化的环节（强制）

### 1.1 测试工程自动化（CI）

每次提交/合并请求 MUST 自动执行：
- 静态检查：lint/format/typecheck（语言相关）
- 单元测试：覆盖核心路径
- 契约校验：OpenAPI/JSON Schema 校验与兼容性检查
- 集成测试（P0 变更必需）：基于 Docker Compose 或等价的依赖环境
- 安全门禁（见 §3）：secret scan、依赖漏洞扫描（SCA）、基础 SAST

### 1.2 部署自动化（CD）

每次发布 MUST 自动执行：
- 构建产物：镜像/制品（含版本号与构建信息）
- 自动部署：dev/staging/prod（按环境）
- 回滚：一键回滚到上一版本（含配置回滚）
- 发布审计：记录发布人、版本、变更范围、时间

### 1.3 可观测性接入自动化

服务上线即默认具备：
- 结构化日志字段（`contracts/log_fields.md`）
- 指标最小集合（`contracts/metrics.md`）与 `endpoint` 归因（`contracts/endpoint_catalog.md`）
- trace 注入与传播（`contracts/openapi/common.yaml` 与 `contracts/error_codes.md`）
- SLO 与告警模板（参考 `contracts/feedback_and_learning.md` 的 Journey/API SLO）

> 要求：这些接入必须由公共库 `runtime/observability` 与平台模板实现，服务侧不手写。

---

## 2. 统一质量门禁（Quality Gates）

合并到主分支前 MUST 通过：
- contracts 校验通过（OpenAPI/Schema）
- 单测通过
- lint/format/typecheck 通过
- 关键变更（P0）通过集成测试
- 安全门禁通过（见 §3）

建议提供一条本地与 CI 共用的门禁命令（例如 `make gate`），并保持其输出稳定可机器判定。
建议采用双层门禁：
- `make gate`：快门禁（本地高频执行）
- `make gate-full`：全量门禁（CI required checks，包含全量测试）

### 2.1 仓库策略（禁止不遵从代码入库）

为实现“未通过门禁不得入库/不得合入主分支”，必须配置仓库策略：
- **CI required checks**：将 `make gate`（以及对应测试套件）作为 PR 的必需检查项
- **Branch protection**：主分支开启保护，禁止直接 push，必须走 PR 且 required checks 全绿
- **本地阻断（可选但强烈建议）**：安装 pre-commit hook，在本地提交前自动执行 `make gate`

本仓库已提供可选脚本：`bash scripts/install-hooks.sh`（安装后当 `quwoquan_service/` 有 staged 变更会自动 gate）。
并提供特性与元数据一致性机检：
- `scripts/verify_feature_traceability.sh`
- `scripts/verify_contract_metadata.sh`

发布到生产前 SHOULD 额外通过：
- 变更影响评估（SLO/告警覆盖检查）
- 基准性能验证（至少对关键接口 p95/p99 对比）

---

## 3. 安全与合规自动门禁（不增加服务负担）

CI MUST 自动执行并阻断：
- **Secret scan**：避免 token/密钥进入仓库
- **SCA**：依赖漏洞扫描（高危阻断）
- **SAST（基础）**：常见注入/不安全用法扫描（高危阻断）
- **License check（可选）**：依赖许可证合规（商用建议启用）

---

## 4. 与公共库/平台模块的关系（强制）

- 运行时横切能力必须通过 `runtime/`：`errors/observability/config/messaging/experiments/learning`
- 流水线模板与脚本应归档到 `platform/`（后续落地），各服务只通过配置启用

