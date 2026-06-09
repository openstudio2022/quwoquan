# 文章内容 SOP（article）

## 检索策略

### 权威源（给 entity_page 补充）

- 维基百科、百度百科、搜狗百科
- 检索词：`{实体名} + {entityType}`

### 内容源（给 post）


| 平台   | 适用场景   | 检索词模板              |
| ---- | ------ | ------------------ |
| 马蜂窝  | 攻略、行程  | `{实体名} 攻略/自由行`     |
| 小红书  | 体验、打卡  | `{实体名} 旅行/拍照/推荐`   |
| 穷游   | 深度游    | `{实体名} 深度游/穷游锦囊`   |
| 携程社区 | 行程安排   | `{实体名} 游记/点评`      |
| 知乎   | 文化深度   | `{实体名} 值得去吗/有什么特色` |
| 今日头条 | 资讯、热点  | `{实体名} 旅游/最新`      |
| 微博   | 实时、UGC | `#{实体名}旅行#`        |
| 去哪儿  | 实用信息   | `{实体名} 门票/交通/住宿`   |


### 检索词生成规则

Agent 根据 entityType + tagRefs 自动推导：

- 景区：`{名} + 攻略/体验/摄影/文化/最佳季节`
- 遗址：`{名} + 历史/考古/参观指南`
- 博物馆：`{名} + 镇馆之宝/展览/导览`

## 下载规则

1. 每实体目标 40+ 篇（smoke 模式 3 篇）
2. 存储格式：`sources/{实体名}/content/source_NN.md`（含 front-matter）
3. front-matter 必须含：url, platform, title, entity, download_date, quality_score

## 质量标准


| 维度  | 阈值               |
| --- | ---------------- |
| 字数  | >= 300 字         |
| 原创性 | 非纯搬运/洗稿          |
| 信息量 | 含具体地名/价格/时间等实用信息 |
| 时效性 | 2 年内为优           |


评分 1-10，>= 6 分入选。

## 生成模板


| 模板ID          | 角度   | 必含章节               | 字数范围     |
| ------------- | ---- | ------------------ | -------- |
| 景区_攻略_article | 实用攻略 | 交通/门票/路线/最佳季节/注意事项 | 800-2000 |
| 景区_体验_article | 沉浸体验 | 初见/核心体验/意外收获/感受    | 600-1500 |
| 景区_文化_article | 文化探索 | 历史/特色/故事/当代意义      | 800-2000 |


## 写作主线（writingIntent）与题材矩阵

每篇文章必须选定且仅选定一条顶层主线（与单一门库 `_common/quality_gates.WRITING_INTENTS` 对齐，review/verify 校验结构匹配）：

| writingIntent | 读者阶段 | 正文必含结构（命中≥3 桶） |
| --- | --- | --- |
| `planning_consultation` | 计划前咨询/攻略 | 顺序/动线、交通(怎么去)、票务(门票/预约/开放时间)、取舍(建议/注意/避开) |
| `decision_experience` | 犹豫值不值得去 | 适合/不适合人群、体验价值、真实喜欢/遗憾、关键取舍 |
| `post_trip_journal` | 游后过程记录 | 时间线、现场场景、情绪转折、复盘 |

旅行题材矩阵（SOP 题材 → 顶层主线映射，供选题与下单配比）：

| 题材 | 顶层主线 | 版面组织 |
| --- | --- | --- |
| 快速攻略 quick_guide / 深度攻略 deep_guide | planning_consultation | 结论先行 → 怎么去 → 怎么玩 → 费用/预约 → 风险/替代 → 适合谁 |
| 路线计划 route_plan | planning_consultation | 路线成立理由 → 节点顺序 → 转场成本 → 每节点亮点/风险 → 删减方案 |
| 决策体验 decision_experience | decision_experience | 为什么去 → 现场过程 → 喜欢/不喜欢 → 关键取舍 → 是否值得 |
| 游后游记 post_trip_journal | post_trip_journal | 时间线 → 现场感 → 情绪转折 → 复盘 |
| 图集 photo_gallery / 视频脚本 video_script | （载体专属） | 视觉节奏/镜头顺序为主，区分镜头脚本与游记正文 |

## 语域与底稿约束（SOP 注入门库）

- **禁用语域**：户外景区/自然线路禁止博物馆语域（`看展`/`展厅`/`展陈`）；该词表由本 SOP 以 `bannedRegisterTerms` 注入 brief → writing_pack，review/verify 的 `registerMismatch` 门据此判定。
- **主底稿 baseSourceRef**：每篇选一个主底稿来源作为风格与事实锚点；其它来源只能补事实，不得成为多篇通用底稿（reducer 会标 `source_reuse_risk`）。
- **图片服务正文**：图片必须贴近所服务的节点/段落（`asset://`），不得只做封面；路线文每个核心节点应有图或显式缺图理由。
- 以上为公共机制 + 旅行垂类规则；具体 region/batch 经验只写任务 `notes.md`，不回写本 SOP。

## 图文引用

```markdown
![描述](asset://filename.jpg)                 <- 全宽
{asset://filename.jpg|wrapLeft|描述|width=45%}  <- 左环绕
{asset://filename.jpg|wrapRight|描述|width=40%} <- 右环绕
```

## 交叉引用

- 实体：`[峨眉山](/entity/峨眉山)`
- 标签：`[佛教文化](/tag/主题/佛教文化)`

## 准出 gate

- 每篇 > 600 字
- 含 >= 1 个 asset:// 引用
- 含 >= 1 个 /entity/ 引用
- 含 >= 1 个 /tag/ 引用
- manifest.sourcePaths 指向真实 source 文件
- manifest.entityRefs 全中文
- manifest.tagRefs 路径格式

