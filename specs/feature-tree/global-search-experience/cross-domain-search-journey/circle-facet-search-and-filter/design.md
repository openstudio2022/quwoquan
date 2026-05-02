# circle-facet-search-and-filter 设计方案

## 设计动因

“频道”已经在 PRD 中冻结为 `Circle` 的分类投影。如果设计阶段不把它做成 facet，而继续把它当作独立结果对象，后续 metadata、result model 和路由都会再次分叉。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `circle-facet-search-and-filter/spec.md` | 已冻结频道只作为群组 facet |
| `circle-facet-search-and-filter/acceptance.yaml` | `A1/S1` 足以承接实施切片 |
| 现有 circle UI | 已存在 `categoryId / subCategory / sectionConfig` 等投影，可作为 facet 真相源输入 |

## 对标输入分析

- 对标可吸收的是“内容结果和分类联动”的展示方式。
- 不能吸收的是把频道当成与群组并列的独立对象。

## 方案对比

### 方案 A：新增独立 `SearchChannels`

优点：

- 展示上直观。

缺点：

- 直接违反 PRD 冻结的对象边界。

### 方案 B：只返回群组结果，App 从本地配置拼 facet

优点：

- 服务端改动少。

缺点：

- facet 与真实搜索结果容易漂移。
- App 会维护第二套分类真相源。

### 方案 C：`SearchCircles` 返回群组项 + facet buckets

优点：

- 群组对象与频道 facet 语义清晰。
- App 不需要维护第二套频道定义。

缺点：

- circle 搜索 contract 需要一次性补齐。

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### KD1：只定义 `SearchCircles`，不定义 `SearchChannels`

### KD2：返回模型冻结为两部分

- `CircleSearchItemView`
- `CircleFacetBucketView`

### KD3：facet key 复用现有分类投影

优先字段：

- `categoryId`
- `subCategory`
- 必要时补 `facetCount`

### KD4：App 侧只维护当前选中的 facet，不维护 facet 真相源

- result page 只负责筛选和展示。
- facet bucket 的定义来自群组搜索结果。
- 若 `circle.group` 触发 local fallback，facet 仍遵循统一 typed contract 返回，不在页面层临时拼接第二套规则。

### KD5：metadata / codegen 方案

- `social/circle/fields.yaml`
  - 新增 `CircleSearchItemView`
  - 新增 `CircleFacetBucketView`
- `social/circle/service.yaml`
  - 新增 `SearchCircles(query, categoryId?, subCategory?)`

## 字段演进、迁移/回填、必要时双读双写方案

- `channel` 不新增主键与独立 DTO。
- App 记录上若有 “频道” UI 组件，迁移为 facet 展示层。
- 不做双写。

## feature flag、观测、SLO 验证与回滚方案

- 无业务 feature flag。
- 观测：
  - `circle_search_latency_ms`
  - `circle_facet_select_count`
  - `circle_facet_empty_result_count`
- 回滚：
  - 整版回退，不恢复独立 channel 方案

## TDD / ATDD 策略

- `T1_schema`：circle search DTO 与 facet bucket
- `T2_module_interaction`：facet chip / section 交互
- `T3_cross_service_integration`：circle 搜索 + facet 过滤
- `T4_user_journey`：从 facet 进入群组详情

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结 circle search 与 facet contract | `T1_schema` |
| `P2` | 落地 facet 过滤与结果展示 | `T2_module_interaction`, `T3_cross_service_integration` |
| `P3` | 验证 facet 空态与详情跳转 | `T2_module_interaction`, `T4_user_journey` |

## 未来演进

- 若群组分类体系后续升级，也只扩展 facet bucket，不引入独立 channel 主域。
