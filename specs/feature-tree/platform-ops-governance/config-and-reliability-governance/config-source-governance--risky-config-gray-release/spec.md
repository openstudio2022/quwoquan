# L4 细节：risky-config-gray-release

## 功能说明

建立高风险配置变更的灰度发布机制，支持“配置独立发布”，不依赖镜像重建。

高风险配置示例：
- redis.mode
- redis.addrs / addr
- redis.password / tls
- 服务关键路由开关
- es.enabled / es.endpoints / es.insecureTls（统一搜索索引写侧：内容/圈子/实体/用户
  服务作为灌数生产者写入共享 ES/OpenSearch 集群，端点与凭据经部署密钥注入，
  开启/端点/TLS 校验属基础设施敏感项，必须经灰度发布而非全量直发）

## 当前变更的准出边界

当前服务配置已把若干过去的本地回退显式化：Assistant 的 PostgreSQL/Mongo/Redis
连接与 Notification command endpoint、Content 的 realtime Redis 和持久化端口、Chat
的 OSS 上传边界、Integration 的外部回调通道，以及 User 的一键登录 resolver。
这些字段中的 `mode`、`addr`、`addrs`、`password`、`tls` 与任何等价的连接/路由开关
都属于本节点的高风险配置；空值只是“尚未注入”，不是可以跳过发布校验的激活态。

本轮只完成配置契约与服务本地配置版本的收口，**不代表**任一生产连接、第三方
provider 或 hosted rollout 已完成。任何激活必须同时满足：

1. 服务自有 `configs/releases/<version>.yaml` 已生成并经 package provenance 校验；
2. secret 仅由部署密钥系统注入，源码和 release snapshot 均不得保存凭据正文；
3. 先在 gamma 以 stable/canary 双实例绑定不同 `CONFIG_VERSION` 验证连接、错误率、P95、
   日志脱敏和审计，再逐阶段进入 prod `gray-initial -> carry-on -> full`；
4. 每阶段必须保留同一 run 的 SLO、回滚目标和回滚演练证据；任一依赖不可用即停止，
   不得把默认空值、内存实现或 dry-run 当作成功。

## 发布策略

- 5% -> 25% -> 50% -> 100% 渐进
- 每阶段设置观察窗口与自动门禁
- 指标异常自动停止并触发回滚

## 新老版本配置绑定示例

灰度期间同时存在两个实例组：
- Stable：`IMAGE_VERSION=1.7.2`, `CONFIG_VERSION=v2026.02.27.1`
- Canary：`IMAGE_VERSION=1.8.0`, `CONFIG_VERSION=v2026.02.28.0`

规则：
- 每个实例组显式绑定自身 `CONFIG_VERSION`
- 严禁“全环境共享单一 current 配置”
- 流量只在实例组之间切换，不在实例内动态切换高风险配置

## 适用范围与约束

适用：
- 生产环境配置变更

约束：
- 高风险变更必须走灰度，不允许全量直发
- 配置变更必须有版本号（CONFIG_VERSION）与审计记录

## 验收标准

- A1：配置可独立发布并分阶段生效
- A3：灰度策略可配置且可审计
- A4：发布过程可观测

## Folded current node `one-click-config-rollback`

# L5 叶子：one-click-config-rollback

## 功能说明

为配置灰度发布提供“一键回滚”能力：
- 指定目标配置版本失败时自动回退到前一稳定版本
- 回滚后触发服务滚动恢复
- 保留完整审计轨迹

## 约束

- 回滚目标版本必须存在且通过记录验证
- 回滚操作需幂等（重复触发不造成状态错乱）

## 验收标准

- A1：异常触发后可在规定时间内恢复稳定版本
- A3：回滚动作受权限控制并可审计
- A8：回滚流程具备自动化演练测试

## 统一门禁矩阵（FF 配置发布契约）

| 阶段命令 | 必过项（最小集） | 不通过处理 |
|---|---|---|
| `/prd` | spec.md 含风险配置/灰度/回滚范围与环境变量；acceptance.yaml 含对应验收项 | 阻断 FF，先补文档 |
| `/design` | 灰度发布与回滚链路按 APP_ENV 分环境校验有测试；门禁脚本可执行 | 阻断 apply，先补实现与测试 |
| `/commit` / submit-with-gate | strict gate 通过；CONFIG_VERSION 文件存在且可映射；回滚目标版本可验证 | 禁止提交入库 |
