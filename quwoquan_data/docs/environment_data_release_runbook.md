# 环境数据发布与一致性 Runbook

本 runbook 固化 `qwq-data ship` 之后的环境发布闭环：release artifact、事务边界、一致性扫描、分环境 rollout、回滚和四层验证。

## 发布边界

- 事务边界：`releaseId + env + sourceOwner`。
- 默认来源：`sourceOwner=qwq_data`；local-gamma fixture 使用 `sourceOwner=fixture`。
- 生产默认删除策略：`tombstone`；`hard-delete` 必须有审批并单独执行。
- 真实用户不由数据工程接管；数据工程只校验 `fixture_` 作者和演示用户引用闭包。

## 标准流程

1. 生成 release artifact：

```bash
python3 quwoquan_data/scripts/cli.py ship \
  --skip-promote \
  --env gamma \
  --data-release-id <releaseId> \
  --mode upsert \
  --delete-policy none
```

2. 查看 preflight 报告：

```bash
make verify-data-release-consistency \
  RELEASE_FILE=quwoquan_data/publish/env_releases/<releaseId>/gamma.json
```

3. dry-run 目标环境导入：

```bash
python3 quwoquan_data/scripts/cli.py ship \
  --skip-promote \
  --env gamma \
  --data-release-id <releaseId> \
  --import \
  --mongo-uri <gamma-mongo-uri> \
  --dry-run
```

4. apply：

```bash
python3 quwoquan_data/scripts/cli.py ship \
  --skip-promote \
  --env gamma \
  --data-release-id <releaseId> \
  --mode sync \
  --delete-policy tombstone \
  --import \
  --mongo-uri <gamma-mongo-uri>
```

5. post-activation 扫描与 API/T4 验证。

## 分环境策略

| 环境 | apply 模式 | 删除策略 | 额外门 |
|---|---|---|---|
| alpha | `upsert` 或 `reset-source` | `tombstone` | T1/T2 必过 |
| beta | `sync` | `tombstone` | T1/T2/T3 必过 |
| gamma | `sync` | `tombstone` | `gate-local-gamma` 或远端 T3/T4 必过 |
| prod | `sync` | `tombstone` | dry-run artifact、审批、post-activation smoke、观察窗口 |

`prod` 真实写入必须显式加 `--confirm-prod-apply`：

```bash
python3 quwoquan_data/scripts/cli.py ship \
  --skip-promote \
  --env prod \
  --data-release-id <releaseId> \
  --mode sync \
  --delete-policy tombstone \
  --import \
  --mongo-uri <prod-mongo-uri> \
  --confirm-prod-apply
```

## 四层验证

- T1：`python3 quwoquan_data/tests/ship/test_data_release_consistency.py`、`python3 quwoquan_data/tests/ship/test_ship_sampling.py`、`make verify-data-release-consistency RELEASE_FILE=...`。
- T2：`go test ./services/content-service/cmd/import`、`go test ./services/tag-service/...`；有 `QWQ_TEST_MONGO_URI` 时覆盖真实 Mongo tombstone/read-model 清理。
- T3：`make gate-local-gamma` 或远端 `make test-api-contract API_CONTRACT_ENV=gamma`，确认 feed/search/detail/tag/profile 不返回 tombstone 或悬挂对象。
- T4：Patrol 覆盖 discovery feed、详情、实体主页、tag 聚合、用户交集卡；删除异常路径需验证下线内容不可达。

## 一致性阻断项

以下任何一项出现都不能激活 release：

- `dangling_post_entity_ref`
- `dangling_post_tag_ref`
- `dangling_post_fixture_author`
- `prod_hard_delete_without_approval`
- `post_action_not_in_desired_refs`
- `missing_source_hash`

post-activation 观察窗口内发现 `danglingRefs > 0`、`dirtyActiveRows > 0`、`feedDeletedLeak > 0` 或 API smoke 失败，标记 release 为 `degraded`，执行回滚。

## 回滚

未激活 release：删除 pending/staging 数据或标记 `aborted`。

已激活 release：

1. 将 `data_release_state.activeReleaseId` 切回上一 release。
2. 对新 release 写 `rolled_back` 审计事件。
3. 重新运行 consistency scanner 与 T3 smoke。
4. 保留 tombstone 和 import report，不做即时硬删。
