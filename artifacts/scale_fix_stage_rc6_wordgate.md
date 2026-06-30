# 阶段证据：RC6 形态自适应字数门——消除固定 600 第二真相源

归属：L3 三类解耦无人托管创作 → 文章字数门形态自适应（200 图文混排 / 600 长文）。

## 问题

固定 600 字数门散落多处构成"第二真相源"，会把图多文少的真·图文混排底稿误判为太短而放弃：
- `task/run.py` 预检 `_content_plan_base_draft_shortfall_refs` 用 `MIN_ARTICLE_BASE_DRAFT_CHARS=600` 做 raw 门（不看形态）。
- `verify/verify_content_quality.py:117` raw `< 600`。
- `_common/content_review.py:85` `carrier != gallery and < 600`（漏 image carrier）。

## 修复（统一到 base_draft.base_draft_readiness 单一真相源）

1. `base_draft.py`：`RICH_MIXED_MIN_TEXT_CHARS 180→200`（对齐权威"正文≥200"），补注释钉死唯一真相源。
2. `run.py` 预检改为 `base_draft_readiness(base_text, publish_media_mode=...)`，按形态判 ready；删除 raw 600 import。
3. `verify_content_quality.py` 改形态自适应：image/gallery 豁免长度门；article 走 readiness（长文≥600 或图文混排正文≥200+≥3图+图注）。
4. `content_review.py` 同上，并把豁免从 `gallery` 扩到 `image/gallery`。
5. run.py 两处放弃 reason 文案 `below_600` → `below_adaptive_word_gate`，避免误导性"600"叙事第二真相源。

## 三层测试证据（local_contract）

- 新增 `tests/local_contract/common/test_adaptive_word_gate__local_contract_test.py`（6 passed）：长文需≥600；图多文少（正文≥200+3图，总<600）判 rich_mixed 通过；text_only 声明下不得借图文形态绕过长文门；<3图不算 rich_mixed；content_review 形态感知（image/gallery 豁免）。
- 回归：`-k "base_draft or content_review or content_quality or narrative or gallery_carrier or auto_content_plan or release_integrity"` → 79 passed。

## 残留

- `auto_plan_writer.py:140 articleLengthPassChars=600`、`site_supply/core.py:55`、`scale_readiness.py:219` 仍有 600 字面量，属发现/规划提示与站点供给，非发布硬门第二真相源；后续随三类解耦一并收敛。
