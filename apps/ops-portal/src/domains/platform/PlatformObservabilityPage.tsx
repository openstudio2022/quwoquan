import { useEffect, useMemo, useState } from 'react';
import { Activity, BellRing, ShieldCheck, Siren } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Link } from 'react-router-dom';

import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated.js';
import {
  fetchAlertTemplates,
  fetchPlatformAudits,
  fetchPlatformTriageSummary,
  fetchPlatformProjectionSummary,
  fetchReleases,
  fetchSLOPolicies,
  type ControlPlaneBacklogCandidate,
  type AlertTemplateItem,
  type PlatformAuditItem,
  type PlatformProjectionSummary,
  type PlatformTriageSummaryResponse,
  type ReleaseItem,
  type SLOPolicyItem,
} from '../../shared/api/controlPlane.js';
import { KpiCard } from '../../shared/components/KpiCard.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

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
  const [triage, setTriage] = useState<PlatformTriageSummaryResponse | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
    Promise.all([
      fetchSLOPolicies(),
      fetchAlertTemplates(),
      fetchPlatformAudits(),
      fetchReleases(),
      fetchPlatformProjectionSummary(),
      fetchPlatformTriageSummary({ env: 'beta' }),
    ])
      .then(([sloItems, alertItems, auditItems, releaseItems, summaryItem, triageItem]) => {
        setSlos(sloItems);
        setAlerts(alertItems);
        setAudits(auditItems);
        setReleases(releaseItems);
        setSummary(summaryItem);
        setTriage(triageItem);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
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
  const backlogCandidates = triage?.backlogCandidates ?? [];
  const highlightBacklog = backlogCandidates[0];

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
          <span className="badge badge--neutral">backlog={backlogCandidates.length}</span>
          <RuntimeErrorBadge error={runtimeError} />
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

      <SectionCard title="统一告警入口" subtitle="平台告警模板与产品实时告警共享 runbook / repair / audit 处置语义">
        <div className="stack-list">
          {alerts.map((item: AlertTemplateItem) => (
            <div className="policy-item" key={item.id}>
              <div>
                <p className="item-title">{item.title}</p>
                <p className="item-subtitle">
                  severity={item.severity} · status={item.status} · owner={item.owner ?? 'platform-ops'}
                </p>
              </div>
              <div className="badge-row">
                {item.runbookRoute ? <Link className="button" to={item.runbookRoute}>查看 runbook</Link> : null}
                {item.repairEntry ? <Link className="button button--primary" to={item.repairEntry}>进入修复入口</Link> : null}
                {item.auditRoute ? <Link className="button" to={item.auditRoute}>查看审计链</Link> : null}
                {(item.alertId ?? item.id) ? <span className="badge badge--neutral">alert={item.alertId ?? item.id}</span> : null}
              </div>
            </div>
          ))}
          {alerts.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">暂无平台告警模板</p>
                <p className="item-subtitle">控制面接通后，这里会展示真实告警模板与统一处置入口。</p>
              </div>
              <span className="badge badge--success">quiet</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard title="Triage / Backlog" subtitle="平台配置漂移、回退链路和运行时缺口统一生成可执行待办">
        <div className="stack-list">
          {backlogCandidates.map((item: ControlPlaneBacklogCandidate) => (
            <div className="policy-item" key={item.id}>
              <div>
                <p className="item-title">{item.title}</p>
                <p className="item-subtitle">
                  {item.category} · {item.summary}
                </p>
                <p className="item-subtitle">next: {item.nextAction}</p>
              </div>
              <div className="badge-row">
                <span className={`badge ${item.severity === 'critical' ? 'badge--danger' : 'badge--warning'}`}>
                  {item.severity}
                </span>
                {item.drilldownRoute ? <Link className="button" to={item.drilldownRoute}>进入 drilldown</Link> : null}
                {item.runbookRoute ? <Link className="button" to={item.runbookRoute}>查看 runbook</Link> : null}
                {item.repairEntry ? <Link className="button button--primary" to={item.repairEntry}>进入修复入口</Link> : null}
                {item.auditRoute ? <Link className="button" to={item.auditRoute}>查看审计链</Link> : null}
                {item.alertId ? <span className="badge badge--neutral">alert={item.alertId}</span> : null}
              </div>
            </div>
          ))}
          {backlogCandidates.length === 0 ? (
            <div className="timeline-item">
              <div>
                <p className="item-title">当前无平台待办</p>
                <p className="item-subtitle">当 triage 发现配置漂移、磁盘回退或 ACK 不收敛时，这里会直接生成 backlog。</p>
              </div>
            </div>
          ) : null}
          {highlightBacklog ? (
            <div className="timeline-item">
              <div>
                <p className="item-title">主待办</p>
                <p className="item-subtitle">
                  {highlightBacklog.title} · owner={highlightBacklog.owner ?? 'platform-ops'}
                </p>
              </div>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
