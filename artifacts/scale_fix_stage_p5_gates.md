# Phase D 证据：P5 四川批次门禁逐项结论

批次 `p5_sichuan_20260630`，materialize 7 篇文章包。

| Phase D 门 | 结论 | 证据 |
|---|---|---|
| 零 Wikimedia 替代图 | ✅ PASS | 7/7 manifest 全无 wikimedia/wikipedia 字样；RC4 红线 same_authorized_collection 显式拒 |
| sourceUrls 单源 | ✅ PASS | 7/7 `sourceUrls` 长度=1（如都江堰篇仅 `youji/7901034`）；直接消解用户"为何如此多来源"投诉 |
| storySpine 无污染 | ✅ PASS | primaryEntity=都江堰、routeEntities=[都江堰]、beats 源自底稿真实内容、`citedSourceRefs` 单源 su_01cf6be7 |
| 文章与实体物理解耦 | ✅ PASS | 文章在 `posts/article/`、实体在 `entities/`；manifest 单 citedSourceRef、entityRefs 仅作标签 |
| release verify PASSED | ✅ PASS | `verify --task <T> --batch <B> --scope current` → PASSED（posts root release integrity） |
| firstPassRate ≥ 0.9 | ⚠️ 0.875 | review 7 PASS/1 FAIL；唯一 FAIL=318川藏游记 entityCoverage（fidelity 96.7% 但未提都江堰=content_plan 源-实体错配，硬门正确拦截，非本修复回归） |
| source.md 保图文混排 | ⚠️ 未达（陈旧源） | 本批 27 source.md 仅 1 含内联图；文章落 `publishMediaMode=text_only`、`assets=[]`。RC3 内联图提取器**已代码修复+契约测试 gate 绿**，但本批 download 是修复前陈旧源；真实 qunar lazy-load 重下载验证待后续。**= RC4「图文不同源」P0 风险（用户已确认登记 backlog）** |

## 达标项

底稿忠实（7/8 fidelity≥55%，都江堰 90.8%）、单源、零替代图、storySpine 净、物理解耦、release verify
均经真实 composer-2.5 产物验证通过。

## 未达标项（如实 GATE_BLOCK，非假装通过）

1. **firstPassRate 0.875 < 0.9**：1 篇 entityCoverage 源-实体错配，属 content_plan 把不覆盖目标实体的
   底稿误分配给该实体；修复方向=content_plan 分配前校验底稿是否覆盖目标实体（后续项，非本轮 fidelity/解耦修复范围）。
2. **图文混排未在产物体现**：本批沿用修复前下载源（图被剥离），文章退化为 text_only。RC3 提取器代码侧
   已修复并契约测试通过，但需对真实去哪儿 youji（lazy-load `data-*` 图）**重新 download** 才能端到端证明
   图文混排进入 source.md 与文章。本窗受网络/时间/反复 PING 超时限制未做真实重下载 → 登记 backlog RC4 P0。
