# quwoquan Agent Guide

声明全仓不变量；领域与 Review 约束渐进加载。

## Skill-first 最小上下文

顺序固定为：根 `AGENTS.md` → `.agents/skills/*/SKILL.md` metadata 选择唯一 Workflow Skill（简单问答可跳过）→ Skill body → PRE 确定 exact target → 最近子树 `AGENTS.md` → exact contexts/tests。已知路径可先读子树规则，但子树不参与路由；不建中央关键词表、resolver 或第二流程正文。

`make feature-context TARGET=<exact-path>` 仅提供非授权上下文查询；无关联或多关联都不阻断 mutation。mutation 以用户授权、整文件 exact-path claim 冲突检查与 current actual diff/ImpactPlan 为边界，Feature context 不授予写权限。细则归 REQ-002 与各 Skill PRE。

Feature Tree 上下文算法见 [`specs/feature-tree/README.md`](specs/feature-tree/README.md)。各层只表达本层 Journey/DOM/SIT/GWT 与设计决定；不建 backlog 或完成台账，版本化 Human/Review registry 保持各自独立权威边界。

## 工作流选择

`.agents/skills/<name>/SKILL.md` 是 Workflow Skill 的唯一 authoring source 与宿主发现面；自然语言与显式入口加载同一 Skill body 并进入同一生命周期。

- 始终选择当前最早且足以闭环的 Skill；目标、证据或阻断改变时按 metadata 切换，而不是沿用错误流程。
- Skill 就地声明五段生命周期；根与子树不复制步骤或路由。
- 工作流切换只改变执行契约，不扩大用户授权；提交、发布、外部写入、不可逆动作和高风险环境操作仍须满足原有明确授权与确认边界。

## 真相源与修改顺序

- 用户价值、行为和验收属于 Feature spec；跨对象边界、恢复与设计不变量属于最近 L2/L1 design。
- 字段、path、operation、surface、route、event、metric、错误码和 wire 恢复语义属于服务 `contracts/**`；跨服务共享 schema/协议属于 `quwoquan_service/contracts/metadata/**`。
- 边界、结果状态、模型属性与显式配置等横切工程语义属于 [`runtime/system-architecture-and-engineering-guide`](specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md)，只由技术 profile 加载。
- 先改 authoring source，再跑 verify/codegen，最后改业务逻辑；禁止手改生成物、为错误实现加 fallback，或以 dual-read/dual-write、长期 shim 和 warn-only 回避单轨契约。
- 未完成能力、外部阻断、风险和未来规划写入最低可关闭节点的 `OPEN-###`。

修改规格后运行 `make verify-feature-tree`；需概览时运行 `make feature-tree-overview`。

## 证据诚实性

- 验证匹配影响面，分层报告源码/契约、测试、构建/启动、runtime、release/readback、设备/UAT；上游 PASS 不代表下游闭环。
- 任一 required 证据失败时保留首个 typed blocker，不用旧 receipt、旧 plan 或旧指纹冒充当前完成。
- 开发期 POST 默认零 Reviewer，只报告命名 evidence；仅显式 `/review` 或准出（lane acceptance/integration 发布、handoff、release）派审，形态归 review Skill。
- 无法证明时返回 `GATE_BLOCK`。失败门禁不包装为成功，也不因工作树其他红项隐藏本任务结果。

## 共享工作树与安全

- 脏工作树是常态。写入前声明不重叠的整文件exact path scope并与活跃claim对齐；不同 scope 可并行；相等/父子/rename/delete/generated 冲突只允许一个 writer。只编辑本 scope，禁止回滚、覆盖、清理、kill 或隔离他人成果。
- 一 worktree 一 Cursor 工作区；根只能是固定 lane 或唯一 `integration/`，禁止容器根、bare repo 或多 worktree workspace。
- 路径 owner 与 lane 边界只读 `quwoquan_ops/policies/lane_ownership.yaml`（engineering=开发→发布态工程面，ops=发布后运行态）。
- 独立读取/测试/不重叠修改可并行；candidate 用私有 `GIT_INDEX_FILE` 且 scope 外继承 parent；默认 index/HEAD/ref、环境、设备、共享产物/锁串行。
- `.qwq_output/` 只放可删除且可从版本控制真相源重建的运行输出。源码树禁止 `__pycache__/`、`*.pyc`、`*.pyo`、`.pytest_cache/`；缓存重定向到 `.qwq_output/env/repo/local/**`。
- 不泄露 secret/PII；不执行超出用户范围的删除、发布、外部写入或不可逆动作。

## Git 不变量

- 本地分支闭集为 `dev1.0`、只读 `main` 与六条长期 `lane/*`；lane upstream 统一为 `origin/dev1.0` 且不推远端，远端仅 `dev1.0/main`。`dev1.0` 只接受 trusted publisher CAS、持 bundle 的 integration non-force FF publish、managed backsync；其他 push、force/delete、来源不符均拒绝。唯一 promotion 为 `dev1.0 -> main`；Prod 只消费 main-reachable stable tag AdmissionFact 的 exact OCI digests。
- 新建 linked worktree 或再次 clone 每次都须先取得用户明确授权，并以 `QWQ_WORKTREE_AUTHZ="<授权理由>" <command>` 执行。clone 后先运行 `make install-hooks`。
- 无验真 bundle/admission 不移动 `origin/dev1.0`；`env=1` 不证明 admission。bundle/admission、Lane Gate 左移、dev 发布资格与回同步只读 `daily-merge-release-strategy` REQ-002 及两个同步 Skill；日常 dev 由 accept/bundle/integrate/hook 强制。普通凭据可 FF 但不证明 Alpha；hosted 强制缺口保持 OPEN-track；dev 禁删/禁非 FF。同步目标只取本轮已发布 `origin/dev1.0` exact SHA，不回落本地 dev、不推 lane。Gamma/IQF 后仅 `dev1.0 -> main` PR，MainSourceSeal 后仅受管 backsync。
- 只有用户明确要求时才创建提交；提交按 `commit` Skill 执行，不用 `--no-verify` 作为常规通道。

## 沟通

默认使用中文说明、计划、总结和提交信息；思考过程与代码内联注释同样默认中文。代码标识符、命令与路径保持原文；日志、报错与外部资料的原文引用及无通行中文译名的专有名词保持原文。先给结论，再给必要证据、未决项和下一步。
