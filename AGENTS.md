# quwoquan Agent Guide

本文件只声明全仓始终成立的执行不变量。领域、服务、功能、交付件和 Review 角色约束按目标渐进加载，不复制到这里。

## 最小上下文

1. 先读本文件与目标路径上最近的子树 `AGENTS.md`。
2. 已知 spec 或代码路径时运行 `make feature-context TARGET=<path>`，消费默认 compact manifest；只有人工诊断才请求 expanded 格式。
3. manifest 是开发 PRE 与 Review POST 共享的 owner 事实。多 owner、无 owner 或锚点冲突时返回 typed `GATE_BLOCK`，先修正特性树归属。
4. 只读 manifest 列出的 canonical spec/design/contracts、适用 `AGENTS.md`、Workflow Skill 与必要测试；不沿角色 reference 或 IDE rule 追链功能事实。

Feature Tree 结构与 owner 算法见 [`specs/feature-tree/README.md`](specs/feature-tree/README.md)。AppRoot/L1/L2/L3 各自只拥有对应层级的 Journey/DOM/SIT/GWT 与设计决定；不建中央 backlog、feature registry、第二状态台账或完成日志。

## 工作流选择

`.agents/skills/<name>/SKILL.md` 是 Workflow Skill 唯一真相源。根据用户意图选择最早且足以闭环的工作流：

- 定位与风险：`explore`
- 需求与可测验收：`prd`
- 边界、回滚、观测与架构决定：`design`
- 已冻结规格的实现/修复：`dev`
- 中断续跑：`continue`
- 轮次收口：`plan-next`
- 评审：`review`
- 用户明确要求提交：`commit`
- 环境、内容生产、事故检视与教训沉淀：分别由 `environment-ops`、`content-production`、`incident-inspection`、`distill` 按触发词加载。

自然语言与显式 Skill 进入同一执行契约。Skill 就地声明触发与输入、执行、完成证据、失败停止和条件性交接；根规则不复制各工作流步骤。

## 真相源与修改顺序

- 用户价值、行为和验收属于 Feature spec；跨对象边界、恢复与设计不变量属于最近 L2/L1 design。
- 字段、path、operation、surface、route、event、metric、错误码和 wire 恢复语义属于服务 `contracts/**`；跨服务共享 schema/协议属于 `quwoquan_service/contracts/metadata/**`。
- 边界、结果状态、模型属性与显式配置等横切工程语义属于 [`runtime/system-architecture-and-engineering-guide`](specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md)，只由技术 profile 加载。
- 先改 authoring source，再跑 verify/codegen，最后改业务逻辑；禁止手改生成物、为错误实现加 fallback，或以 dual-read/dual-write、长期 shim 和 warn-only 回避单轨契约。
- 未完成能力、外部阻断、风险和未来规划写入最低可关闭节点的 `OPEN-###`。

修改规格后运行 `make verify-feature-tree`；需概览时运行 `make feature-tree-overview`。

## 证据诚实性

- 验证与影响面匹配，分开报告源码/契约、本地测试、编译/打包/安装/启动、runtime health、release/import/readback 和真实设备/UAT；上游 PASS 不代表下游闭环。
- 任一 required 证据失败时保留首个 typed blocker，不用旧 receipt、旧 plan 或旧指纹冒充当前完成。
- Review PRE 不自动派 Reviewer；POST 消费同一 owner manifest，先执行去重命名 evidence，再按 Review Skill 的角色预算派发。Reviewer 不补跑 gate。
- 无法证明时返回 `GATE_BLOCK`。失败门禁不包装为成功，也不因工作树其他红项隐藏本任务结果。

## 共享工作树与安全

- 脏工作树是常态。修改前检查 HEAD/status、目标路径 diff、untracked 与活跃 writer；只编辑本任务所有的字节，禁止回滚、覆盖、清理、kill 或隔离其他 owner 的成果。
- 并行执行独立读取、测试与不同 owner 的修改；同一环境变更、共享生成物和共享锁串行。
- `.qwq_output/` 只放可删除且可从版本控制真相源重建的运行输出。源码树禁止 `__pycache__/`、`*.pyc`、`*.pyo`、`.pytest_cache/`；缓存重定向到 `.qwq_output/env/repo/local/**`。
- 不泄露 secret/PII；不执行超出用户范围的删除、发布、外部写入或不可逆动作。

## Git 不变量

- 本地与远端只允许 `dev1.0` 与 `main`；日常开发合入 `dev1.0`，唯一 PR 边为 `dev1.0 -> main`。Prod source 必须是可达 `main` 的精确 SHA。
- 新建 linked worktree 或再次 clone 每次都须先取得用户明确授权，并以 `QWQ_WORKTREE_AUTHZ="<授权理由>" <command>` 执行。clone 后先运行 `make install-hooks`。
- 只有用户明确要求时才创建提交；提交按 `commit` Skill 执行，不用 `--no-verify` 作为常规通道。

## 沟通

默认使用中文说明、计划、总结和提交信息；思考过程与代码内联注释同样默认中文。代码标识符、命令与路径保持原文；日志、报错与外部资料的原文引用及无通行中文译名的专有名词保持原文。先给结论，再给必要证据、未决项和下一步。
