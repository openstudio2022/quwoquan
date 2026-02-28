# Design: config-provider-layering

## 设计动因

现有服务配置主要依赖单文件 + 环境变量覆盖，缺少统一的环境分层模型与版本化治理，导致：
- 本地/集成/生产行为不一致
- 紧急配置修改难以审计
- 配置与灰度发布链路脱节

## 设计决策

1. **环境分层目录标准化**
   - `configs/default/config.yaml`
   - `configs/local/config.yaml`
   - `configs/integration/config.yaml`
   - `configs/prod/config.yaml`

2. **加载顺序固定**
   - default -> APP_ENV -> env override
   - 覆盖规则采用深度合并（map 深覆盖，数组按整体替换）
   - 若设置 `CONFIG_VERSION`，追加版本快照层（default -> env -> config_version -> env vars）

3. **显式环境选择**
   - `APP_ENV` 必填（本地未设置可默认 local）
   - 生产必须显式 `APP_ENV=prod`

4. **配置版本化**
   - 配置发布版本 `CONFIG_VERSION`
   - 镜像版本 `IMAGE_VERSION`
   - 启动时做兼容校验（最小支持版本）

## 外部挂载公共目录方案（生产标准）

容器统一挂载：
- `CONFIG_ROOT=/etc/qwq-config`

路径规则：
- `${CONFIG_ROOT}/configs/<service>/default/config.yaml`
- `${CONFIG_ROOT}/configs/<service>/<env>/config.yaml`
- `${CONFIG_ROOT}/releases/config/<service>/<config_version>.yaml`

该方案满足：
- 配置与镜像解耦发布
- 新老 ReplicaSet 可绑定不同 `CONFIG_VERSION` 并行运行
- 回滚只需切回旧 `CONFIG_VERSION`

## 灰度新老版本绑定示例

灰度期间同一环境内存在两组实例：

- Stable 组：`IMAGE_VERSION=1.7.2`, `CONFIG_VERSION=v2026.02.27.1`
- Canary 组：`IMAGE_VERSION=1.8.0`, `CONFIG_VERSION=v2026.02.28.0`

发布系统按流量权重推进（5/25/50/100），不共享“单一当前配置”，而是实例级绑定配置版本。

## 门禁设计（必须通过）

1. **目录完备门禁**
   - 校验每个服务必须包含 `default/local/integration/prod/config.yaml`
2. **环境变量契约门禁**
   - 校验 `APP_ENV` 仅允许 `local|integration|prod`
   - 校验生产清单必须显式声明 `APP_ENV` 与 `CONFIG_VERSION`
3. **版本可用性门禁**
   - 校验 `CONFIG_VERSION` 在版本目录存在对应文件
4. **兼容性门禁**
   - 校验配置 `min_image_version/max_image_version` 与 `IMAGE_VERSION` 兼容
5. **不可变门禁**
   - 已发布版本配置文件禁止覆盖，只允许新增版本
6. **部署拓扑门禁**
   - `deploy/shared/process_domain_mapping.yaml` 必须声明 `dev/integration/prod` 三环境
   - 同一环境中 domain 不可重复归属到多个部署进程
   - `integration` 与 `prod` 的进程-领域映射必须一致

## 与治理主线协同

- 运行时节点负责“如何加载和校验”
- 平台治理节点负责“如何灰度发布与回滚”
- SLO 节点负责“如何自动触发回滚”
- 部署映射节点负责“进程打包拓扑如何声明并被门禁校验”

## 适用场景与约束

适用：
- 多环境部署、配置高频变更、需要审计追溯的服务

不适用：
- 一次性脚本型工具（无长期运行服务）

约束：
- 高风险配置项（如 Redis mode/addrs/password/tls）仅支持滚动灰度，不支持热更新

## 未来演进

- 将加载器抽象到 `runtime/config` 公共库，服务端统一接入
- 接入配置中心推送并保留 Git 版本真源
- 将上述门禁脚本并入 `make gate-full` 的强制阶段
