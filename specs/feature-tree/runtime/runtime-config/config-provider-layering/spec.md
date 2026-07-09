# L3 组件：config-provider-layering

## 功能定位

统一定义服务配置加载与覆盖的分层模型，确保云侧当前环境集合（如 alpha、beta、gamma、prod）以同一逻辑运行，避免配置漂移与服务内重复实现。端侧 App 构建环境为 alpha、beta、gamma、prod；生产只有一个 App 包，灰度由应用市场分发策略、端侧上下文与云侧灰度策略共同决定。

本节点作为 `runtime-config` 的核心子组件，承载配置来源优先级、环境识别、版本兼容校验与发布化接入约束。

## 目标能力

- 统一目录结构：`default/` + `alpha/` + `beta/` + `gamma/` + `prod/`
- 统一覆盖顺序：默认配置 -> 环境配置 -> 环境变量覆盖
- 显式环境识别：`APP_ENV=alpha|beta|gamma|prod`
- 配置发布版本：`CONFIG_VERSION` 与 `IMAGE_VERSION` 兼容校验
- 运行前校验：关键字段合法性与依赖连通性（如 Redis ping）
- 统一部署映射：`environments -> deploy process -> domains`
- 拓扑一致性：`beta`、`gamma`、`prod` 的进程-领域映射保持一致
- 端侧生产包唯一：不存在 `app-prod-gray`；生产灰度由云侧发布波次与策略表达，不单独占用环境枚举。
- 统一 environment topology：当前环境集合共享 `environment_topology_manifest.yaml` schema，alpha 仅通过 mock boundary 差异化。
- 统一环境包策略：app/service 包的 host allowlist、secret scope、dataSource 与 purity gate 由 manifest 驱动。
- 统一自动化入口：环境打包、校验、健康检查与巡检统一经 `stackctl` 暴露机器可读报告。

## 目录与版本示例（实施标准）

运行时公共挂载目录（容器内）：

```text
/etc/qwq-config/
  configs/
    content-service/
      default/config.yaml
      alpha/config.yaml
      beta/config.yaml
      gamma/config.yaml
      prod/config.yaml
  releases/
    config/
      content-service/
        v2026.02.27.1.yaml
        v2026.02.28.0.yaml
```

实例运行时环境变量：
- `SERVICE_NAME=content-service`
- `APP_ENV=prod`
- `CONFIG_VERSION=v2026.02.28.0`
- `IMAGE_VERSION=1.8.0`
- `CONFIG_ROOT=/etc/qwq-config`

加载顺序（固定）：
1. `${CONFIG_ROOT}/configs/${SERVICE_NAME}/default/config.yaml`
2. `${CONFIG_ROOT}/configs/${SERVICE_NAME}/${APP_ENV}/config.yaml`
3. `${CONFIG_ROOT}/quwoquan_service/services/${SERVICE_NAME}/${CONFIG_VERSION}.yaml`
4. 环境变量覆盖（最高优先级）

## Environment Topology Manifest

统一环境真相源：`quwoquan_ops/environments/environment_topology_manifest.yaml`

每个环境必须显式声明：

- `publicBases.api / realtime / productOps / mediaAvatar / mediaImage / mediaVideo / mediaUpload`
- `subnets.edge / media / service / data`
- `mockBoundaryFlags`
- `artifactPolicy.app / artifactPolicy.service`
- `hostAllowlist`
- `forbiddenHostTokens`
- `rolloutStagePolicy`

强制约束：

- `alpha` 的 topology 字段必须完整，不能通过缺字段表达“简化环境”。
- `prod` 只允许 `artifactPolicy.app.runtimeEnv=prod`，禁止任何 `prod-gray` 目录或枚举。
- 本地 profile 与 host 端口必须来自 `quwoquan_ops/environments/local_env_port_manifest.yaml`，不得散落在脚本内作为官方默认值。

## Packaging Contract

环境包必须同时满足：

- App env package 与 service env package 都携带 topology schema 版本、artifact policy 摘要与机器可读报告。
- `verify_public_vs_upstream_url_contract.py` 阻断 public base / upstream base 混用。
- `verify_environment_packaging_contract.py` 阻断环境枚举、dataSource、artifact 目录、host allowlist 漂移。
- `verify_env_artifact_isolation.py` 阻断跨环境 host、mock/seed/debug 信息进入错误环境产物。
- `verify_prod_package_purity.py` 阻断 prod 产物携带 alpha/mock/seed/debug/local/test 配置。

## Stackctl Contract

统一自动化入口：`quwoquan_ops/cli/stackctl.py`

命令面至少覆盖：

- `package`
- `up` / `down` / `status`
- `verify`
- `health`
- `inspect`
- `doctor`
- `repair`
- `deploy`

所有命令必须输出稳定的 JSON 报告，并将 Markdown 摘要归档到 `.qwq_output/runs/<env>/<run-id>/`。

## 子节点

- `env-file-secret-configcenter-provider`：配置来源抽象（env/file/secret/config center）
- `env-overlay-config-release`（新增）：环境覆盖与配置发布化落地
- `environment-process-domain-mapping`（新增）：部署进程与领域归属四态映射与门禁
- `future-evolution-closed-loop`（新增）：C11~C13 未来演进闭环（spec/design/tasks/acceptance + 门禁草案）

## 适用范围与约束

适用：
- 所有服务端 Go 服务
- 本地开发、办公电脑集成联调、容器生产发布

约束：
- 不允许服务自行实现“私有加载器”
- `prod` 环境必须显式设置 `APP_ENV=prod`
- App 只构建 `alpha/beta/gamma/prod`；生产灰度不能通过不同 App 安装包表达。
- 服务端配置目录只允许 `default/alpha/beta/gamma/prod`，禁止 `prod-gray` 目录。
- 高风险配置（连接拓扑、鉴权）不支持热更新，仅支持灰度滚动切换
- 版本快照配置文件不可变（immutable），仅允许新增版本，不允许覆盖已发布版本
- 密钥字段禁止进入版本快照，必须通过 Secret/env 注入
- 同一环境内一个 domain 仅允许归属一个部署进程
- 部署拓扑变化不允许修改领域对外 API 路由契约

## 验收概要

- A1：三级覆盖模型行为一致且可测试
- A3：配置发布可灰度、可回滚、可审计
- A7：配置结构与运行时实现一致
- A8：本地/集成/生产加载逻辑有自动化测试
- A8：topology/packaging/stackctl 契约可由 gate 自动执行并产出证据

## 统一门禁矩阵（FF 配置发布契约）

| 阶段命令 | 必过项（最小集） | 不通过处理 |
|---|---|---|
| `/prd` | spec.md 含目录/环境变量/拓扑 manifest / artifact policy / stackctl 命令面；acceptance.yaml 含对应验收项 | 阻断 FF，先补文档 |
| `/design` | 每服务 default/alpha/beta/gamma/prod 目录齐；topology manifest 与 local port manifest 已落地；加载顺序与 APP_ENV 校验有测试；门禁脚本可执行 | 阻断 apply，先补实现与测试 |
| `/commit` / submit-with-gate | strict gate 通过；CONFIG_VERSION 文件存在且可映射；配置-镜像兼容校验通过；prod purity / artifact isolation 通过 | 禁止提交入库 |
