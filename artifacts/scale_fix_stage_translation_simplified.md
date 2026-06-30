# 阶段证据：非中文来源译简体中文（fix-translation）

特性树归属：`AppRoot -> 数据工程内容生产(L1) -> 多语言来源本地化(L2) -> 发布字段简体中文就绪(L3)`
验收意图：contract（发布字段简体中文门）；测试证据：`local_contract`。

## 目标

非中文来源（英文 / 拉丁主导，如 English Wikipedia、外文图库 caption；繁体，如 Wikivoyage 繁体、港台景区名）
的正文 / 标题 / caption，必须**译 / 折叠为简体中文后才能发布**，原文与出处保留存档。

## CLI-first 范式定位

翻译是语义操作，归 `CLI prepare -> Agent translate -> CLI validate + gate` 的 **Agent 语义阶段**；
本阶段（离线、可验证）落地**确定性 CLI validate 门**：发布字段「简体中文就绪」校验，保证发布前
标题 / 正文 / caption 已是简体中文。Agent 翻译阶段属在线工作（需模型），按抗超时纪律推迟到真实
agent 阶段；原文与出处由 source unit（`source.md` + `sourceUrl` + `provenance`）存档，本门不丢弃原文。

## 本阶段改动（离线、单一真相源、无死代码）

1. 新增 `quwoquan_data/scripts/_common/localization.py`（简体中文本地化门单一真相源）：
   - `fold_to_simplified`：繁→简折叠（旅游/地名常见繁体字表，集中于此供全仓共用）。
   - `latin_dominant`：拉丁主导判定（阈值 latin≥6 且 ≥cjk×2，与历史 caption 退化门同源）。
   - `has_traditional_chars` / `needs_translation_to_simplified`：是否仍需译/折叠为简体。
   - `simplified_chinese_publish_issues(title, body, label)`：发布标题/正文「简体中文就绪」门
     （外文未译 / 繁体未折叠 → 阻断）。
2. 消除第二真相源（R24/R06）：
   - `asset_placement._caption_is_degraded` 改为复用 `latin_dominant`（行为保持：外文 caption 仍退化、
     中文 caption 通过），删除本地 `_CAPTION_LATIN_RE`。
   - `content_evidence._fold_zh_variants` 改为委托 `fold_to_simplified`，删除本地 33 字繁简表副本。
3. 真实挂接（非死代码）：实体主页采纳门 `entity_page_quality.entity_page_quality_issues`
   新增「H1 标题 + 正文须简体中文」检查（复用 `simplified_chinese_publish_issues`），
   与既有工程/模板污染门、章节语义门并列。
4. 新增 hermetic 契约测试 `quwoquan_data/tests/common/test_localization_simplified_chinese.py`（7 例），
   并接入 `verify_quwoquan_data.sh`（紧随 `test_quality_gates.py`）。

## 测试证据

```
$ python3 quwoquan_data/tests/common/test_localization_simplified_chinese.py
PASS test_caption_gate_reuses_shared_latin_dominant
PASS test_content_evidence_fold_reuses_shared_table
PASS test_fold_to_simplified_folds_common_traditional_place_chars
PASS test_has_traditional_chars
PASS test_latin_dominant_only_for_foreign_text
PASS test_needs_translation_to_simplified
PASS test_simplified_chinese_publish_issues_flags_foreign_and_traditional
localization simplified-chinese tests passed (7)
```

无回归（复用重构行为保持）：
```
$ python3 quwoquan_data/tests/build/test_build_homepage.py            # build homepage tests passed (20)
$ python3 quwoquan_data/tests/produce/test_entity_composer.py         # entity composer tests passed (7)
$ .venv/bin/python -m pytest -q quwoquan_data/tests/verify/test_release_integrity_gate.py            # 13 passed
$ .venv/bin/python -m pytest -q .../download/test_image_collection_gate__local_contract_test.py      # 10 passed
```

## 剩余风险 / 受限（如实标注）

- **Agent 翻译语义阶段（外文正文逐句译中）尚未联机执行**：需模型 + 联网，属在线工作；
  本阶段已落地确定性发布门把关「发布前必须简体中文」，外文/繁体未处理会被采纳门阻断，不绕硬门。
- 繁简折叠表为旅游/地名常见字子集（非全量 OpenCC）；当前管线以简体中文来源为主，足够拦截
  地名繁体；如需全量繁简转换可后续接 OpenCC 词典（不改门接口）。
