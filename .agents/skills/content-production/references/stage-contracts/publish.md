# 阶段契约：publish

把 approved 对象原子写入 canonical publish。

## 身份

- stage：`publish`（与磁盘目录一字不差）
- 前置阶段：`5.review`
- 合法 next：`release`
- 角色人设：[release-operator](../roles/release-operator.md)
- 写目录 allowlist：canonical publish 根（只经原子命令）、工作包根 `publish_ref.json`

## 做前（PRE）

- `5.review` receipt `verdict=pass`；复跑：

```bash
python3 quwoquan_data/scripts/cli.py verify rubric --file <rubric结果路径> \
  --generation-family <4.draft 实际生成族>
python3 quwoquan_data/scripts/cli.py verify stage-artifacts --execution-id <id>
```

- 准出前置：

```bash
python3 quwoquan_data/scripts/cli.py verify execution-readiness --execution-id <id>
```

## 做中（DURING）

- 唯一 CLI：`python3 quwoquan_data/scripts/cli.py release pool-append --input <input> --apply`
  （省略 `--apply` 为 plan-only 校验，先 plan 后 apply）。
- [MUST NOT] 手拷文件进 canonical publish 根。
- [MUST NOT] 让 raw source、草稿、prompt、日志或运行状态进入 canonical。

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
