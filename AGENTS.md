# quwoquan Agent Guide

本文件只声明全仓始终成立的执行不变量。领域、服务、功能、交付件和 Review 角色约束按目标渐进加载，不复制到这里。

## Skill-first 最小上下文

顺序固定为：根 `AGENTS.md` → `.agents/skills/*/SKILL.md` metadata 选择唯一 Workflow Skill（简单问答可跳过）→ Skill body → PRE 确定 exact target → 最近子树 `AGENTS.md` → exact contexts/tests。已知路径可先读子树规则，但子树不参与路由；不建中央关键词表、resolver 或第二流程正文。

只读/控制型 Skill 对 `make feature-context TARGET=<exact-path>` 的 owner 解析 best-effort，无 owner 时记录 typed 结果继续只读；任何 mutation 或送审 Skill 写入前必须持有唯一 current owner identity ref，否则 `GATE_BLOCK`。细则归 REQ-002 与各 Skill PRE。

Feature Tree 与 owner 算法见 [`specs/feature-tree/README.md`](specs/feature-tree/README.md)。各层只拥有本层 Journey/DOM/SIT/GWT 与设计决定；不建 backlog 或完成台账，版本化 Human/Review registry 只在各自 owner 内拥有映射。

## 工作流选择

`.agents/skills/<name>/SKILL.md` 是 Workflow Skill 的唯一 authoring source 与宿主发现面；自然语言与显式入口加载同一 Skill body 并进入同一生命周期。

- 始终选择当前最早且足以闭环的 Skill；目标、证据或阻断改变时按 metadata 切换，而不是沿用错误流程。
- Skill 就地声明输入、执行、完成证据、失败停止和条件性交接；根与子树规则不复制步骤、不声明自然语言路由。
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
- 开发期 POST 默认零 Reviewer，只报告命名 evidence；仅显式 `/review` 或准出（lane→`dev1.0` PR、handoff、release）派审，形态归 review Skill。
- 无法证明时返回 `GATE_BLOCK`。失败门禁不包装为成功，也不因工作树其他红项隐藏本任务结果。

## 共享工作树与安全

- 脏工作树是常态。写入前声明不重叠的整文件exact path scope并与活跃claim对齐；同一worktree可并行写不同scope，path相等/父子/rename/delete/generated冲突只允许一个winner。只编辑本scope字节，禁止回滚、覆盖、清理、kill或隔离其他owner成果。
- 一 worktree 一 Cursor 工作区。工作区根必须是当前固定 lane 目录或唯一 `integration/`；禁止把项目容器根、bare `quwoquan.git/` 或多个 worktree 作为单个/多根 workspace 打开。
- 路径 owner 与 lane 边界只读 `quwoquan_ops/policies/lane_ownership.yaml`（engineering=开发→发布态工程面，ops=发布后运行态）。
- 并行执行独立读取、测试与不重叠scope修改；candidate使用私有`GIT_INDEX_FILE`且scope外tree继承parent。默认index/HEAD/ref、同一环境、设备、共享生成物与共享锁串行。
- `.qwq_output/` 只放可删除且可从版本控制真相源重建的运行输出。源码树禁止 `__pycache__/`、`*.pyc`、`*.pyo`、`.pytest_cache/`；缓存重定向到 `.qwq_output/env/repo/local/**`。
- 不泄露 secret/PII；不执行超出用户范围的删除、发布、外部写入或不可逆动作。

## Git 不变量

- 本地与远端只允许`dev1.0`、`main`与六条长期`lane/*`；lane只推同名lane。`dev1.0`只接受trusted publisher CAS、`integration/`匹配本地ref的non-force fast-forward push与managed system backsync三条通道，非快进、force/delete或来源不匹配一律阻断；`main`本地只读、禁止direct push，唯一promotion边为`dev1.0 -> main`；Prod只消费main-reachable stable tag AdmissionFact绑定的exact OCI digests。
- 新建 linked worktree 或再次 clone 每次都须先取得用户明确授权，并以 `QWQ_WORKTREE_AUTHZ="<授权理由>" <command>` 执行。clone 后先运行 `make install-hooks`。
- 裸push只提交源码、不签发任何资格，资格只经`make integrate`（`daily-merge-release-strategy` REQ-002）。lane 与 dev 的本地同步只走 `sync-lane-from-dev`（dev→本 lane）和 `integrate-lane-to-dev`（lane→dev 并回同步各 lane），不手拼 merge。
- 只有用户明确要求时才创建提交；提交按 `commit` Skill 执行，不用 `--no-verify` 作为常规通道。

## 沟通

默认使用中文说明、计划、总结和提交信息；思考过程与代码内联注释同样默认中文。代码标识符、命令与路径保持原文；日志、报错与外部资料的原文引用及无通行中文译名的专有名词保持原文。先给结论，再给必要证据、未决项和下一步。
