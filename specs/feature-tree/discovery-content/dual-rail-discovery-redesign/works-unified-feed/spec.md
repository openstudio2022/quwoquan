# L3 Story：作品统一内容流 (`works-unified-feed`)

> 所属能力：[`dual-rail-discovery-redesign`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)
>
> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览内容的用户，
我希望在同一内容流发现图片、视频和文章，从任意媒体预览进入对应聚焦面，
从而连续浏览并在返回后保留原内容位置与互动结果。

## 2. 范围与非目标

### In Scope

- 三类 Post 在同一内容流中的浏览、打开与返回。
- 图片集合的等高宫格预览、媒体定位及失败隔离。

### Out of Scope

- 以内容身份划分的作品轨与点滴轨；新 Surface、推荐排序算法或新契约取值。
- 聚焦面中的翻页、播放器和评论交互细节，由作品沉浸式浏览器 Story 拥有。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 同一内容流按权威目的面打开

- 图片、视频、文章在同一内容流按服务端结果呈现，不按退役身份拆分入口或重新排序。
- 点击采用出站目的面，图片与视频进入媒体聚焦面，文章进入文章阅读面；可共用浏览器壳，不将壳名称当作内容身份。
- 返回保留来源列表、cursor、当前项与已有互动结果；读取失败不改跳无关 feed，也不伪造空白成功。

<a id="req-002"></a>
### REQ-002 图片宫格稳定且任意媒体可定位打开

- 含多张图片的预览宫格中，同一行图片使用统一高度与既定裁切；加载成功或失败不改变已分配的宫格位置。
- 用户点击任一图片或视频预览，聚焦面初始定位到该 Post 的所选媒体，关闭后恢复原列表位置。
- 图片有无配文均沿图片内容路径，配文不与图片形成文章段落混排；文章内插图仍属于原文章。
- 卡片内部媒体宫格与页面级列数是不同边界；页面列数仅由 canonical SurfaceLayoutPolicy 决定。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/types.yaml#ListItemPresentationEnvelope`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/post_read_presentation.yaml#PostReadPresentation`
- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 混排流打开与返回不中断上下文

- GIVEN 已加载的同一列表包含图片、视频和文章，用户停留在非首项且存在下一页 cursor。
- WHEN 用户分别打开各类内容、完成一次赞操作并返回列表。
- THEN 每次均打开出站声明的目的面，返回后保持原项、列表位置、cursor 与已确认的赞状态，不出现点滴轨或媒体嗅探分流。
- AND 当前项读取失败时保留返回与 canonical 恢复动作，其他已加载项仍可浏览。

<a id="gwt-002"></a>
### GWT-002 等高宫格与所选媒体定位

- GIVEN 图片内容包含横图、竖图与一张加载失败图片，并分别有配文和无配文样本。
- WHEN 用户观察宫格加载过程、点击第二张图片进入聚焦面，再关闭返回。
- THEN 同行预览保持等高与稳定位置，失败仅影响对应格；初始聚焦第二张图片且返回恢复原列表位置。
- AND 配文保持独立区域，不插入媒体序列，不因配文或加载结果变成文章。

## 6. 依赖

- 前置要求：[`dual-rail-discovery-redesign`](../spec.md) 的范围、要求与 SIT。
- 四轴定义：[`content-type-framework`](../../content-type-framework/spec.md)。
- 聚焦面交接：[`works-immersive-viewer`](../works-immersive-viewer/spec.md)。
- 父级设计：[L2 DEC-001](../design.md#dec-001)。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 统一内容流与宫格交接验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺当前单轨混排流的真实导航、互动回流、等高宫格与所选媒体定位证据；旧轨入口退役不等于交互已实现。
- 完成判定：`GWT-001`、`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
