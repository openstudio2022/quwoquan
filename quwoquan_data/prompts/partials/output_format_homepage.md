<output_format>
- 把创作的正文写回同目录 `page.md`（覆盖占位），正文去空白 ≥ {{min_page_chars}} 字。
- 正文写**带多级小标题（`##`/`###`）的纯文字 Markdown**；配图、封面、`_entity.json`、`manifest.json`
  由 finalize 自动生成（按章节锚点把同源真实图注入正文 figure 块），你**无需也不必**手写图片指令或元数据文件。
- 正文必须能在底稿 / 来源中回溯事实，禁止机械模板句、工程化口径与重复凑字。
- 完成后运行 `qwq-data data workflow run --resume` 进入 finalize / 采纳门；失败按 validator 提示修改正文重跑。
</output_format>
