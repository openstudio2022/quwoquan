# L2 特性：runtime-control-plane-foundation

## 功能说明
- 为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal` 的共同上位规格，冻结门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- 冻结各垂直领域的三类面架构：`user-plane`、`platform-control-plane`、`product-control-plane`，要求三类面在契约层独立，并支持部署时任意组合。
- 冻结控制面元数据体系与 codegen 目标，确保 Web / Go / Python / App 共享同一份控制面真相源。
- 冻结配置分层边界：`sys.*` 归 `platform-ops`，`ops.*` 归 `product-ops`，IaC 与基础设施参数不进入业务配置中心。
- 冻结端侧可配置边界：一级/二级 tab、栏目、版面、布局与体验类 feature flag 可配置，但 long-polling 周期、超时、限流、采样率等运行时参数必须归入 `sys.*`。

## 门户范围

### 一级菜单
- `总览`
- `Platform Ops`
- `Product Ops`
- `审计与变更`
- `系统设置`

### 二级菜单基线
- `总览`：环境态势、发布与告警、待办事项、最近变更、重点实验与治理事件
- `Platform Ops`：服务目录、配置中心、治理策略、发布灰度、环境与依赖、可观测与 SLO、Runbook 与演练、CI/CD 门禁
- `Product Ops`：事件与指标、标签与分群、实验与灰度、推荐运营、内容治理、账号治理、申诉与恢复、客服工单、策略中心
- `审计与变更`：配置变更审计、运营策略审计、处罚与恢复审计、发布记录、回滚记录、双签审批记录
- `系统设置`：门户权限、字典与枚举、通知渠道、附件与证据存储、集成配置

## 适用范围与约束

适用范围：
- 作为 `platform-ops` 与 `product-ops` 的共同上位规格
- 作为统一控制面元数据、统一 codegen、统一部署组合与统一集成验收的基线
- 作为后续各领域接入控制面时的强约束

约束：
- 统一门户前端技术栈冻结为 `React + TypeScript`
- 控制面后端主栈冻结为 `Go`
- 推荐训练、离线分析、模型评估等计算型能力保留 `Python`
- 控制面接口禁止手写第二套临时 admin / ops API，必须由元数据和 codegen 驱动
- 三类面契约不得依赖当前部署拓扑，不得以“先混合、后拆分”为前提
- 每个领域必须能够支持三类面在部署期任意组合，避免后期返工

## 借鉴输入

借鉴点：
- `Backstage + Argo Rollouts`：统一研发自助入口、服务目录、发布与灰度治理
- `LaunchDarkly / Statsig / Amplitude`：实验、灰度、指标归因、策略审计
- `TikTok / YouTube Studio / Trust & Safety`：治理处置、申诉恢复、证据与审计工作流

不直接照搬：
- 不引入过重的 mesh-first 平台体系
- 不让控制台绕过 repo / metadata 直接成为唯一真相源
- 不将业务治理逻辑直接硬编码在控制面 UI 或脚本中

## 职责边界

本节点负责：
- 统一门户壳层
- 三类面架构基线
- 控制面元数据对象基线
- codegen 产出目标基线
- 控制面部署组合基线
- 统一集成验收口径

本节点不负责：
- `platform-ops` 的详细产品设计与实施细节
- `product-ops` 的详细产品设计与实施细节
- 各具体领域的治理动作、推荐策略、审核流程细节
- 具体 K8s / Terraform / Helm 模板实现

## 核心约束
- 所有领域必须支持三类面：`user-plane`、`platform-control-plane`、`product-control-plane`
- 所有领域的控制面能力必须通过统一控制面元数据表达并 codegen
- 允许短期使用 `seed-box` 独立容器与领域处置服务同 Pod 部署
- 长期必须支持控制面独立 Deployment / Pod 与独立扩缩容
- `platform-control-plane` 与 `product-control-plane` 在逻辑上独立，部署上可合可分
- 端侧 IA / 布局 / 栏目 / 体验 flag 属于 `ops.*`
- long-polling 周期、超时、限流、采样率等运行时参数属于 `sys.*`

## 验收标准概要
- A1：统一门户壳层、菜单、全局能力边界明确，且可作为两大控制面的共同上位规格
- A3：三类面与部署任意组合原则冻结，支持短期同 Pod、长期独立 Pod
- A4：审计、通知、环境切换、搜索与全局导航在门户层有统一口径
- A5：`sys.*` / `ops.*` / IaC 分层清晰，端侧可配置边界冻结
- A7：控制面元数据对象、codegen 目标与运行时约束一致
- A8：统一集成验收链路可落到 metadata、codegen、部署组合和门户壳层验证
