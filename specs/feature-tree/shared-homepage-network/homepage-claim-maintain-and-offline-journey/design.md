# homepage-claim-maintain-and-offline-journey 设计方案

## 设计动因

`homepage-claim-maintain-and-offline-journey/spec.md` 已冻结共享主页的治理主线，但如果没有 Journey 级设计，后续开发仍会踩进四个高风险区：

1. 候选建档会被拆成抓取、导入、用户补充、内容反抽四条彼此无关的临时流程，无法形成生命周期闭环。
2. 认领如果没有材料分层、审核状态和维护边界，很快会在“太重没人申请”和“太轻谁都能认领”之间失衡。
3. 认领后如果不冻结可维护字段，维护者会直接越权触碰用户口碑和历史内容。
4. 下线如果没有正式合同，极易回到硬删除或彻底隐藏，直接破坏历史可信度和内容锚点。

本次 `/design` 的目标，是把主页治理收口为一套可实施的生命周期与治理模型：

- **候选主页统一 intake -> verify -> publish**
- **认领采用分层材料 + 明确审核状态**
- **认领后只允许基础维护，不可改写用户事实**
- **统一软下线 + 历史保留，不做合并**

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `shared-homepage-network/spec.md` | 已冻结候选/待校验/已发布/已下线，认领分层和软下线历史保留合同 |
| `homepage-claim-maintain-and-offline-journey/spec.md` | 已冻结范围、SLO/KPI、权限与回滚口径 |
| `homepage-claim-maintain-and-offline-journey/acceptance.yaml` | `J1/J2/J3/R1` 足以承接 plan slices |
| 4 个 L3 scenario spec / acceptance | 已明确最小实施单元：候选建档、认领审核、认领后维护、下线与历史保留 |
| `shared-homepage-network/design.md` | 已冻结 `entity-service` 为主页主档、认领和状态治理归属 |
| 基准对标：Booking/Airbnb / 微信公众号/商家入驻 / 大众点评 | 已明确认领材料分层、维护边界与软下线合同方向 |

结论：

- `/design` 准入满足。
- 本 Journey 的实施顺序固定为：`lifecycle metadata -> claim/offline metadata -> codegen -> candidate publish flow -> claim flow -> maintenance + offline contract -> tests`。
- G1 已实际执行：
  - `make -C quwoquan_service verify-metadata`
  - `make codegen`
  - `make codegen-app`

## G1 基线结果

已执行：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

结果：

- metadata 校验通过
- codegen / codegen-app 基线通过
- 后续候选主页、认领请求、状态上报与错误码可以按正式生成链路推进

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|---|---|---|
| Booking/Airbnb | 经营主体验证、主理方维护、状态治理 | 不吸收交易/库存/房态后台 |
| 微信公众号 / 电商商家入驻 | 营业执照、操作者身份、授权材料、审核状态 | 不吸收超重 KYC 作为 baseline 统一门槛 |
| 大众点评 | 已关闭商户保留历史主页和用户评论 | 不吸收纯目录平台治理方式 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|---|---|
| `shared-homepage-network/design.md` | 候选来源、认领分层、软下线与历史保留大方向 |
| `platform-ops-governance` 类设计 | 审核状态、SLA、回滚和观测的治理写法 |
| `content` / `circle` 现有读模型 | 已下线主页继续保留历史内容和相关群组摘要的消费方式 |

结论：

- 主页治理必须是 **ops-backed lifecycle**，不能只靠前台表单。
- 认领要轻重分层，而不是所有类目都走同一套重 KYC。
- 下线必须是 soft-offline contract，而不是 delete contract。

## 方案对比

### 方案 A：用户可直接创建正式主页，后续再认领

核心思路：

- 用户或抓取结果都能直接生成公开主页。
- 后续有问题再人工处理。

优点：

- 冷启动快。
- 前台交互简单。

缺点：

- 重复主页、脏数据和错误主页会急剧增多。
- 候选/正式边界不存在，后续治理成本极高。
- 无法建立稳定可审计的认领链路。

### 方案 B：统一候选态 + 统一审核发布 + 分层认领 + 软下线

核心思路：

- 所有来源先进入候选态。
- 正式发布前统一验证。
- 认领按类目风险走材料分层。
- 已认领主页可维护基础字段，但不能触碰用户事实。
- 已关闭主页统一软下线保留历史。

优点：

- 生命周期边界清晰。
- 候选、认领、维护、下线四段可以分别治理。
- 最符合“共享主页是长期锚点”的产品定位。

缺点：

- 实现链路更长，需要审核和审计能力。
- 需要清晰的状态机和错误码。

### 方案 C：全部重 KYC + 硬下线清理

核心思路：

- 所有认领都要求重材料。
- 关闭主页直接删除或深度隐藏。

优点：

- 风控规则看似统一。

缺点：

- 认领门槛过高，不利于冷启动。
- 硬下线直接破坏历史内容和口碑锚点。
- 与本项目“长期主页”定位相反。

## 选型决策

**选定方案：方案 B**

决策理由：

1. 只有候选态和正式态分离，主页网络才具备长期可治理性。
2. 分层认领能够兼顾冷启动效率与类目风险差异。
3. 软下线保留历史是共享主页可信度的底线，不可退让。

## 关键设计决策

### KD1：所有主页来源都先统一进入 candidate pipeline

统一来源：

- 网络抓取
- 运营导入
- 用户补充
- 内容反抽

统一状态机：

- `candidate`
- `pending_verify`
- `published`
- `offline`

原则：

- 没有任何来源可以绕过 candidate pipeline 直接成为正式主页
- 来源证据必须被记录到 `EntitySourceEvidence`

### KD2：认领采用两级材料分层

baseline 分层：

- `basic_claim`
  - 营业执照或经营主体证明
  - 官方手机号/邮箱
  - 操作者身份信息
  - 必要授权书
- `verified_claim`
  - 在基础材料上追加身份证件、地址/经营证明、类目所需许可

不采用：

- 所有类目一刀切重 KYC
- 仅手机号验证码式超轻认领

### KD3：认领后只开放基础维护面

允许维护：

- 名称补充说明
- 封面与图库
- 营业/开放状态
- 官方说明
- 服务入口信息

不允许维护：

- 用户口碑内容
- 历史用户内容
- 评分结果
- 群组关系本体

若对用户事实有争议：

- 只能发起申诉或补充官方说明
- 不能直接覆写

### KD4：维护操作必须可审计

至少记录：

- 操作者
- 变更前后字段
- 变更时间
- 变更来源
- 审核结果或系统动作

原则：

- 主页主档是可治理对象，不是随意可写的 profile
- 所有维护行为都要可追溯

### KD5：软下线是正式合同，不是权宜文案

软下线后保留：

- 原 URL
- 历史内容
- 历史口碑
- 相关群组摘要关系

软下线后降级：

- 搜索曝光
- 推荐曝光
- 运营入口

软下线后新增限制：

- 默认关闭新的运营型入口
- 认领/维护流程需受额外审核或暂停

### KD6：主页治理状态由 entity-service 单域持有

正式写模型：

- `EntityProfile`
- `EntitySourceEvidence`
- `EntityClaimRequest`
- `EntityStatusReport`

消费方：

- 搜索结果消费主页状态
- 内容聚合消费主页状态决定展示标识
- 群组关联消费主页状态决定摘要提示

不允许：

- search / content / circle 自己复制一份主页状态机作为长期真相源

### KD7：下线与恢复按“显式流程”治理

允许入口：

- 普通用户上报
- 认领方上报
- 平台运营标记

结果：

- `status_report` 进入审核
- 审核通过才切换主页状态

恢复：

- 允许后续恢复，但不在本期冻结复杂后台
- 最小要求是状态机允许 `offline -> published` 的受控恢复

### KD8：metadata / codegen 方案

| 目录 | 设计动作 | 产物 |
|---|---|---|
| `entity/homepage/fields.yaml` | 新增候选主页、认领请求、状态上报、维护审计相关 view / entity fields | entity generated DTO |
| `entity/homepage/service.yaml` | 新增 `IntakeHomepageCandidate`、`PublishHomepageCandidate`、`CreateHomepageClaimRequest`、`ReviewHomepageClaimRequest`、`UpdateClaimedHomepageBasics`、`CreateHomepageStatusReport`、`ReviewHomepageStatusReport` | entity API metadata |
| `entity/homepage/errors.yaml` | 新增候选发布、认领材料、越权维护、下线合同相关错误码 | generated errors |
| `_shared/request_context.yaml` | 新增 claim / report / maintenance surfaces 的 request page ids | `*_request_page_ids.g.dart` |
| `entity/homepage/ui_config.yaml` | 冻结认领材料分层、可维护字段集、已下线展示策略 | app UI config |

## metadata / codegen 方案

正式顺序：

1. `entity/homepage` lifecycle / claim / offline metadata
2. `_shared` 的 request context 与相关 surface
3. `errors.yaml` 和 `ui_config.yaml`
4. 运行 G1：
   - `make -C quwoquan_service verify-metadata`
   - `make codegen`
   - `make codegen-app`
5. 再进入审核流程、维护面、下线展示与历史保留实现

当前 G1 基线已在本轮 `/design` 实际执行并通过。

## 字段演进、迁移/回填、必要时双读双写方案

### 字段演进

- 主页状态由散落文案升级为正式 `status`
- 认领从“是否认领”升级为 `claimStatus + claimTier + claimEvidence`
- 下线上报从临时反馈升级为 `EntityStatusReport`

### 迁移 / 回填

- 历史导入条目统一回填为 `candidate` 或 `published`，由证据完整度决定
- 已存在的“关闭/停业”数据若可信，可回填为 `offline` 并保留原因标签
- 历史认领数据若不具备材料，不自动升级为 `claimed`

### 双读 / 双写

- **不做状态真相双写**
- 允许短期双读旧文案状态和新 `status`，用于 UI 迁移
- 退出条件：
  - 搜索、主页详情、内容聚合只读新状态字段
  - 旧文案状态完全退出

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- `enable_homepage_claim`
- `enable_homepage_claim_review`
- `enable_homepage_offline_report`
- `enable_homepage_offline_history_badge`

策略：

- 先开 candidate/publish 主线
- 再开 claim 申请
- 再开 claim review / maintenance
- 最后开 offline report 与 offline badge

### 观测

- `homepage_candidate_publish_success_count`
- `homepage_claim_request_submit_count`
- `homepage_claim_review_latency_hours`
- `homepage_claim_permission_denied_count`
- `homepage_offline_report_submit_count`
- `homepage_offline_history_view_count`

### SLO 验证

- 认领审核 SLA `<= 3 个工作日`
- 下线处理 SLA `<= 7 天`
- 已下线主页历史保留率 `100%`

### 回滚

- 一级回滚：关闭 claim 入口，但保留已认领主页与历史状态展示
- 二级回滚：关闭 offline report 入口，但不得破坏已下线主页历史页
- 不允许回滚到硬删除主页

## TDD / ATDD 策略

### T1：schema / metadata

- lifecycle 状态、claim fields、status report fields、错误码、ui config

### T2：module interaction

- claim 表单、补件/驳回、基础维护表单、offline report 表单

### T3：cross service integration

- published/offline 状态被搜索、内容聚合、群组摘要正确消费
- 已下线主页仍可保留历史内容和口碑

### T4：user journey

- 候选主页发布
- 认领申请 -> 审核 -> 基础维护
- 上报下线 -> 审核 -> 历史可见

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 验证层 |
|---|---|---|
| `P1` | 冻结 lifecycle / claim / offline metadata | `T1` |
| `P2` | 建立 codegen baseline 与错误码生成物 | `T1` |
| `P3` | 落候选主页 intake / publish 主线 | `T2`, `T3`, `T4` |
| `P4` | 落 claim request / review | `T2`, `T3`, `T4` |
| `P5` | 落 claimed homepage maintenance 与审计边界 | `T2`, `T3` |
| `P6` | 落 offline report / history retention | `T2`, `T3`, `T4` |
| `P7` | 加固观测、SLO、回滚与整体验收 | `T3`, `T4` |

## 未来演进

- 支持多门店/总部批量认领与批量维护，但不影响本期单主页治理模型
- 支持更细的 claim tier 和行业许可模板，但仍通过 `ui_config` 和 metadata 管理
- 支持主页合并，但必须在独立 Journey 中定义历史迁移合同，不能提前侵入本 Journey
- 引入更丰富的风控策略和审核自动化，但仍不允许绕过 candidate / claim / offline 正式状态机
