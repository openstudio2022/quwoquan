# quwoquan Codex Guide

本仓库使用“目录即树、节点自解释”的规格驱动开发。进入子目录时，先读取本文件，再读取路径上更近的 `AGENTS.md`。

## 唯一执行入口

非纯查询任务按以下顺序建立最小上下文：

1. 最近的 `AGENTS.md`。
   进入 `quwoquan_data/**` 时必须继续读取 `quwoquan_data/AGENTS.md`。
2. [`specs/feature-tree/README.md`](specs/feature-tree/README.md)。
3. AppRoot `spec.md/design.md`。
4. 目标 L1 `spec.md/design.md`。
5. 目标 L2 `spec.md` 与按需 `design.md`。
6. 目标 L3 `spec.md`。
7. 节点引用的 metadata 与测试。

已知目标路径时执行 `make feature-context TARGET=<spec-or-code-path>`；代码路径若被多个 L1 同优先级认领或没有 owner，返回 `GATE_BLOCK`，先修规格归属。

阶段语义由对应 `.cursor/commands/*.md` 定义：`/explore`、`/prd`、`/design`、`/baseline`、`/extend`、`/dev`、`/verify`、`/plan-review`、`/plan-next`。自然语言请求与最接近的阶段命令等价，不因用户未输入 slash command 而跳过规格理解和验证。

## 每次任务三段协议

### Spec Entry

开始实施前明确：

- 目标与用户价值。
- In Scope / Out of Scope。
- AppRoot Journey/Scenario。
- `L1_domain_service / L2_business_capability / L3_story` 父链。
- 验收意图：`UAT / DOM / SIT / GWT / contract`。
- 测试证据：`local_contract / api_integration / user_acceptance`。
- 当前 OPEN 与准出影响。

任一项无法明确时，先执行 `/explore` 或 `/prd` 刷新对应 `spec.md`，不要直接写实现。

### Pre-work Reflection

实施前逐项判断：metadata-first、runtime error 链路、Mock 隔离、页面质量、Data CLI-first、stackctl、跨域 E2E、四环境、观测与回滚是否被触发。触达多个区域时证明 `Data -> Service -> App -> Behavior -> Recommendation -> Observability -> Environment` 无断点。

### Exit Review

交付时如实说明：规格达成、三层测试、E2E、产品/UX、运营观测、自动化/门禁、OPEN 变化和剩余阻断。失败门禁不得包装为成功。

## 特性树与文档规则

- AppRoot `spec.md` 拥有全应用目标、Journey、Scenario、UAT；AppRoot `design.md` 拥有全局架构与跨域约束。
- L1 `spec.md/design.md` 拥有领域事实、边界、工程归属、DOM 与领域设计。
- L2 `spec.md` 拥有能力组合行为和 SIT；仅达到设计门槛时保留 `design.md`。
- L3 只保留 `spec.md`，使用 REQ/GWT，设计决定上收到 L2/L1 DEC。
- 字段、path、operation、surface、route、event、metric、错误码和恢复语义只引用所属服务 `contracts/**`；跨服务 schema、共享协议和值定义引用 `quwoquan_service/contracts/metadata/**`，不在规格复制。
- 未完成能力、外部阻断、风险与未来规划写入最低可关闭节点的 `OPEN-###`。解决后删除 OPEN，并转为当前 REQ/设计事实；禁止中央 backlog 或完成日志。
- 不维护 feature registry/index、Journey registry、acceptance YAML、changelog、成熟度矩阵或第二套状态台账。
- 增量由当前会话目标、Git diff、代码/测试结果和 `make feature-tree-change-report` 表达；历史使用 `git log --follow`。
- 修改规格后运行 `make verify-feature-tree`；需要总览运行 `make feature-tree-overview`。

## 商用品质默认门

- Review：从产品、架构、代码、质量、测试、用户、运维、运营八角色检查契约漂移、无测试、无观测、体验断点、第二真相源和不合理抽象。
- 三层测试：`local_contract`、`api_integration`、`user_acceptance` 必须映射 UAT/DOM/SIT/GWT/contract；Remote 行为必须能回到测试树内对象级 typed double/Provider/Widget/领域规则覆盖，任何测试 double 不得进入环境 App。
- 四环境：`alpha`、`beta`、`gamma`、`prod` 的 App 均使用同一 Remote composition；内容、Creator、实体与媒体只来自 canonical immutable release activation，用户、评论、圈子、会话与消息只经所属领域公开 command/event 生效。Alpha/Beta/Gamma 可由 `stackctl verify` 使用真实非生产身份创建候选绑定验收数据，Prod 只接受真实用户或正式运营行为；任何环境均禁止 fixture、直接数据库 seed 与派生投影预填。分层证明配置、包纯度、URL/topology、部署与回滚。不存在 `prod-gray`，生产灰度只是 `prod` rollout stage。
- 错误链路：metadata errors、HTTP 响应、端侧 mapper/UI、恢复动作、埋点、日志、告警和测试必须同源。
- 可观测与配置：新增页面、API、行为信号、推荐策略和数据发布必须声明 SLI/SLO、指标、采样、保留、告警、配置来源、灰度与回滚。
- 无法证明时返回 `GATE_BLOCK`，补规格、metadata、测试或运维证据。

## 编码总约束

- `quwoquan_service/services/<service>/contracts/**` 是该服务业务对象、wire 字段、错误码、path、route、surface、operation 与 decoder context 的唯一真相源；`quwoquan_service/contracts/metadata/**` 只保留跨服务 schema、共享协议和值定义。先 contracts，后 verify/codegen，再写业务逻辑，禁止手改 codegen 产物。
- 错误码使用 `MODULE.KIND.REASON`；动态上下文只进入 string-only `context.attributes`。
- Mongo/bson 可用 `_id`；客户端 HTTP/WS/DTO JSON 只认 canonical `id`/`postId` 等键。
- 契约单轨：禁止版本信封、wire 多键双读、dual-read/dual-write、长期 shim、compat/warn-only 逃逸和为错误实现加 fallback。
- `.qwq_output/` 只存可删除、可重建的运行输出；删除后仍必须能凭受版本控制真相源重建。
- 源码树不得保留 `__pycache__/`、`*.pyc`、`*.pyo`、`.pytest_cache/`；缓存重定向到 `.qwq_output/env/repo/local/**`。
- 每个第一方服务以 `environments/<alpha|beta|gamma|prod>/` 作为环境自治入口，共享定义只存在于服务内 `config/schema.yaml`、`resources/` 与 `deploy/base/`；环境之间禁止继承。环境装配、部署、巡检、修复统一使用 `python3 quwoquan_ops/cli/stackctl.py`。
- 本地长期分支只允许 `dev1.0`；未经用户明确同意不得创建、提交或推送其他分支。
- 脏工作树是常态；禁止回滚、覆盖或清理与当前任务无关的用户改动。

## 工作方式

- 默认中文说明与注释；代码标识符、命令和路径保持原文。
- 优先做可验证的小改动，执行与影响面匹配的 gate/test。
- 本地 `/commit` pre-commit 仅跑 L0 `quwoquan_ops/gate/commit_gate.sh`（目标 ≤10 分钟，硬顶 15 分钟）；全量 local_contract 由 CI Delivery Gate 分片承接，禁止把 `--no-verify` 当常规合入手段。
- 稳定、反复出现的规则写入最近的 `AGENTS.md`、特性树 README 或对应命令，不留在会话临时约定中。
