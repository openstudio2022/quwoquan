# RC1 收尾 · route_assets 文章配图去实体键控

阶段：fix-rc1（RC1 download 去实体键控 + 清剩余 dormant 第二路径）
检查点起点：HEAD 877ff7988（干净）

## 改动

`quwoquan_data/scripts/produce/route_assets.py` `_build_route_assets` 文章 carrier 分支：

- RC4 同源收紧后，文章配图已 100% 来自单一 `baseSourceRef` 底稿来源自身 assets。
  此前仍按 `routeNodes` 实体位置键控选图（`per_entity[entity_names[0]]` 作 cover、
  `per_entity[entity_names[-1]]` 作 closing、node 逐实体取 `per_entity[name]`），属
  RC4 之后的 **dormant 第二路径**：非 base 实体的 per_entity 恒为空，且当 base 源不在
  首/末节点时 cover/closing 会漏图（潜在 bug）。
- 改为汇聚单一 `base_pool`（跨 per_entity 聚合后按 `sourceRef == baseSourceRef` +
  `sourceAssetRef` 前缀过滤，按 sourceAssetRef 稳定排序），cover/node/closing 全部从
  该同源池去重取图（**去实体键控**）。node 数仍以 `routeNodes` 长度 bound（保留线路
  推进感），池耗尽即止（`break`）。
- `baseSourceRef` 缺失 ⇒ 不配图（text_only），绝不回退借用同实体/兄弟来源（保留 RC4 红线）。

## 验证（离线、硬超时 600s）

```
quwoquan_data/.venv/bin/python -m pytest -q \
  quwoquan_data/tests/local_contract/produce/test_route_assets_layout__local_contract_test.py \
  quwoquan_data/tests/produce/test_route_assets_layout.py \
  quwoquan_data/tests/common/test_source_unit_evidence_chain.py
=> 14 passed
```

回归隔离（stash 本改动后在干净 HEAD 跑 `tests/produce/` + `tests/local_contract/produce/`）：

- 干净 HEAD：10 failed / 219 passed
- 含本改动：10 failed / 219 passed（**失败集完全一致**）

⇒ 本改动零新增回归；route_assets.py lint 干净。

## 预存在红线基线（FINDING，非本改动引入，下一子步排查修复）

HEAD 877ff7988 上已存在 10 个失败（与本改动无关，stash 对照已证明）：

- `test_entity_composer*::test_entity_e2e_materialize_verify_green` 等：
  `evidenceQuality: compose payload missing assets` / `imageGate: no verifiable image assets`
- `test_route_brief_and_evidence*::test_route_workflow_generates_real_review_green`
- `test_route_brief_and_evidence*::test_agent_draft_time_facts_are_stable_and_monotonic`
  （`createdAt == updatedAt` 时间断言）

初判：疑似上一窗口已提交的 RC4 同源收紧（`route_assets`/`source_quality` 显式拒
`same_authorized_collection` + 空 baseSourceRef 不配图）导致 entity composer / route
workflow 的测试 seed 不再产出可用 assets。需在下一子步定位并对齐测试 seed 或修正逻辑，
使 `verify_quwoquan_data.sh` 全绿，零技术债。
