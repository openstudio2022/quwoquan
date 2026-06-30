# Scale Fix Stage · 主页源复用陈旧测试随源单元布局迁移修复

承接 `scale_fix_stage_rc2_rc4_cleanup.md` 中记录的 finding。

## 根因(非生产回归,陈旧测试)

`test_source_quality_gate::test_verified_homepage_reuse_filters_bad_or_thin_source_units`
在 HEAD `bec517cb3` 即失败(`["home_official"] == []`)。

探针确认 good 源**通过**文本质量判定(`_homepage_fact_signal_count=5`、`_homepage_text_quality_issue=''`),
即被测过滤逻辑无 bug。真正原因:

- 被测函数 `_verified_homepage_sources_from_source_units` 经 `iter_source_units(obj)` 读取
  **新版批根 `sources/su_*/`** 源单元布局(由 `write_source_unit` 写入 + `source_refs.json` 关联)。
- 该用例却**手工**在**旧版 `obj/1.download/sources/NN.name/`** 下拼 meta/source.md/source.quality.json,
  无 `source_refs.json` → `iter_source_units` 漏读 → 返回 `[]`。
- 属源单元布局迁移后**未同步更新的陈旧测试**,生产链路(`write_source_unit`)早已写新布局。

## 修复(测试对齐真相源)

改用 `write_source_unit(..., research_lane="homepage", quality={...}, task_id/batch_id)` 写三源:
- `home_wikipedia`:消歧页(`可以指` + 多 `位于`)→ 命中 `disambiguation_homepage` 过滤。
- `home_official_thin`:< 80 字 → 命中 `homepage_text_too_short` 过滤。
- `home_official`:5 句正常官网主页 → 通过 → 唯一保留。

不动任何生产代码;仅把 fixture 从废弃布局迁到 `iter_source_units` 真相源布局。

## 验证

```
pytest tests/local_contract/download/test_source_quality_gate__local_contract_test.py
=> 19 passed
```

至此 `source_quality_gate` 全文件、以及 RC2/RC4 受影响集合全绿;数据门禁内该红灯清除。
