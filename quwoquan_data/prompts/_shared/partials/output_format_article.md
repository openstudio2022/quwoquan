<output_format>
- 把创作的正文写回同目录 `draft.article.md`（覆盖占位）。
- 正文用 Markdown：首行 `# 标题`；正文用自然的 `## ` 小标题分节；图按 `<figure_contract>` 原样保留占位符 fence。
- 在同目录 `draft_meta.json` 写：`generator=agent`、`model`、`styleFamily`、`openingStrategy`、
  `citedSourcePaths`、`coveredFacts`、`creativePlan`（≥2 候选构思 + selectedPlanId + selectionReason +
  readerPromise + unusedFacts）、`selfCritique`（readerPromise / titlePromise / informationDensity /
  evidenceBoundary / personaBoundary）。
- 之后运行 `post --stage review` 过门禁；失败按 `5.review/repair_report.json` 的 issues 自修重跑，
  直到 `ref_review_gate` 全绿（approved），不得在未过门时宣称完成。
</output_format>
