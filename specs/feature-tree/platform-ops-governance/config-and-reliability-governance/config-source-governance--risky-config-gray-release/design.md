# Design: risky-config-gray-release

## 设计动因

配置错误常导致全量故障。将高风险配置直接全量生效不可接受，必须引入渐进发布与自动回退。

## 关键设计

1. 配置发布与镜像发布解耦，配置拥有独立版本号
2. 灰度阶段固定模板：5% -> 25% -> 50% -> 100%
3. 每阶段基于 SLO 指标自动判定继续/暂停/回滚
4. 发布记录必须可审计（版本、操作者、时间、结果）
5. 实例组级别绑定：`IMAGE_VERSION` 与 `CONFIG_VERSION` 成对绑定投放

## 配置来源路径（生产）

统一挂载根目录：`/etc/qwq-config`

版本文件路径：
- `/etc/qwq-config/releases/config/<service>/<config_version>.yaml`

基础环境配置路径：
- `/etc/qwq-config/configs/<service>/default/config.yaml`
- `/etc/qwq-config/configs/<service>/<env>/config.yaml`

## 与 runtime 节点协同

- runtime 节点负责读取与校验配置
- 本节点负责配置版本如何逐步投放到生产实例

## 适用场景与约束

适用：
- Redis 拓扑与鉴权配置变更

约束：
- 需配合一键回滚节点使用
- 需接入 SLO 观测节点提供门禁指标
- 已发布版本配置文件不可变，回滚通过“切换版本指针”而非覆盖文件

## Folded legacy node `one-click-config-rollback`

# Design: one-click-config-rollback

## 设计动因

配置发布故障窗口需要压缩到分钟级，人工排查 + 手动回滚过慢且不稳定。

## 关键设计

1. 发布系统维护“稳定版本指针”
2. 触发回滚时将 `current_version` 直接切回稳定版本
3. 自动触发工作负载滚动更新使回滚配置生效
4. 回滚过程输出审计事件（操作者、原因、耗时）

## 版本目录回滚方式

不修改历史配置文件内容，仅切换版本指针：
- from: `CONFIG_VERSION=v2026.02.28.0`
- to: `CONFIG_VERSION=v2026.02.27.1`

通过工作负载重建使实例重新按版本路径加载配置。

## 触发条件

- 自动触发：SLO 指标越界
- 手动触发：运维审批后执行

## 约束

- 回滚必须支持幂等
- 回滚失败需再次告警并冻结后续发布
