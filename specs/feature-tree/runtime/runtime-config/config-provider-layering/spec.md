# L3 组件：config-provider-layering

## 功能定位

统一定义服务配置加载与覆盖的分层模型，确保云侧 alpha、beta、gamma、prod-gray、prod 五套环境以同一逻辑运行，避免配置漂移与服务内重复实现。端侧 App 构建环境为 alpha、beta、gamma、prod；生产只有一个 App 包，灰度由应用市场分发策略、端侧上下文与云侧灰度策略共同决定。

本节点作为 `runtime-config` 的核心子组件，承载配置来源优先级、环境识别、版本兼容校验与发布化接入约束。

## 目标能力

- 统一目录结构：`default/` + `alpha/` + `beta/` + `gamma/` + `prod-gray/` + `prod/`
- 统一覆盖顺序：默认配置 -> 环境配置 -> 环境变量覆盖
- 显式环境识别：`APP_ENV=alpha|beta|gamma|prod-gray|prod`
- 配置发布版本：`CONFIG_VERSION` 与 `IMAGE_VERSION` 兼容校验
- 运行前校验：关键字段合法性与依赖连通性（如 Redis ping）
- 统一部署映射：`environments -> deploy process -> domains`
- 拓扑一致性：`beta`、`gamma`、`prod-gray`、`prod` 的进程-领域映射保持一致
- 端侧生产包唯一：不存在 `app-prod-gray`；prod-gray 仅作为云侧灰度配置/策略语义。

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
      prod-gray/config.yaml
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
3. `${CONFIG_ROOT}/releases/config/${SERVICE_NAME}/${CONFIG_VERSION}.yaml`
4. 环境变量覆盖（最高优先级）

## 子节点

- `env-file-secret-configcenter-provider`：配置来源抽象（env/file/secret/config center）
- `env-overlay-config-release`（新增）：环境覆盖与配置发布化落地
- `environment-process-domain-mapping`（新增）：部署进程与领域归属五态映射与门禁
- `future-evolution-closed-loop`（新增）：C11~C13 未来演进闭环（spec/design/tasks/acceptance + 门禁草案）

## 适用范围与约束

适用：
- 所有服务端 Go 服务
- 本地开发、办公电脑集成联调、容器生产发布

约束：
- 不允许服务自行实现“私有加载器”
- `prod` 环境必须显式设置 `APP_ENV=prod`
- App 只构建 `alpha/beta/gamma/prod`；生产灰度不能通过不同 App 安装包表达。
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
