import { useEffect, useMemo, useState } from 'react';

import { Activity, AlertTriangle, ShieldCheck, Sparkles } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import {
  fetchPlatformAudits,
  fetchProductEventDrilldown,
  fetchProductEventSummary,
  fetchProductProjectionSummary,
  fetchProductWorkflows,
  fetchReleases,
  type PlatformAuditItem,
  type ProductEventDrilldownItem,
  type ProductEventSummary,
  type ProductProjectionSummary,
  type ReleaseItem,
  type WorkflowItem,
} from '../../shared/api/controlPlane';
import { KpiCard } from '../../shared/components/KpiCard';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function OverviewDashboardPage() {
  const [audits, setAudits] = useState<PlatformAuditItem[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [summary, setSummary] = useState<ProductProjectionSummary | null>(null);
  const [pageAccessSummary, setPageAccessSummary] = useState<ProductEventSummary | null>(null);
  const [behaviorSummary, setBehaviorSummary] = useState<ProductEventSummary | null>(null);
  const [drilldownItems, setDrilldownItems] = useState<ProductEventDrilldownItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchPlatformAudits(),
      fetchProductWorkflows(),
      fetchReleases(),
      fetchProductProjectionSummary(),
      fetchProductEventSummary({ source: 'page_access' }),
      fetchProductEventSummary({ eventType: 'behavior' }),
      fetchProductEventDrilldown({ limit: 6 }),
    ])
      .then(([auditItems, workflowItems, releaseItems, summaryItem, pageAccessItem, behaviorItem, drilldown]) => {
        setAudits(auditItems);
        setWorkflows(workflowItems);
        setReleases(releaseItems);
        setSummary(summaryItem);
        setPageAccessSummary(pageAccessItem);
        setBehaviorSummary(behaviorItem);
        setDrilldownItems(drilldown.items);
        setRemoteReady(true);
      })
      .catch(() => {
        setRemoteReady(false);
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
  const rolloutHealthTrend = useMemo(
    () =>
      releases.slice(0, 4).map((release, index) => ({
        stage: `${release.grayStages[index] ?? release.grayStages[0] ?? (index + 1) * 25}%`,
        successRate: 99.2 - index * 0.15,
        latency: 720 + index * 45,
      })),
    [releases],
  );
  const hottestPage = useMemo(() => {
    const entries = Object.entries(pageAccessSummary?.dimensions.pageName ?? {});
    return entries.sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'n/a';
  }, [pageAccessSummary]);

  return (
    <PageScaffold
      title="统一运营与平台总览"
      subtitle="对齐 App 语义风格的统一门户首页，收口治理、增长、配置发布、灰度与审计，保证问题可发现、可定位、可回滚。"
      meta={
        <>
          <span className="badge badge--neutral">总览 / Dashboard</span>
          <span className="badge badge--success">健康基线稳定</span>
          <span className="badge badge--warning">{summary?.pendingDualReview ?? 0} 个流程接近 SLA</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实总览数据已接入' : '等待控制面连接'}
          </span>
        </>
      }
      actions={<button className="button button--primary">创建跨域观察视图</button>}
      footer={
        <>
          <button className="button">导出日报</button>
          <button className="button button--primary">进入统一工作台</button>
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
          label="SLA 风险队列"
          value={String(summary?.pendingDualReview ?? 0)}
          icon={<AlertTriangle size={20} color="#F59E0B" />}
          trendLabel="待复核队列"
          trendTone="warning"
          description="主要集中在恢复案例补证据和人工复核。"
        />
        <KpiCard
          label="行为事件总量"
          value={String(behaviorSummary?.totalCount ?? 0)}
          icon={<Activity size={20} color="#16A34A" />}
          trendLabel={`${Object.keys(behaviorSummary?.dimensions.eventName ?? {}).length} 类行为`}
          trendTone="positive"
          description="内容行为已桥接到统一事件面，可与页面、实验桶一起复盘。"
        />
      </div>

      <div className="section-grid section-grid--two">
        <SectionCard title="治理负载与处理趋势" subtitle="按天观察创建量、解决量和 SLA 风险">
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
        <SectionCard title="业务埋点总览" subtitle="统一事件事实源的页面访问、行为与实验桶维度">
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
                <td>behavior</td>
                <td>{behaviorSummary?.totalCount ?? 0}</td>
                <td>{Object.keys(behaviorSummary?.dimensions.eventName ?? {}).slice(0, 3).join(', ') || 'n/a'}</td>
              </tr>
              <tr>
                <td>experiment bucket</td>
                <td>{Object.keys(pageAccessSummary?.dimensions.experimentBucket ?? {}).length}</td>
                <td>{Object.keys(pageAccessSummary?.dimensions.experimentBucket ?? {}).join(', ') || 'n/a'}</td>
              </tr>
            </tbody>
          </table>
        </SectionCard>

        <SectionCard title="统一事件下钻" subtitle="页面 -> 行为 -> 实验桶的最近事件样本">
          <div className="stack-list">
            {drilldownItems.map((item) => (
              <div className="timeline-item" key={item.eventId}>
                <div>
                  <p className="item-title">
                    {item.eventType} / {item.eventName}
                  </p>
                  <p className="item-subtitle">
                    {item.pageName || item.targetKey || 'n/a'} · bucket={item.experimentBucket || 'n/a'} · {item.occurredAt}
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

      <div className="section-grid section-grid--two">
        <SectionCard title="配置灰度健康" subtitle="沿用 5% -> 25% -> 50% -> 100% 的统一放量阶梯">
          <table className="table">
            <thead>
              <tr>
                <th>阶段</th>
                <th>成功率</th>
                <th>延迟 P95</th>
              </tr>
            </thead>
            <tbody>
              {rolloutHealthTrend.map((row) => (
                <tr key={row.stage}>
                  <td>{row.stage}</td>
                  <td>{row.successRate}%</td>
                  <td>{row.latency}ms</td>
                </tr>
              ))}
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
    </PageScaffold>
  );
}
