# Persona / PersonaRelationship 单模型发布 Runbook

## 不可变准入

- `UserAccount` 只管理账号状态，`Persona` 是公开身份聚合，`PersonaRelationship` 是 persona-to-persona 关系的唯一聚合。
- 所有 relationship command 必须经 `PersonaRelationshipService`；所有跨上下文读取经具名 Reader/View，不直接读子对象。
- 无 `persona_model_v2`、`persona_graph_v1/v2`、`persona_context_v1` 或 `profile_subject_v1` 运行时开关；任何环境变量都不能恢复旧模型。
- 无 dual-read、dual-write、owner-id fallback 或 flag-off 回退测试。

## 一次性数据重整

1. 在停写窗口对旧用户容器、persona/subAccount、内容/消息/关系主体做 dry-run。
2. 将主体引用一次性重写为 `personaId`，以确定性规则生成唯一 `userHandle`。
3. 执行 `scripts/persona/persona_migration_dry_run.sh` 与 `scripts/persona/persona_migration_validate.sh`；任一 `missing_identity`、`history_mapping_gap` 或 `public_leakage` 都阻断发布。
4. 重整完成后立即删除临时工具和旧表/集合，不在 service runtime 保留迁移分支。

## 观测与阻断阈值

- `persona_switch_latency_ms`：P95 < 250ms。
- `persona_attribution_mismatch_count`：必须为 0。
- `persona_public_leakage_count`：必须为 0。
- `persona_migration_failed_count`：必须为 0。
- `persona_relationship_counter_mismatch_count`、`filter_mismatch_count`、`page_drift_count`：必须为 0。
- outbox pending/oldest-age、projection checkpoint lag 超过 SLO 时阻断扩大 prod rollout stage。

## 发布与回滚

- alpha 仅由独立 runner/fixture 验证契约；beta/gamma/prod 使用同一 production composition。
- 灰度只是 prod 部署阶段，不是业务模型开关。
- 回滚只能恢复同一 schema 契约的上一个镜像与配置版本；禁止通过环境变量恢复旧 owner/follow/block 模型。
- 若一次性数据重整已开始且无法安全恢复快照，停止发布并保持写入冻结，不运行旧新双轨。

## Rehearsal 顺序

```text
bash scripts/persona/persona_migration_dry_run.sh
bash scripts/persona/persona_migration_validate.sh
go test ./runtime/persona ./runtime/governance ./runtime/sync
go test ./services/user-service/internal/application/...
go test ./services/user-service/tests/api_integration
```

然后在 gamma 执行 Persona 创建/激活/退役、follow/block 双向不变量、公开资料隔离、幂等重放、outbox 投递与投影收敛。本地测试通过不代表 gamma/prod 演练完成。
