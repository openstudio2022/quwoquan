# quwoquan Agent Guide

本文件只声明全仓始终成立的执行不变量。领域、服务、功能、交付件和 Review 角色约束按目标渐进加载，不复制到这里。

## Skill-first 最小上下文

顺序固定为：根 `AGENTS.md` → `.agents/skills/*/SKILL.md` metadata 选择唯一 Workflow Skill（简单问答可跳过）→ Skill body → PRE 确定 exact target → 最近子树 `AGENTS.md` → exact contexts/tests。已知路径可先读子树规则，但子树不参与路由；不建中央关键词表、resolver 或第二流程正文。

`explore`、`plan-next` 和 `continue` 的只读恢复 best-effort 运行 `make feature-context TARGET=<exact-path>`：唯一 owner 时消费 compact immutable exact ref；无 owner、多 owner或解析失败时记录 typed 结果，按当前 Git 快照继续只读且不得据此 mutation。`prd`、`design`、`dev` 写入前必须持有唯一 PRE owner identity ref，否则 `GATE_BLOCK`；显式或准出 Review 以该 ref 为 predecessor，并为 exact changed paths 生成 current candidate evidence ref。expanded 仅供人工诊断。

Feature Tree 与 owner 算法见 [`specs/feature-tree/README.md`](specs/feature-tree/README.md)。各层只拥有本层 Journey/DOM/SIT/GWT 与设计决定；不建中央自然语言 resolver、第二流程正文、backlog 或完成台账，版本化 Human/Review registry 只在各自 owner 内拥有映射。

## 工作流选择

`.agents/skills/<name>/SKILL.md` 同时是 Workflow Skill 的唯一 authoring source 与宿主发现面。自然语言与显式入口必须加载同一 Skill body 并进入同一生命周期，不以机器 boolean、route receipt 或中央 manifest 自证同轨。

- 始终选择当前最早且足以闭环的 Skill；执行中若目标、证据或阻断改变，应重新按 metadata 自适应切换到足以闭环的 Skill，而不是沿用错误流程。
- Skill 就地声明输入、执行、完成证据、失败停止和条件性交接；根规则不复制步骤，子树 `AGENTS.md` 不声明自然语言路由。
- 工作流切换只改变执行契约，不扩大用户授权；提交、发布、外部写入、不可逆动作和高风险环境操作仍须满足原有明确授权与确认边界。

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
- 开发期 POST 默认零 Reviewer，只报告命名 evidence；仅显式 `/review` 或准出（lane→`dev1.0` PR、handoff、release）派审，携带 PRE owner identity + POST candidate predecessor，先去重 evidence，再按主审加最多一名专审执行；Reviewer 不补跑 gate。
- 无法证明时返回 `GATE_BLOCK`。失败门禁不包装为成功，也不因工作树其他红项隐藏本任务结果。

## 共享工作树与安全

- 脏工作树是常态。修改前检查 HEAD/status、目标路径 diff、untracked 与活跃 writer；只编辑本任务所有的字节，禁止回滚、覆盖、清理、kill 或隔离其他 owner 的成果。
- 一 worktree 一 Cursor 工作区。工作区根必须是当前固定 lane 目录或唯一 `integration/`；禁止把项目容器根、bare `quwoquan.git/` 或多个 worktree 作为单个/多根 workspace 打开。
- `lane/engineering` 拥有开发→发布态工程面（Agent/Skill、review/handoff、Feature Tree、CI/CD、gate/hook、branch/worktree/lane governance、local readiness）；`lane/ops` 只拥有发布后运行态（stackctl、环境 manifests、observability、runbook、migration、Portal、hosted authority/provider conformance）。路径判定只读 `lane_ownership.yaml`。
- 并行执行独立读取、测试与不同 owner 的修改；同一环境变更、共享生成物和共享锁串行。
- `.qwq_output/` 只放可删除且可从版本控制真相源重建的运行输出。源码树禁止 `__pycache__/`、`*.pyc`、`*.pyo`、`.pytest_cache/`；缓存重定向到 `.qwq_output/env/repo/local/**`。
- 不泄露 secret/PII；不执行超出用户范围的删除、发布、外部写入或不可逆动作。

## Git 不变量

- 本地与远端只允许 `dev1.0`、`main` 与六条声明的长期 `lane/*` 分支；日常开发主要在 `lane/*`，经 PR 或 `integration/` 同名 expected-old 快进合入 `dev1.0`；唯一发布 PR 边为 `dev1.0 -> main`。Prod source 必须是可达 `main` 的精确 SHA。
- 新建 linked worktree 或再次 clone 每次都须先取得用户明确授权，并以 `QWQ_WORKTREE_AUTHZ="<授权理由>" <command>` 执行。clone 后先运行 `make install-hooks`。
- `main` 是本地只读分支，不得本地提交；`integration/`（`dev1.0`）与六条 lane 一视同仁：可本地合入并推送同名远端，integration 另强制 expected-old 快进。日常功能开发优先同名 lane worktree，路径与分支由 `worktree_policy.yaml` 交叉验证。
- 只有用户明确要求时才创建提交；提交按 `commit` Skill 执行，不用 `--no-verify` 作为常规通道。

## 沟通

默认使用中文说明、计划、总结和提交信息；思考过程与代码内联注释同样默认中文。代码标识符、命令与路径保持原文；日志、报错与外部资料的原文引用及无通行中文译名的专有名词保持原文。先给结论，再给必要证据、未决项和下一步。
