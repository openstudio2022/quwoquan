# 阶段证据:verify_quwoquan_data.sh 全绿(离线门禁闭环)

- 时间:2026-06-30
- HEAD 链:5f0458861 → c13c01b45 → 1669eb949 → b7e76deda
- 结论:`bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh` **EXIT=0 `[verify-quwoquan-data] PASSED`**(~343s),
  且全量跑后**零泄漏**到真实 `quwoquan_data/tasks/`(仅 规模门 task.yaml 的 createdAt noise dirty,语义与已提交一致)。

## 本阶段收口的零散改动(按精确路径小步提交)

1. `c13c01b45` — RC3 收口:`test_inline_source_images` 迁至 local_contract 规范路径(纯重命名,与门禁第163行引用一致),消除门禁断链。
2. `1669eb949` — 修复**预存在**批量测试污染:图片 lane 跨任务复用/救援用例 hermetic 化。
3. `b7e76deda` — 修复**预存在**测试隔离泄漏:`source_plan_guidance_fixtures` 导入后重钉路径根,阻止 `store.save_spec` 把夹具规格写进真实仓库。

> 未提交、归属不明、且不影响数据门禁的零散改动(agent_ops `patrol_cli.py`/gamma/smoke patrol、`artifacts/app_alpha_beta_seed_matrix.json`、`creator_batch100_commercial_readiness.json`)按指令**原样保留不提交不回滚**;工作树中 `quwoquan_app/**` 一律不碰。

## 两处预存在测试隔离 bug(非本轮回归,已证 877ff7988 同样失败)

### A. 图片 lane 跨任务复用污染(批量失败、隔离通过)
- 现象:门禁批(行191-203)中 `test_auto_research_image_lane` 2 例失败
  (`collections==2` got 4、`commons_calls==2` got 1);单文件隔离跑 7 passed。
- 根因:fixture 导入期 `tempfile.mkdtemp()` 设进程级共享 `QWQ_RUNTIME_ROOT`,同 session 多文件共用同一 `batches_root`;
  跨任务复用门 `_verified_image_collections_from_prior_plans` 按 `entity_id` glob 所有批次 `image_source_plan.json`,
  兄弟文件为同名实体(黄山风景区/故宫博物院)先写计划即污染,且按 `sourceCollectionId` 去重(不同 id 计入多余)。
- 判定:回退本会话 9 个源文件到 877ff7988 后**同批仍失败** → 预存在,非本轮内容改动引入。
- 修复:两个用例在 seed/运行前清掉共享 `batches_root` 下该实体旧 `image_source_plan.json`(仅归零测试输入,
  不改实体名、不动 collection gate、不改任何业务逻辑)。生产里跨任务复用同实体 collections 是预期行为。

### B. committed-tasks 泄漏真实仓库(导入顺序敏感)
- 现象:`task lint` 报 `旅行/地域/测试省/景区/{图片救援发现,图片别名发现,图片唯一数量门,并行可用性报告隔离}`
  "effective content.angles 为空";这些正是测试夹具 task 名,且为**未提交**目录,反复删了又被测试重建。
- 根因:`_common.paths` 的根是导入期冻结的模块常量;批量 pytest 中前序文件(如 test_cursor_probe)先导入 paths
  (env 未指向临时根),`COMMITTED_TASKS_ROOT` 冻结成真实 `quwoquan_data/tasks/`;fixture 后续 env 重设对已缓存模块无效,
  于是 `store.save_spec(key=测试省)` 把夹具规格写进真实仓库,被 `task lint`(扫真实 committed 全集)判失败并污染工作树。
- 修复:fixture 导入后重钉已冻结常量到临时根(`_common.paths` 的 RUNTIME/TASKS/COMMITTED/PUBLISH/RELEASE 与 `task.store`
  的 COMMITTED 副本),强制隔离不受导入顺序影响。全批 91 passed 且零真实 tasks 泄漏。

## 已覆盖门禁(摘)
- task lint OK、template lint/creator-lint/rec-contract/audience-lint PASSED
- cli-first ratchet、agent executor contract、creator match、section_outline+asset_placement、object stages+wikitext
- 批(行191-203)91 passed:P0 探针分类、cursor credentials、scaled-e2e run、形态自适应字数门、实体聚焦、
  source/image collection gate、source plan registry、auto research(article/homepage/image lane/transport)、route assets layout
- 简体中文发布门(localization)、inline source images(RC3 local_contract)、release integrity gate、route brief&evidence

## 下一步(真实 agent 驱动,反复超时根源,按可恢复单元做)
- B) P0 N=20 探针重测(拉长超时+warm 复用,区分 auth/真5xx/timeout),真5xx<10% 才进 E2E
- C) P5 四川三类 scaled-e2e 小批(3-5),scaled-e2e run 状态机断点续跑,单次 agent 调用 bound ≤15min
- D) P5 逐项门禁 + firstPassRate≥0.9 + release verify PASSED
- E) 若 token 轮换/网络受限无法达标,如实 GATE_BLOCK + 最小续跑指令
