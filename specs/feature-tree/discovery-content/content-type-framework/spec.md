# L2 特性：content-type-framework（内容类型通用框架）

## 功能说明

- **定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景。
- **结论**：content_feed 应当做媒体类型区分（标签、特征、运营可差异化），但基于**统一 Post 聚合 + contentType 判别**，通用框架保证共性，各类型在标签/特征/运营上按需扩展。
- **范围**：内容模型（Post）、标签体系（content_tags）、推荐特征槽位、content_feed 召回/排序/多样性与运营策略的约定；与 metadata（post、_shared/types、tag_taxonomy）、recommend_feature、rec_model_service、runtime/recommendation 对齐。

## 约束

- 不新增独立内容实体表；Post 保持单聚合，contentType 为必填枚举。
- 类型扩展通过 contentType 分支与可选扩展字段/配置实现，不破坏通用契约。
- 设计细节与元数据对应关系见 [design.md](design.md)；开发任务见 [tasks.md](tasks.md)。

## 验收标准（概要）

- A1：metadata 与设计约定一致（Post、ContentType、content_tags、推荐特征）。
- A7：契约与 OpenAPI/metadata 一致；Post 聚合描述引用本特性。
- A8：涉及 content_feed 的测试覆盖 contentType 与多样性逻辑。
