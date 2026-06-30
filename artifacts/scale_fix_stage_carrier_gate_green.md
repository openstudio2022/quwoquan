# 阶段证据：载体错配修复 + 门 A 全绿

## 背景
P5 四川三类 scaled-e2e 在 `produce_compose` 阶段撞 ReAct 回退上限（2）转人工
（`status=manual_required`, `lastFailedStage=produce_compose`）。

## 根因（实测证据，唯一阻断）
读取 P5 批次 `posts/**/3.compose/compose_brief_gate.json`，**全部 6 个失败都是
image（画报）作品**，且失败 issue **完全一致**：

```
posts/image/画报/九寨沟·Mountains of Sichuan...        ["evidenceQuality: missing emotion evidence"]
posts/image/画报/峨眉山·Mount Emei and Exiu Lake       ["evidenceQuality: missing emotion evidence"]
posts/image/画报/峨眉山·​摄于峨眉山风景区               ["evidenceQuality: missing emotion evidence"]
posts/image/画报/都江堰·dujiangyan tour map...         ["evidenceQuality: missing emotion evidence"]
posts/image/画报/都江堰·Current Dujiangyan...          ["evidenceQuality: missing emotion evidence"]
posts/image/画报/九寨沟·Jiuzhaigou...Waterfall          ["evidenceQuality: missing emotion evidence"]
```

**无任何 off_entity / 文章 / 系统性失败**——载体错配是唯一阻断。

`gate_route_evidence_bundle` 是**线路/体验叙事门**（要求 UGC 情感信号 likes/painPoints、
storySpine 进程、路线节点覆盖、mustIncludeFacts 叙事）。它被无差别施加到 image/gallery
**画报作品**。开放许可图集（Wikimedia/CC）只有事实性 caption、无 UGC 互动信号，
**必然**缺 emotion evidence → 6 个图片作品必败 → 整批转人工。这是 category error
（载体错配），不是放宽硬门的问题。

## 修复
`quwoquan_data/scripts/_common/content_evidence.py` 的 `gate_route_evidence_bundle`
载体感知：`carrier ∈ {image, gallery}` 直接放行（不产线路叙事 issue）。
图片作品的把关由 **许可(rights)/资产落盘/相关性/works_gate** 负责，职责不变、未削弱。

`_writing_pack_readiness_issues`（route_compose）对 image 现在只剩"资产存在"检查，
有合格资产即 `passed:true`。

## 测试（已接入 verify_quwoquan_data.sh 第126行 pytest）
`quwoquan_data/tests/produce/test_route_brief_and_evidence.py` 新增：
- `test_gate_route_evidence_skips_narrative_requirements_for_image_carrier`：
  image/gallery 空证据放行（含大小写）。
- `test_gate_route_evidence_still_gates_narrative_carriers`：
  article/route 空证据仍拦截 `missing emotion evidence` + `route progression spine`
  （回归护栏，禁止误伤叙事门）。

## 门 A 全绿证据
```
[verify-quwoquan-data] PASSED
GATE_A_EXIT=0
```
最后一批 pytest：`91 passed in 9.49s`（含本次新增的两个载体门契约测试）。
全量 `verify_quwoquan_data.sh` 退出码 0。

## 提交
- `7e8390371` 修复载体错配 + 契约测试。

## 下一步
- B) P0 N=20 探针重测（区分 auth/真5xx/timeout）。
- C) P5 resume produce_compose（载体修复后 6 个图片作品应通过）→ produce_author（文章 agent 写作）。
