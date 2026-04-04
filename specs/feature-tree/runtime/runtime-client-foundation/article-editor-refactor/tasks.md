# article-editor-refactor 任务

## /baseline（已冻结）

- [x] `spec.md` / `design.md` / `acceptance.yaml` / `plan.yaml`
- [x] 冻结文章编辑器 WYSIWYG、图文环绕、工具栏 IA、undo/redo 与 **编辑/预览** 目标态（废止卡片/瀑布流顶栏）
- [x] 登记 `tree_index.yaml` 的 L3 节点与父级 `runtime-client-foundation/spec.md` 引用
- [x] 以 2026-04-02 `/baseline` 收口：编辑/预览共用 page slice、顶栏与 CTA 对齐图片编辑器质感、预览宿主对齐侵入式浏览器、前翻/回翻动效、caption 空态不占高、用户可见“正文/小标题/大标题”

## /dev（进行中）

- [x] slice-metadata-article-editor-contract：补齐文章块/布局契约与 metadata 对齐
- [x] slice-codegen-app-content：运行 codegen / codegen-app，更新 app 端模型与常量
- [x] slice-editor-state-rename：收口 `CreateEditorState` 命名与开关语义
- [x] slice-wysiwyg-layout-and-wrap：落地分页、环绕、卡片侵入式编辑体验
- [x] slice-toolbar-panels-and-history：收口五项底栏、面板与 undo/redo
- [x] slice-edit-preview-chrome：编辑/预览顶栏、Word 纵向编辑、沉浸横向预览与翻书动效（见 design §5.4）
- [ ] slice-tests-and-gates：`acceptance.yaml` tests 列表、`design` §9/§10 已更新；PR 前跑 `make verify-app-page-horizontal-quality` 与 `bash scripts/gate_repo.sh --scope app`
