import { useEffect, useState } from 'react';
import { Activity, BellRing, Siren } from 'lucide-react';
import { Link } from 'react-router-dom';

import {
  ackAlert,
  fetchActiveAlerts,
  fetchPlatformAudits,
  fetchPlatformTriageSummary,
  fetchPlatformProjectionSummary,
  fetchRuntimeLogDrilldown,
  fetchRuntimeLogSummary,
  type ActiveAlertItem,
  type ControlPlaneBacklogCandidate,
  type PlatformAuditItem,
  type PlatformProjectionSummary,
  type PlatformTriageSummaryResponse,
  type RuntimeLogDrilldown,
  type RuntimeLogSummary,
} from '../../shared/api/controlPlane.js';
import { KpiCard } from '../../shared/components/KpiCard.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { usePortalScope } from '../../shared/layout/PortalContext.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

function alertTone(status: string): string {
  if (status === 'firing') {
    return 'danger';
  }
  if (status === 'acknowledged') {
    return 'warning';
  }
  return 'success';
}

export function PlatformObservabilityPage() {
  const { environment } = usePortalScope();
  const [activeAlerts, setActiveAlerts] = useState<ActiveAlertItem[]>([]);
  const [audits, setAudits] = useState<PlatformAuditItem[]>([]);
  const [summary, setSummary] = useState<PlatformProjectionSummary | null>(null);
  const [triage, setTriage] = useState<PlatformTriageSummaryResponse | null>(null);
  const [runtimeLogSummary, setRuntimeLogSummary] = useState<RuntimeLogSummary | null>(null);
  const [runtimeLogDrilldown, setRuntimeLogDrilldown] = useState<RuntimeLogDrilldown | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeLogsReady, setRuntimeLogsReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const [runtimeLogsError, setRuntimeLogsError] = useState<RuntimeError | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actorHashQuery, setActorHashQuery] = useState('');
  const [messageQuery, setMessageQuery] = useState('');

  const loadControlPlane = () =>
    Promise.all([
      fetchActiveAlerts(),
      fetchPlatformAudits(),
      fetchPlatformProjectionSummary(),
      fetchPlatformTriageSummary({ env: environment }),
    ])
      .then(([alertItems, auditItems, summaryItem, triageItem]) => {
        setActiveAlerts(alertItems);
        setAudits(auditItems);
        setSummary(summaryItem);
        setTriage(triageItem);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });

  useEffect(() => {
    void loadControlPlane();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [environment]);

  const loadRuntimeLogs = (filters: { actorHash?: string; messageContains?: string } = {}) => {
    const to = new Date();
    const from = new Date(to.getTime() - 24 * 60 * 60 * 1000);
    const query = { from: from.toISOString(), to: to.toISOString() };
    return Promise.all([
      fetchRuntimeLogSummary(query),
      fetchRuntimeLogDrilldown({
        ...query,
        limit: 12,
        actorHash: filters.actorHash || undefined,
        messageContains: filters.messageContains || undefined,
      }),
    ])
      .then(([summaryItem, drilldownItem]) => {
        setRuntimeLogSummary(summaryItem);
        setRuntimeLogDrilldown(drilldownItem);
        setRuntimeLogsReady(true);
        setRuntimeLogsError(null);
      })
      .catch((error) => {
        setRuntimeLogsReady(false);
        setRuntimeLogsError(coerceRuntimeError(error));
      });
  };

  useEffect(() => {
    void loadRuntimeLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAck = async (fingerprint: string) => {
    try {
      const acked = await ackAlert(fingerprint);
      setActionMessage(`告警 ${acked.alertName || fingerprint} 已由当前 principal 认领并落审计。`);
      setRuntimeError(null);
      await loadControlPlane();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  const firingAlerts = activeAlerts.filter((item) => item.status === 'firing');
  const backlogCandidates = triage?.backlogCandidates ?? [];
  const runtimeSignals = Object.entries(runtimeLogSummary?.dimensions.signal ?? {})
    .sort(([, left], [, right]) => right - left)
    .slice(0, 6);

  return (
    <PageScaffold
      title="Platform Ops / 可观测与 SLO"
      subtitle="活动告警来自 Alertmanager webhook 回流，运行诊断来自统一遥测链路；不展示任何合成曲线。"
      meta={
        <>
          <span className="badge badge--neutral">alerts / triage / runtime logs</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实可观测数据已接入' : '等待平台控制面连接'}
          </span>
          <span className={`badge ${firingAlerts.length > 0 ? 'badge--danger' : 'badge--success'}`}>
            firing={firingAlerts.length}
          </span>
          <span className="badge badge--neutral">env={environment}</span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      footer={actionMessage ? <span className="badge badge--warning">{actionMessage}</span> : undefined}
    >
      <div className="section-grid section-grid--cards">
        <KpiCard
          label="活动告警"
          value={String(summary?.activeAlerts ?? activeAlerts.filter((item) => item.status !== 'resolved').length)}
          icon={<BellRing size={20} color="#DC2626" />}
          trendLabel={`${firingAlerts.length} 条待认领`}
          trendTone={firingAlerts.length > 0 ? 'negative' : 'positive'}
          description="Alertmanager 推送的 firing/acknowledged 告警集合。"
        />
        <KpiCard
          label="审批与回滚事件"
          value={String(summary?.approvalCount ?? 0)}
          icon={<Siren size={20} color="#DC2626" />}
          trendLabel={`${summary?.auditCount ?? 0} 条审计事件`}
          trendTone="warning"
          description="高风险操作的审批与审计已统一沉淀到平台控制面。"
        />
        <KpiCard
          label="24h 运行诊断"
          value={String(runtimeLogSummary?.totalCount ?? 0)}
          icon={<Activity size={20} color="#7C3AED" />}
          trendLabel={runtimeLogsReady ? `${runtimeSignals.length} 个高频 signal` : '等待运行日志查询权限'}
          trendTone={runtimeLogsError ? 'warning' : 'positive'}
          description="端、云、数据和 Portal 统一记录的 runtime / exception 信号。"
        />
      </div>

      <SectionCard
        title="活动告警与认领"
        subtitle="firing → ack → resolved 状态机；每次 ack 由登录 principal 落审计，可在审计页回溯"
      >
        <div className="stack-list">
          {activeAlerts.map((alert) => (
            <div className="policy-item" key={alert.fingerprint}>
              <div>
                <p className="item-title">
                  {alert.alertName || alert.fingerprint}
                  {alert.service ? ` · ${alert.service}` : ''}
                </p>
                <p className="item-subtitle">
                  severity={alert.severity || 'unknown'} · startsAt={alert.startsAt ?? '-'}
                  {alert.ackedBy ? ` · ackedBy=${alert.ackedBy}` : ''}
                </p>
                {alert.annotations.summary ? <p className="item-subtitle">{alert.annotations.summary}</p> : null}
              </div>
              <div className="badge-row">
                <span className={`badge badge--${alertTone(alert.status)}`}>{alert.status}</span>
                {alert.status === 'firing' ? (
                  <button className="button button--primary" onClick={() => void handleAck(alert.fingerprint)}>
                    认领
                  </button>
                ) : null}
              </div>
            </div>
          ))}
          {activeAlerts.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">当前无活动告警</p>
                <p className="item-subtitle">Alertmanager receiver 指向控制面 ingest 端点后，firing 告警会实时出现在这里。</p>
              </div>
              <span className="badge badge--success">quiet</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard title="最近审计" subtitle="发布、配置、告警认领等危险动作共享一条时间线">
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

      <SectionCard
        title="运行诊断统一视图"
        subtitle="默认展示最近 24 小时聚合和三天内原始明细；关联键默认脱敏，只有持有敏感诊断权限时才可显式展开。按用户（actorHash）检索需要敏感诊断权限。"
      >
        <div className="toolbar-row">
          <label className="toolbar-field">
            <span>按用户（actorHash）</span>
            <input
              value={actorHashQuery}
              placeholder="a.xxxx（敏感权限）"
              onChange={(event) => setActorHashQuery(event.target.value)}
            />
          </label>
          <label className="toolbar-field">
            <span>日志文本</span>
            <input
              value={messageQuery}
              placeholder="消息子串检索"
              onChange={(event) => setMessageQuery(event.target.value)}
            />
          </label>
          <button
            className="button button--primary"
            onClick={() =>
              void loadRuntimeLogs({
                actorHash: actorHashQuery.trim(),
                messageContains: messageQuery.trim(),
              })
            }
          >
            检索明细
          </button>
        </div>
        <div className="stack-list">
          <div className="policy-item">
            <div>
              <p className="item-title">聚合来源：{runtimeLogSummary?.sourceKind ?? 'unavailable'}</p>
              <p className="item-subtitle">
                freshness={runtimeLogSummary?.freshness ?? 'unknown'} · window={runtimeLogSummary?.actualFrom ?? '-'} → {runtimeLogSummary?.actualTo ?? '-'}
              </p>
            </div>
            <RuntimeErrorBadge error={runtimeLogsError} />
          </div>
          {runtimeSignals.map(([signal, count]) => (
            <div className="policy-item" key={signal}>
              <div>
                <p className="item-title">{signal}</p>
                <p className="item-subtitle">跨语言登记 signal · last 24h</p>
              </div>
              <span className="badge badge--neutral">{count}</span>
            </div>
          ))}
          {(runtimeLogDrilldown?.items ?? []).map((item) => (
            <div className="timeline-item" key={item.rowKey}>
              <div>
                <p className="item-title">{item.severity} · {item.signal}</p>
                <p className="item-subtitle">
                  {item.occurredAt} · {item.resource.sourceType}/{item.resource.service} · {item.errorCode ?? 'no-error-code'}
                </p>
                <p className="item-subtitle">{item.message}</p>
              </div>
            </div>
          ))}
          {runtimeSignals.length === 0 && (runtimeLogDrilldown?.items.length ?? 0) === 0 ? (
            <div className="timeline-item">
              <div>
                <p className="item-title">暂无可查询的运行诊断</p>
                <p className="item-subtitle">先通过 alpha / beta / gamma 验收流上报已登记 signal，再在此处按 signal、错误码和指纹下钻。</p>
              </div>
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
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
