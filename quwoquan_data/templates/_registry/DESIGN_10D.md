# 模板库 10D 升级设计与三视角自检

本文是模板库从 8D 升级到 10D（新增「地域」「季节」两个正交条件维）的设计真相源与自检记录。维度内容唯一定义在 `_registry/catalogs/`，模板与脚本不得二次硬编码。

## 一、三视角自检结论

### 专业编辑视角

- E1 地域写死：`blueprints/Format/内容角度/线路/补给避险.tmpl.yaml` 把 `高原与医疗`/`高原风险` 写进 `structure.required` 与 `mustIncludeFacts`；`Format/内容角度/线路/自驾路书.tmpl.yaml` 写死 `海拔`；`_registry/catalogs/evidence_catalog.yaml` 的 `travel_route` 同样固化 `海拔`。这些对沿海、平原、海岛、沙漠、热带不成立。
- E2 季节缺位：季节仅以「最佳季节/季节窗口」零散出现，缺四季 × 地区的系统建模（雨季/旱季/旺季/淡季/极端天气），出行四季变换无统一抓手。
- E3 风格默认死引用：`intent_catalog.yaml` 中 `科普 → defaultStyleFamily: 人文深读风`，但 `style_profile_catalog.yaml` 无该风格族；所有科普模板实际声明 `地理画报风`。需把默认对齐为已存在族。
- E4 国家地理级版式不足：`地理画报风/地理深读` 已有专题报道体，但缺信息图、图说、分栏画报版式与强图注约束。
- E5 类别盲区：旅行缺城市漫步（`city_walk` evidence 已存在却无模板）、风物美食（区别于餐厅探店）、节庆民俗；校园缺校招就业。

### 不同读者视角

- R1 孤儿受众：`audience_catalog.yaml` 定义了 `photoTraveler`、`jobSeeker`，但无任何模板/路由命中。
- R2「此时此地」缺失：同一受众在不同地域/季节需求差异大（夏季亲子避暑 vs 冬季亲子滑雪），现无法表达。
- R3 深度分层：旅行入门→进阶→专业较全；校园偏入门，缺数据/专业向与轻量碎片向。

### 数据工程视角

- D1 模型升 10D：地域、季节为正交条件维，禁止为每地域/季节分裂模板（5 线路 × 6 地域 × 4 季节将爆炸，违反编码军规 R24）。
- D2 single-source：新增 `region_catalog.yaml` + `season_catalog.yaml`；模板只声明哪些 fact/图位/风险段是条件化的，内容由 catalog 提供、brief 阶段注入。
- D3 接入点：`RouteRequest` 透传 `region/season`（不参与选模板）；`scripts/plan/brief.py` 注入 `conditionContext` 与条件 facts/图位。
- D4 校验缺位：lint 无「地域写死」黑名单扫描，无 region/season catalog 完整性校验，无孤儿受众检测。

## 二、10D 模型

| 维度 | 真相源 | 是否参与选模板 |
|---|---|---|
| 1 subject | subject_catalog.yaml | 是 |
| 2 intent | intent_catalog.yaml | 是 |
| 3 carrier | carrier_catalog.yaml | 否（默认推导） |
| 4 audience | audience_catalog.yaml | 是（细分路由） |
| 5 styleProfile | style_profile_catalog.yaml | 否（family 展开） |
| 6 evidenceQuality | evidence_catalog.yaml | 否 |
| 7 creatorPersona | creator_profile_catalog.yaml + creator_profiles/ | 是（archetype） |
| 8 recProfile | recommendation_contract.yaml | 否 |
| 9 region（新增） | region_catalog.yaml | 否（条件注入） |
| 10 season（新增） | season_catalog.yaml | 否（条件注入） |

地域、季节是「条件修饰维」：模板保持地域/季节无关，仅通过可选块 `conditionAxes` 声明哪些段落/事实会被条件化；brief 阶段按 `request.region/season` 命中 catalog 注入。

## 三、条件修饰维设计

模板新增可选块：

```yaml
conditionAxes:
  region: { applicable: true, slot: 地区与医疗 }
  season: { applicable: true, slot: 季节窗口与提示 }
```

注入规则（`resolve_compose_brief`）：当 `request.region` 命中 `region_catalog` 且 `conditionAxes.region.applicable` 为真时——

- `region.conditionFacts` 并入 `mustIncludeFacts`
- `region.imageHints` 追加进 `imagePlan`
- 产出 `conditionContext.region = { name, packing, riskNotes }`

季节同理。`conditionContext` 同时进入 recommendation manifest，供推荐侧按地域/季节切分。

## 四、single-source 边界

- 地域/季节内容唯一定义在 `region_catalog.yaml` / `season_catalog.yaml`。
- 模板 `structure`/`mustIncludeFacts` 禁止出现地域专有词黑名单（高原、海拔、雪山、高反、沿海、海岛、沙漠、戈壁、热带、雨林、台风、潮汐等），由 lint 扫描。
- `tagRefs` 仅挂经 `tag_exists` 校验通过的已存在标签。

## 五、待闭合清单

- 风格默认对齐：`intent_catalog.科普.defaultStyleFamily` 由 `人文深读风` 改为已存在的 `地理画报风`。
- 孤儿受众：`photoTraveler` → `主题_城市漫步`；`jobSeeker` → `学校_校招就业`。
- NatGeo 版式：新增 `主题_地理图说`（或强化 `主题_地理深读` 的信息图/图说版式与图注约束）。
- 类别盲区：`主题_风物美食`（风物向，区别于餐厅探店）。
