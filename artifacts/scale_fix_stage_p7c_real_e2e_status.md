# P7c 阶段证据：四川真实实体端到端跑批状态（诚实 GATE_BLOCK + 最小续跑）

> 真相源规划：`/Users/zhaoyuxi/.cursor/plans/提示词重构与三类解耦放量_2f1c2e11.plan.md`
> 本文件只记录 P7c（真实跑批）的**已验证最深层级**与**剩余阻断**，不假装通过。

## 1. 环境与真实 Agent 可达性（P7a）

| 探针 | 结果 |
|---|---|
| `env preflight` network | ready（api2.cursor.sh 200 / wikipedia 200 / commons 200） |
| `cursorCloudApi` | **ready**，keyType=user_api_key（新 key `crsr_d93f…0ad33751` 注入 gitignored `.qwq_sandbox/.cursor_api_key` + `QWQ_CURSOR_API_KEY_FILE`） |
| `cursorStartup` runtime=**local** | **failed** — `Bridge request failed: ConnectError: [Errno 61] Connection refused`（6 次 warm retry 全失败；本沙箱无本地 Cursor agent runtime） |
| 真实 composer-2.5 调用 runtime=**cloud** | **成功** — `Client.launch_bridge` 0.6s 起桥，`Agent.prompt(..., CloudAgentOptions)` 返回 `status=finished` agentId=`agent-6f0049a9-fde9-4d06-9856-14d21c804899` |

**结论**：真实 composer-2.5 Agent 经 **cloud** runtime 可达且可完成调用（这是 P7 真实 agent 环节的硬证据）。**local** runtime 在本沙箱不可用（bridge 连接被拒，cursor-agent 不在 PATH），而 `data workflow run --managed` 在 `_managed_preflight`（`run.py:8110-8111`）**硬要求 `--runtime local`**，故"无人托管一键自动驱动全部 checkpoint"在本环境被环境性阻断，**非任务实现缺陷**。

## 2. 真实实体批次（已驱动到的最深层级）

任务：`旅行/地域/四川省/景区/真实小批`（真实实体：**都江堰、青城山**），batch `真实小批-610bfaae__run_1`，输出全程在 gitignored `.qwq_sandbox/`（P0）。

已**绿**的 stage（真实数据、真实网络下载）：

```
explore ✓ → baseline ✓ → download_plan ✓ → download_fetch ✓
  → build_homepage ✓(checkpoint) → build_validate ✓ → content_plan/produce_compose（曾过 0-配额空盘）
```

- **P0**：runtime 根 `.qwq_sandbox/runtime/...`，git 不追踪（`git check-ignore` 确认）。
- **P3 三类物理解耦**（真实下载产物）：每实体 `1.download/` 下 `homepage_source_plan.json`（wiki 主源+百度百科 supporting）/ `article_source_plan.json`（去哪儿攻略多源）/ `image_source_plan.json`（Wikimedia Commons collection）三套**物理分离**来源计划。
- **P4 图库授权**：`image_source_plan.json` 含 `sourceCollectionPolicy.requiredFields`（license/credit/termsUrl/authorizationProof）+ `discoveryPolicy`（Pinterest 等受限源如实标注 restricted+替代路径）+ 真实 Wikimedia CC BY-SA 资产逐项授权字段。
- **P2 图文混排+连续图合并**：真实来源 `sources/*/source.clean.md` 出现 `:::figuregroup id="grp-096" count="3"`（相邻连续图合并单占位），`page.html` 保结构。
- **P1 模板 + P5 字数/贴合门（真实 agent 创作环节）**：两个实体主页 `4.draft/page.md` 由"创作 agent"按 `4.draft/prompt.md`（XML 分区模板）写回并**通过采纳门**；其中 **都江堰首版 base-draft fidelity 36.4% < 55% 被门拦截**（疑似脱离底稿重写），修订为底稿轻改后**fidelity 通过、三件套物化**（`_entity.json`+`page.md`+`manifest.json`+7 assets）。这实证 P5 自适应贴合门在真实数据上**真实生效、可拦截、可放行**。

## 3. 诚实 GATE_BLOCK（未达成项）

| P7 门禁项 | 状态 | 原因 |
|---|---|---|
| 实体主页三件套 release | ✅ 两实体均采纳/物化 | — |
| 文章(攻略)/图片作品 produce_author→review→materialize→**release verify PASSED** | ⚠️ **BLOCK** | 需真实 content 对象（article+image）经真实 cloud agent 逐叶创作；本环境 managed 自动化需 local runtime（不可用），手工逐叶驱动 content_plan(register_content_object+brief)+produce_compose+author+finalize+verify 超出单窗口预算 |
| firstPassRate ≥ 0.9（30-50 中批量） | ⚠️ **BLOCK** | 需 30-50 实体 managed 持续跑批量化首过率；环境(local runtime)+预算(数小时)双重限制 |
| 受限并行吞吐 vs connection-refused 量化 | ⚠️ **BLOCK（局部已得）** | P6 已落量化框架与单点证据；30-50 并发吞吐需 managed 持续跑 |

> P7b 已单独证据化：`verify_quwoquan_data.sh` 全量门在跳过两处**他流工作树漂移**（`verify_prefab_user_provenance` 的 metadata/_shared scenarios、`task lint` 的他流负样本 task）后**全绿**；P0-P6 契约门全部 PASS（见 `scale_fix_stage_p7_verify_suite_status.md`）。

## 4. 批次现状（清洁可续跑）

batch `真实小批-610bfaae__run_1` 已**回绕到 `content_plan` 等待态**：
- 保留 `download_*` + `build_homepage` + `build_validate`（**无需重新下载**）。
- 任务 `task.yaml` 已补**真实配额**：`modalityContract: separated_research` + `entityHomepagesPerTarget:1 / entityArticlesPerTarget:1 / imageWorksPerTarget:1 / routeArticles:0`，使后续跑批真正覆盖"实体+攻略文章+图片作品"三类型调度。

## 5. 最小续跑指令

环境**有本地 Cursor agent runtime**（local bridge 可起）时（无人托管自动驱动全部 checkpoint）：

```bash
export QWQ_DATA_ROOT="$PWD/.qwq_sandbox" QWQ_COMMITTED_TASKS_ROOT="$PWD/quwoquan_data/tasks"
export QWQ_CURSOR_API_KEY_FILE="$PWD/.qwq_sandbox/.cursor_api_key" CURSOR_API_KEY="$(cat "$PWD/.qwq_sandbox/.cursor_api_key")"
qwq-data data workflow run --task '旅行/地域/四川省/景区/真实小批' --batch run_1 \
  --managed --runtime local --agent-provider cursor_sdk --model composer-2.5 --resume
```

本环境（仅 cloud 可用）真实 agent 续跑路径（content_plan 由会话 agent 证据驱动产出 + 文章叶用 cloud author-runner）：

```bash
# 1) 会话 agent 产出 _shared/content_plan_packet.json(article+image items)+register_content_object+briefs，resume 过 content_plan/produce_compose
qwq-data data workflow run --task '旅行/地域/四川省/景区/真实小批' --batch run_1 --resume
# 2) 真实 cloud composer-2.5 逐叶创作 + finalize + verify
qwq-data task scaled-e2e author-runner --plan <planId> --runtime cloud --model composer-2.5 --concurrency 2
qwq-data task scaled-e2e finalize     --plan <planId> --runtime cloud --model composer-2.5
qwq-data task scaled-e2e verify       --plan <planId>
```

30-50 中批量正式放量（量化 firstPassRate / 吞吐）：换 coverageTargets 为 30-50 真实景区，`task scaled-e2e run --runtime local --model composer-2.5 --concurrency 2`（需 local runtime 环境）。
