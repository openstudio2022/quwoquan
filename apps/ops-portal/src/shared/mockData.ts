export const moderationTrend = [
  { day: 'Mon', created: 128, resolved: 96, slaRisk: 12 },
  { day: 'Tue', created: 142, resolved: 118, slaRisk: 10 },
  { day: 'Wed', created: 151, resolved: 132, slaRisk: 8 },
  { day: 'Thu', created: 164, resolved: 143, slaRisk: 11 },
  { day: 'Fri', created: 172, resolved: 151, slaRisk: 9 },
  { day: 'Sat', created: 138, resolved: 127, slaRisk: 6 },
  { day: 'Sun', created: 126, resolved: 121, slaRisk: 5 },
];

export const recommendationGuardrailTrend = [
  { day: 'Mon', ctr: 8.2, complaints: 0.34, diversity: 64 },
  { day: 'Tue', ctr: 8.4, complaints: 0.32, diversity: 66 },
  { day: 'Wed', ctr: 8.7, complaints: 0.36, diversity: 68 },
  { day: 'Thu', ctr: 8.6, complaints: 0.31, diversity: 67 },
  { day: 'Fri', ctr: 8.9, complaints: 0.29, diversity: 69 },
  { day: 'Sat', ctr: 9.1, complaints: 0.28, diversity: 72 },
  { day: 'Sun', ctr: 9.0, complaints: 0.3, diversity: 71 },
];

export const rolloutHealthTrend = [
  { stage: '5%', successRate: 99.7, latency: 720 },
  { stage: '25%', successRate: 99.4, latency: 760 },
  { stage: '50%', successRate: 99.2, latency: 810 },
  { stage: '100%', successRate: 98.9, latency: 845 },
];

export const caseQueue = [
  {
    title: '内容治理 / 举报案例 CASE-4018',
    subtitle: '涉及 post:post_901 · 双签待完成 · 26 分钟后触达首响 SLA',
    status: 'warning',
  },
  {
    title: '账号恢复 / REC-2009',
    subtitle: 'user:user_1827 · 证据已补齐 · 等待二审',
    status: 'danger',
  },
  {
    title: '实验放量 / EXP-feed-layout-v3',
    subtitle: '已进入 25% 灰度 · guardrail 正常',
    status: 'success',
  },
];

export const recommendationPolicies = [
  {
    title: '新作者扶持 rerank 模板',
    subtitle: '作用层：精排 / 重排 · 作者多样性 +0.12 · 可回滚',
    status: 'neutral',
  },
  {
    title: '本地生活召回白名单',
    subtitle: '作用层：召回 · 覆盖 segment:city-tier-1 · 今日投诉率 0.21%',
    status: 'success',
  },
  {
    title: '风险内容预过滤阈值',
    subtitle: '作用层：粗排 · guardrail 接近阈值 82%',
    status: 'warning',
  },
];

export const configReleases = [
  {
    title: 'CFG-2026-03-08-01',
    subtitle: 'content / gateway · 当前阶段 25% · rollback ready',
    status: 'success',
  },
  {
    title: 'CFG-2026-03-08-02',
    subtitle: 'assistant · 追踪采样调整 · 需二次审批',
    status: 'warning',
  },
  {
    title: 'CFG-2026-03-08-03',
    subtitle: 'orchestrator · downstream timeout 变更 · 观测中',
    status: 'neutral',
  },
];

export const auditTimeline = [
  {
    title: '推荐策略 `policy_discovery_rank_v12` 已进入 canary',
    subtitle: '10:32 · actor: wang.ops · rollback_token: rbk_9812',
  },
  {
    title: '恢复案例 `REC-2009` 完成首审',
    subtitle: '09:48 · actor: li.cs · evidence_count: 4',
  },
  {
    title: '配置发布 `CFG-2026-03-08-01` 进入 25% 灰度',
    subtitle: '09:10 · actor: zhao.fs · slo_gate: pass',
  },
];

export const platformServiceCatalog = [
  {
    service: 'gateway-orchestrator',
    plane: 'platform-control-plane',
    owner: 'platform-team',
    health: 'success',
    summary: '承接统一入口、路由治理、上下文传播与灰度绑定。',
  },
  {
    service: 'content-service',
    plane: 'user-plane / platform-control-plane',
    owner: 'content-team',
    health: 'warning',
    summary: '内容发布与审核链路已接入配置灰度与 SLO 观察。',
  },
  {
    service: 'assistant-service',
    plane: 'user-plane / platform-control-plane',
    owner: 'assistant-team',
    health: 'neutral',
    summary: '追踪采样与下游超时策略已纳入统一配置中心。',
  },
];

export const platformGovernancePolicies = [
  {
    title: 'gateway.timeout.default',
    subtitle: '默认超时 800ms · 作用于 orchestrator / gateway。',
    status: 'warning',
  },
  {
    title: 'content.mongo.pool',
    subtitle: 'Mongo 连接池上限 120 · 需要 restart 生效。',
    status: 'neutral',
  },
  {
    title: 'assistant.trace.sampling',
    subtitle: 'OTel 采样率 0.2 · 支持热更新。',
    status: 'success',
  },
];

export const platformDependencies = [
  {
    dependency: 'MongoDB / content-primary',
    profile: 'primary-write',
    latency: '12ms',
    status: 'success',
  },
  {
    dependency: 'Redis / cache-cluster-a',
    profile: 'rate-limit + cache',
    latency: '4ms',
    status: 'success',
  },
  {
    dependency: 'LLM Gateway / assistant-upstream',
    profile: 'external-api',
    latency: '480ms',
    status: 'warning',
  },
];

export const platformCapacityProfiles = [
  {
    plane: 'user-plane',
    resourceClass: '4c8g',
    scaling: 'HPA CPU / QPS',
    splitTrigger: 'user traffic spike',
  },
  {
    plane: 'platform-control-plane',
    resourceClass: '2c4g',
    scaling: 'manual + batch window',
    splitTrigger: 'config release / audit backlog',
  },
  {
    plane: 'product-control-plane',
    resourceClass: '2c4g',
    scaling: 'case backlog / operator concurrency',
    splitTrigger: 'SLA backlog growth',
  },
];

export const platformRunbooks = [
  {
    title: '配置发布回滚演练',
    subtitle: '每周一次，验证 rollback token、SLO gate 与恢复路径。',
    status: 'success',
  },
  {
    title: 'Mongo 主从切换演练',
    subtitle: '覆盖 content / user 关键写路径。',
    status: 'warning',
  },
  {
    title: '控制面独立扩容演练',
    subtitle: '验证 seed-box 到独立 Pod 的切换准备度。',
    status: 'neutral',
  },
];

export const platformGateRules = [
  {
    rule: 'config_release_error_rate',
    stage: '25%',
    status: 'success',
    summary: 'error_rate < 0.5% 且 p95 < 900ms',
  },
  {
    rule: 'dependency_health_mongo',
    stage: '50%',
    status: 'warning',
    summary: '副本延迟接近阈值，需人工复核',
  },
  {
    rule: 'rollback_readiness',
    stage: '100%',
    status: 'neutral',
    summary: '回滚包与上一个稳定版本均已就绪',
  },
];
