# 开发任务：reliable-async-task-channel

## T0：现状盘点与范围冻结

- [x] 盘点 Go API 入口：`assistant-service`、`chat-service`、`content-service`、`circle-service`、`entity-service`、`integration-service`、`product-ops-service`、`platform-ops-service`、`rtc-service`、`user-service`。
- [x] 盘点 Python 独立进程：`rec-model-service` 保持独立，不并入 Go `seed-box`。
- [x] 盘点部署资产：`seed-box`、`chat-service`、`content-service`、`rtc-service`、`livekit-sfu`、`coturn` 已有 Kustomize；其它 Go 服务主要依赖 seed-box 组合。
- [x] 标记缺口：`notification`、`gateway`、`orchestrator` 需以 module/catalog 方式明确工程归属。

验收：
- 所有 domain 均在 `deploy/shared/module_package_mapping.yaml` 或 `deploy/shared/reliable_task_module_catalog.yaml` 中有处置。

## T1：模块化部署规格

- [x] 扩展 `spec.md`，纳入 `RuntimeModule`、`ModuleCapability`、`DeploymentPackage`、`ProcessInstance`。
- [x] 扩展 `runtime-config` process-domain 规格，保留 domain 唯一归属并新增 package/module 映射。
- [x] 更新 `process_domain_mapping_runbook.md` 与 `seed-box` Kustomize README。

验收：
- `seed-box` 可表达跨 domain module 组合。
- 热点 worker package 可独立拆分，且不改变领域 API 契约。

## T2：Catalog 与路由

- [x] 新增 `deploy/shared/module_package_mapping.yaml`。
- [x] 新增 `deploy/shared/reliable_task_module_catalog.yaml`。
- [x] 新增 `deploy/shared/reliable_task_retention_policy.yaml`。
- [ ] 实现 deployment package 启动期 catalog 兼容性校验，确保 runtime/catalog 版本不兼容时 fail-fast。

验收：
- 每个 taskType 都能找到唯一 dispatcherModule 和 workerModule。
- 每个 workerModule 都存在于 module catalog。
- 每个 retentionPolicyRef 和 rateLimitPolicyRef 都存在于 retention policy。

## T3：可靠通道 Runtime

- [x] 新增 `quwoquan_service/runtime/reliabletask/` 基础包。
- [x] 实现内存 store：延迟合并、到期 dispatch、claim、ACK、Retry/DLQ、notification ledger 基础语义。
- [x] 实现 Mongo store 基础版本：Outbox、Task、Notification、recipient ledger 的 CRUD 与租约 token 校验。
- [x] 实现 catalog loader：从 `deploy/shared/reliable_task_module_catalog.yaml` 构造任务声明并校验 payload allowlist。
- [x] 实现事务绑定的 `TaskOutboxWriter(ctx, tx, req)`，业务服务只能通过受控 writer 在业务事务内声明任务。
- [x] 实现生产级 dispatcher 基础能力：`env + domain + module + shardId` shard lease、到期扫描、重复 dispatch 幂等。
- [x] 实现 Redis/MQ ready 执行索引适配；Redis/MQ 丢失后仍以 DB 账本为事实源。
- [x] 实现 production worker runtime 基础能力：handler registry、ACK-after-commit、RuntimeFailure、统一 retry/DLQ。
- [x] 实现 notification outbox dispatcher 与 recipient delivery ledger 的生产 fanout runtime 基础能力。
- [ ] 实现 retention、backpressure、rate limit 与观测指标输出。

验收：
- 业务数据 + Outbox 同事务。
- 结果 + Notification Outbox 同事务。
- ACK 只在结果事务成功后发生。
- Redis/MQ 索引丢失后可由 DB 账本恢复。

## T4：租约与模块弹性

- [x] 实现 dispatcher shard lease：`env + domain + module + shardId`。
- [x] 实现 worker task lease token 基础校验，旧 lease token 不得 ACK 新租约。
- [x] 实现 onebox 与拆分 worker package 并存时的安全竞争基础测试。
- [ ] 实现扩缩容 rebalance 策略与更完整的 lease timeout 接管演练。

验收：
- dispatcher 崩溃后其它实例可接管 shard。
- API 扩缩容不放大 dispatcher 扫描。
- 同一 task 不因 onebox 与拆分 package 并存产生重复有效副作用。

## T5：领域服务接入

- [ ] `chat` 首批完整接入：群头像、roster、inbox、notification fanout。
- [x] `chat` 群头像已有 `ReliableGroupAvatarTaskScheduler` 适配和目标测试覆盖，包含建群、加人、退人、ACK 重放、notification 补偿、alpha/beta ready index。
- [x] 迁移 `chat-service` 群头像生产接线到 reliable-task；旧 scheduler 文件仅允许 deprecated compatibility adapter。
- [ ] `user` 接入头像传播。
- [ ] `content` 接入搜索或 feed 投影，证明非头像公共能力。
- [ ] 其它 domain 完成 module/catalog/config 声明或显式禁用。

验收：
- 至少一个非头像场景通过 T3。
- 所有 Go 服务 config 都具备 reliable task module 配置位或显式声明不启用。
- `chat-service` 不再保留私有 timer/local queue 与 reliable-task 双链路长期共存。

## T6：脚本与门禁

- [x] 新增 `scripts/verify_module_package_mapping.py`。
- [x] 新增 `scripts/verify_reliable_task_catalog.py`。
- [x] 新增 `scripts/verify_reliable_task_retention_policy.py`。
- [x] 新增 `scripts/verify_module_permission_scope.py`。
- [x] 新增 `scripts/verify_reliable_task_migration.py`。
- [x] 接入 `Makefile`、`make verify`、`make gate`、`scripts/gate_repo.sh --scope service`。
- [x] 扩展 `scripts/build_service_env_package.sh` 输出 module package 报告。

验收：
- 缺失 module package mapping、task catalog、retention policy、catalog version 任一项时门禁失败。
- task catalog 引用不存在的 module 时门禁失败。
- package 中 module 越权访问其它 domain 时门禁失败。

## T7：T1-T4 自动化

- [x] T1：内存 store 覆盖合并策略、到期投递、lease token、Retry/DLQ、payload 白名单基础语义。
- [x] T2：静态门禁覆盖 task catalog、module/package catalog、retention policy、权限边界。
- [x] T2：schema 契约与 Mongo 索引/唯一约束自动校验基础覆盖。
- [x] T3：dispatcher 恢复、重复投递幂等、ACK 失败重放、notification outbox 恢复、recipient ledger 基础覆盖。
- [x] T4：连续加人风暴、部分 fanout 失败、DLQ/ACK 恢复、alpha/beta ready index 基础覆盖。
- [ ] T4：Redis/Mongo 短暂不可用、真实进程崩溃、扩缩容 rebalance 的系统级演练。

验收：
- 设计文档的所有不变量均有测试或门禁证明。

## T8：最终自检

- [x] 对照 `spec.md`、`design.md`、`acceptance.yaml`、`tasks.md`、deploy catalog 与当前实现逐项检查。
- [x] 输出自检报告：通过项、延期项、阻断项。

验收：
- 任一设计不变量缺少任务、测试或门禁时，不得声明完成。
- 任一领域服务缺少 catalog/config 处置时，不得声明完成。

## T9：群头像全链路一致性补全

- [x] 服务端链路加固：群头像 dispatcher 默认按 `DefaultShardCount` 遍历 shard 并使用 shard lease，避免单实例扫描全局 outbox 或只处理 shard 0；`actorID` 进入可靠任务 payload；非 active 群不重算；notification recipient 过滤非 user 成员。
- [x] 服务端回归测试：补齐 notification ACK 失败重放、退群 outbox 失败事务回滚、连续 add/remove 风暴最终收敛到最新 top9 source hash。
- [x] 端侧最终一致：`syncAvatarPatches()` 记录失败状态，patch/full-sync 应用失败时不推进 `lastUserSyncSeq`；`UserAvatarUpdated` 触发成员列表和会话补偿刷新。
- [x] Probe 与报告：Python 3.10+ 兼容；相对 `avatarUrl` 使用 `--media-base-url` 归一化；报告补充 `blockingReason`、`recoveryPolicy`（`action` / `disruptionLevel`）、`serviceEndpointEvidence`。
- [x] local-gamma 拓扑：Docker compose 纳入 `chat-service`、可靠任务 Redis scene、共享 media mount；Caddy 补 `/v1/chat/*`、`/v1/user/sync`、`/media/*`；T3 默认包含 chat API contract。
- [x] ECS 门禁：`deploy-gamma-ecs.yml` 增加 chat avatar API probe、self-hosted chat-avatar Patrol 矩阵、prod smoke 和 push paths；self-hosted workflow 支持 `matrix_kind=chat-avatar`。
- [x] 本地可执行验证（2026-05-03）：`python3 -m py_compile scripts/run_chat_avatar*.py scripts/run_local_gamma_avatar_e2e.py scripts/run_local_gamma_t3.py`、`bash -n scripts/start_local_gamma_mirror.sh`、`go test ./runtime/reliabletask`、`go test ./services/chat-service/tests -run TestGroupAvatar`、`flutter test test/cloud/realtime/realtime_avatar_sync_handler_test.dart` 均通过。
- [ ] 真实环境矩阵证据：`beta`、`local-gamma`、`cloud-gamma-pre`、`cloud-gamma-prod-smoke` 在可访问网关、ECS 凭据与本机或 self-hosted Android/iOS 就绪后运行 **非 dry-run** 报告；**且** `make verify-chat-avatar-commercial-matrix COMMERCIAL_MATRIX_MANIFEST=artifacts/commercial-matrix/chat-avatar/manifest.yaml`（或等价 `python3 scripts/verify_chat_avatar_commercial_matrix_evidence.py`）**退出码 0**。未满足前不得声明商用矩阵完成。
  - 执行手册（不打折扣）：[`commercial-e2e-matrix-runbook.md`](./commercial-e2e-matrix-runbook.md)。
  - 阶段顺序：**Phase L（local-gamma）→ Phase B（beta）→ Phase C（cloud pre/smoke）→ manifest 机器校验**；四条路径填入 [`artifacts/commercial-matrix/chat-avatar/manifest.sample.yaml`](../../../../../artifacts/commercial-matrix/chat-avatar/manifest.sample.yaml) 的副本后执行校验。
  - 一键编排：`bash scripts/run_chat_avatar_commercial_matrix_orchestrator.sh` / `make run-chat-avatar-commercial-matrix-local`。
  - 自检：`python3 scripts/check_avatar_commercial_matrix_prereqs.py --strict`（不替代 manifest 校验）。

验收：
- 建群首帧头像不得为空或契约占位，群头像异步生成不得阻塞建群。
- 加人/退人触发可靠任务，最终 `groupAvatarVersion` 递增，并通过 notification ledger 与 sync patch 送达目标成员。
- message sender avatar 不随 conversation avatar patch 回退。
- `cloud-gamma-pre` chat avatar API probe 或 self-hosted 模拟器失败时阻断 prod；`cloud-gamma-prod-smoke` 失败时阻断发布完成结论。
