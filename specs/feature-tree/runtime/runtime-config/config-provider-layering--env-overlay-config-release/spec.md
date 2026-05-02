# L4 细节：env-overlay-config-release

## 功能说明

在服务内落地配置分层与发布化能力：
- 配置目录统一：default/alpha/beta/gamma/prod-gray/prod
- 覆盖规则统一：default -> APP_ENV -> env var
- 生产挂载统一：`CONFIG_ROOT=/etc/qwq-config`
- 版本快照路径：`${CONFIG_ROOT}/releases/config/<service>/<config_version>.yaml`
- 版本约束：CONFIG_VERSION 与 IMAGE_VERSION 兼容校验
- 运行校验：关键配置合法性与依赖连通性检查

## 示例（新老版本并行）

同一 `prod` 环境灰度时：
- Stable 实例组：`IMAGE_VERSION=1.7.2`, `CONFIG_VERSION=v2026.02.27.1`
- Canary 实例组：`IMAGE_VERSION=1.8.0`, `CONFIG_VERSION=v2026.02.28.0`

两组实例通过不同 `CONFIG_VERSION` 读取不同版本配置，实现“老镜像读老配置、新镜像读新配置”。

## 范围边界

本节点负责“加载与校验机制”，不负责发布平台的灰度编排（由 platform-ops-governance 节点负责）。

## 适用范围与约束

适用：
- 服务部署到本地、办公电脑集成、容器生产三类场景

约束：
- `APP_ENV` 仅允许 `alpha|beta|gamma|prod-gray|prod`
- 高风险配置变更仅通过滚动灰度发布生效
- 版本配置文件不可变，发布后禁止覆盖写入

## 验收标准

- A1：配置分层加载结果可预测且一致
- A3：配置版本兼容校验可阻断不安全发布
- A8：测试覆盖三环境 + 覆盖优先级
