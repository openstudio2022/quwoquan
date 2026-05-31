# 模板库编辑总规

## 用户可见内容

- 像真实创作者发布：正文允许出现公开身份和自然口吻，例如“自驾路线整理者”“风光摄影师”“学长姐”。
- 禁止出现工程词：冷启动、批次、角色、占位、fixture、contract、推荐权重、系统内置。
- 标签和实体引用要自然嵌入正文，不允许独立“标签：”段落。
- 事实和体验分层：价格、路况、开放时间等事实必须有来源；个人感受必须用主观边界表达。

## 编辑质量

- 攻略类要给出可执行路线、成本、时间和替代方案。
- 地理深读要解释区域、地貌、季节与人的关系，避免空泛抒情。
- 图文画报要把图片作为内容主体，图注必须说明地点、季节、画面和限制。
- 点评类要说清优缺点和适合人群，禁止商业化口吻。

## 地域与季节（条件修饰维）

- 模板本身保持地域/季节无关：不在 `structure`/`mustIncludeFacts` 写死「高原、海拔、雪山、高反、沿海、海岛、沙漠、戈壁、热带、雨林、台风、潮汐」等地域专有词。
- 地域/季节的事实、风险、打包与图位，唯一来自 `_registry/catalogs/region_catalog.yaml` 与 `season_catalog.yaml`，由 CLI 在 `conditionContext` 中注入。
- 正文写到地域专有现象（如高反、潮汐、雪线）时，必须是 `conditionContext` 已授权的地域/季节，禁止脱离当前地域臆造。
- 同一受众在不同地域/季节给出不同建议：夏季避暑、冬季冰雪、雨季备伞、旺季提前预订等，依据 `season_catalog` 的 `conditionFacts/crowdNotes`。

## 推荐与作者边界

- `creatorProfileId`、`isSystemBuiltin`、`qualityScore`、`templateId`、`routingReason` 等只写入 manifest，不进入正文。
- `tagRefs`、`entityRefs`、`authorId` 必须由 CLI/模板库生成并校验，不由 Agent 临时编造。
- `conditionContext`（地域/季节）随 manifest 透出，供推荐侧切分，不以工程词形式进入正文。
