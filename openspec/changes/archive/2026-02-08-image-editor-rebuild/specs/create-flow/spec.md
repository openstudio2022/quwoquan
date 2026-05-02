# create-flow

## MODIFIED Requirements

### 需求：创作页为四 Tab 统一编辑容器

创作页（CreatePage）须提供四个 Tab：随记（moment）、图片（photo）、视频（video）、文章（article）。从入口抽屉选择某一类型后，创作页以对应 initialTab 打开。草稿、退出确认、保存与丢弃行为须与原型一致。**图片（photo）Tab 须使用由 image-editor 能力提供的重建后图片编辑器**，该编辑器具备三段式布局（顶栏返回/序号/蓝色完成、中部图片、底栏编辑按钮）、Snapseed 式记录操作、底栏工具集（旋转、裁剪、滤镜、专业修图、相框、文字、涂鸦、马赛克）及统一操作面板结构；不得使用过往版本或简化版 ImageEditor。

#### 场景：创作页 Tab 与内容

- **当** 用户从入口抽屉选择任一类进入创作页
- **则** 创作页展示对应 Tab 的编辑区域（随记对应 MomentEditorCard、图片对应 image-editor 能力提供的重建后图片编辑器、视频对应 VideoEditorCard、文章对应 ArticleEditorCard）；用户可切换 Tab 编辑不同类型
