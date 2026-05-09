# Markdown Article Kernel Tasks

本文件是 `plan.yaml` 的人读版索引。开发执行以 `plan.yaml` 的 `D0-D8` 为准。

## D0 规格冻结

- 补齐 `spec.md`、`design.md`、`acceptance.yaml`、`plan.yaml`。
- 补齐 `metadata-change-draft.yaml` 与 CR。
- 确认 Markdown 是唯一持久化真相源，旧 `articleDocument` 预制数据不做兼容。

## D1 端侧 AST

- 新增 `quwoquan_app/lib/ui/content/markdown/`。
- 实现 `QwqMarkdownDocument`、block、inline、asset ref 和 parser wrapper。
- 覆盖标准 Markdown、front matter、富布局指令和未知指令校验。

## D2 分页与 reader

- 实现 `MarkdownPaginationEngine`。
- 输出 `QwqMarkdownPageData`。
- 接入只读 `ImmersiveMarkdownReader`，并复用 pageflip 物理层。

## D3 metadata 契约

- 修改 `content/post/fields.yaml`。
- 修改 `service.yaml` writable fields。
- 修改 `storage.yaml` 与 detail/discovery projections。
- 更新素材治理字段草案并运行 metadata/codegen。

## D4 content-service

- 支持 Markdown create/update/get。
- 计算 digest。
- 校验 asset manifest。
- 完成素材 bind 与合同测试。

## D5 全局创作入口

- 支持 Markdown 导入。
- 编辑会话回写 Markdown。
- 发布 payload 不再写 `articleDocument`。

## D6 quwoquan_data

- `raw/` 保存 `source.md` 与图片素材。
- `publish/` 生成 `article.md`、`gallery.md`、`manifest.json`、`images/*`。
- dry-run payload 映射到 Markdown CreatePost 字段。

## D7 无兼容债

- 清理旧 `articleDocument` 长文 fixture/seed。
- 预制长文全部重生成 Markdown。
- 增加扫描门禁防止回退。

## D8 验证收口

- 补齐 T1-T4。
- 跑通 `make gate-full`。
- 验证 beta/gamma remote 与多端分页。
