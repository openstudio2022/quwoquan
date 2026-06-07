# 回填与索引重建说明

这份说明用于历史回填、批量重跑和发布前复验，避免 `_entity.json`、`manifest.json`、`publish/v1/index/` 三层职责再次混写。

## 真相源

- `_entity.json` 是实体事实源。
- 实体叶不再保留 `manifest.json`；`manifest.json` 仅用于 post 包等发布元数据，不承载实体事实。
- `publish/v1/index/` 是 lookup 索引层，不承载事实字段。
- `publish/v1/index/_manifest.json` 记录索引分片和条数，不参与业务查询。

## 本轮冻结的 canonical 切分

> 本节是 `rename-migrate` 的目标口径。旧路径可以保留为 alias 或迁移锚点，但不再新增新叶；凡属于同一语义轴的内容，只保留一个 canonical 主路径。

| 语义组 | canonical 根 | 旧路径 / alias | 轴内拆分 | 互斥边界 |
| --- | --- | --- | --- | --- |
| 摄影 | `Topic/摄影` | `摄影`、`摄影创作`、`摄影文化` | `题材社区` / `知识方法` / `活动赛事` | `Format/表现手法` 只管怎么拍；`Topic/旅行/玩法/摄影旅拍` 只管旅行体验；`后期技巧`、`摄影史`、`器材评测` 归知识方法 |
| 时尚穿搭 | `Topic/时尚穿搭` | `穿搭`、`服饰搭配`、`造型` | `风格` / `场景` / `单品品类` / `搭配方法` | 品牌、商品、价格、测评归 `Entity/商品` 或 `Topic/购物消费`；身材、年龄、性别归 `Audience`；季节归 `Topic/时间` |
| 美妆护肤 | `Topic/美妆护肤` | `美妆`、`护肤`、`化妆美容`、`彩妆` | `护肤` / `彩妆` / `造型修饰` / `工具与产品` | 商品、品牌、口碑榜单不进主轴叶子；成分研究可与 `Topic/购物消费` 联动但不混为同轴 |
| 事件 / 话题 | `Topic/事件`、`Topic/话题` | 旧 `Topic/事件话题` 已退役 | `事件` 只收新闻事件、历史事件、社会事件等可指称事实；`话题` 只收稳定议题语义 | 今日热词、热搜、挑战、平台话题不直接落静态标签，统一走 runtime 实例层，再由事件簇 / 话题簇回写 |
| 科技 / 数码 / 游戏电竞 / 运动电竞 | `Topic/科技`、`Topic/数码`、`Topic/游戏电竞`、`Topic/运动/电竞赛事` | 旧 `Topic/数码科技` 已退役 | `科技` 走行业 / 趋势 / 公司 / 新技术；`数码` 走消费电子 / 影像 / 无人机 / 电子城；`游戏电竞` 走玩法 / 攻略 / 直播 / 硬件；`运动/电竞赛事` 走竞赛 / 战队 / 联赛 / 赛制 | `电竞赛事` 只能有一个 canonical 归属；同一内容不得同时把“玩法轴”和“赛事轴”当主标签 |
| 住宿 | `Topic/住宿` | `住宿`、`住宿内容` | `住宿形态` / `档次等级` / `主题` / `设施服务` / `房型` / `区位` / `认证评级` / `预订特征` | `闪订` 统一为 `即时确认`；平台名只做 alias，不进 canonical；认证评级拆成官方评级 / 平台榜单 / 口碑榜单 / 行业奖项 |
| 人文 / 历史文化 | `Topic/人文社科`、`Topic/历史文化` | `人文`、`社科`、`历史`、`文明史` | `人文社科` 负责城市观察 / 社会纪实 / 民俗风物 / 旅行人文 / 乡土生活 / 文化评论；`历史文化` 负责文明史 / 遗产遗迹 / 文博考古 / 地方史志 / 典籍文献 | `历史事件` 回到 `Topic/事件`；`人文摄影` 保持在 `Topic/摄影`，不在内容轴里再造一棵“人文”树 |

### 统一别名策略

- 平台名、渠道名、榜单名只允许进入 `aliases` 或 `description`，不进入 canonical label。
- 旧路径只要能无歧义迁移，就保留为别名锚点；如果一个旧路径被拆成多个新轴，只能按“语义主对象”分流到一个 canonical 主路径，其余通过 alias / crosswalk 回写。
- 动态热话题、热搜、挑战、新闻事件实例不进静态标签树，统一走 `tag_runtime/` 运行时层；静态树只保留稳定分类。
- 动态实例的字段、状态流转和落盘结构见 [`dynamic_topic_event_model.md`](dynamic_topic_event_model.md)。

## 回填顺序

推荐顺序如下：

```bash
python3 scripts/publish_ops/build_publish_lookup_indexes.py
bash scripts/verify/verify_quwoquan_data.sh   # 原 gate_e2e.py 已 CLI-first 拆分
python3 verticals/campus/verify/verify_campus_taxonomy.py
python3 scripts/ml/verify_feature_consistency.py
```

如果是学校数据专项回填，先执行 `verticals/campus/scripts/bootstrap_school_entities.py` 和 `verticals/campus/scripts/bootstrap_school_posts.py`，再重建索引和门禁。

## posts 路径约定

canonical 目录结构为：

```text
posts/{contentType}/{angle}/{title}/{seq}/
```

其中 `{angle}` 取 `Format/内容角度/*` 的最后一段。历史兼容的 `posts/{contentType}/内容角度/{angle}/...` 仍可被解析，但新产出应使用 canonical 结构。

## 语义边界提示

产品层的 taxonomy id 和发布层的语义路径不是同一粒度，建议只做映射说明，不要强行合并成一套树：

| 产品语义 | 发布语义轴 |
| --- | --- |
| `education` | `Topic/教育成长` |
| `food` | `Topic/美食餐饮` |
| `travel` | `Topic/旅行` |
| `photography` | `Topic/摄影` |
| `campus` | `Topic/教育成长` + `Audience/圈子/校园圈` + `Format/内容角度/经验分享` |

## 什么时候必须重建索引

- 回填历史实体或 posts 之后。
- 批量修正 tagRefs、geoTagRef、entityRefs 之后。
- 调整学校、住宿、旅行、摄影等高基数目录之后。
- 修改 `bootstrap_*` 产物生成脚本之后。

## 验证标准

- `scripts/verify/verify_quwoquan_data.sh`（原 `gate_e2e.py`）通过，包含 G28 lookup 索引完整性和 G29 校园专项。
- `verify_campus_taxonomy.py` 通过。
- `verify_feature_consistency.py` 通过。

