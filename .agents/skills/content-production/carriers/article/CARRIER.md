# Article · 独立文章

本文件唯一拥有文章模板、加工与评分；取来源时只读 [sources 的对应小节](sources.md)。

## 输入与产物

- 对象身份 `posts/article/<angle>/<title>/<seq>`，target 指定实体类型/名称与 `publishAngle/publishTitle`；先查 pool，引用的 homepage 必须已发布或同批先发布，不能为补文章重复 init 已有实体。
- 候选/选择见 [candidate](schemas/candidate.schema.json)、[selection](schemas/selection.schema.json)；至少一份 page 事实底稿，可多源参考与 0/1/N 配图，不读取 image 载体候选/工作区来隐式供图。
- 唯一产物 `4.draft/draft.article.md`。frontmatter 声明真实 `title`、已注册 `tagRefs` 与 `creatorProfileId`；正文图片只写本对象合法 `assets/<fileName>` 引用，首图作封面，无图为 text_only。最终 seal/schema 拥有引用合法性，不以 lint 代替。

## 选题与加工

- article 是独立选题，不强制一实体一篇。可以从实体条目换人文、攻略、风光、摄影、自驾、徒步等角度，也可选主题条目；不复制百科全文凑数量。
- 游记事实参考优先正文约 ≥1500 字、包含行程/交通/费用/时间/贴士中 ≥3 项、近 3 年且非软广/纯图流水账；数字只作候选建议，单篇薄可多篇互补，不能把参考长度变 author 字数硬门。
- 来源文本都作 `factual_reference_only`；AI 亲笔组织表达，不搬运句段、不编造旅行亲历、路线、费用或时令。有时间敏感事实时优先公开官方公告，冲突注明或省略。
- 配图逐项切题，caption 不超过实际像素与来源；正文/封面可引用同一稳定资产，但不能给相同/近似字节换 assetId，或据此新发第二个同来源 image 作品。同 ID 不同字节/来源也拒绝；author 前用 canonical inventory 预检，publish 再验。homepage cover 不按跨 Post 重复作品判否，但资产身份仍不得漂移。

## 文章模板

1. frontmatter：`title/tagRefs/creatorProfileId`。
2. 开头：明确角度与读者要解决的问题，不空泛夸大。
3. 2–4 个有信息的小节：按路线、主题或叙事组织事实；有据的交通、时间、费用与注意事项放在需要的位置。
4. 图片可插在相关段落，0/1/N 均合法；不强制“一段一图”。
5. 结尾：有据的实用收束或观察，不伪装亲历结论。

没有事实的小节省略；长度/段落/图片数量只 advisory。`adapter.lint` 仅提示 frontmatter 和本地图片引用形状，不创作、不判断观点或最终合法性。

## 六维评分

独立 reviewer 在唯一 seal.review 输入中可记 1–5 整数；3 是明确达标，4 必须指出优于 3 的具体段落和未达 5 的不足，2 介于 1/3。分数只记录、不补零、不改变 admission；不因文字通顺默认给 4，也不为拉开分布刻意降分。关键论断缺证据等按 review 规则处理。

| 维度键 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- |
| `fact_traceability` | 关键论断在来源中找不到 | 事实可查 | 事实可查且多源互证 |
| `originality` | 沿用来源段落或句式 | 按读者问题重组事实，但主要是摘要 | 从多条有据事实建立明确比较或解释，不虚构观点依据 |
| `angle_and_title` | 无角度、标题即实体名 | 角度明确、标题点题 | 鲜明、有吸引力且不夸张 |
| `practical_density` | 路线/时间/费用/贴士全无 | 有两项具体信息 | 四类信息充分有据且可执行 |
| `readability` | 指代不清、重复或长段影响理解 | 小节顺序清楚、句子可懂，仍有赘述或跳转 | 一遍扫读可抓住问题与结论，衔接自然且无可删重复 |
| `image_match` | 配图不相关 | 切题；text_only 记 3 | 图与段落呼应，caption 有信息 |
