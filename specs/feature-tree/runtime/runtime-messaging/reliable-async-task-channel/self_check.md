# 可靠异步任务通道自检报告

## 结论

本轮已将可靠异步任务通道从单一消息通道设计扩展为“可靠通道 + 模块化部署 + 统一治理”的正式规划真相源。当前文档、catalog、静态门禁脚本和基础 Go runtime 已具备后续实现基础。

代码层不是零实现：`quwoquan_service/runtime/reliabletask/` 已包含模型、接口、内存 store、Mongo store、catalog loader 与基础单元测试，`chat-service` 也已有群头像可靠任务适配。但生产级可靠通道尚未完成，因此本报告结论是：**规划、静态门禁与基础 runtime 已建立；事务 writer、shard lease、生产 dispatcher/worker、Redis/MQ ready 索引、业务全量接入与故障注入测试仍需继续完成**。

## 设计不变量覆盖

| 不变量 | 规格 | 设计 | 验收/门禁 | 状态 |
|--------|------|------|-----------|------|
| Outbox 是事实源，队列只是执行索引 | `spec.md` | `design.md` | `acceptance.yaml` / catalog 校验 | 已覆盖 |
| 业务数据 + Outbox 同事务 | `spec.md` | `design.md` | T3/T4 测试规划 | 已覆盖 |
| 未到期任务保留在 DB，`startAt <= now` 才投递 | `spec.md` | `design.md` | `verify_reliable_task_catalog.py` 间接约束 | 已覆盖 |
| payload 只保存版本提示，worker 重读 DB | `spec.md` | `design.md` | payload allowlist 校验 | 已覆盖 |
| 结果 + Notification Outbox 同事务 | `spec.md` | `design.md` | T3/T4 测试规划 | 已覆盖 |
| ACK 只在结果事务后发生 | `spec.md` | `design.md` | T3/T4 测试规划 | 已覆盖 |
| 至少一次投递 + 幂等 | `spec.md` | `design.md` | task catalog 幂等/partition 约束 | 已覆盖 |
| DLQ 与人工恢复 | `spec.md` | `design.md` | retention policy 校验 | 已覆盖 |
| recipient 级通知去重 | `spec.md` | `design.md` | T3/T4 测试规划 | 已覆盖 |

## 模块化部署覆盖

| 能力 | 落点 | 状态 |
|------|------|------|
| RuntimeModule / DeploymentPackage | `spec.md`、`design.md`、`module_package_mapping.yaml` | 已覆盖 |
| onebox 与拆分 package 等价 | `design.md`、runbook、seed-box README | 已覆盖 |
| `env + domain + module + shardId` 租约 | `design.md`、`tasks.md` | 已覆盖 |
| task/module/package catalog | `reliable_task_module_catalog.yaml` | 已覆盖 |
| catalog 版本与 fail-fast | `spec.md`、`design.md`、`tasks.md` | 已覆盖 |
| domain/module 权限边界 | `design.md`、`verify_module_permission_scope.py` | 已覆盖 |
| beta/gamma/prod-gray/prod 一致性 | `verify_module_package_mapping.py` | 已覆盖 |

## 领域服务处置

| Domain / Process | 处置 |
|------------------|------|
| `chat` | 首批完整接入；私有 group avatar scheduler 必须迁移 |
| `user` | 头像传播作为第二阶段公共能力接入 |
| `content` | 搜索/投影作为非头像公共能力接入 |
| `circle` | catalog/config 声明，业务 worker 可延期 |
| `assistant` | catalog/config 声明，避免影响 stream/replay |
| `entity` | catalog/config 声明 |
| `integration` | 外部 API retry worker 规划 |
| `ops` | 审计投影 worker 规划 |
| `notification` | fanout、retry、delivery ledger 工程归属明确 |
| `rtc/realtime/media/turn` | 作为 infra module 纳入 catalog，不接业务 Outbox |
| `recommendation` | Python 独立进程，catalog 引用但不并入 Go onebox |

## 门禁覆盖

- `quwoquan_app/scripts/runtime/verify_module_package_mapping.py`
- `scripts/verify_reliable_task_catalog.py`
- `scripts/verify_reliable_task_retention_policy.py`
- `scripts/verify_module_permission_scope.py`
- `scripts/verify_reliable_task_migration.py`
- `Makefile` 新增 `verify-reliable-task-topology`
- `make verify` 与 `make gate` 已接入可靠任务拓扑校验
- `agent_ops/gate/gate_repo.sh --scope service` 已接入可靠任务拓扑校验
- `scripts/verify_topology_contract_regression.sh` 已接入 module/package/catalog 校验

## 已验证项

- `python3 quwoquan_app/scripts/runtime/verify_module_package_mapping.py`
- `python3 scripts/verify_reliable_task_catalog.py`
- `python3 scripts/verify_reliable_task_retention_policy.py`
- `python3 scripts/verify_module_permission_scope.py`
- `python3 scripts/verify_reliable_task_migration.py`
- `make verify-reliable-task-topology`
- `bash scripts/verify_topology_contract_regression.sh`
- `go test ./runtime/redis`
- `go test ./runtime/reliabletask`
- `go test ./services/chat-service/tests -run 'TestGroupAvatar'`
- `go test ./services/chat-service/tests -run 'TestGroupAvatar|TestReliable|TestInboxProjection'`
- `make verify`

以上均已通过。`verify_reliable_task_migration.py` 当前允许 `chat-service` 旧 `group_avatar_recompute_scheduler.go` 作为 deprecated compatibility adapter，但生产接线已通过 reliable-task 路径验证。

## 全局门禁结果

- `make verify` 已通过。
- 本次未安装额外环境依赖；`python3`、`make`、`go test` 均可用，未发现因本机环境缺失导致测试无法继续的问题。

## 剩余实现项

- retention、backpressure、rate limit 与观测指标输出仍需进一步产品化。
- 扩缩容 rebalance、真实进程崩溃、Redis/Mongo 短暂不可用等系统级演练仍需进入更高阶 T4 环境。
- `chat` 的群头像链路已接入 reliable-task；roster/inbox 仍需按后续切片接入同一公共通道。
- `user` 与 `content` 业务场景尚未接入。
- alpha/beta 已通过本地 ready index 场景测试；真实部署环境的长稳压测仍需后续补充。

## 后续详细规划

1. **高阶弹性与观测**
   - 完成 retention、backpressure、rate limit 指标输出和告警面。
   - 增加扩缩容 rebalance 与真实进程崩溃接管演练。

2. **更高阶环境故障注入**
   - 在 alpha/beta 之外补充更接近部署态的 Redis/Mongo 短暂不可用、ready index 丢失重建、DLQ 人工恢复演练。

3. **业务接入扩展**
   - `chat`：继续迁移 roster、inbox、notification fanout 到公共通道。
   - `user`：接入头像传播。
   - `content`：接入搜索或 feed 投影，证明非头像公共能力。
   - 其它 domain：完成 config/catalog 显式启用、禁用或延期。

4. **最终准出**
   - 在本轮 `make verify` 基础上继续跑 `make gate` / `make gate-full`。
   - 汇总 alpha/beta 长稳报告与 DLQ 恢复证据。

## 准出判断

当前可靠异步任务通道已完成群头像主链路的可信闭环和 alpha/beta 本地 ready index 验证，可作为公共通道继续扩展。仍不能声明全部业务域完成，原因是 user/content/roster/inbox 接入、系统级故障演练、观测与限流产品化仍在后续范围内。
