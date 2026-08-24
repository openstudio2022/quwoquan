# 阶段契约：publish

把 approved 对象物化为成品并原子写入 canonical publish（物化 + 提升
一条原子链，设计归属 L2 `design.md#dec-027`）。

## 身份

- stage：`publish`（与磁盘目录一字不差）
- 前置阶段：`5.review`
- 合法 next：`release`
- 角色人设：[release-operator](../roles/release-operator.md)
- 写目录 allowlist：对象根成品（`article.md`/`manifest.json`，只经原子命令）、
  canonical publish 根（只经原子命令）、工作包根 `publish_ref.json`

## 做前（PRE）

- `5.review` receipt `verdict=pass`；复跑：

```bash
python3 quwoquan_data/scripts/cli.py verify stage-artifacts \
  --execution-id <id> --through 5.review
python3 quwoquan_data/scripts/cli.py verify content-execution-layout \
  --execution-id <id>
```

- 物化输入已冻结：发布坐标（`publishAngle/publishTitle/publishSeq`）在
  `0.plan/target_set.json` 逐 target 在场；每个 approved 对象的
  `3.compose/writing_pack.json` 含 `creatorProfileRef`、`tagRefs`
  （schema 真相源 `quwoquan_data/schema/content/writing_pack.schema.json`）。
  缺失时回对应阶段补冻结，不得靠命令参数替代。

## 做中（DURING）

- 唯一 CLI：`python3 quwoquan_data/scripts/cli.py release publish-execution \
  --execution-id <id> --apply`（省略 `--apply` 为 plan-only 校验，先 plan 后 apply）。
  命令内部完成：资格判定（receipt 链 + attestation）→ 成品物化 →
  delivery intent → 单对象事务写 canonical。
- [MUST NOT] 手拷文件进 canonical publish 根，或手写成品 `manifest.json`。
- [MUST NOT] 让 raw source、草稿、prompt、日志或运行状态进入 canonical。
- [MUST NOT] 对 receipt 协议 execution 使用 `verify execution-readiness` /
  `release pool-append` / `task drain-pool-delivery`——三者语义属存量 campaign 轨。

## 做后（POST）

交付件：canonical 对象 + `publish_ref.json`。完成判据：

```bash
python3 quwoquan_data/scripts/cli.py verify publish-purity
python3 quwoquan_data/scripts/cli.py verify publish-closure
```

常见 issue → 修复（教训 3：读 issue 修产物，不盲试）：

- purity 报非 approved 对象 → 回查 `5.review` 结论；对象不合格则从本次
  publish 范围移除，不放宽门禁。
- closure 报孤立 creator/media 或悬空引用 → 补齐被引用对象的 publish 或
  修正引用，重跑原子命令。

按 [handoff-protocol.md](../handoff-protocol.md) 落 receipt。

## 交接（HANDOFF）

- `next=release`。
