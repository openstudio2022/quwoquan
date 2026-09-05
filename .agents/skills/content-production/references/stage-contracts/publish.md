# 阶段契约：publish

AI 对每个 approved 对象逐个调用 canonical 单对象事务；不存在 execution 级 publish orchestration。批量并发与限流属于宿主 runtime。

## PRE

AI 在 OPEN 只提交并冻结 approved 对象清单，以及每对象唯一 carrier draft、唯一 `content_review.json`、source/media/content-library bindings 的 exact refs；逐资产 rights 结论直接来自同一 `content_review.json`。video 还提交 source video/source poster CAS exact refs。

## DURING

AI 先确认 rejected 对象未混入范围，再按 approved 对象逐一准备最终 package，并调用当前真实命令：

```bash
python3 quwoquan_data/scripts/cli.py release publish-object --execution-id <id> --target-ref <targetRef>
python3 quwoquan_data/scripts/cli.py release publish-object --execution-id <id> --target-ref <targetRef> --apply
```

第一条生成/校验 plan，第二条执行同对象原子 I/O。AI 记录 transaction/package/apply exact refs；一个对象失败只使该对象 blocked，不撤销其它成功对象。禁止 `publish-execution`、publish runner、drain/process manager、campaign/pool direct-write、手拷 canonical 或手写事务 receipt。

## POST

机械 verifier：

```bash
python3 quwoquan_data/scripts/cli.py verify stage-artifacts --execution-id <id>
python3 quwoquan_data/scripts/cli.py verify publish-purity
python3 quwoquan_data/scripts/cli.py verify publish-closure
```

AI self-check：逐对象对账 `content_review.json` approved → package → canonical object → pool record/content-library binding；确认 rejected 对象未写入且对象失败/shortfall 已保留 typed issues。

## HANDOFF

- receipt ref/digest；
- `resultRefs`：每个成功对象的 canonical ref、transaction package/apply receipt、pool record 与 content-pool handoff query exact refs/digests；
- `typedIssues`；
- Skill 固定后继：`release`。
