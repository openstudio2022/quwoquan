# 趣我圈工程目录说明

本仓库按领域自治和 Ops 横切面治理组织。顶层只保留长期工程域；`.qwq_output/` 只保存可删除重跑的运行证据、发布包、进程记录和缓存，绝不保存配置、部署拓扑、证书规则或密钥。

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
.worktrees/         本地 Git worktree 缓存。
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
- Ops 只放横切能力：统一调度、环境拓扑、跨域策略、gate、CI/CD、全局可观测、runbook 和 Portal。
- 根目录不承载工具 workspace：Ops Portal 的 `package.json`、`package-lock.json` 和 `node_modules` 归 `quwoquan_ops/portal/`，根目录不保留 Node workspace。
- 运行输出按唯一 taxonomy 归位：环境输出为 `.qwq_output/env/<env>/{runs,observability,local/<target>/{process,cache}}/`，repo 级输出位于 `.qwq_output/env/repo/`，数据工程输出为 `.qwq_output/data/{tasks,releases,local}/`。App、Service、Legal-static 与 Portal 的 deploy payload、渲染配置、Caddy、TLS 和 env 文件统一写入 `QWQ_DEPLOY_WORK_ROOT/<target>/`；其生成规则和网络配置只在领域 `deploy/configs` 与 `quwoquan_ops/environments/` 中定义。

## 常用入口

```bash
python3 quwoquan_ops/cli/stackctl.py package --env alpha --kind runtime --include-services
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --profile integration
cd quwoquan_ops/portal && npm test && npm run build
bash quwoquan_ops/gate/gate_repo.sh
```

## 分支治理

- 本地与远端只允许 `dev1.0`、`main` 与六条声明的长期 `lane/*` 分支：日常开发只经 `lane/* -> dev1.0` PR 合入集成真相源，发布晋级只走 `dev1.0 -> main` PR；`main -> dev1.0` 只允许 promotion 成功后的系统 fast-forward backsync。
- Prod 只接受可达 `main` 的精确 SHA；禁止白名单外分支、lane 直达 `main` 或绕过 promotion PR 直接更新 `main`。GitHub 原生保护不可用时，仓内 gate 只阻断 release eligibility，不冒充远端 ref 未被修改。
- 本地执行 `bash quwoquan_ops/hooks/run_install_hooks.sh` 后，`pre-commit` 只做 staged boundary（secret/PII、generated/cache 边界、branch policy），`pre-push` 只做 branch policy 阻断非白名单分支与直推 `dev1.0`/`main`；两者都不消费 readiness 回执，秒级完成。
- 硬门只在准出：`lane/* -> dev1.0` PR 由 CI Delivery Gate 分片承接全量 local_contract 与 required checks；L0 `make commit-gate`（目标 ≤10 分钟，硬顶 15 分钟）由 commit Skill 在用户要求提交时显式运行，不挂 git hook。

规格入口见 `specs/feature-tree/README.md`，Codex/Cursor 执行约束见 `AGENTS.md` 与 `.cursor/commands/*.md`。
