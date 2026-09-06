# 里程碑 handoff

`release finalize` 是唯一 terminal writer；成功后 producer 固定到 `END`。

## cohort（AI 写）

```json
{"schema":"quwoquan_data.release_cohort",
 "releaseId":"<date>--travel-research-<milestone>--<slug>-<nnn>",
 "milestone":"M1|M10|M100|M1000",
 "releaseClass":"research",
 "expectedCarrierCounts":{"homepage":1,"article":1,"image":1,"video":1},
 "objectRefs":["posts/article/...","entities/..."],
 "producerBaselineRevision":"<40-hex git commit>"}
```

里程碑目标固定：M1 `1/1/1/1`、M10 `10/10/10/2`、M100 `100/100/100/10`、M1000 `1000/1000/1000/100`（homepage/article/image/video）。按 `cumulative_unique_finalized_objects` 累计：凡已完成 canonical publish 事务且 review approved 的对象，不论产出协议新旧都可进入 cohort；复用对象绑定其 canonical identity 与原 publish proof，不伪造新 receipt。

## handoff（脚本写，create-once）

`.qwq_output/data/releases/<releaseId>/producer_release_handoff.json` 包含：release ref/digest、cohort ref/digest、milestone、四载体 counts（含 total）、逐对象 canonical identity 与 pool query digest、`producerBaselineRevision` 与 `producerContractDigest`（实际消费的 producer 契约文件 merkle）。不含任何 consumer/environment facts。

## 复核

`python3 quwoquan_data/scripts/cli.py release handoff-verify --release-id <id>` 只读重放 handoff 内嵌字节并逐项比对；漂移即 typed blocker。
