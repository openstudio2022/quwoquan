# M5 Rollout Runbook

## M4 审计前提

- M4 只能视为主链路已落地，不能视为 Journey 级完全完成。
- 本轮 M5 只负责上线治理、迁移、灰度、观测、回滚与 rehearsal。
- `共同粉丝 / mutual` 反推同一 `userId` 的更强隔离验证，仍保留在 M4/M6 缺口中，不在本轮伪装为已完成。

## T5-1 迁移对象冻结

- 旧 `owner/user container` 统一映射到 `User`。
- 旧 `persona/subAccount/profileSubject` 统一映射到 `Persona`。
- 记录 `content / message / follow` 主体字段统一收敛到 `personaId`。
- 公开可见标识统一收敛到 `userHandle`，来源优先级为 `username -> nickname -> personaId`。
- `phone / email` 下沉到分身级；若目标分身为空，则默认继承主分身值。
- `userHandle` 冲突策略：
  - 先尝试标准化后的请求值。
  - 若与已保留 handle 冲突，则附加 `personaId` 后缀。
  - 仍冲突时继续附加序号，保证幂等重跑时输出稳定。

## T5-2 可重跑脚本与校验入口

- dry-run 入口：`scripts/persona_migration_dry_run.sh`
- validate 入口：`scripts/persona_migration_validate.sh`
- 底层工具：`quwoquan_service/tools/persona_rollout`
- 默认演练输入：`quwoquan_service/runtime/persona/testdata/rehearsal_input.json`
- 输出内容：
  - 迁移后的 `personaId / userHandle / phone / email` 计划
  - `historyMappings`
  - `patchTypes`
  - 校验结果与四类验收指标映射
- 校验失败语义：
  - `missing_identity` 计入 `persona_migration_failed_count`
  - `history_mapping_gap` 计入 `persona_attribution_mismatch_count`
  - `public_leakage` 计入 `persona_public_leakage_count`

## T5-3 Flag 能力矩阵

- 分身管理主开关：`ops.user.persona_model_v2`
  - 默认 `true`
  - 关闭后：分身管理与 persona model v2 行为整体回退到旧入口/旧解析链
- 公开分身资料开关：`ops.user.profile_subject_v1`
  - 默认跟随 `ops.user.persona_model_v2`
  - 关闭后：公开资料读取退回到 `personaId` 直读，不再走 `userHandle` 优先解析
- 分身资料同步开关：`ops.user.persona_sync_v2`
  - 默认跟随 `ops.user.persona_model_v2`
  - 关闭后：保留分身编辑，但关闭跨分身同步广播
- 上下文透传开关：`ops.user.persona_context_v1`
  - 默认跟随 `ops.user.persona_model_v2`
  - 关闭后：上下文侧回到最小 persona fallback
- 图谱读写开关：`ops.user.persona_graph_v2`
  - 默认优先读取自己；若未显式配置，则退回 `ops.user.persona_graph_v1`，再退回 `ops.user.persona_context_v1`
  - 关闭后：follow/graph 保持只读安全基线，不要求新语义继续写入

## T5-4 指标与告警口径

- `persona_switch_latency_ms`
  - 真实来源：`ActivateSubAccount` 切换耗时
  - 建议阈值：`p95 < 250ms`
  - 触发动作：冻结 `ops.user.persona_model_v2` 继续放量
- `persona_attribution_mismatch_count`
  - 真实来源：退役归因 fallback、relationship capability mismatch、graph filter/page drift，以及 rehearsal 校验中的 `history_mapping_gap`
  - 建议阈值：`> 0` 即阻断扩大灰度
- `persona_public_leakage_count`
  - 真实来源：公开读样本校验或运行时公开视图泄露检测
  - 建议阈值：`> 0` 立即关闭 `ops.user.profile_subject_v1` / `ops.user.persona_graph_v2`
- `persona_migration_failed_count`
  - 真实来源：dry-run / validate 中的 `missing_identity` 或其它迁移失败对象
  - 建议阈值：`> 0` 不允许进入真实迁移

## T5-5 Sync 与回滚底座

- persona patch type 固定为：
  - `persona.activated`
  - `persona.profile.updated`
  - `persona.retired`
- persona patch 必须携带 `personaId`，否则拒绝写入。
- 仍统一复用 `runtime/sync` 的顺序、gap、expiry、`requiresResync` 语义。
- 回滚原则：
  - 不保留长期双语义双写。
  - 回滚优先级：先关 `ops.user.persona_graph_v2`，再关 `ops.user.persona_context_v1`，最后关 `ops.user.persona_model_v2`。
  - 回滚后允许退回只读安全基线，但不允许公开接口泄露 `ownerUserId`。

## T5-6 Rehearsal 清单

1. 运行 `scripts/persona_migration_dry_run.sh`
2. 确认 `persona_migration_failed_count == 0`
3. 确认 `persona_public_leakage_count == 0`
4. 运行 `go test ./runtime/persona ./runtime/governance ./runtime/sync ./services/user-service/internal/domain/user/telemetry`
5. 核对 `ops.user.persona_model_v2 / persona_sync_v2 / profile_subject_v1 / persona_context_v1 / persona_graph_v2` 的默认值与回退链
6. 执行 flag-off 演练：
   - 关 `persona_graph_v2`，确认 graph 回到只读安全基线
   - 关 `profile_subject_v1`，确认公开资料退回 `personaId` 读取
   - 关 `persona_model_v2`，确认管理台与上下文透传停止使用新主语义

## 本会话已完成的本地演练

- 已执行：`go run ./tools/persona_rollout --input ./runtime/persona/testdata/rehearsal_input.json --switch-latency-ms 18.4`
- 结果：
  - `persona_switch_latency_ms = 18.4`
  - `persona_attribution_mismatch_count = 0`
  - `persona_public_leakage_count = 0`
  - `persona_migration_failed_count = 0`
- 限制：
  - 本会话没有 staging 控制面与真实业务数据快照，因此仍缺少真实环境的 `T4_release_rehearsal` 证据。
