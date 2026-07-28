<output_format>
- 把创作的正文写回同目录 `page.md`（覆盖占位），正文去空白 ≥ {{min_page_chars}} 字，
  且每个 `##` 章节（不含『相关图片』）去空白 ≥ {{min_section_chars}} 字：
  写不够这个体量的章节直接省略或并入邻近章节，不要留下信息量不足的空壳小标题。
- 正文写**带多级小标题（`##`/`###`）的纯文字 Markdown**；底稿材料中形如 `[[IMG:fig_NN]]`
  的整行是系统图片占位符，必须原样带回（不改 id、不移动、不复制、不删除、不新增，行尾不加文字）。
- 封面、图片展开、『相关图片』区、`_entity.json`、`manifest.json` 全部由 finalize 代码侧生成；
  你不得书写任何 `asset://`、`:::figure`、`:::gallery` 或 frontmatter。
- 正文必须能在底稿 / 来源中回溯事实，禁止机械模板句、工程化口径与重复凑字。
- 写回正文后停止；`task execute` 调度器会自动执行 finalize / 采纳门。失败时仅按 validator 提示修正正文，不得调用其它工作流入口。
</output_format>
