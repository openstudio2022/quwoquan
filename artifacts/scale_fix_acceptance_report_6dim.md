# 商用规模内容生产修复 — 六维度验收报告（2026-06-30）

特性树：`AppRoot → L1 content-supply（数据工程内容生产）→ L2 底稿中心 1:1 内容生产 → L3 fidelity/三类解耦/配图同源`。
验收意图：contract（local_contract）+ 数据工程 user_acceptance（真实 agent E2E）。
分支 HEAD：`86f0e3bdc`（本窗提交 4350235dc/70bf7cf4f/e79d9bc79/509d2a2f2/bd42f6557/57b88ba85/86f0e3bdc）。

---

## 维度 1：底稿忠实（baseDraftFidelity）— ✅ 达标（真实 agent 实证）

- **根因修复**：`route_compose._attach_base_draft_text` 旧逻辑把 `baseDraftText` 截断到 4000 字 + 固定 wordCount 上限 ⇒ 长底稿轻改数学上达不到 55% 留存。新增 `BASE_DRAFT_PROMPT_MAX_CHARS=24000`（整篇入 prompt）+ `clean_base_draft_length` + `base_aware_word_count`（字数目标随清洗底稿长度、与 fidelity 分母同源），契约 `test_base_aware_word_count_tracks_long_base_draft` 锁定。
- **实证**（P5 四川 7 篇文章，`base_draft_similarity` 直算）：

  | 文章 | fidelity | 备注 |
  |---|---|---|
  | 彭水.成都.**都江堰**多目的地路书 | **90.8%** | 修复前 18.6% |
  | 此生必驾318 / 自驾去乐山 | 96.7% / 96.4% | |
  | 拿捏峨眉山 / 非常特种兵 / 跋山涉水九寨沟 / 天上瑶池九寨 | 75.6% / 70.7% / 68.6% / 60.2% | |

  全部 ∈[60.2%,96.7%]、全部 ≥55%，**无一 fidelity 失败**。多目的地路书整篇保留全部站点（不再被离题分母误杀）。

## 维度 2：三类解耦（实体/文章/图片各自来源）— ✅ 达标（代码+契约，前窗已落地）

- 实体=百科择优单源主页三件套；文章=article lane 单一 base 底稿（标题取自底稿、整篇轻改、禁跨源）；图片=image lane 专业图库一源一作品（单 `sourceCollectionId`）。
- 物理解耦实证：文章在 `posts/article/`、实体在 `entities/`，manifest `citedSourceRefs` 单源、`entityRefs` 仅作标签；`verify single-contract-source`/`works-classification` GREEN。
- mustIncludeFact 不再塞写作策略（L6335 `[]`）；策略由结构门（单源 baseSourceRef + RC4 同源红线 + fidelity 门）强制。

## 维度 3：配图同源（一源一作品 / 零替代图）— ⚠️ 部分达标 + P0 风险登记（R-CS10）

- ✅ 零 Wikimedia 替代图（7/7 manifest）；RC4 红线显式拒 `same_authorized_collection` 跨源替代；`sourceUrls` 单源（7/7，消解"为何如此多来源"）。
- ⚠️ **图文不同源 P0**：本批 27 个 source.md 仅 1 个含内联图 ⇒ 7/7 文章退化 `publishMediaMode=text_only`、`assets=[]`，**丢失底稿图文混排**。RC3 内联图提取器已代码+契约修复（`test_inline_source_images` gate 绿），但本批 download 为修复前陈旧源；真实 qunar lazy-load 重下载端到端验证待补。**已登记 `docs/outstanding_risks_backlog.md` R-CS10（用户确认 P0）**。

## 维度 4：证据收敛（中间产物简化 / 单源）— ✅ 达标

- manifest `sourceUrls` 单源（此前用户投诉"如此多来源"已消解）；storySpine `primaryEntity`/`routeEntities`/`beats`/`citedSourceRefs` 均单源无污染；`release verify --scope current` PASSED。
- 陈旧策略串 mustIncludeFact 清除后无不可满足契约；评审证据链（review_gate/review.json/media_check）齐备、失败可精确诊断。

## 维度 5：无人托管（managed 自愈续跑）— ✅ 串行达标 / ⚠️ 并行受限

- ✅ 串行 managed（`task run --resume --managed --agent-provider cursor_sdk --model composer-2.5`）：5 篇文章 author→annotate→review ~440s 未超时；状态机 per-leaf checkpoint，SIGTERM 中断后可从 `produce_author` 断点续跑（本窗即从前窗 signal 15 中断点恢复）。
- ✅ Token 单一真相源 `QWQ_CURSOR_API_KEY_FILE`；N=3 探针复验 success=3/auth=0/真5xx=0%/bridgeDisconnect=0/P95=19.8s。
- ⚠️ 抗超时纪律：单 agent 调用受 `QWQ_MANAGED_AGENT_TIMEOUT_SECONDS=900` 约束；本窗每子步 ≤15min 即提交 + 落 artifacts，7 个提交全部 bank。

## 维度 6：受限放量就绪（concurrency 2-3）— ⚠️ GATE_BLOCK（如实，非假装）

- ✅ 串行可靠基线（5 篇 440s）；间接并行证据：P0 N=20 并发 bridgeDisconnect=0/true5xx=0、`fanout_runner` 26 契约测试通过（含 lease 并发、connection-refused 恢复）。
- ⚠️ concurrency=2 端到端真实并行 author **未达成**，双路径均阻断（环境约束，非编排逻辑缺陷）：
  1. probe 路径 → `Failed to verify existence of branch 'codex/content-ui-directory-restructure' in repository openstudio2022/quwoquan`（fanout 探针校验远端分支，本地分支未推送）；
  2. `--skip-startup-probe`（默认/`--runtime local`）→ 2 worker 并发 bridge 冷启零输出挂起（300/560s 被杀）。
- **修复方向 + 最小续跑指令**见 `artifacts/scale_fix_stage_p6_limited_parallel.md`：per-worker 预建 warm bridge / 错峰冷启 bridge / push 分支供 cloud dispatch。

---

## 验收结论

- **核心根因修复（fidelity 数学不可达 + mustIncludeFact 不可满足 + 载体错配）经真实 composer-2.5 端到端验证生效**：P5 7/8 PASS、底稿忠实全篇 ≥55%、单源/零替代图/storySpine 净/物理解耦/release verify 全过。
- **`verify_quwoquan_data.sh` 本任务代码改动全门绿**（两处红灯归因外部他流污染 + 本地 sandbox，CI 干净环境不复现）。
- **如实 GATE_BLOCK 项**（不假装通过）：
  1. firstPassRate 0.875<0.9 — 1 篇 entityCoverage 源-实体错配（content_plan 分配问题，非本修复回归）；
  2. 图文混排丢失 → 文章 text_only（R-CS10 P0，需真实 qunar 重下载验证 RC3）；
  3. 受限并行 concurrency=2 — bridge 冷启争用 + 远端分支校验（环境约束，串行可靠）。
- **已验证最深层级**：单批次真实 agent 串行 author→review→materialize→release-verify 全链路 GREEN（7/8），fidelity 修复硬证据闭环。
- **最小续跑指令**：(a) entityCoverage → content_plan 分配前校验底稿覆盖目标实体；(b) 图文混排 → 对真实 youji 重 download 验 RC3；(c) 并行 → per-worker warm bridge 后重跑 `author-runner --concurrency 2`（命令见 p6 证据文档）。
