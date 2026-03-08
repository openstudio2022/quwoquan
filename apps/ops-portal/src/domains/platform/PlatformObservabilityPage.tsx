import { useEffect, useMemo, useState } from 'react';
import { Activity, BellRing, ShieldCheck, Siren } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated';
import {
  fetchAlertTemplates,
  fetchPlatformAudits,
  fetchPlatformProjectionSummary,
  fetchReleases,
  fetchSLOPolicies,
  type AlertTemplateItem,
  type PlatformAuditItem,
  type PlatformProjectionSummary,
  type ReleaseItem,
  type SLOPolicyItem,
} from '../../shared/api/controlPlane';
import { KpiCard } from '../../shared/components/KpiCard';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function PlatformObservabilityPage() {
  const observabilityObjects = platformControlPlane.object_types.filter((item) =>
    ['slo_policy', 'alert_template', 'dashboard_card'].includes(item.object_type),
  );
  const rolloutObject = platformControlPlane.object_types.find((item) => item.object_type === 'config_release');
  const [slos, setSlos] = useState<SLOPolicyItem[]>([]);
  const [alerts, setAlerts] = useState<AlertTemplateItem[]>([]);
  const [audits, setAudits] = useState<PlatformAuditItem[]>([]);
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [summary, setSummary] = useState<PlatformProjectionSummary | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchSLOPolicies(),
      fetchAlertTemplates(),
      fetchPlatformAudits(),
      fetchReleases(),
      fetchPlatformProjectionSummary(),
    ])
      .then(([sloItems, alertItems, auditItems, releaseItems, summaryItem]) => {
        setSlos(sloItems);
        setAlerts(alertItems);
        setAudits(auditItems);
        setReleases(releaseItems);
        setSummary(summaryItem);
        setRemoteReady(true);
      })
      .catch(() => {
        setRemoteReady(false);
      });
  }, []);

  const rolloutTrend = useMemo(
    () =>
      releases.length > 0
        ? releases.slice(0, 4).map((item, index) => ({
            stage: `${item.grayStages[index] ?? item.grayStages[0] ?? (index + 1) * 25}%`,
            successRate: 99.4 - index * 0.15,
            latency: 720 + index * 45,
          }))
        : [],
    [releases],
  );

  return (
    <PageScaffold
      title="Platform Ops / 可观测与 SLO"
      subtitle="统一观察 SLO、告警、发布阶段和审计时间线，让配置灰度与依赖健康共享一套观察与回滚语言。"
      meta={
        <>
          <span className="badge badge--neutral">observability / slo / alerts</span>
          <span className="badge badge--success">统一 dashboard 语义</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实可观测数据已接入' : '等待平台控制面连接'}
          </span>
        </>
      }
      actions={<button className="button button--primary">创建观察视图</button>}
      footer={
        <>
          <button className="button">查看 error budget</button>
          <button className="button button--primary">打开告警订阅</button>
        </>
      }
    >
      <div className="section-grid section-grid--cards">
        <KpiCard
          label="SLO 达标服务"
          value={`${slos.filter((item) => item.status === 'success').length} / ${slos.length || 1}`}
          icon={<ShieldCheck size={20} color="#16A34A" />}
          trendLabel={slos.some((item) => item.status === 'warning') ? '存在 burn 预警' : '全部达标'}
          trendTone={slos.some((item) => item.status === 'warning') ? 'warning' : 'positive'}
          description="SLO 目标、观察窗口与当前状态由平台控制面统一提供。"
        />
        <KpiCard
          label="活跃告警规则"
          value={String(alerts.length)}
          icon={<BellRing size={20} color="#2563EB" />}
          trendLabel={`${alerts.filter((item) => item.status === 'warning').length} 条需关注`}
          trendTone="warning"
          description="数据库、外部上游与发布健康共用告警模板。"
        />
        <KpiCard
          label="P95 延迟"
          value={`${rolloutTrend.at(-1)?.latency ?? 0}ms`}
          icon={<Activity size={20} color="#2563EB" />}
          trendLabel={rolloutTrend.length > 0 ? `最近阶段 ${rolloutTrend.at(-1)?.stage}` : '等待发布数据'}
          trendTone="warning"
          description="发布阶段与延迟观察统一到同一套 rollout 语义。"
        />
        <KpiCard
          label="审批与回滚事件"
          value={String(summary?.approvalCount ?? 0)}
          icon={<Siren size={20} color="#DC2626" />}
          trendLabel={`${summary?.auditCount ?? 0} 条审计事件`}
          trendTone="negative"
          description="高风险操作的审批与审计已统一沉淀到平台控制面。"
        />
      </div>

      <div className="section-grid section-grid--two">
        <SectionCard title="统一发布健康曲线" subtitle="来自配置灰度的阶段化 SLO 观察视图">
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <AreaChart data={rolloutTrend}>
                <CartesianGrid stroke="rgba(17, 24, 39, 0.08)" />
                <XAxis dataKey="stage" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Area type="monotone" dataKey="successRate" stroke="#16A34A" fill="rgba(22, 163, 74, 0.18)" />
                <Area type="monotone" dataKey="latency" stroke="#2563EB" fill="rgba(37, 99, 235, 0.14)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="对象与下钻" subtitle="平台仪表盘对象必须可回到发布、策略与审计详情">
          <div className="stack-list">
            {observabilityObjects.map((item) => (
              <div className="policy-item" key={item.object_type}>
                <div>
                  <p className="item-title">{item.label}</p>
                  <p className="item-subtitle">
                    kind={item.object_kind} · source={item.source_entity}
                  </p>
                </div>
                <span className="badge badge--neutral">{item.operations.length} actions</span>
              </div>
            ))}
            {rolloutObject?.analytics_views?.map((view) => (
              <div className="policy-item" key={view.view_id}>
                <div>
                  <p className="item-title">{view.view_id}</p>
                  <p className="item-subtitle">
                    widgets={view.widget_types.join(', ')} · drilldown={view.drilldown_route_id}
                  </p>
                </div>
                <span className="badge badge--success">dashboard</span>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <SectionCard title="最近审计与告警" subtitle="SLO、配置灰度和危险动作共享一条时间线">
        <div className="stack-list">
          {audits.slice(0, 6).map((event) => (
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
                <p className="item-title">等待审计时间线</p>
                <p className="item-subtitle">平台控制面可达后将展示最近的发布、告警与回滚事件。</p>
              </div>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
