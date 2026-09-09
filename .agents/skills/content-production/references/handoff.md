# 里程碑 handoff

`release finalize` 是唯一 terminal writer；成功后 producer 固定到 `END`。

## cohort（AI 写）

```json
{"schema":"quwoquan_data.release_cohort",
 "milestone":"M1|M10|M100|M1000",
 "objectRefs":["posts/article/...","entities/..."],
 "producerBaselineRevision":"<40-hex git commit>"}
```

`releaseId` 由 CLI `--release-id` 给出，模板 `<date>--travel-<milestone>--<slug>-<nnn>`，不写进 cohort。cohort 不写发布类别；`expectedCarrierCounts` 缺省由脚本按 `objectRefs` 派生；`objectRefs` 无需预先排序，脚本会规范化。

cohort 由 AI 显式决定「全部 eligible 对象进入」并用 `jq` 从 `pool-query --json` 输出构造（不是脚本扫池隐式选择）：

```text
python3 quwoquan_data/scripts/cli.py release pool-query --json <workspace>/pool.json
jq --arg m M1000 --arg rev "$(git rev-parse HEAD)" '{schema:"quwoquan_data.release_cohort", milestone:$m, producerBaselineRevision:$rev, objectRefs:(.eligible.homepages + [.eligible.posts[].objectRef])}' <workspace>/pool.json > <workspace>/cohort.json
```

`producerBaselineRevision` 必须是已包含当前 `quwoquan_data/publish/**` 的提交，因此 finalize 前先提交 baseline。

里程碑目标固定：M1 `1/1/1/1`、M10 `10/10/10/2`、M100 `100/100/100/10`、M1000 `1000/1000/1000/100`（homepage/article/image/video）。达标判据是四载体计数**不低于**目标，可以把全部 eligible 对象纳入；运营生产目标（如四载体各 1000）高于底线时按生产目标继续放量，finalize 时机由澄清阶段的决定给出。按 `cumulative_unique_finalized_objects` 累计：凡已完成 canonical publish 事务且 review approved 的对象，不论产出协议新旧都可进入 cohort；复用对象绑定其 canonical identity 与原 publish proof，不伪造新 receipt。

## eligible 集合

`python3 quwoquan_data/scripts/cli.py release pool-query [--json <out>]` 只读列出 `quwoquan_data/publish` 中可入 cohort 的对象与被排除对象的原因码；不满足 `publish/entity.schema.json` 的实体及引用它们的帖子被标为 excluded。cohort 只从 eligible 集合形成。

## handoff（脚本写，create-once）

`.qwq_output/data/releases/<releaseId>/producer_release_handoff.json` 包含：release ref/digest、cohort ref/digest、milestone、四载体 counts（含 total）与 milestoneTargets、逐对象 canonical identity 与 pool query digest、`producerBaselineRevision` 与 `producerContractDigest`（实际消费的 producer 契约文件 merkle）。不含任何 consumer/environment facts。

finalize 成功后同时把 `cohort.json` 与 `producer_release_handoff.json` create-or-same 复制到受版本控制的 `quwoquan_data/reference/releases/<releaseId>/`：这是可删除输出根之外的耐久副本，随后随 baseline 提交入库；它不是第二 canonical writer，`handoff-verify` 仍只读输出根。

## 复核

`python3 quwoquan_data/scripts/cli.py release handoff-verify --release-id <id>` 只读重放 handoff 内嵌字节并逐项比对；漂移即 typed blocker。

## 收官报告附录

M1000 收官报告除六段外附：`qualityScores` 按载体×维度的最终分布与 [quality.md](quality.md) 定稿、来源矩阵实际使用统计（各站点对象数、`rightsStatus` 分布、`watermarkedAssetIds` 与 `authorizationRequiredAssetIds` 计数）。
