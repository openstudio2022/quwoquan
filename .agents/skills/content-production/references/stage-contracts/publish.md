# 阶段契约：publish

AI 对每个 approved 对象逐个调用 canonical 单对象事务；不存在 execution 级 publish orchestration。

## PRE

- `5.review` CLOSE 为 pass。
- AI 在 OPEN 显式冻结 approved 对象清单，以及每对象 draft/manifest 输入、attestation、source/rights/media/content-library bindings；video 对象必须同时冻结 source video 与 source poster 的 CAS ref/digest，以及分别对应的 `media_ref_review.rightsReviews[]` 行，禁止以视频 rights 行隐含覆盖 poster。
- 每个对象必须可独立验证；不得把 rejected 对象混入范围。

## DURING

AI 按 approved 对象逐一：准备该对象的最终 package，先调用 `python3 quwoquan_data/scripts/cli.py release publish-object --execution-id <id> --target-ref <targetRef>` 生成/校验 plan，再以相同参数追加 `--apply` 执行原子 IO，记录 transaction/package/apply exact refs。一个对象失败只使该对象 blocked，不撤销其它成功对象。

禁止调用或保留 `publish-execution`、publish runner、drain/process manager、campaign/pool direct-write；禁止手拷 canonical、手写事务 receipt 或把 raw source/draft/log 写入 canonical。

## POST

```bash
python3 quwoquan_data/scripts/cli.py verify stage-artifacts --execution-id <id>
python3 quwoquan_data/scripts/cli.py verify publish-purity
python3 quwoquan_data/scripts/cli.py verify publish-closure
```

AI 逐对象对账 attestation → package → canonical object → pool record/content-library binding，并提交真实 verifier facts 与每对象 result refs。

## HANDOFF

- `resultRefs`：每个成功对象的 canonical ref、transaction package/apply receipt 与 pool record。
- pass 后由 Skill 固定进入 `release`；partial failure 以 typed issues 明确列出，不改写成功对象。
