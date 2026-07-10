# quwoquan_data — 数据工程

Agent 驱动的语义数据加工管线，从地理实体发现到内容生产发布。

## 核心原则

- **Agent 语义闭环**：所有语义处理由 Cursor Agent 在命令会话中完成，脚本只负责 IO 准备和输出校验。
- **标准三段式**：每个步骤遵循 `[CLI prepare]` → `[Agent semantic]` → `[CLI validate + gate]`。
- **任务控制面单一真相源**：任务实例、家族 preset/recipe、共享运行 profile 统一在
  `control_plane/`（`tasks/` + `families/` + `_shared/`）；默认值只由 `task.yaml.presetRef` 决定，
  运行编排只走 `qwq-data task run-recipe`（详见 [`docs/pipeline_directory_layout_spec.md`](docs/pipeline_directory_layout_spec.md) §0.5）。
- **任务/批次隔离**：运行期输出统一落 `QWQ_OUTPUT_ROOT`（默认 `.qwq_output/`），按批次三轴
  `data/local/runtime/{phase}/{contentType}/{supplyMode}/{intentLabel}-{taskHash}__{batch}/` 组织，支持并行。
- **中文优先**：所有标签、实体、文章的 ID 和目录名使用中文，英文作为扩展字段。
- **轻量 schema**：标签本体只含稳定语义字段，动态规则外置到 `tag_policy.yaml` 和 `tag_runtime/`。

## CLI-first + Skill 范式（强制）

所有内容生产/冷启动/校验能力统一经 `qwq-data` 暴露，禁止为单场景新写孤立可执行脚本。完整说明见 [`.cursor/skills/quwoquan-data-content/SKILL.md`](../.cursor/skills/quwoquan-data-content/SKILL.md)。

```
python3 quwoquan_data/scripts/cli.py <command> ...
```

| 命令 | 作用 |
|---|---|
| `plan` | 内容指令 → compose_brief（叙事契约 / imagePlan / imagePolicy） |
| `download` | 多平台素材获取 + 来源质量评分 + 匿名化 |
| `site-supply` | 网站维度前半段供给线：site frontier/candidate/score/map/rollup packet 与站点准出门 |
| `produce --stage compose-brief` | 准备阶段：analyze + 选图 → 落写作契约 `writing_pack.json` + `prompt.md` + 占位（**不拼正文**） |
| `produce --stage review` | 校验阶段：读会话模型写回的 `article.md` → 三道门 + 图片/游记感密度门 → 裁决 |
| `produce --stage review --materialize` | review 通过后落地为 post package（仅 `generator=agent`；含账本/实体 sidecar） |
| `media check-images` | 真实 CV 图片门：人脸/水印/OCR 文叠/感知去重 |
| `annotate` | Human-in-loop 标注：发布前对账本图片/事实/文章下人判定/打分/置发布态/记再加工 |
| `ship` | 一键发布：promote→重建索引→按环境采样写 sample bundle→(可选)调用服务侧 importer 灌库 |
| `verify` | 收紧范围校验 post package（schema + 语义 + 图片 + 三道门） |
| `verify scale-readiness` | 指令/地域维度放量准出门：百级目标满足率、source-ready 容量、Cursor startup、TokenLedger、release/import 与漏斗报告 |
| `verify site-scale-readiness` | 网站维度放量准出门：trial 验结构/吞吐/账本，commercial 额外强制 release/import/搜索推荐证据 |
| `template lint` | 模板蓝图门禁（route 叙事契约 / gallery imagePolicy） |

> **Human-in-loop + 发布门**：review 产出每图/事实/文章的 agent 判定+打分写账本（`produce/review/ledger/{ref}.json`）；
> `annotate` 下人判定；`promote`/`ship` 据账本过滤（discard 图剔除、无主页实体过滤、fix 项跳过）。详见
> [`docs/content_pipeline_spec.md`](docs/content_pipeline_spec.md)。
> 目录与资产证据链唯一真相源见 [`docs/pipeline_directory_layout_spec.md`](docs/pipeline_directory_layout_spec.md)。
> **一键发布到运行库**：`publish/` 单一主线（prod 全量），`ship` 按 `quwoquan_ops/environments/content_sampling_manifest.yaml`
> 确定性采样出 `publish/sample_bundles/{env}.json`；服务侧
> `quwoquan_service/services/content-service/cmd/import` 消费它把 posts/entities 幂等灌入 mongo。

> **正文只能由会话模型创作**：`compose` 已删除全部脚本拼正文。compose-brief 产出写作契约后，由 Agent 按 `prompt.md` 创作正文写回 `batches/<batch>/posts/{contentType}/{angle}/{title}/{seq}/4.draft/draft.article.md`（`generator=agent`），再 review。
> **三道真实性门**（review + verify 强制）：generator 出处门、模板指纹门、事实可回溯门。

**硬约束**：新能力 = `<command>/handler.py`（`register_parser` + `handle_*`）+ 可选 `gate.py`，复用逻辑沉到 `_common/`；`SKILL.md` 只暴露 CLI；禁止在 `scripts/**` 新增可直跑（`__main__`）业务入口（旧脚本只能薄壳委托）。门禁：`python3 quwoquan_data/scripts/verify/verify_cli_first.py`（基线 `cli_first_allowlist.txt`）+ `bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh`。

Cursor SDK 环境门：`python3 quwoquan_data/scripts/cli.py env ready --json` 默认执行真实 `Agent.prompt` startup probe；只通过 key/import/network 探测不代表可进入百级 author-runner。需要离线检查时可显式加 `--no-cursor-startup`，但该报告不能作为放量准入证据。

## 标签体系设计

### 四分组架构（Topic-Audience-Format-Entity）

对标 TikTok、Facebook、小红书等主流平台，采用四大顶级分组：


| 分组           | 语义边界                                                        | 维度数 | 标签数   | 占比    |
| ------------ | ----------------------------------------------------------- | --- | ----- | ----- |
| **Topic**    | 32 垂类（含美食餐饮 9 维 + 住宿 8 维 + 旅行 7 维 + 摄影 28 项 + 教育成长 12 子域 74 项）+ 地理(3509) + 时间 + 场景 + 事件 / 话题 | 36  | 4330  | 84.7% |
| **Audience** | 用户画像 + 创作者 + 圈子（含校园圈 6 项）                                   | 3   | 233   | 4.6% |
| **Format**   | 内容载体/角度(含经验分享 5 项)/表现手法(含摄影技法+构图手法)/视觉风格/互动玩法/商业形式        | 6   | 248   | 4.9% |
| **Entity**   | 地点(含城市)/机构(含学校 35 类型标签)/活动/人物/品牌(含摄影器材)/作品(含摄影集/展)/商品/生物/交通工具 | 9   | 300   | 5.9% |


总计 **5111** 标签节点（地理 3509，非地理 1602）。地理维度占比高是因为中国三级行政区（34 省 + 337 市 + 3056 区县）全量覆盖。

### 层级结构

- 每个层级 3-100 个节点，层深 2-7 层（行政区最深 7 层）
- 标签 ID 即目录路径，如 `Topic/地理/行政区/中国/四川省/成都市`
- 兄弟节点互斥正交，父子为语义包含关系

### Topic 分组详览


| 类型   | 维度名             | 内容                                     | 标签数 |
| ---- | --------------- | -------------------------------------- | --- |
| 垂类   | **美食餐饮**        | 9 正交子维度：菜系(34)/品类(18)/饮品(11)/就餐时段(8)/用餐场合(9)/饮食特征(13)/风味口味(10)/认证评级(16)/特色食材(11) | **150** |
| 垂类   | **住宿**          | 8 正交子维度：业态(25含星级+度假短租+特色)/价位(5)/主题(13)/设施(15)/房型(12)/区位(13)/认证(12)/预订(7) | **105** |
| 垂类   | 旅行              | 7 子维度：旅行主题(14)/玩法(22)/出行方式(13)/行程形态(6)/旅行时长(6)/住宿话题(15)/旅行筹备(9) | 86  |
| 垂类   | 自然风光            | 审美天象景观（星空/极光/彩林/花海/云海/日出日落/雾凇/雪景/候鸟迁徙） | 11  |
| 垂类   | **摄影**           | 22 题材社区（风光/人像/街头/纪实/建筑/野生动物/微距/美食/静物/人文/时尚/运动/婚礼/商业/旅行/水下/航拍/夜景星空/抽象/艺术/新闻/花卉）+ 6 知识类（教程/器材评测/后期技巧/赛事/摄影史/手机摄影） | 29  |
| 垂类   | 运动              | 休闲健身/户外探险/竞技体育/极限运动/电竞（5 子类正交合并）       | 35  |
| 垂类   | 健康养生            | 中医养生/营养学/心理健康（含 MBTI）/睡眠/理疗等           | 29  |
| 垂类   | 历史文化            | 古镇/宗教/考古/红色/帝王/三国/丝路/茶酒/建筑/文物         | 14  |
| 垂类   | 时尚穿搭/美妆护肤       | 穿搭/护肤/彩妆/香水/风格（各 15 项）                | 30  |
| 垂类   | 其他 22 个垂类       | 数码/汽车/家居/教育/职场/亲子/情感/影视/游戏/...        | 各 5-13 |
| 垂类   | **教育成长**        | 12 子域：基础教育(5)/校园生活(9)/学业学术(7)/升学深造(5)/考试认证(8)/实习求职(4)/留学海外(5)/语言学习(5)/学习方法(4)/成人教育(4)/职业技能(2)/阅读写作(3) | **74** |
| 结构维度 | 场景              | 情绪场景/生活场景(含校园场景)/社交场景（3 类）              | 20  |
| 结构维度 | 事件 / 话题         | 事件：新闻事件/历史事件/社会事件/赛事事件/地区事件/政策事件；话题：社会议题/公共议题/文娱话题/地区话题/科技话题/教育议题 | 33  |
| 结构维度 | 时间              | 四季/24 节气/法定节假日/传统节日/纪念日/商业节日/生肖年       | 70  |
| 结构维度 | 地理              | 行政区（中国 34 省 337 市 3056 区县 + 泰国 7 府 + 欧洲 11 国）+ 地形地貌 + 区域（5 大洲 24 子区） | 3566 |


### 美食餐饮专项设计（9 维正交）

美食餐饮是本地生活、旅行、出差、出行的核心消费场景。专项设计对标美团、大众点评、饿了么、猫途鹰、米其林、黑珍珠 6 大平台，采用 **菜系×品类×饮品×时段×场合×特征×口味×评级×食材** 九维正交结构：

```
Topic/美食餐饮/
├── 菜系/         → 中国菜系(19) + 国际菜系(15) = 34
├── 品类/         → 火锅/烧烤/串串/面食/小吃/烘焙/甜品/… = 18
├── 饮品/         → 咖啡/茶饮/奶茶/葡萄酒/白酒/啤酒/鸡尾酒/… = 11
├── 就餐时段/      → 早餐/早茶/午餐/下午茶/晚餐/夜宵/深夜/24h = 8
├── 用餐场合/      → 约会/家庭/商务/朋友/独食/亲子/宴席/节日/独酌 = 9
├── 饮食特征/      → 纯素/清真/低GI/生酮/无麸质/孕妇餐/儿童餐/… = 13
├── 风味口味/      → 麻辣/酸辣/香辣/清淡/咸鲜/酸甜/烟熏/… = 10
├── 认证评级/      → 米其林(5)/黑珍珠(3)/必吃榜/老字号/非遗/GI = 16
└── 特色食材/      → 海鲜/牛肉/菌菇/川味食材/应季食材/有机/… = 11
```

#### 菜系 / 品类 / 业态 三正交防混表

| | Topic/美食餐饮/菜系 | Topic/美食餐饮/品类 | Entity/地点/餐厅 |
|---|---|---|---|
| **回答的问题** | 什么文化流派？ | 什么食物形态？ | 什么经营实体？ |
| **示例** | 川菜、粤菜、日料 | 火锅、面食、烧烤 | 火锅店、面馆、烧烤店 |
| **命名规则** | 纯流派名 | 纯食物名 | 带"店/馆/吧"后缀 |
| **验证规则** | R11 不得与餐厅重名 | R12 不得与餐厅同名 | R11 不得与菜系重名 |

### 住宿专项设计（8 维正交 + 三层架构）

住宿是旅行、出差、出行的核心场景。专项设计对标携程、猫途鹰、Booking.com、Vrbo、马蜂窝、去哪儿 6 大平台 + 米其林之钥 + GB/T 14308，采用 **Topic/住宿（标签体系）+ Entity/地点/住宿（实体骨架）+ Topic/旅行/住宿（话题角度）** 三层正交架构：

```
Topic/住宿/                    → 内容标签体系（讲住宿的什么维度）
├── 业态/                      → 星级酒店(5)/连锁/商务/度假/精品/设计/公寓/青旅/客栈/民宿/
│   │                            农家乐/营地/胶囊/度假短租(3)/特色住宿(6) = 25
├── 价位档次/                   → 经济/中端/高端/奢华/超奢华 = 5
├── 主题/                      → 亲子/情侣/宠物/温泉/滑雪/亲水/康养/商务/文化/田园/自驾/女性/单人 = 13
├── 设施服务/                   → 泳池/健身/SPA/餐厅/酒吧/停车/洗衣/接送/儿童/无障碍/… = 15
├── 房型/                      → 单人/双床/大床/家庭/亲子/套房/复式/Loft/海景/山景/园景/城景 = 12
├── 区位/                      → 市中心/机场/高铁/地铁/景区/商圈/CBD/滨海/山中/… = 13
├── 认证评级/                   → 米其林之钥(3)/携程必住/金枕头/Travelers Choice/… = 12
└── 预订特征/                   → 即时确认/免费取消/价保/含早/含三餐/限时/会员 = 7

Entity/地点/住宿/              → 实体类型骨架（地方是什么住宿）
├── 酒店/民宿/客栈/青旅/度假村/农家乐/营地/酒店式公寓/胶囊酒店/特色住宿 = 10

Topic/旅行/住宿/               → 话题角度（旅行中怎么讲住宿）
├── 住宿攻略/酒店体验/民宿体验/商旅/出差/川西/高原/度假/温泉/亲子/… = 15
```

三层正交边界：
- `Topic/住宿` 回答"内容标签是什么住宿维度"（8 维标签属性）
- `Entity/地点/住宿` 回答"实体是什么住宿业态"（10 类扁平骨架）
- `Topic/旅行/住宿` 回答"旅行内容讲住宿的哪个话题"（15 话题角度）

### Audience 分组详览


| 维度  | 内容                                                 | 标签数 |
| --- | -------------------------------------------------- | --- |
| 用户  | 性别/代际/国籍/族群/语言/教育/职业/收入/婚姻家庭/消费特征/生活阶段/作息习惯/性格特质/健康状况/数字使用习惯/创作行为（16 子维度） | 191 |
| 创作者 | 粉丝量级/创作领域宽度/平台属性/创作风格                              | 22  |
| 圈子  | 地缘圈/官方圈/付费圈/兴趣聚合圈/校园圈(母校/院系/年级/校友/职场互助/备考)（5 种组织形式）     | 21  |


### Format 分组详览


| 维度   | 内容                                                   | 标签数 |
| ---- | ---------------------------------------------------- | --- |
| 内容载体 | 文章/视频(短/中/长/直播回放)/图文/直播/音频/问答/行程单（7 大媒介）             | 47  |
| 内容角度 | 攻略(含新生攻略/选课攻略)/体验/测评(含校园评测)/探店/种草/拔草/避雷/盘点/教程/科普/观点/资讯/叙事/日记(含校园日记)/经验分享(考研/保研/留学/求职/校招)（含酒店探店/茶馆探店/Bistro 探店等 106 项） | 106 |
| 表现手法 | 表演形态/剪辑形态/运镜/特效/**摄影技法**(14项:长曝光/多重曝光/光绘/延时/全景接片/高速抓拍/追焦/星轨/景深合成/红外/倒影/剪影/散景/堆栈)/**构图手法**(9项:三分法/对称/引导线/框架/留白/对角线/前景纵深/俯拍/仰拍) | 57  |
| 视觉风格 | 视觉调性(15项含**黑白/纪实风/色彩浓郁**)/后期风格(6项)                   | 23  |
| 互动玩法 | 话题讨论/抽奖/征集/连麦/接力/合辑/投票互动                             | 7   |
| 商业形式 | 带货/品牌合作/广告/赞助/团购/效果广告/内容植入/联名                        | 8   |


### Entity 分组详览


| 维度   | 说明                                                        | 标签数 |
| ---- | --------------------------------------------------------- | --- |
| 地点   | 景区(8)/遗址(3)/古镇(3)/餐厅(22)/住宿(10)/城市/博物馆/公园/宗教/温泉/书店/健身/运动场馆/购物/打卡地/美食街/自然景观(6)/主题乐园(6)/交通枢纽(7)/演艺场馆(6) | 91  |
| 机构   | 学校(含 35 类型标签：学段 13 + 高校层次 8 + 学科类型 12 + 办学性质 2)/公司/研究所/医院/社团/政府/媒体/金融机构/国际组织 | 44  |
| 活动   | 赛事/节庆/展会/演出/学术会议/公益活动                                    | 6   |
| 人物   | 历史人物/政治人物/演艺人物/体育人物/商业人物等                                | 31  |
| 品牌   | 汽车/餐饮/科技/运动/美妆/住宿/**摄影器材**(佳能/尼康/索尼/富士/哈苏/徕卡/适马/腾龙/大疆等 12 项)等 | 39  |
| 作品   | 影视/音乐/文学/游戏/数码产品/软件/艺术品/设计/**摄影集/摄影展**                  | 10  |
| 商品   | 物理品类 + 画像维度（类目/价位/适用受众/适用场景/销售形式）                        | 58  |
| 生物   | 哺乳/鸟类/爬行/两栖/昆虫/鱼类/植物/菌类/海洋无脊椎/濒危/外来入侵/观赏/经济/药用         | 15  |
| 交通工具 | 飞行器/轨道/船舶/公路/特种/新能源                                      | 6   |


### 正交性设计原则

1. **Topic vs Entity**：Topic 回答"内容讲什么"（审美现象、文化流派、科学分类），Entity 回答"对象是什么"（具体实例类型骨架）
2. **菜系 vs 品类 vs 业态**：三维严格正交——菜系（川菜）= 文化流派，品类（火锅）= 食物形态，业态（火锅店）= 经营实体。R11/R12 门禁强制检查
3. **住宿三层正交**：Topic/住宿（标签属性 8 维）⊥ Entity/地点/住宿（实体骨架 10 类）⊥ Topic/旅行/住宿（话题角度 15 项）
4. **自然风光 vs 地形地貌 vs 自然景观**：
   - `Topic/自然风光`：审美天象（星空/极光/云海）——内容主题
   - `Topic/地理/地形地貌`：地理科学分类（山地/平原/峡谷）——学术分类
   - `Entity/地点/自然景观`：具体自然地物的类型标签——实体归类
5. **时间唯一真相源**：所有节日/季节信息只在 `Topic/时间/` 下定义，事件 / 话题和场景不重复
6. **无显式关系**：标签间不维护引用关系文件，通过 tagRef 共现度隐式生成关联
7. **旅行七维度正交**：旅行主题⊥玩法⊥出行方式⊥行程形态⊥旅行时长⊥住宿话题⊥旅行筹备
8. **区域 vs 行政区**：Topic/地理/区域（跨国文化聚合）⊥ Topic/地理/行政区（行政管辖区划）
10. **行政区 vs 城市实体**：
    - `Topic/地理/行政区/中国/四川省/成都市` — 行政归属标签，回答"在哪"
    - `Entity/地点/城市` — 扁平叶子类型标签（无子类型），回答"是什么类型的地点"
    - `entities/地点/城市/成都/` — 实体实例，通过 geoTagRef 关联行政区标签
    - 城市属性（省会/旅游/历史名城等）通过 tagRefs 多标签描述，不在 Entity 类型骨架中分子类
9. **摄影四维正交**：
   - `Topic/摄影/风光摄影`：内容属于什么摄影社区/流派（What community）
   - `Format/表现手法/摄影技法/长曝光`：技术上怎么拍的（How technically）
   - `Format/表现手法/构图手法/三分法`：画面怎么组织的（How composed）
   - `Format/视觉风格/视觉调性/黑白`：视觉上看起来什么样（How it looks）

### 本轮重构冻结口径（rename-migrate）

> 详细决策矩阵见 [`docs/backfill_and_index_rebuild.md`](docs/backfill_and_index_rebuild.md)。

- `Topic/摄影` 冻结为 `题材社区 / 知识方法 / 活动赛事` 三条主线；`后期技巧`、`摄影史`、`器材评测` 归知识方法，`静物摄影`、`儿童摄影` 等补回题材轴。
- `Topic/时尚穿搭` 与 `Topic/美妆护肤` 分开冻结：穿搭负责风格 / 场景 / 单品 / 搭配方法，美妆护肤负责护肤 / 彩妆 / 造型修饰 / 工具与产品。
- `Topic/科技`、`Topic/数码`、`Topic/游戏电竞`、`Topic/运动/电竞赛事` 分轴冻结：科技看产业趋势，数码看消费电子与器材，游戏电竞看玩法与攻略，运动/电竞赛事看竞赛与联赛。
- `Topic/住宿` 冻结为 `住宿形态 / 档次等级 / 主题 / 设施服务 / 房型 / 区位 / 认证评级 / 预订特征`；`闪订` 统一改名为 `即时确认`，平台名只进 alias。
- `Topic/人文社科` 与 `Topic/历史文化` 分开冻结：前者承接城市观察、社会纪实、民俗风物、旅行人文；后者承接文明史、遗产遗迹、文博考古、地方史志。
- `Topic/事件` 与 `Topic/话题` 作为稳定分类骨架，日更热词、热搜、挑战、新闻事件实例统一走 runtime 实例层，不直接占静态标签位；详细模型见 [`docs/dynamic_topic_event_model.md`](docs/dynamic_topic_event_model.md)。

### 标准 tagRefs 示范

**餐饮实体示例（陈麻婆豆腐总店）：**

```json
{
  "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市",
  "tagRefs": [
    "Entity/地点/餐厅/中式正餐",
    "Topic/美食餐饮/菜系/中国菜系/川菜",
    "Topic/美食餐饮/品类/小吃",
    "Topic/美食餐饮/风味口味/麻辣",
    "Topic/美食餐饮/认证评级/中华老字号",
    "Format/内容角度/探店"
  ]
}
```

**住宿实体示例（青城山六善酒店）：**

```json
{
  "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市",
  "tagRefs": [
    "Entity/地点/住宿/度假村",
    "Topic/住宿/价位档次/奢华型",
    "Topic/住宿/主题/康养主题",
    "Topic/住宿/主题/温泉主题",
    "Topic/住宿/设施服务/SPA",
    "Topic/住宿/设施服务/泳池",
    "Topic/住宿/设施服务/停车场",
    "Topic/住宿/业态/度假短租/整租别墅"
  ],
  "sourceRefs": ["https://www.sixsenses.com/en/resorts/qing-cheng-mountain/"]
}
```

**景区 Post 示例（峨眉山攻略）：**

```json
{
  "entityRefs": ["地点/景区/峨眉山"],
  "tagRefs": [
    "Topic/旅行/旅行主题/雪山探险",
    "Topic/旅行/玩法/观光游览",
    "Topic/旅行/出行方式/自驾",
    "Topic/旅行/行程形态/自由行",
    "Topic/旅行/旅行时长/3-5日中线",
    "Format/内容角度/攻略",
    "Entity/地点/景区"
  ]
}
```

**摄影 Post 示例（贡嘎雪山日照金山拍摄攻略）：**

```json
{
  "entityRefs": ["地点/景区/海螺沟"],
  "tagRefs": [
    "Topic/自然风光",
    "Topic/旅行",
    "Topic/摄影/风光摄影",
    "Topic/摄影/夜景星空",
    "Format/内容角度/攻略",
    "Format/内容载体/文章",
    "Format/表现手法/摄影技法/长曝光",
    "Format/表现手法/摄影技法/堆栈",
    "Format/表现手法/构图手法/三分法",
    "Format/视觉风格/视觉调性/电影感",
    "Entity/地点/景区"
  ]
}
```

### 轻量 Schema（_definition.json）

```json
{
  "label": "川菜",
  "labelEn": "Sichuan Cuisine",
  "description": "以麻辣著称的四川菜系",
  "aliases": ["四川菜", "蜀菜"],
  "sourceRefs": ["manual:2026-05"],
  "createdAt": "2026-05-15T00:00:00+08:00",
  "updatedAt": "2026-05-15T00:00:00+08:00"
}
```

- `additionalProperties: false`：严格禁止扩展字段
- `tagId` 由目录路径推导，不写入文件
- 动态属性外置：热点热度 → `tag_runtime/topic_hotness.ndjson`，推荐权重 → `tag_runtime/tag_weight_overlay.ndjson`

### 外置策略（tag_policy.yaml）

- **blocking 策略**：`tagref_resolvable`、`post_angle_dir_match`
- **warning 策略**：`path_policy_hints`、`group_capacity_balance`

### 业界对标

详见 [`docs/food_lodging_benchmark.md`](docs/food_lodging_benchmark.md)，对标 10 个平台 + 4 个评级体系：

| 平台 | 核心借鉴 |
|------|---------|
| 美团/大众点评 | 菜系/品类筛选、必吃榜/黑珍珠认证 |
| 饿了么 | 外卖品类/时段/口味筛选 |
| 猫途鹰 | Cuisine/Dietary/Travelers' Choice |
| 携程/去哪儿 | 星级/品牌/位置/设施/金枕头 |
| Booking.com | 24 种 PropertyType/Facilities |
| Vrbo | 度假短租分类/Amenities |
| 马蜂窝 | 旅行攻略/住宿话题 |
| 米其林指南 | 星级(1-3)/必比登/餐盘/之钥(1-3) |

## 工程验证能力

### Schema 校验（5 个 JSON Schema）


| 文件                                   | 校验对象                              |
| ------------------------------------ | --------------------------------- |
| `schema/tag/_group.schema.json`      | 四分组定义                             |
| `schema/tag/_dimension.schema.json`  | 维度元数据                             |
| `schema/tag/_definition.schema.json` | 标签节点（additionalProperties: false） |
| `schema/tag/_taxonomy.schema.json`   | 全局分类体系快照                          |
| `schema/tag/tag_ref.schema.json`     | tagRef 字符串格式                      |


### 语义验证规则（scripts/verify/verify_tag_tree.py R1-R12）


| 规则  | 检查内容                                                     | 级别 |
| --- | -------------------------------------------------------- | --- |
| R1  | 四分组 _group.json 存在                                       | BLOCK |
| R2  | 必需维度存在 + Topic 垂类/旅行 7 维/美食 9 维/住宿 8 维 完备 | BLOCK |
| R3  | _definition.json 必填字段（label/labelEn/createdAt/updatedAt） | BLOCK |
| R4  | 兄弟节点互斥正交（子串重叠检测，短名≥⌈长名/2⌉才告警）                            | WARN |
| R5  | 多省行政区抽样完备（34 省级 + 10 省地级城市抽样）                            | BLOCK |
| R6  | Entity 深度≤4                                              | WARN |
| R7  | 总量≥4800 / 非地理≥1000                                       | BLOCK |
| R8  | 禁止字段检查                                                   | BLOCK |
| R9  | 容量均衡（每维度≥3 子节点，跳过已知稀疏维度）                                  | WARN |
| R10 | label 与目录名一致                                             | BLOCK |
| **R11** | **Entity/地点/餐厅 业态不得与 Topic/美食餐饮/菜系 重名** | **BLOCK** |
| **R12** | **Topic/美食餐饮/品类 与 Entity/地点/餐厅 不得完全同名（Entity 须带店/馆/吧后缀）** | **WARN** |


### 门禁检查（G1-G29，统一入口 `scripts/verify/verify_quwoquan_data.sh`，原 gate_e2e.py 已 CLI-first 拆分）


| 门禁  | 检查内容                       | 级别    |
| --- | -------------------------- | ----- |
| G1  | 标签数量+字段+禁止字段               | BLOCK |
| G11 | Entity 领域与类型完整（餐厅≥15，住宿≥8）  | BLOCK |
| G12 | 四分组维度完备（含 Topic/住宿）         | BLOCK |
| G13 | 行政区完备（34 省级 + 多省地级抽样）       | BLOCK |
| G14 | 必填字段+禁止字段                  | BLOCK |
| G15 | 标签总量≥4800，非地理≥1000         | BLOCK |
| G16 | _definition.json schema 违规 | BLOCK |
| G17 | tagRef 100% 可解析            | BLOCK |
| G18 | 路径策略提示                     | WARN  |
| G19 | post 内容角度目录一致性             | BLOCK |
| G20 | 反向索引/共现覆盖                  | WARN  |
| G21 | label 与目录名同步               | BLOCK |
| G22 | refHint 国籍→行政区对应           | WARN  |
| G23 | 分组容量均衡（Topic≤45）           | WARN  |
| G24 | tagRefs 四分组前缀合法            | BLOCK |
| G25 | 旅行类实体 post 含 Topic/旅行/* tagRef | BLOCK |
| G26 | entity geoTagRef 指向 Topic/地理/行政区/ | BLOCK |
| G27 | 已知互斥标签对                    | WARN  |
| G28 | 实体/帖子 lookup 索引完整          | BLOCK |
| G29 | 校园标签体系专项                  | BLOCK |


### 回填与索引重建

批量回填实体或 posts 后，先重建 `publish/index/`（去版本化单一主线，无 `v{N}`），再跑总门禁与专项门禁：

更完整的步骤和语义边界说明见 `docs/backfill_and_index_rebuild.md`。

```bash
python3 scripts/publish_ops/build_publish_lookup_indexes.py
# gate_e2e.py 已按 CLI-first 重构拆分到各命令 gate.py + 统一入口：
bash scripts/verify/verify_quwoquan_data.sh
python3 verticals/campus/verify/verify_campus_taxonomy.py
```


## 四大应用场景

### 场景1：数据加工


| 脚本                           | 功能                       |
| ---------------------------- | ------------------------ |
| `scripts/bootstrap/taxonomy/bootstrap_tags.py`          | 生成四分组完整标签树（31 垂类 + 4 结构维度） |
| `scripts/bootstrap/taxonomy/bootstrap_admin_regions.py` | 生成行政区标签（数据源：`reference/admin_regions/pca.json`，中国 34 省 337 市 3056 区县 + 泰国 + 欧洲） |
| `scripts/bootstrap/taxonomy/bootstrap_geo_landmarks.py` | 生成地形地貌科学分类标签             |
| `scripts/bootstrap/taxonomy/bootstrap_event_topics.py`  | 生成事件 / 话题标签             |
| `verticals/campus/scripts/bootstrap_school_entities.py` | 从 seed catalog 批量生成学校实体三件套（全国高校 + 北京上海中学/幼儿园） |
| `verticals/campus/scripts/bootstrap_school_posts.py`  | 分层生成学校 Posts（全量索引帖 + 重点深内容） |
| `scripts/verify/verify_tag_tree.py`         | R1-R12 正交性/完整性/命名/容量验证   |
| `verticals/campus/verify/verify_campus_taxonomy.py`  | C1-C10 校园标签专项正交门禁        |
| `verticals/campus/verify/verify_school_catalog_coverage.py` | S1-S6 学校数据源覆盖率验证    |
| `verticals/campus/verify/verify_school_entities.py`  | E1-E7 学校实体完整性验证          |
| `verticals/campus/verify/verify_school_posts.py`     | P1-P4 学校 Posts 完整性验证     |
| `scripts/publish_ops/build_publish_lookup_indexes.py` | 基于 publish/v1 实体与 posts 生成 lookup 索引 |
| `scripts/tags/tag_stats.py`               | 按四分组统计标签数量、深度、叶枝比        |
| `scripts/tags/tag_graph.py`               | 基于 tagRef 共现度生成关系图谱      |
| `verify/verify_quwoquan_data.sh` | G1-G29 端到端门禁统一入口（原 `gate_e2e.py` CLI-first 拆分） |


### 场景2-4：内容创作/推荐搜索/关系图谱

通过 Tag Service API 支持，详见 `quwoquan_service/contracts/metadata/tag/service.yaml`。

平台级内容供给的 Agent 组织模型、AI 自主创作边界、角色职责、交接契约和质量门，见 `docs/agent_content_supply_operating_model.md`。

日产十万级商用化总蓝图（三个关键决策、三层 Agent 协同、作品 vs 随记准入、两种工作流、标签实体治理、任务清单与验收标准），见 [`docs/content_supply_commercialization_plan.md`](docs/content_supply_commercialization_plan.md)。两种工作流的百 / 千 / 万级端到端验证提示词：站点维度（携程 / Pinterest）见 [`docs/content_supply_site_scale_prompts.md`](docs/content_supply_site_scale_prompts.md)，指令维度（旅行垂类）见 [`docs/content_supply_instruction_scale_prompts.md`](docs/content_supply_instruction_scale_prompts.md)。

## 快速验证

```bash
cd quwoquan_data

# 生成标签树
python3 scripts/bootstrap/taxonomy/bootstrap_tags.py
python3 scripts/bootstrap/taxonomy/bootstrap_admin_regions.py
python3 scripts/bootstrap/taxonomy/bootstrap_geo_landmarks.py
python3 scripts/bootstrap/taxonomy/bootstrap_event_topics.py

# 验证标签体系（R1-R12, 目标: 0 错误）
python3 scripts/verify/verify_tag_tree.py

# 统计报告
python3 scripts/tags/tag_stats.py
```

## 设计基准

核心设计决策：

1. **Entity 不实例化**：Entity 分组只定义类型骨架，具体实例放在 `entities/` 中通过 `tagRefs` 引用
2. **菜系/品类/业态三正交**：R11/R12 门禁强制检查命名不重叠
3. **住宿三层架构**：Topic/住宿（8 维标签）⊥ Entity/地点/住宿（10 类骨架）⊥ Topic/旅行/住宿（15 话题角度）
4. **去掉 appliesTo/status/lifecycle**：标签本体保持轻量，动态属性全部外置
5. **tagId 由目录推导**：不在 `_definition.json` 中冗余存储
6. **label 与目录名强一致**：G21 门禁强制检查
7. **四分组固定不变**：通过 `_group.schema.json` 的 enum 约束
8. **正交三分**：自然风光（审美）⊥ 地形地貌（科学分类）⊥ 自然景观（Entity 实例类型）
9. **时间唯一真相源**：节日/季节信息只在 Topic/时间/ 定义
10. **无显式关系文件**：标签关联通过 tagRef 共现度隐式计算
11. **行政区数据驱动**：中国行政区来自民政部权威数据源（`reference/admin_regions/pca.json`），脚本驱动生成，不硬编码
12. **行政区 vs 城市正交**：行政区标签回答"在哪"（Topic/地理/行政区），城市实体回答"是什么类型"（Entity/地点/城市），通过 geoTagRef 关联
13. **Entity/机构/学校只放类型标签**：学段(13)+高校层次(8)+学科类型(12)+办学性质(2)=35 个叶子直接挂在 L4，严禁出现具体学校名；学校实例在 `entities/机构/学校/{name}/` 目录
14. **校园标签四组联动**：Topic/教育成长(12 子域) + Entity/机构/学校(35 类型) + Audience/圈子/校园圈(6 社群) + Format/内容角度(含经验分享 5 角度) 协同覆盖校园场景

## 校园数据工程

### Entity/机构/学校 类型骨架

```
Entity/机构/学校/          (L3)
  ├── 学段: 幼儿园/小学/初中/高中/完全中学/九年一贯制/十二年一贯制/中等职业/大学/高职/国际学校/特殊教育/培训机构 (13)
  ├── 高校层次: 985高校/211高校/双一流/普通本科/独立学院/民办本科/中外合作办学/军事院校 (8)
  ├── 高校学科类型: 综合类/理工类/师范类/农林类/医药类/财经类/政法类/体育类/艺术类/军事类/民族类/语言类 (12)
  └── 办学性质: 公办/民办 (2)
```

### 数据源（`.qwq_output/data/local/runtime/seed/school_catalog/`）

| 数据文件 | 来源 | 行数 |
|---------|------|------|
| `universities_national.ndjson` | 教育部《全国普通高等学校名单》 | 2922 |
| `schools_beijing.ndjson` | 北京市教委学校/幼儿园名录 | 177 |
| `schools_shanghai.ndjson` | 上海市教委学校/幼儿园名录 | 169 |

### 生成产物

| 产物 | 数量 | 说明 |
|------|------|------|
| 学校实体（三件套） | 3268 | 含全国高校 + 北京上海中学/幼儿园 |
| 索引帖 | 3268 | 每校 1 篇 |
| 深内容帖 | 3357 | 重点学校多篇（985/211 3-6 篇、普通本科 1-2 篇） |

### 学校实体 tagRefs 示范

```json
{
  "label": "北京大学",
  "geoTagRef": "Topic/地理/行政区/中国/北京市/北京市",
  "tagRefs": [
    "Entity/机构/学校",
    "Entity/机构/学校/大学",
    "Entity/机构/学校/985高校",
    "Entity/机构/学校/211高校",
    "Entity/机构/学校/双一流",
    "Entity/机构/学校/综合类",
    "Entity/机构/学校/公办"
  ]
}
```
