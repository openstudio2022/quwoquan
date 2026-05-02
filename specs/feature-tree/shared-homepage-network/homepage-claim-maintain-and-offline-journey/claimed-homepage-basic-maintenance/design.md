# claimed-homepage-basic-maintenance 设计

## 设计动因

`claimed-homepage-basic-maintenance/spec.md` 已冻结“认领通过后允许维护主页主档、但不得越权改写用户事实”的产品边界，但如果没有单独的 L3 设计，落地时仍会反复滑向三类错误：

1. 把已认领主页当作经营者私有主页，允许直接改写用户口碑、记录内容和评分结果。
2. 把维护入口做成“提交工单”，导致认领后的日常运营没有最小自助能力。
3. 没有正式审计边界，后续无法解释“谁在什么时间改了主页什么字段”。

本设计的目标，是冻结一套可落地的 baseline：认领通过后的主页只开放 **canonical basics maintenance**，允许经营主体维护主页主档和官方说明，不允许直接覆写用户内容事实，并要求所有变更可审计、可回滚、可被详情页和搜索稳定消费。

## 上游输入评审

### 已冻结输入

- L1：`specs/feature-tree/shared-homepage-network/spec.md`
- L2：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/spec.md`
- L2 acceptance：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/acceptance.yaml`
- L3：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/claimed-homepage-basic-maintenance/spec.md`
- L3 acceptance：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/claimed-homepage-basic-maintenance/acceptance.yaml`
- Journey 设计：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/design.md`
- iOS UX 基线：`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`

### 当前实现基线评审

当前共享主页主线已经具备：

- `entity-service` 的 `UpdateClaimedHomepageBasics` 写接口；
- 主页详情页的治理入口和 claimed maintenance 导航；
- iOS 原生全屏维护表单，用于编辑名称、副标题、城市、地址和分类标签；
- 主页详情、搜索和内容挂接对 canonical homepage 的读链路。

当前仍需在规格上明确的，是“哪些字段属于认领方可维护主档，哪些字段仍然属于用户事实或治理事实”，避免后续演进时重新发散。

### G1 基线结果

已执行：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

结果：

- metadata 校验通过；
- codegen / codegen-app 基线通过；
- 当前仓库已满足把 claimed maintenance 正式纳入 `/dev` 与 gate 的前置条件。

## 对标输入分析

| 对标 | 吸收点 | 不吸收点 |
|---|---|---|
| Google Business Profile | 商家可维护名称、地址、营业说明和对外展示资料 | 不吸收过重后台与广告投放体系 |
| Booking / Airbnb Host 管理 | 主理方维护主档资料，但住客评价仍保留独立事实 | 不吸收交易、库存、订单管理 |
| 大众点评商户资料治理 | 商户资料与用户点评分层，商户不能直接删改用户评论 | 不吸收纯目录站的弱主页关系 |

结论：

- 认领方必须拥有最小可用的主页主档维护能力，否则认领没有持续运营意义。
- 主页主档与用户事实必须严格分层，否则共享主页很快会退化成商家自营页。
- 审计不是补充能力，而是 baseline 合同的一部分。

## 方案对比

### 方案 A：认领后开放主页全部编辑权限

描述：

- 认领方可直接编辑主页所有字段；
- 用户口碑、评分摘要、记录内容和相关群组都允许被直接调整。

优点：

- 实现表面上最直接；
- 经营者控制感最强。

缺点：

- 直接破坏“共享主页”定位；
- 用户事实失真，平台可信度不可逆受损；
- 审核和争议处理成本急剧升高。

### 方案 B：只开放 canonical basics maintenance，并保留审计边界

描述：

- 认领方只能维护主页主档字段；
- 用户口碑、记录内容、评分聚合和群组关系不允许被直接改写；
- 所有维护操作落审计记录，并由详情页读取最新主档。

优点：

- 同时满足运营可维护性与共享可信度；
- 与当前 `entity-service` 单域真相源和 app 端治理页结构完全一致；
- 易于继续叠加审核、回滚和灰度。

缺点：

- 需要明确定义“允许字段集”；
- 某些经营者诉求需要走补充申诉，而不是直接修改。

### 方案 C：认领后不开放任何自助维护，只能提工单

描述：

- 经营主体不能自行维护主页；
- 所有变更都通过平台人工处理。

优点：

- 越权风险最低；
- 字段边界最容易控制。

缺点：

- 认领后没有即时价值；
- 维护效率低，不适合共享主页网络的长期运营；
- 平台运营会被低价值工单淹没。

### 选型

选择 **方案 B**。

原因：

1. 这是唯一同时满足“共享主页可信度”和“认领后可运营性”的方案。
2. 它与已实现的 `UpdateClaimedHomepageBasics`、主页治理页和 canonical attach 链路完全同向。
3. 它为后续的审计、灰度和精细审核保留了最清晰的扩展接口。

## 关键设计决策

### D1：维护对象是主页主档，不是用户事实

本场景允许修改的对象定义为 `Homepage` 的 canonical basics：

- 标题 `title`
- 副标题 `subtitle`
- 城市 `cityName`
- 地址 `address`
- 分类标签 `categoryTags`
- 其他主档说明性字段（例如官方说明、营业/开放说明）在同一维护边界内演进

不在本场景开放直接修改的对象：

- 用户口碑正文与评分明细
- 记录内容正文、配图、视频、文章
- 聚合评分结果
- 相关群组关系本体
- 审核记录和状态上报结果

原则：

- 认领方维护的是“主页资料”，不是“平台上所有关于这个主页的事实”。

### D2：维护权限必须以 claimed 状态为前置

进入维护页的前提：

- 当前主页认领状态为 `claimed`；
- 当前用户是通过审核的认领方或被授权维护者；
- 非认领方只能浏览主页，不能进入维护提交链路。

错误处理：

- 非认领方进入维护时返回明确权限错误；
- 维护提交失败时保留表单已填信息，允许用户继续编辑后重试。

### D3：维护提交采用“最小可写字段集”

baseline 提交 contract：

- 只提交本期冻结的 canonical basics；
- 服务端执行字段级写入，不接受任意 map 式自由扩写；
- 未开放字段即使前端透传，也必须被服务端拒绝或忽略。

本期 UI baseline：

- iOS 原生全屏表单；
- 顶部导航明确“主页维护”；
- 保存按钮仅在字段合法且有变更时可提交；
- 成功后返回主页详情并消费最新 shell/detail 数据。

### D4：详情页与搜索消费同一份维护后主档

维护成功后，以下消费方读取同一 canonical homepage：

- 主页详情页 hero / meta 信息；
- 搜索结果中的主页摘要；
- 内容发布时 attach 的主页快照；
- 后续群组、内容和网络搜索的主页入口。

不允许：

- 维护页本地保存一套私有展示状态；
- 搜索、内容或圈子单独维护另一份主页名称/地址真相源。

### D5：维护操作必须产生日志化审计记录

最小审计记录应包含：

- homepageId
- operatorId
- 变更字段集
- 变更前快照
- 变更后快照
- 操作时间
- 来源 surface / operation

baseline 不要求复杂后台审计 UI，但必须保证后续可接入审计查询和争议处理。

### D6：封面图库、状态与官方说明采用“同边界、分阶段灰度”

本场景 spec 已冻结以下能力归属在 maintenance boundary 内：

- 封面与图库维护
- 状态与官方说明维护

但实现顺序允许分阶段：

1. 先落 canonical basics maintenance 主线；
2. 再在同一权限边界下追加封面/图库和官方说明字段；
3. 如涉及主页状态切换，必须继续遵守 offline/report/review 的显式治理流程，不允许绕开状态机直接硬切。

这意味着：

- “展示说明类字段”可逐步扩充进 maintenance；
- “生命周期状态改变”仍由状态上报与审核流程主导。

## metadata / codegen 方案

| 目录 | 设计动作 | 产物 |
|---|---|---|
| `contracts/metadata/entity/homepage/service.yaml` | 冻结 `UpdateClaimedHomepageBasics` operation 的 writable fields 与权限语义 | app / service metadata |
| `contracts/metadata/entity/homepage/fields.yaml` | 冻结 canonical basics 字段集合与说明性字段归属 | generated DTO / store model |
| `contracts/metadata/entity/homepage/errors.yaml` | 冻结未认领、越权维护、非法字段更新错误码 | generated error constants |
| `_shared/request_context.yaml` | 挂接 maintenance page 的 request page id | request page ids |
| `_shared/ui_surfaces.yaml` | 维护 surface 与 operation 绑定 | app UI surface metadata |

顺序：

1. 先冻结字段边界和错误码；
2. 再跑 `verify-metadata -> codegen -> codegen-app`；
3. 最后实现服务端校验、app 表单和详情页刷新。

## 字段演进与迁移策略

### 字段演进

- 从“散落在 UI 的可编辑文案”升级为正式 metadata 驱动的 writable field 集；
- 从“是否能编辑”的隐式逻辑升级为 `claimStatus + operator permission` 的显式判断；
- 从“更新成功即可”升级为带审计痕迹的维护行为。

### 迁移策略

- 已有 published 主页默认不可维护，直到存在合法 claimed 关系；
- 记录主页名称、地址等主档字段直接沿用，不做额外结构迁移；
- 记录用户内容与评分数据不被 maintenance flow 回写。

### 双读 / 双写

- 不做主档真相双写；
- 允许 UI 在短期内兼容旧展示字段，但最终只消费 `entity-service` 的 canonical homepage；
- 退出条件是详情页、搜索结果和内容 attach 全部只读新 contract。

## feature flag、观测、SLO 与回滚

### feature flag

- `enable_homepage_claimed_maintenance`
- `enable_homepage_maintenance_gallery`
- `enable_homepage_maintenance_official_note`

策略：

- 先开放 claimed basics；
- 再灰度开放图库和官方说明；
- 与 offline 状态治理相关能力保持独立 flag。

### 观测

- `homepage_maintenance_submit_count`
- `homepage_maintenance_success_count`
- `homepage_maintenance_permission_denied_count`
- `homepage_maintenance_validation_error_count`
- `homepage_maintenance_apply_latency_ms`

### SLO

- 前台保存提交成功率 `>= 99%`
- 主页详情反映最新主档的刷新时延 `<= 5s`
- 越权维护拦截率 `100%`

### 回滚

- 一级回滚：关闭 maintenance 入口，但保留已更新的 canonical basics；
- 二级回滚：关闭扩展字段（图库、官方说明）编辑，仅保留基础信息维护；
- 不允许通过回滚把已更新主页恢复成不可解释的旧展示状态。

## TDD / ATDD 策略

### T1：schema / metadata

- `UpdateClaimedHomepageBasics` writable fields 与错误码校验；
- 维护 surface、request page id 与 metadata 绑定校验。

### T2：module interaction

- 认领后进入维护页并提交基础信息；
- 非认领方被拒绝；
- 提交失败时表单状态保留。

### T3：cross service integration

- 维护后的标题、副标题、地址被主页详情和搜索结果正确消费；
- 内容 attach 读取的是维护后的 canonical homepage snapshot。

### T4：user journey

- `claim approved -> maintain homepage basics -> detail refresh`
- `unauthorized user -> maintenance denied`

## 未来演进

- 支持封面图库批量管理，但仍遵守同一 claimed maintenance boundary；
- 支持更细的多角色授权维护者模型，但不改变“非认领方不可写”的主规则；
- 支持审计后台和字段级回滚，但不允许突破“用户事实不可直接覆写”的底线。
