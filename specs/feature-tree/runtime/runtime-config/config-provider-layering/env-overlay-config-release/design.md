# Design: env-overlay-config-release

## 设计动因

当前配置加载缺少环境分层规范，导致不同环境加载方式不一致，且配置变更难以发布化管理。

## 关键设计

1. **目录结构**
   - `${CONFIG_ROOT}/configs/<service>/default/config.yaml`
   - `${CONFIG_ROOT}/configs/<service>/local/config.yaml`
   - `${CONFIG_ROOT}/configs/<service>/integration/config.yaml`
   - `${CONFIG_ROOT}/configs/<service>/prod/config.yaml`
   - `${CONFIG_ROOT}/releases/config/<service>/<config_version>.yaml`

2. **加载流程**
   - 读取 default
   - 读取 APP_ENV 对应文件并深度覆盖
   - 读取 CONFIG_VERSION 对应版本快照并覆盖（若设置）
   - 应用环境变量覆盖
   - 执行 schema/连通性校验

3. **版本机制**
   - `CONFIG_VERSION`: 配置发布版本
   - `IMAGE_VERSION`: 镜像版本
   - 启动时校验 `min_image_version` 等兼容规则

4. **运行策略**
   - 低风险配置可动态刷新（后续）
   - 高风险配置需滚动发布并可回滚

## 容器环境识别与参数契约

- `APP_ENV`: `local|integration|prod`
- `SERVICE_NAME`: 服务名（如 `content-service`）
- `CONFIG_VERSION`: 配置发布版本（如 `v2026.02.28.0`）
- `IMAGE_VERSION`: 镜像版本（如 `1.8.0`）
- `CONFIG_ROOT`: 配置挂载根目录（默认 `/etc/qwq-config`）

生产要求：
- `APP_ENV=prod` 必须显式设置
- `CONFIG_VERSION` 必须存在并可解析

## 门禁实现建议（脚本级）

- 目录门禁：校验所有服务环境目录完整
- 环境变量门禁：校验 `APP_ENV` 值域与 `CONFIG_VERSION` 必填规则
- 版本映射门禁：校验 `CONFIG_VERSION` 文件存在
- 兼容门禁：校验 `IMAGE_VERSION` 与配置兼容范围

## 适用场景与约束

适用：
- 配置变更频繁、环境差异明显的服务

约束：
- `prod` 场景要求显式环境变量，禁止默认回退
- 密钥类配置不入仓，必须通过 Secret/env 注入

## 未来演进

- 接入配置中心并保留 Git 真源
- 增加运行时配置漂移上报
