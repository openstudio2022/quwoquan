# 阶段契约：release

immutable Travel Research release 只能消费宿主 Agent 显式 cohort；禁止隐式 all-publishable 或按目录全选。本阶段业务 pass 先由 `stage-close` create-once 封存 sequence 009 `release` receipt；producer 尚需执行一次纯机械 terminal materialization 才到 `END`。handoff writer 只读已封存 receipt/release/cohort/pool/baseline 与逐对象原 producer proof，不派生 milestone、cohort、verdict 或后继。

## PRE

AI 在 OPEN 只提交并冻结以下 exact refs：

- explicit cohort document；
- cohort 内每个 canonical object、pool record 与 content-pool handoff query；
- 固定 `releaseClass=research`、release identity、40 位 producer baseline commit revision 与 taxonomy/content-library bindings 所在的受治理输入。

本级新增或实际执行 `release` stage 的 execution 必须在 release OPEN 中冻结同一份 cohort exact scope/ref/digest；从较低里程碑复用的 canonical 对象不重开原 execution，也不补写新的 sequence-009 receipt，只由本级 cohort/release/handoff 原样绑定其原 producer proof。handoff 不接受事后替换的等价 cohort 文件。

## DURING

AI 确认 cohort 逐对象列出且非空，显式决定 milestone，并使 carrier counts 与 cohort 一致；M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 累计。更高级别可复用 canonical 对象，但必须绑定对象首次生产的原 execution、sequence-001..009 receipts 与 publish transaction proof，不为复用伪造新 receipts；重复 identity 不增加累计值。对象资格只由既有 schema/硬事实 verifier 重验，不让 builder 自动扩展。随后使用当前真实原子 I/O 构建环境无关 Research release：

```bash
python3 quwoquan_data/scripts/cli.py release pool-build \
  --release-id <releaseId> --cohort-file <cohort.json> --release-class research
```

AI 选择 cohort 与 milestone；每级必须形成自己的 full explicit cohort、release 与 handoff。builder 只验证/物化，不得回退到全部可发布对象或从环境推导选择。逐对象不合格时 AI 提交 typed exclusion/shortfall；cohort 整体 identity/integrity 失败时 blocked，并以新 immutable cohort/release 重试，不得原地修改既有 release。

## POST

机械 verifier：

```bash
python3 quwoquan_data/scripts/cli.py verify release-integrity --release <releaseId>
```

AI self-check：release payload 是否与 OPEN cohort 逐对象一致；release resultRefs 是否明确包含当前 `payload/release.json`，供 CLOSE 按实际 bytes 冻结。

release build 验证通过后，AI 先调用 `task stage-close --stage release` 形成 sequence 009/pass receipt，再调用：

```bash
python3 quwoquan_data/scripts/cli.py release handoff \
  --release-id <releaseId> \
  --cohort-file <cohort.json> --milestone <M1|M10|M100|M1000> \
  --producer-baseline-revision <40-hex-git-commit>
```

`producer_release_handoff.json` 位于 release 根而非 `payload/` 内：release receipt 与 handoff 都绑定已封存 payload/header bytes，handoff 单向再绑定 release receipt，因此不存在相互 digest 循环。同 bytes 重放返回 replay；不同 bytes 冲突。

## HANDOFF

required immutable handoff 内容固定为：

- release header 的完整、唯一、排序 `executionIds`，以及每个 execution 的 sequence-009 producer `release` receipt output ref/digest；
- release ref 与 release digest；
- explicit cohort ref 与 cohort digest；
- AI 显式 milestone；
- `homepage|article|image|video` carrier counts；
- cohort 中逐对象内嵌完整 content-pool handoff query document 及 canonical digest；
- 每对象原 producer execution、sequence receipts 与 publish transaction proof exact refs/digests；复用对象保持原 proof 不变；
- producer baseline revision（40 位 git commit SHA；固定 producer contract paths 从该 commit 到 working tree/index 必须无差异）；
- Skill 固定后继：`END`。

handoff 明确不含 UAT sample plan/sampling authority、import/activate/readback、App/API UAT、EAF、environment promotion、rollback 或其他 consumer facts。

上述字段由 producer handoff authoring contract 单一约束；对应 schema/writer/reader 的后续实现必须严格闭合。writer 应重验 release integrity、cohort/policy/milestone/cumulative unique counts、每对象原 producer proofs、sequence-009/pass resultRefs、baseline commit drift，并比对 live canonical 与 sealed release pool projection后 create-once；reader 只用 sealed release bytes + handoff 重投影，不依赖未来可变 publish root或任何环境状态。成功后 Skill 固定后继为 `END`。
