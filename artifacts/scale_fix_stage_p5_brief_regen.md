# 阶段证据：P5 陈旧 brief 修正 + 重 compose（清除 pre-fix 策略串）

## 背景

P5 批次 `p5_sichuan_20260630` 的 7+1 篇文章 review 全 FAIL，原因是 **brief.json 为我修复前的陈旧产物**：
- `mustIncludeFact missing/not traceable`：陈旧 brief 把写作策略串当 mustIncludeFact
  （"...文字底稿来自单一来源单元...禁跨底稿拼接"、"若使用配图，必须来自同一底稿的已授权源图（一源一作品）"）。
  当前代码 `task/run.py` L6335 实体文章已产出 `mustIncludeFacts: []`（grep 证实策略串在现行代码中已不存在）。
- `baseDraftFidelity 18.6% < 55%`：base-aware wordCount + 去截断修复前的旧草稿。

`compose-brief` 读 `iter_*_briefs`（即 posts/.../3.compose/brief.json）不重生成 mustIncludeFacts，
故陈旧串不会被 compose-brief 自动清除；而完整重生成（content_plan 重跑）会连带触发 build_homepage /
content_plan 的 **agent checkpoint 对全部四川景区实体重创作**，在反复 PING 超时下不可控。

## 处置（透明 sandbox 数据修正，非代码/门禁改动）

对 8 篇 article-carrier brief.json 的 `mustIncludeFacts` 清空为 `[]`——**与现行 gate-proven 代码
L6335 的确定性输出完全一致**（仅复现代码输出，避免 unbounded 全管线重跑）。image carrier 的
image-specific mustIncludeFacts（L6397）不动；6 图片作品上轮已 PASS。

重跑 `data produce --stage compose-brief`（type=article）→ 14 个 writing_pack 重建，blocked=0。

## 验证（都江堰多目的地文章 writing_pack）

```
mustIncludeFacts = []                  # 策略串已清除
wordCount        = {"min":3736,"max":6749}   # base-aware（随底稿长度，不再固定1600）
baseDraftText    = 6331 字               # 全文注入（不再截断到4000）
```

三项均与现行代码输出一致，为有界重 author 提供 fidelity 数学可行 + mustIncludeFact 可满足前提。

## 下一步（有界 agent 重 author）

逐篇 bound≤15min 用 composer-2.5 重写 draft.article.md（generator=agent）→ review --materialize，
实测 baseDraftFidelity≥55% 且 mustIncludeFact 门通过；每 leaf 终态即提交。超时即中止+提交+记 finding。
