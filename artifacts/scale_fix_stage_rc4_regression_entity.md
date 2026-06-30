# RC4 连带回归收口（一）· entity_composer 测试对齐 1:1 同源+轻改

阶段：fix-rc4-regression-baseline（HEAD 877ff7988 上预存在红线，非本窗口 route_assets 改动引入）

## 根因

上一窗口已提交的 RC4 同源收紧（`route_assets` 删 `not base_source_ref` 逃逸、
`source_quality` 显式拒 `same_authorized_collection`）使「文章配图必须有 baseSourceRef
且 100% 同源」成为硬门。`tests/produce/test_entity_composer.py` 的 3 个直连 compose 测试
（`_compose_entity_agent_draft` → `analyze_route_ref`/`build_entity_writing_pack`）用
`_entity_brief()` **不设 baseSourceRef**，绕过了生产 `handler._assign_base_draft` 的赋值：

- baseSourceRef 空 ⇒ 文章无可用配图 ⇒ `imageGate: no verifiable image assets` /
  `evidenceQuality: compose payload missing assets` ⇒ review revision_needed。
- 旧测试从未被 `baseDraftFidelity` 门约束（空 base ⇒ `base_draft_fidelity_issues` 返回 []）。

## 修复（测试对齐生产，非放宽硬门）

`tests/produce/test_entity_composer.py`（local_contract 副本为 DO NOT EDIT 生成桥接，自动同步）：

1. `_seed_sources()` 返回落盘底稿来源单元的 `sourceRef`；3 个直连 compose 测试显式
   `brief["baseSourceRef"] = base_ref`（镜像生产 `_assign_base_draft`）。
2. SOURCE_TEXT 重写为 ~700 字富叙事底稿（`_BASE_PARAS` 十段，含动机/第一印象/停留展厅/
   参观时间/推荐动线/不足/离开感受，覆盖 mustIncludeFacts，无裸数字）——原 ~200 字底稿
   本就不符合长文 readiness（≥600）。
3. 新增 `_faithful_entity_draft`：模拟会话模型"轻改底稿"——保留底稿骨架并按 structure
   必需小节(进馆第一印象/最停留的展厅/参观动线/离开后的感受)组织，仅对第 6 段(不足)
   语气轻改，使 `base_draft_similarity` 留存率落在 [55%,99.5%]（既非脱稿从零另写，
   也非整篇零加工逐字照搬）。`_compose_entity_agent_draft` 改用它，移除 `entity_article` 依赖。

## 验证（离线，硬超时 200s）

```
quwoquan_data/.venv/bin/python -m pytest -q quwoquan_data/tests/produce/test_entity_composer.py
=> 7 passed
```

`baseDraftFidelity` 落在 [55%,99.5%]（imageGate/factTraceability/structure/density 同绿）；lint 干净。

## 剩余（下一子步）

- route_brief 的 `test_route_workflow_generates_real_review_green` 同类（route_article 非
  忠实底稿），需同样对齐。
- 两份重复测试文件共享进程级 `QWQ_RUNTIME_ROOT`（import 时 mkdtemp）造成的跨文件污染
  （`test_compose_brief_persists`/`test_agent_draft_time` 仅在合跑第二副本失败），单跑均通过；
  待评估是否需在合跑序列中隔离。
