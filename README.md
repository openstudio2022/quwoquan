# 趣我圈工程目录说明

本仓库按领域自治组织。源代码 worktree 位于项目容器根的同名子目录；`.qwq_output/` 只保存可删除重跑的运行证据、发布包、进程记录和缓存，绝不保存配置、部署拓扑、证书规则或密钥。

Cursor 必须“一 worktree 一工作区”：只打开当前 `integration/` 或某个 lane 目录，禁止打开容器根、bare `quwoquan.git/`，也禁止多根 `.code-workspace`。这样终端、Git 身份、hook 和 Agent 的 writer scope 始终属于同一条 lane。

## 顶层目录

```text
quwoquan_app/       Flutter App 工程，拥有 App 配置、发布规则、App 自用包和端侧观测片段。
quwoquan_service/   服务端工程，拥有服务契约、服务配置、服务部署模板和服务观测片段。
quwoquan_data/      数据工程，由宿主 AI Agent 按内容生产 Skill 生成、发布并交付不可变内容对象。
quwoquan_ops/       Ops 横切控制面，拥有 stackctl、gate、CI、环境拓扑、策略、全局可观测和 Ops Portal。
specs/              当前产品、架构、特性树与验收的唯一规格体系；不维护 changelog、registry 或 backlog。
docs/               少量长期工程说明；不承载命令协议、功能规格、状态台账或风险清单。
.github/            CI 工作流入口。
.qwq_output/        gitignored；唯一运行输出根，不是配置或状态真相源。
```

## 本地忽略目录

这些目录可能在开发机上出现，但不是工程源码域，不参与职责划分：

```text
ref/                外部参考实现或资料，不提交。
.vscode/            本地 IDE 配置。
quwoquan_ops/portal/node_modules/ Ops Portal Node 依赖缓存。
quwoquan_app/build/ Flutter 构建缓存。
quwoquan_app/.dart_tool/ Dart/Flutter 工具缓存。
```

禁止恢复这些历史顶层目录：

```text
agent_ops, deploy, artifacts, releases, apps, packages, state, contracts,
changes, openspec, app_log, runtime, build, tmp, tools, githooks, social_content_app
```

## 目录边界

- 领域私有资产归领域：服务 Dockerfile、部署规则和 release config 位于 `quwoquan_service/services/<service>/`；App 配置与发布规则位于 `quwoquan_app/configs/`、`quwoquan_app/deploy/`；Data 的可复用输入、canonical publish 与发布规则归 `quwoquan_data/`，内容阶段顺序只由内容生产 Skill 定义。
- Engineering 拥有开发到发布态的软件工程控制：Agent/Skill、review/handoff、Feature Tree、CI/CD pipeline-as-code、gate/hook、branch/worktree/lane policy 与 local readiness。
- Ops 拥有发布后运行态和横切运行能力：stackctl 运行编排、四环境 manifests、环境拓扑、全局可观测、runbook、migration、Portal、hosted authority 与 provider conformance。`quwoquan_ops/` 是历史物理根和横切能力载体，不等于所有内容都归 `lane/ops`；逐路径归属只读 `quwoquan_ops/policies/lane_ownership.yaml`。
- 根目录不承载工具 workspace：Ops Portal 的 `package.json`、`package-lock.json` 和 `node_modules` 归 `quwoquan_ops/portal/`，根目录不保留 Node workspace。
- 运行输出按唯一 taxonomy 归位：环境输出为 `.qwq_output/env/<env>/{runs,observability,local/<target>/{process,cache}}/`，repo 级输出位于 `.qwq_output/env/repo/`，数据工程输出为 `.qwq_output/data/{tasks,releases,local}/`。App、Service、Legal-static 与 Portal 的 deploy payload、渲染配置、Caddy、TLS 和 env 文件统一写入 `QWQ_DEPLOY_WORK_ROOT/<target>/`；其生成规则和网络配置只在领域 `deploy/configs` 与 `quwoquan_ops/environments/` 中定义。

## 常用入口

```bash
python3 quwoquan_ops/cli/stackctl.py package --env alpha --kind runtime --include-services
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --profile integration
cd quwoquan_ops/portal && npm test && npm run build
bash quwoquan_ops/gate/gate_repo.sh
```

## 固定 worktree 布局

项目根、bare hub、六 lane 和唯一 integration 的物理关系由 `quwoquan_ops/policies/worktree_policy.yaml` 声明；分支闭集仍只由 `branch_policy.yaml` 声明，路径 ownership 只由 `lane_ownership.yaml` 声明。

```text
quwoquan/
  quwoquan.git/       bare hub（不得作为 Cursor 工作区）
  integration/        dev1.0，验真 acceptance bundle 后仅快进发布的集成工作区
  product-mainline/   lane/product-mainline
  data-engineering/   lane/data-engineering
  engineering/        lane/engineering
  ops/                lane/ops
  small-fix/          lane/small-fix
  refactor/           lane/refactor
```

`make lane-bootstrap` 与 `make lane-resync` 只打印待人工审阅的 mutation 命令；`make lane-preflight` 才执行只读身份/clean/HEAD 校验。

## 分支治理

- 本地保留 `dev1.0`、只读 `main` 与六条长期 `lane/*`；六 lane 仅为检出/验收 identity，upstream 统一指向 `origin/dev1.0`。远端闭集仅 `dev1.0`/`main`，不得推送 lane，也不依赖 lane PR。lane 与 integration 可按不重叠整文件 scope 构造 exact candidate；canonical 更新合同区分受信 publisher、验真 acceptance admission 的 integration FF 发布与受管 system backsync，不存在 source-only 旁路。
- `main` 只表示 source-admitted 的最新可用源码；Prod 唯一 selector 是 `ReleaseTagAdmissionFact` 中绑定的 main-reachable stable tag peeled commit 与 exact OCI digests。禁止白名单外分支、lane 直达 `main`、绕过 promotion PR 直接更新 `main`，也禁止以 `main HEAD` 或裸 SHA 选择 Prod。仓内 gate 只证明仓库合同，Hosted ruleset/readback 仍须独立验真。
- 本地执行 `bash quwoquan_ops/hooks/run_install_hooks.sh` 后，`pre-commit` 只做 staged boundary（secret/PII、generated/cache 边界与 `--local-commit` 当前 HEAD 检查），`pre-push` 只做 branch policy，不重跑 readiness：拒绝远端 lane、main direct push 与未知 ref；integration 只有 exact admission、匹配 dev 来源/remote 和 before/after non-force FF 证明才可发布。最终 publisher 独立验真 admission 自摘要、前驱引用/签名/有效期、candidate/tree、规范路径/remote 和 ancestry；仅 `QWQ_ACCEPTANCE_PUBLISH=1` 不构成资格。缺证据、漂移、non-FF、force/delete 均阻断。
- `--local-commit` 只检查当前 HEAD 非 detached、Git authority 可读且属于 allowed local branches，不枚举其他陈旧 refs；全 ref 治理仍由无参数默认模式执行。同步 Skill 与 lane resync 每轮冻结 fetch/权威读回后的已发布 `origin/dev1.0` exact SHA，不回落本地未发布 dev；常规仅 FF，分叉须当前 lane 显式授权合并并重新验收。脏重叠、分叉或进行中操作在跨 lane 回同步中零写，保留 WIP，不推远端 lane。
- 质量生产与发布分开：lane `make accept` 对同一 exact candidate 去重执行 required 本地 readiness、Lane Gate 完整检查集合、Alpha（必跑）与 Beta（仅 `BETA=1`），形成 portable acceptance bundle；integration 在移动 HEAD 前先验 bundle/远端 parent，通过才本地 FF，并由 `make integrate ACCEPTANCE_BUNDLE=… PUBLISH=1` admit/publish/readback。本地 accept/bundle/integrate/hook 强制验真且不重跑完整套件。可按授权撤 dev 旧 `04. Lane Gate` required check、删除已可达已发布 dev 且未发布增量已保全的远端 lane，不等待专用 publisher/broker；hosted 资格强制仍是 daily-merge OPEN-004 `track`，不阻塞有效本地验收后的日常合入。服务端普通授权凭据仍可 FF dev，不能保证 Alpha 必经；dev 禁删/禁 non-FF 与 main promotion 强制继续保留。
- 后续闭环是已发布 current dev head 的 Gamma → IQF → `dev1.0 -> main` PR/Delivery Gate → MainSourceSeal → 受管 system backsync → 已发布 dev → integration/本地 lane。缺前驱不得推进，dev 发布不等于 main 合入或 Prod 成功；生产仍沿 main + stable tag 的现行正式链。生产治理仅作 `administrative` 简化：合并冗余人工审批和重复 CI，不削弱 main/stable、签名物料、health、Provider、回滚等技术门，也不授予直接放量权。成功 publish 后下一次 readiness 排除已发布变化，但未发布差异增长时不保证常量范围/耗时。L0 `make commit-gate`（预算 180 秒，硬顶 300 秒）只由 commit Skill 在用户明确要求提交时运行，不挂 Git hook。

规格入口见 `specs/feature-tree/README.md`，Codex/Cursor 执行约束见 `AGENTS.md` 与 `.cursor/commands/*.md`。
