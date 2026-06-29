# Scale Fix Stage · RC6 残留固定 600 字数门收口(单一真相源)

承接 `scale_fix_stage_rc6_wordgate.md`。本步扫描 `base_draft.py` 之外仍硬编码 600 的文章字数门第二真相源并收敛。

## 唯一真相源

- `_common/base_draft.py::ARTICLE_MIN_BASE_DRAFT_CHARS = 600`(长文)+ `RICH_MIXED_MIN_TEXT_CHARS = 200`(图文混排)。
- 形态自适应判定统一经 `base_draft_readiness(text)`。

## 收口的残留(4 处)

1. `produce/route_review.py`:article 载体 review 原对**无 figure** 分支用裸 `len(...) >= 600` 兜底,
   且该兜底其实是**死计算**(仅 `article.count(":::figure")` 为真时才被消费)。统一改为始终
   `base_draft_readiness(article)`,删除裸 600 第二真相源 + 死分支。
2. `_common/release_integrity.py`:`MIN_ARTICLE_BASE_DRAFT_CHARS = 600` 独立字面量 → 改为
   `= ARTICLE_MIN_BASE_DRAFT_CHARS`(从 base_draft 导入的兼容别名),消除重复常量。
3. `download/research/auto_plan_writer.py`:`scoringPolicy.articleLengthPassChars: 600` → 引用
   `ARTICLE_MIN_BASE_DRAFT_CHARS`,报告指标与真相源同步。
4. `verify/scale_readiness.py`:article lane 可发布性计数原裸 `_compact_len(...) >= 600` →
   改为 `base_draft_readiness(...)["ready"]`,图文混排底稿(正文≥200+足量内联图)也正确计入。

> 说明:其余 600 命中均为无关项(HTTP 5xx 区间、图片尺寸 1600/600x600 reject、caption 限长 300、
> 退避秒数、站点供给线 site_supply 独立常量等),不属文章字数门第二真相源,未改动。

## 验证

```
pytest -k "route_review or release_integrity or scale_readiness or content_quality or adaptive_word_gate or auto_research"
=> 124 passed (309s)
```
