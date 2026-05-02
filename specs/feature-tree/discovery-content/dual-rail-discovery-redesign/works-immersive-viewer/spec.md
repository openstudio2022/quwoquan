# L3 子特性：works-immersive-viewer

## 功能说明

作品频道的沉浸式浏览器：垂直强制分页 PageView 呈现 works-feed 内容，统一手势模型（垂直切换作品、水平查看媒体细节），以及横切所有媒体类型的覆盖层组件（Tab 呼吸筛选、毛玻璃 Drawer、点位评论光点）。

## 范围

- `WorksImmersiveViewer`（垂直 PageView，强制分页，接入 `WorksFeedProvider`）
- 通用手势模型（优先级排列，边缘保护）
- 关灯主题：`worksForceDarkProvider` + 进入/退出主题切换
- 三类媒体子组件（各在对应 L4 节点中实现）：
  - `works-tab-filter`：二级 Tab 呼吸动画 + 筛选
  - `photo-gallery-swipe`：美图水平翻页 + 进度条 + 环境色背景
  - `video-series-swipe`：视频自动播放 + 系列水平切换
  - `article-magazine-cover`：封面模式 + 卡片分页 + 块渲染
  - `works-glass-drawer`：毛玻璃评论 Drawer
  - `works-annotation-dot`：长按点位光点

## 适用范围与约束

- **适用**：作品频道浏览器（`DiscoveryPage` 作品轨内）
- **前置条件**：`works-unified-feed`（WorksFeedProvider 可用）；`article-rich-content-blocks`（ArticleBlock DTO 已 codegen）
- **不适用**：微趣轨；圈子流；个人主页作品列表
- **约束**：
  - 垂直 PageView 与水平子 PageView 之间手势竞争须通过 `GestureDetector.behavior` + `HorizontalDragGestureRecognizer` 精细控制
  - 边缘 15px 保护区不得响应水平拖拽（iOS 系统返回手势保护）
  - Drawer 以 `Overlay` 定位，不影响底部 SafeArea / Home Indicator
  - 底部工具栏必须共享媒体 rail：作者组左锚 rail 左缘，赞/转/评动作组右锚 rail 右缘，iPad 不得把媒体内容、顶栏或底栏收窄居中。
  - 作者名最多展示 12 个 Unicode 字符；作者名槽按屏幕断点固定为 compact 4 字、regular 5 字、expanded/iPad 6 字，短名不得让关注按钮贴近文本。
  - 关注按钮固定接在作者名槽之后，显隐动画不得改变作者名槽、动作组右锚或 rail 对齐；作者名单行放不下时改用两行紧凑展示。

## 子节点

| L4 节点 | 职责 |
|---------|------|
| works-tab-filter | 二级分类 Tab + 1.5s 收起 + Elastic 弹性展开 |
| photo-gallery-swipe | 多图水平翻页 + 环境色模糊背景 + 蓝色进度条 |
| video-series-swipe | 全屏视频自动播放音量淡入 + 水平滑系列/集合卡 |
| article-magazine-cover | magazine cover 封面 + 水平卡片分页 + 块渲染排版 |
| works-glass-drawer | 右侧 40% BackdropFilter 评论 Drawer |
| works-annotation-dot | 长按光点（P1 UI）+ PageView 锁定 |

## 验收标准概要

- A1：垂直 PageView 强制分页，每次滑动精确切换一个完整作品，滑到底触发 `appendNextPage`
- A2：水平手势优先于垂直：先判定角度，< 45° 偏水平时交给子 Widget；>= 45° 才触发垂直换页
- A3：边缘 15px 无水平拖拽响应（iOS 系统返回手势不受干扰）
- A4：进入作品轨 → `worksForceDarkProvider` 激活，退出 → 恢复系统主题
- A5：全部 L4 子节点集成后，Mock 模式下三类媒体均可正确渲染
- A6：iPad 下 3 字作者名仍占 6 字槽，关注按钮位于 6 字槽后；5 字作者名应在 6 字槽内完整单行展示。
