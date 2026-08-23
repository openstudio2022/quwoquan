# 阶段契约：sources

逐目标收集可追溯来源单元。

## 身份

- stage：`sources`（与磁盘目录一字不差）
- 前置阶段：`0.plan`
- 合法 next：`1.download`
- 角色人设：[source-researcher](../roles/source-researcher.md)
- 写目录 allowlist：`sources/`

## 做前（PRE）

- `0.plan` receipt `verdict=pass`；复跑以下判据命令确认 target_set 已冻结：

```bash
python3 quwoquan_data/scripts/cli.py verify runtime-input-ownership
python3 quwoquan_data/scripts/cli.py verify content-execution-layout --execution-id <id>
```

## 做中（DURING）

- 逐目标收集来源单元写入 `sources/`：URL、抓取时间、许可证线索、与目标的
  关联证据。来源单元产物清单真相源：`stage_artifact_contract.py` 的
  `SOURCE_UNIT_ARTIFACTS`。
- 信源政策按 `quwoquan_data/AGENTS.md` 分轨执行：正文底稿锁三百科闭集，
  结构化事实额外允许官网与政府/文旅门户；每条结构化事实逐字段落 `factSources`。
- **补源循环**（教训 2）：某目标合格来源不足配额时，更换检索策略再收集，
  每轮记录已试策略；最多 3 轮。
- [MUST NOT] 伪造来源、复用未授权来源、把 OTA/门户/媒体投影为正文底稿。

## 做后（POST）

交付件：`sources/` 来源单元 + 保留/淘汰判定记录。完成判据：

```bash
python3 quwoquan_data/scripts/cli.py verify source-digest --execution-id <id>
```

常见 issue → 修复：

- source identity 缺字段 → 补齐来源单元 `meta.json` 的抓取 URL/时间/许可证线索。
- digest 不一致 → 不改历史字节；以新来源单元替换并重新判定。

按 [handoff-protocol.md](../handoff-protocol.md) 落 receipt。

## 交接（HANDOFF）

- 每目标合格来源 ≥ 配额 → `next=1.download`。
- 3 轮补源后仍有缺口 → `verdict=blocked`，`openItems` 逐条列缺口目标与已试策略
  （`gate_block`），报告用户裁决（缩目标集或换区域）。
