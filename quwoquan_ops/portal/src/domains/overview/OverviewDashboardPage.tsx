import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Activity, AlertTriangle, ShieldCheck, Sparkles } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import {
  fetchGrowthOverview,
  fetchPlatformAudits,
  fetchProductEventDrilldown,
  fetchProductEventSummary,
  fetchProductL1L4Metrics,
  fetchProductProjectionSummary,
  fetchProductWorkflows,
  fetchRecommendationBehaviorMetrics,
  fetchReleases,
  type GrowthOverviewResponse,
  type PlatformAuditItem,
  type ProductEventDrilldownItem,
  type ProductEventSummary,
  type ProductMetricItem,
  type ProductProjectionSummary,
  type RecommendationBehaviorMetrics,
  type ReleaseItem,
  type WorkflowItem,
} from '../../shared/api/controlPlane.js';
import { KpiCard } from '../../shared/components/KpiCard.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

export function OverviewDashboardPage() {
  const [audits, setAudits] = useState<PlatformAuditItem[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [summary, setSummary] = useState<ProductProjectionSummary | null>(null);
  const [pageAccessSummary, setPageAccessSummary] = useState<ProductEventSummary | null>(null);
  const [businessSummary, setBusinessSummary] = useState<ProductEventSummary | null>(null);
  const [qoeSummary, setQoeSummary] = useState<ProductEventSummary | null>(null);
  const [behaviorMetrics, setBehaviorMetrics] = useState<RecommendationBehaviorMetrics | null>(null);
  const [drilldownItems, setDrilldownItems] = useState<ProductEventDrilldownItem[]>([]);
  const [l1l4Metrics, setL1l4Metrics] = useState<ProductMetricItem[]>([]);
  const [growth, setGrowth] = useState<GrowthOverviewResponse | null>(null);
  const [growthError, setGrowthError] = useState<RuntimeError | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
    const now = new Date();
    const rawFrom = new Date(now.getTime() - 15 * 60 * 1000).toISOString();
    const rawTo = now.toISOString();
    const closedTo = new Date(now);
    closedTo.setUTCMinutes(0, 0, 0);
    const closedFrom = new Date(closedTo.getTime() - 24 * 60 * 60 * 1000).toISOString();
    Promise.all([
      fetchPlatformAudits(),
      fetchProductWorkflows(),
      fetchReleases(),
      fetchProductProjectionSummary(),
      fetchProductEventSummary({ eventType: 'page_open', from: closedFrom, to: closedTo.toISOString() }),
      fetchProductEventSummary({ from: closedFrom, to: closedTo.toISOString() }),
      fetchProductEventSummary({ eventType: 'video_playback_qoe', from: closedFrom, to: closedTo.toISOString() }),
      fetchRecommendationBehaviorMetrics(),
      fetchProductEventDrilldown({ from: rawFrom, to: rawTo, limit: 6 }),
      fetchProductL1L4Metrics({}),
    ])
      .then(([auditItems, workflowItems, releaseItems, summaryItem, pageAccessItem, businessItem, qoeItem, behaviorItem, drilldown, l1l4Payload]) => {
        setAudits(auditItems);
        setWorkflows(workflowItems);
        setReleases(releaseItems);
        setSummary(summaryItem);
        setPageAccessSummary(pageAccessItem);
        setBusinessSummary(businessItem);
        setQoeSummary(qoeItem);
        setBehaviorMetrics(behaviorItem);
        setDrilldownItems(drilldown.items);
        setL1l4Metrics(l1l4Payload.items);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });
    fetchGrowthOverview(30)
      .then((payload) => {
        setGrowth(payload);
        setGrowthError(null);
      })
      .catch((error) => {
        setGrowth(null);
        setGrowthError(coerceRuntimeError(error));
      });
  }, []);

  const queueItems = useMemo(
    () =>
      workflows.slice(0, 3).map((item) => ({
        title: `${item.objectType} / ${item.objectId}`,
        subtitle: `workflow=${item.workflowId} · state=${item.state}`,
        status: item.state.includes('pending') || item.state.includes('review') ? 'warning' : 'success',
      })),
    [workflows],
  );
  const moderationTrend = useMemo(
    () => [
      {
        day: 'now',
        created: workflows.length,
        resolved: workflows.filter((item) => ['closed', 'completed', 'active', 'approved', 'recovered'].includes(item.state)).length,
        slaRisk: summary?.pendingDualReview ?? 0,
      },
    ],
    [summary?.pendingDualReview, workflows],
  );
  // 只展示控制面真实返回的发布字段；SLO 成功率/延迟需待 Prometheus recording rule 落点后接入，
  // 在此之前显式标注「暂无数据」，禁止用 index 合成趋势冒充真实健康度（T7.1）。
  const rolloutHealthRows = useMemo(
    () =>
      releases.slice(0, 6).map((release) => ({
        releaseId: release.releaseId,
        service: release.service,
        stage:
          release.currentStage != null
            ? `${release.currentStage}%`
            : release.grayStages.length > 0
              ? `${release.grayStages[release.grayStages.length - 1]}%`
              : '—',
        state: release.stageState ?? release.releaseState,
      })),
    [releases],
  );
  const l1l4ByLevel = useMemo(() => {
    const map = new Map<string, ProductMetricItem>();
    l1l4Metrics.forEach((item) => {
      if (!map.has(item.level)) {
        map.set(item.level, item);
      }
    });
    return map;
  }, [l1l4Metrics]);
  const hottestPage = useMemo(() => {
    const entries = Object.entries(pageAccessSummary?.dimensions.pageName ?? {});
    return entries.sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'n/a';
  }, [pageAccessSummary]);
  const behaviorTotal = useMemo(
    () => behaviorMetrics?.series.reduce((total, item) => total + item.value, 0) ?? 0,
    [behaviorMetrics],
  );
  const behaviorStates = useMemo(
    () => new Set(behaviorMetrics?.series.map((item) => item.labels.state).filter(Boolean) ?? []).size,
    [behaviorMetrics],
  );
  const pageUsageRows = useMemo(
    () =>
      Object.entries(pageAccessSummary?.dimensions.pageName ?? {})
        .sort(([, left], [, right]) => right - left)
        .slice(0, 8),
    [pageAccessSummary],
  );
  const funnelRows = useMemo(() => {
    const dimensions = businessSummary?.dimensions ?? {};
    const rows = [
      ['journey', dimensions.journey ?? {}],
      ['action', dimensions.action ?? {}],
      ['result', dimensions.result ?? {}],
    ] as const;
    return rows.flatMap(([stage, values]) =>
      Object.entries(values)
        .sort(([, left], [, right]) => right - left)
        .slice(0, 4)
        .map(([name, count]) => ({ stage, name, count })),
    );
  }, [businessSummary]);

  return (
    <PageScaffold
      title="统一运营与平台总览"
      subtitle="对齐 App 语义风格的统一门户首页，收口治理、增长、配置发布、灰度与审计，保证问题可发现、可定位、可回滚。"
      meta={
        <>
          <span className="badge badge--neutral">总览 / Dashboard</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '控制面已连接' : '等待控制面'}
          </span>
          <span className="badge badge--warning">{summary?.pendingDualReview ?? 0} 个流程接近 SLA</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实总览数据已接入' : '等待控制面连接'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
    >
      <div className="section-grid section-grid--cards">
        <KpiCard
          label="待处理治理案例"
          value={String(workflows.length)}
          icon={<ShieldCheck size={20} color="#2563EB" />}
          trendLabel={`${summary?.pendingDualReview ?? 0} 个需双签`}
          trendTone="warning"
          description="治理、申诉、恢复与实验工作流统一汇总到总览。"
        />
        <KpiCard
          label="运行中实验"
          value={String(workflows.filter((item) => item.objectType === 'experiment').length)}
          icon={<Sparkles size={20} color="#2563EB" />}
          trendLabel="来自真实工作流"
          trendTone="positive"
          description="覆盖发现页 IA、推荐扶持和召回策略。"
        />
        <KpiCard
          label="页面访问事件"
          value={String(pageAccessSummary?.totalCount ?? 0)}
          icon={<Activity size={20} color="#2563EB" />}
          trendLabel={`热点页面 ${hottestPage}`}
          trendTone="positive"
          description="来自统一 event ingestion 的 page access / perf 主事实源。"
        />
        <KpiCard
          label="页面访问会话"
          value={String(pageAccessSummary?.sessionCount ?? 0)}
          icon={<Activity size={20} color="#16A34A" />}
          trendLabel="跨迟到增量合并 HLL"
          trendTone="positive"
          description="会话数由无身份 HyperLogLog 草图合并计算，不直接累加分片 UV。"
        />
        <KpiCard
          label="SLA 风险队列"
          value={String(summary?.pendingDualReview ?? 0)}
          icon={<AlertTriangle size={20} color="#F59E0B" />}
          trendLabel="待复核队列"
          trendTone="warning"
          description="主要集中在恢复案例补证据和人工复核。"
        />
        <KpiCard
          label="推荐反馈总量"
          value={String(behaviorTotal)}
          icon={<Activity size={20} color="#16A34A" />}
          trendLabel={`${behaviorStates} 类反馈状态`}
          trendTone="positive"
          description="直接读取 recommendation_behavior_by_attribution_total，不再伪装为 Ops 事件。"
        />
      </div>

      <SectionCard title="五栏小趣 L1-L4 指标入口" subtitle="产品、业务、系统、基础设施四层指标使用统一口径">
        <div className="section-grid section-grid--cards">
          {(['L1', 'L2', 'L3', 'L4'] as const).map((level) => {
            const m = l1l4ByLevel.get(level);
            const iconMap = {
              L1: <Sparkles size={20} color="#2563EB" />,
              L2: <Activity size={20} color="#16A34A" />,
              L3: <ShieldCheck size={20} color="#2563EB" />,
              L4: <AlertTriangle size={20} color="#F59E0B" />,
            };
            return (
              <KpiCard
                key={level}
                label={m ? `${level} ${m.label}` : level}
                value={m ? `${m.value}${m.unit}` : 'n/a'}
                icon={iconMap[level]}
                trendLabel={m?.trend ?? 'n/a'}
                trendTone={m?.status === 'warning' ? 'warning' : 'positive'}
                description={m?.description ?? '等待控制面数据。'}
              />
            );
          })}
        </div>
        <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
          <Link className="button button--primary" to="/product/l1-l4/environment">
            进入四层指标页
          </Link>
        </div>
      </SectionCard>

      <SectionCard
        title="用户规模与留存（user_activity_daily）"
        subtitle="DAU/WAU/MAU、PV 与 D1/D7 留存来自天级活跃聚合（sessionId actor 段去重），业界标准口径"
      >
        {growthError ? <RuntimeErrorBadge error={growthError} /> : null}
        <div className="section-grid section-grid--cards">
          <KpiCard
            label="今日 DAU"
            value={String(growth?.todayDau ?? 0)}
            icon={<Activity size={20} color="#2563EB" />}
            trendLabel={`PV ${growth?.todayPv ?? 0}`}
            trendTone="positive"
            description="当日 distinct 活跃用户（actorHash 去重）。"
          />
          <KpiCard
            label="WAU / MAU"
            value={`${growth?.wau ?? 0} / ${growth?.mau ?? 0}`}
            icon={<Sparkles size={20} color="#16A34A" />}
            trendLabel="7 / 30 天窗口 union 去重"
            trendTone="positive"
            description="周活与月活（跨日 union 去重，非累加）。"
          />
          <KpiCard
            label="D1 留存"
            value={`${(growth?.d1RetentionPercent ?? 0).toFixed(1)}%`}
            icon={<ShieldCheck size={20} color="#2563EB" />}
            trendLabel="cohort ∩ 次日活跃"
            trendTone={(growth?.d1RetentionPercent ?? 0) >= 30 ? 'positive' : 'warning'}
            description="首见 cohort 的次日回访比例。"
          />
          <KpiCard
            label="D7 留存"
            value={`${(growth?.d7RetentionPercent ?? 0).toFixed(1)}%`}
            icon={<AlertTriangle size={20} color="#F59E0B" />}
            trendLabel="cohort ∩ 第 7 日活跃"
            trendTone={(growth?.d7RetentionPercent ?? 0) >= 15 ? 'positive' : 'warning'}
            description="首见 cohort 的第 7 日回访比例。"
          />
        </div>
        <div style={{ width: '100%', height: 240, marginTop: 16 }}>
          <ResponsiveContainer>
            <AreaChart data={growth?.days ?? []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" hide />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Area type="monotone" dataKey="dau" stroke="#2563EB" fill="#DBEAFE" name="DAU" />
              <Area type="monotone" dataKey="newActors" stroke="#16A34A" fill="#DCFCE7" name="新增" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </SectionCard>

      <div className="section-grid section-grid--two">
        <SectionCard title="治理负载与处理趋势" subtitle="当前控制面闭合窗口的创建量、解决量和 SLA 风险">
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <AreaChart data={moderationTrend}>
                <CartesianGrid stroke="rgba(17, 24, 39, 0.08)" />
                <XAxis dataKey="day" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Area type="monotone" dataKey="created" stackId="1" stroke="#2563EB" fill="rgba(37, 99, 235, 0.18)" />
                <Area type="monotone" dataKey="resolved" stackId="2" stroke="#16A34A" fill="rgba(22, 163, 74, 0.18)" />
                <Area type="monotone" dataKey="slaRisk" stackId="3" stroke="#F59E0B" fill="rgba(245, 158, 11, 0.18)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="统一工作台" subtitle="优先处理需要审批、补证据和观察的对象">
          <div className="stack-list">
            {queueItems.map((item) => (
              <div className="case-item" key={item.title}>
                <div>
                  <p className="item-title">{item.title}</p>
                  <p className="item-subtitle">{item.subtitle}</p>
                </div>
                <span className={`badge badge--${item.status}`}>{item.status}</span>
              </div>
            ))}
            {queueItems.length === 0 ? (
              <div className="case-item">
                <div>
                  <p className="item-title">等待统一工作台数据</p>
                  <p className="item-subtitle">控制面可达后将展示待审批、补证据与回滚观察对象。</p>
                </div>
                <span className="badge badge--warning">offline</span>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <div className="section-grid section-grid--two">
        <SectionCard title="业务埋点总览" subtitle="产品日志与推荐行为保持正交事实源">
          <table className="table">
            <thead>
              <tr>
                <th>指标</th>
                <th>总量</th>
                <th>关键维度</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>page access</td>
                <td>{pageAccessSummary?.totalCount ?? 0}</td>
                <td>{Object.keys(pageAccessSummary?.dimensions.pageName ?? {}).slice(0, 3).join(', ') || 'n/a'}</td>
              </tr>
              <tr>
                <td>page access sessions</td>
                <td>{pageAccessSummary?.sessionCount ?? 0}</td>
                <td>merged sessionHll</td>
              </tr>
              <tr>
                <td>recommendation behavior</td>
                <td>{behaviorTotal}</td>
                <td>{behaviorMetrics?.source ?? 'n/a'}</td>
              </tr>
              <tr>
                <td>产品日志 freshness</td>
                <td>{pageAccessSummary?.freshness ?? 'n/a'}</td>
                <td>{pageAccessSummary?.sourceKind ?? 'n/a'}</td>
              </tr>
            </tbody>
          </table>
        </SectionCard>

        <SectionCard title="产品事件下钻" subtitle="最近 15 分钟 SLS raw 样本；sessionId 默认掩码">
          <div className="stack-list">
            {drilldownItems.map((item) => (
              <div className="timeline-item" key={item.rowKey}>
                <div>
                  <p className="item-title">
                    {item.logType} / {item.eventType}
                  </p>
                  <p className="item-subtitle">
                    {item.pageName} · {item.appVersion} · {item.networkClass} · {item.occurredAt}
                  </p>
                </div>
              </div>
            ))}
            {drilldownItems.length === 0 ? (
              <div className="timeline-item">
                <div>
                  <p className="item-title">等待统一事件下钻数据</p>
                  <p className="item-subtitle">接入 product-ops 统一事件查询后会展示最近样本。</p>
                </div>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="运营基本盘：PV / 会话 UV / 漏斗 / 页面使用强度"
        subtitle="24 小时闭合窗口；PV、UV、漏斗与轻量页面热力均来自统一事件事实源"
      >
        <div className="section-grid section-grid--two">
          <div>
            <h3 className="item-title">PV / 会话 UV / QoE</h3>
            <div className="stack-list">
              <div className="case-item">
                <span>page_open PV</span>
                <strong>{pageAccessSummary?.totalCount ?? 0}</strong>
              </div>
              <div className="case-item">
                <span>session UV</span>
                <strong>{pageAccessSummary?.sessionCount ?? 0}</strong>
              </div>
              <div className="case-item">
                <span>video QoE samples</span>
                <strong>{qoeSummary?.totalCount ?? 0}</strong>
              </div>
            </div>
            <p className="item-subtitle">
              数据窗口：{pageAccessSummary?.actualFrom ?? 'n/a'} → {pageAccessSummary?.actualTo ?? 'n/a'}；
              {pageAccessSummary?.sourceKind ?? 'n/a'}
            </p>
          </div>
          <div>
            <h3 className="item-title">journey → action → result 漏斗</h3>
            <div className="stack-list">
              {funnelRows.map((row) => (
                <div className="case-item" key={`${row.stage}:${row.name}`}>
                  <span>{row.stage} / {row.name}</span>
                  <strong>{row.count}</strong>
                </div>
              ))}
              {funnelRows.length === 0 ? <div className="item-subtitle">暂无闭合窗口漏斗事件</div> : null}
            </div>
          </div>
        </div>
        <div style={{ marginTop: 16 }}>
          <h3 className="item-title">页面使用强度（pageName 聚合热力）</h3>
          <div className="stack-list">
            {pageUsageRows.map(([pageName, count]) => (
              <div className="case-item" key={pageName}>
                <span>{pageName}</span>
                <strong>{count}</strong>
              </div>
            ))}
            {pageUsageRows.length === 0 ? <div className="item-subtitle">暂无页面访问事件</div> : null}
          </div>
        </div>
      </SectionCard>

      <div className="section-grid section-grid--two">
        <SectionCard title="配置灰度健康" subtitle="仅展示控制面真实回读的阶段与状态；成功率和延迟等待 Prometheus SLO 落点">
          <table className="table">
            <thead>
              <tr>
                <th>服务</th>
                <th>当前阶段</th>
                <th>状态</th>
                <th>成功率</th>
                <th>延迟 P95</th>
              </tr>
            </thead>
            <tbody>
              {rolloutHealthRows.length === 0 ? (
                <tr>
                  <td colSpan={5}>暂无进行中的灰度发布</td>
                </tr>
              ) : (
                rolloutHealthRows.map((row) => (
                  <tr key={row.releaseId}>
                    <td>{row.service}</td>
                    <td>{row.stage}</td>
                    <td>{row.state}</td>
                    <td>暂无数据</td>
                    <td>暂无数据</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </SectionCard>

        <SectionCard title="最近审计事件" subtitle="危险动作、双签动作和放量动作统一可检索">
          <div className="stack-list">
            {audits.slice(0, 5).map((event) => (
              <div className="timeline-item" key={`${event.objectType}:${event.objectId}:${event.at}`}>
                <div>
                  <p className="item-title">{event.objectType} / {event.action}</p>
                  <p className="item-subtitle">
                    {event.at} · actor={event.actor} · env={event.environment}
                  </p>
                </div>
              </div>
            ))}
            {audits.length === 0 ? (
              <div className="timeline-item">
                <div>
                  <p className="item-title">等待最近审计事件</p>
                  <p className="item-subtitle">平台控制面可达后将展示危险动作与放量事件。</p>
                </div>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <SectionCard title="控制面二级入口" subtitle="配置中心与四层指标已升级为可选择、可下钻的二级体验">
        <div className="section-grid section-grid--two">
          <div className="policy-item">
            <div>
              <p className="item-title">配置与可靠性</p>
              <p className="item-subtitle">查看四层配置中心、配置包、实例漂移与磁盘兜底一致性。</p>
            </div>
            <Link className="button button--primary" to="/platform/config/layers">
              进入配置中心
            </Link>
          </div>
          <div className="policy-item">
            <div>
              <p className="item-title">四层指标</p>
              <p className="item-subtitle">从环境整体一路下钻到集群、服务、实例的 L1-L4 指标。</p>
            </div>
            <Link className="button button--primary" to="/product/l1-l4/environment">
              进入四层指标
            </Link>
          </div>
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
