# 趣我圈工程目录说明

本仓库按领域自治和 Ops 横切面治理组织。顶层只保留长期工程域；运行产物、日志、报告和本地状态统一进入 `.qwq_output/`，可整体删除重跑。

## 顶层目录

```text
quwoquan_app/       Flutter App 工程，拥有 App 配置、发布规则、App 自用包和端侧观测片段。
quwoquan_service/   服务端工程，拥有服务契约、服务配置、服务部署模板和服务观测片段。
quwoquan_data/      数据工程，拥有数据任务、模板、发布真相源和数据发布规则。
quwoquan_ops/       Ops 横切控制面，拥有 stackctl、gate、CI、环境拓扑、策略、全局可观测和 Ops Portal。
specs/              当前产品、架构、特性树、验收与 changelog 的唯一规格体系。
docs/               长期工程说明、Codex 工作流、外部依赖登记和正式风险 backlog；不承载功能规格真相源。
.github/            CI 工作流入口。
.qwq_output/        gitignored，本地运行输出、release package、验证证据、日志、指标和临时状态。
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

- 领域私有资产归领域：服务 Dockerfile、k8s、compose、release config 位于 `quwoquan_service/services/<service>/`；App 发布资产位于 `quwoquan_app/deploy/`；数据发布资产位于 `quwoquan_data/deploy/`。
- Ops 只放横切能力：统一调度、环境拓扑、跨域策略、gate、CI/CD、全局可观测、runbook 和 Portal。
- 根目录不承载工具 workspace：Ops Portal 的 `package.json`、`package-lock.json` 和 `node_modules` 归 `quwoquan_ops/portal/`，根目录不保留 Node workspace。
- 生成物只进 `.qwq_output/`：环境相关输出按 `.qwq_output/env/<env>/{runs,observability,release,local}` 归位，repo 工具状态按 `.qwq_output/env/repo/local` 归位，数据工程输出按 `.qwq_output/data/{runs,observability,release,local}` 归位。

## 常用入口

```bash
python3 quwoquan_ops/cli/stackctl.py package --env alpha --kind runtime --include-services
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --tier all
cd quwoquan_ops/portal && npm test && npm run build
bash quwoquan_ops/gate/gate_repo.sh
```

规格入口见 `specs/README.md`，文档边界见 `docs/README.md`，Codex 执行约束见 `AGENTS.md` 与 `docs/codex_workflow.md`。
