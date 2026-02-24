# 设计：内容类型通用框架与按类型扩展

## 1. 通用内容框架（Common Content Framework）

### 1.1 通用内容模型（已满足）

- **聚合根**：Post，唯一内容实体。
- **类型判别**：`contentType`（ContentType 枚举），所有下游按此分支。
- **通用字段**（与现有 Post 一致）：authorId、personaId、title、body、tags、mediaUrls、coverUrl、videoUrl、location、locationName、status、*Count、embedding、时间戳等。
- **约束**：标题等「文章必填、其他可选」的校验在应用层按 contentType 分支实现，不拆表。

### 1.2 通用标签体系

- **已有**：`content_tags` 中  
  - **type**：type_image / type_video / type_micro / type_article（与 ContentType 一一对应）；  
  - **topic / mood / quality / geo**：所有类型共用。
- **约定**：内容打标时 type 维与 Post.contentType 一致；各类型**扩展标签**见 §2.1，作为 content_tags 下的扩展 category，不破坏现有 taxonomy。

### 1.3 通用特征槽位（推荐/模型侧）

content_feed 场景下**所有类型共有**的特征维度，与 CandidateInput / RecommendFeature 对齐：

| 槽位 | 含义 | 来源/说明 |
|------|------|-----------|
| contentId / contentType / authorId | 标识与类型 | Post，已存在 |
| tags | 标签列表 | Post.tags（content_tags） |
| ageHours / 时间相关 | 新鲜度 | 由发布时间推导 |
| viewCount / likeCount / commentCount / shareCount | 互动计数 | Post 计数 |
| recallPath | 召回路径 | 引擎侧 |
| embedding | 向量（若启用） | Post.embedding，统一槽位 |

类型相关**扩展特征**见 §2.2，以「可选字段」或「按 contentType 填充」方式加入。

### 1.4 通用运营策略接口

- **审核**：统一 Post 状态与审核流；按 contentType 可配置不同审核规则或队列。
- **曝光与多样性**：引擎已按 ContentType 做 maxPerType；运营可配置「各类型占比/上下限」，由通用 pipeline 读取配置并按 contentType 执行。
- **降级与兜底**：content_feed 无模型/超时时回退规则（热度+多样性），逻辑与 contentType 无关。

---

## 2. 按类型扩展（Type-Specific Extensions）

### 2.1 标签扩展（可选）

在 content_tags 通用 topic/mood/quality/geo/type 基础上，可按类型增加**仅部分类型适用**的 category：

| 类型 | 扩展 category 示例 | 说明 |
|------|--------------------|------|
| micro | format_short_text / format_poll | 微趣形式（短文案/投票等） |
| image | aspect_ratio / resolution / style | 图片比例、分辨率、风格 |
| video | duration_bucket / aspect_ratio / subtitle | 时长分桶、宽高比、是否有字幕 |
| article | length_bucket / has_toc / section_count | 篇幅、目录、小节数 |

实现：在 `tag_taxonomy.yaml` 的 `content_tags` 下新增 category，注明 `applicable_content_types: [video]` 等。若当前不区分类型专属标签，可仅保留通用 content_tags。

### 2.2 特征扩展（推荐/模型）

- 在 CandidateInput / 宽表 `contentFeatures` 中保留通用槽位，增加**按 contentType 解析的扩展字段**（如 video 填 duration_sec、article 填 word_count），由特征管线根据 contentType 填充。
- 扩展特征名与类型的关系在 contracts（rec_model_service 的 fields 或 feature spec）中声明，便于端云一致。

### 2.3 运营扩展

- **审核**：按 contentType 配置不同规则（如视频先审、文章敏感词+人工抽检）。
- **曝光与占比**：运营配置「content_feed 各类型占比/上下限」，引擎多样性层已具备 typeCount，将配置与 maxPerType 等参数打通。
- **运营位与活动**：「仅视频专区」「仅文章专题」等在编排层或 feed 配置中按 contentType 过滤/加权即可。

---

## 3. content_feed 与推荐链路

- **召回**：可统一召回，候选带 contentType；或为某类型增加专用召回源，候选仍落回统一 Candidate 结构。
- **排序**：统一请求 rec-model-service scenario=content_feed，候选带 contentType 及通用/扩展特征。
- **多样性与截断**：现有逻辑已按 ContentType 做 maxPerType；运营占比可映射为 per-type limit。
- **行为与学习**：行为事件统一带 contentId/contentType，样本与特征管线按 contentType 可做类型维分析。

---

## 4. 与现有元数据对应关系

| 规范/文件 | 对应关系 |
|-----------|----------|
| `contracts/metadata/post/aggregate.yaml` | 单 Post 聚合，四种类型统一建模；描述引用本特性。 |
| `contracts/metadata/post/fields.yaml` | contentType 必填；title 等「文章必填」在应用层校验；tags 使用 content_tags。 |
| `contracts/metadata/_shared/types.yaml` | ContentType 枚举 [image, video, micro, article]。 |
| `contracts/metadata/_shared/tag_taxonomy.yaml` | content_tags 通用 + type 维；类型扩展以新 category + applicable_content_types 扩展。 |
| `contracts/metadata/_projections/recommend_feature.yaml` | 宽表通用 contentFeatures；类型扩展特征以可选/按类型填充加入。 |
| `contracts/metadata/rec_model_service/fields.yaml` | CandidateInput 已有 contentType；扩展特征在 candidates 或 context 中约定。 |
| `runtime/recommendation` | 已用 Candidate.ContentType 做多样性；扩展点：配置化 maxPerType 或 per-type limit。 |
