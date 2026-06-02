# L3 子特性：micro-social-feed（既有 moment wire）

## 功能说明
点滴/微内容频道采用高效率社交信息流：明亮主题，自适应图片宫格（1/2/3-9 图），文字超 5 行截断就地展开，视频内嵌卡片入焦自动播放，支持单列/双列展示策略。

## 范围
- `HomeMultiFormFeed` / `DiscoveryMicroPostCard`（单列关系流 + 双列发现流策略）
- `moment-image-grid`（L4）：1/2/3-9 图自适应宫格 + 轻量图片浏览器
- `moment-text-expand`（L4）：5 行截断就地展开
- `moment-video-autoplay`（L4）：内嵌卡片入焦自动播放

## 适用范围与约束
- **适用**：点滴/微内容频道（`MicroPostDto`，`category=moment` 仅作为既有 wire identity）
- **不适用**：作品频道；不使用 `worksForceDarkProvider`（微趣跟随系统主题）
- **约束**：展示策略由 `HomeChannelConfig` 驱动；`MicroPostDto.body` 为空时仅显示媒体

## 子节点

| L4 节点 | 职责 |
|---------|------|
| moment-image-grid | 自适应宫格布局 + 轻量图片浏览器 |
| moment-text-expand | 5 行截断 + 就地展开 |
| moment-video-autoplay | 内嵌卡片视频入焦自动播放 |

## 验收标准概要
- A1：MicroPostDto 正确渲染（纯文、图、视频各类型）
- A2：单列/双列切换按钮有效，双列显示 `SliverMasonryGrid`，图片 8px 圆角
- A3：子节点各自验收通过（image-grid / text-expand / video-autoplay）
