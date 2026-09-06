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
  integration/        dev1.0，可提交并仅快进推送的集成工作区
  product-mainline/   lane/product-mainline
  data-engineering/   lane/data-engineering
  engineering/        lane/engineering
  ops/                lane/ops
  small-fix/          lane/small-fix
  refactor/           lane/refactor
```

`make lane-bootstrap` 与 `make lane-resync` 只打印待人工审阅的 mutation 命令；`make lane-preflight` 才执行只读身份/clean/HEAD 校验。

## 分支治理

- 本地与远端只允许 `dev1.0`、`main` 与六条声明的长期 `lane/*` 分支：lane 与 integration 都可构造 exact scoped candidate，发布晋级只走 `dev1.0 -> main` PR；canonical `integration_branch_updates` 永久合同允许 trusted integration publisher CAS、匹配 `integration/dev1.0` 的普通认证 non-force fast-forward push，以及 promotion 后可证明的 system fast-forward backsync 更新 `dev1.0`。lane 仍只可推同名 lane。
- `main` 只表示 source-admitted 的最新可用源码；Prod 唯一 selector 是 `ReleaseTagAdmissionFact` 中绑定的 main-reachable stable tag peeled commit 与 exact OCI digests。禁止白名单外分支、lane 直达 `main`、绕过 promotion PR 直接更新 `main`，也禁止以 `main HEAD` 或裸 SHA 选择 Prod。仓内 gate 只证明仓库合同，Hosted ruleset/readback 仍须独立验真。
- 本地执行 `bash quwoquan_ops/hooks/run_install_hooks.sh` 后，`pre-commit` 只做 staged boundary（secret/PII、generated/cache 边界，以及 `--local-commit` 当前 HEAD 分支检查），`pre-push` 只做 branch policy：普通 lane 只推同名远端；`integration/` 仅可从匹配本地 `refs/heads/dev1.0` 向远端同名分支执行普通认证 non-force fast-forward push，并使用 update line 的 before/after OID 证明 ancestry；缺 OID、authority 不可用、非快进、force/delete、来源不匹配、`main` direct push 或未知 ref 全部阻断。trusted publisher CAS 与可证明的受管 system fast-forward backsync 仍保留；两类 hook 都不消费 readiness 回执，秒级完成。
- `--local-commit` 只要求当前 HEAD 非 detached、Git authority 可读且分支属于 allowed local branches，不枚举或治理其他 local/remote-tracking refs；无参数默认模式仍执行全 ref 治理，`--pre-push` 直接执行永久更新合同。integration 工作区 direct fast-forward push 只移动源码 ref，不生产或授予 `integrationEligibility`、Alpha/Beta/Gamma、`IntegrationQualificationFact`、promotion、release 或 Prod authority；需要晋级/发布时仍须 exact candidate + Alpha/Beta、current dev head Gamma 与后续既有资格链。
- 硬门只在准出，且全部位于本地 Environment Ops 执行面：进入 `dev1.0` 的 exact candidate 由 `make integrate` 在远端 ref 移动前完成本地 readiness（exact delta）、Alpha（ImpactPlan 判定 `abg_release_sensitive` 时含 Beta）`EnvironmentAcceptanceFact` 与 publish admission，再以 expected-old lease fast-forward 发布并读回；lane→`dev1.0` PR 只是评审载体，hosted 侧不设 lane required check。`dev1.0 -> main` 前由 `make gate-release ENV=gamma` 承接全量 local_contract（L2）与 Gamma；GitHub `03. Delivery Gate` 只验真不可变证据。L0 `make commit-gate`（预算 180 秒，硬顶 300 秒）由 commit Skill 在用户要求提交时显式运行，并使用同一 `--local-commit` 当前分支边界，不挂 git hook。

规格入口见 `specs/feature-tree/README.md`，Codex/Cursor 执行约束见 `AGENTS.md` 与 `.cursor/commands/*.md`。
