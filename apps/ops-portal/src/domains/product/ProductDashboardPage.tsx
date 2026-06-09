import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import {
  fetchAppealCases,
  fetchModerationCases,
  fetchProductL1L4Metrics,
  fetchProductProjectionSummary,
  fetchProductTriageSummary,
  fetchRecoveryCases,
  fetchProductWorkflows,
  fetchRecommendationPolicies,
  type AppealCaseItem,
  type ControlPlaneBacklogCandidate,
  type ModerationCaseItem,
  type ProductL1L4MetricsResponse,
  type ProductProjectionSummary,
  type ProductTriageSummaryResponse,
  type RecoveryCaseItem,
  type RecommendationPolicyItem,
  type WorkflowItem,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

export function ProductDashboardPage() {
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [policies, setPolicies] = useState<RecommendationPolicyItem[]>([]);
  const [moderationCases, setModerationCases] = useState<ModerationCaseItem[]>([]);
  const [recoveryCases, setRecoveryCases] = useState<RecoveryCaseItem[]>([]);
  const [appealCases, setAppealCases] = useState<AppealCaseItem[]>([]);
  const [summary, setSummary] = useState<ProductProjectionSummary | null>(null);
  const [triage, setTriage] = useState<ProductTriageSummaryResponse | null>(null);
  const [metricsPayload, setMetricsPayload] = useState<ProductL1L4MetricsResponse | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
    Promise.all([
      fetchProductWorkflows(),
      fetchRecommendationPolicies(),
      fetchModerationCases(),
      fetchRecoveryCases(),
      fetchAppealCases(),
      fetchProductProjectionSummary(),
      fetchProductTriageSummary(),
      fetchProductL1L4Metrics(),
    ])
      .then(([workflowItems, policyItems, moderationItems, recoveryItems, appealItems, summaryItem, triageItem, metricsItem]) => {
        setWorkflows(workflowItems);
        setPolicies(policyItems);
        setModerationCases(moderationItems);
        setRecoveryCases(recoveryItems);
        setAppealCases(appealItems);
        setSummary(summaryItem);
        setTriage(triageItem);
        setMetricsPayload(metricsItem);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });
  }, []);

  const queueItems = useMemo(() => {
    return workflows
      .filter((item) => ['moderation_case', 'recovery_case', 'appeal_case', 'experiment'].includes(item.objectType))
      .slice(0, 3)
      .map((item) => ({
        title: `${item.objectType} / ${item.objectId}`,
        subtitle: `workflow=${item.workflowId} · state=${item.state}`,
        status: item.state.includes('pending') || item.state.includes('review') ? 'warning' : 'success',
      }));
  }, [workflows]);

  const backlogCandidates = triage?.backlogCandidates ?? [];
  const alertStates = metricsPayload?.alerts ?? [];
  const topAlert = alertStates[0];
  const highlightBacklog = backlogCandidates[0];
  const topMetric = metricsPayload?.items[0];

  return (
    <PageScaffold
      title="Product Ops 业务总览"
      subtitle="聚焦治理处置、增长实验与推荐运营的统一视图，并把实时 L1-L4、triage 与 backlog 直接接入主路径。"
      meta={
        <>
          <span className="badge badge--neutral">Product Ops</span>
          <span className={`badge ${topAlert?.state === 'firing' ? 'badge--warning' : 'badge--success'}`}>
            {topAlert ? `告警=${topAlert.state}` : '告警静默'}
          </span>
          <span className="badge badge--warning">双签待处理 {summary?.pendingDualReview ?? 0} 个</span>
          <span className="badge badge--neutral">backlog={backlogCandidates.length}</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实产品控制面已接入' : '等待产品控制面连接'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={
        <>
          <Link className="button" to="/product/l1-l4/environment">查看实时 L1-L4</Link>
          <Link className="button button--primary" to={highlightBacklog?.drilldownRoute ?? '/product/dashboard'}>
            {highlightBacklog ? '处理首条 backlog' : '创建策略变更'}
          </Link>
        </>
      }
      footer={
        <>
          <Link className="button" to="/product/governance">打开治理工作台</Link>
          <Link className="button button--primary" to="/product/experiments">发起实验评审</Link>
        </>
      }
    >
      <div className="metric-strip">
        <div className="metric-pill">
          <div className="metric-pill__label">今日治理结案率</div>
          <div className="metric-pill__value">
            {moderationCases.length > 0 ? `${Math.max(0, 100 - (summary?.pendingDualReview ?? 0) * 5)}%` : '0%'}
          </div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">实时指标来源</div>
          <div className="metric-pill__value">{metricsPayload?.source ?? 'snapshot'}</div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">最新 triage 事件量</div>
          <div className="metric-pill__value">
            {triage?.eventSummary.totalCount ?? 0}
          </div>
        </div>
      </div>

      <div className="section-grid section-grid--two">
        <SectionCard title="治理与实验总量" subtitle="突出 case 流量、处理量和实验运行密度">
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <BarChart
                data={[
                  {
                    day: 'now',
                    created: moderationCases.length + recoveryCases.length + appealCases.length,
                    resolved: workflows.filter((item) => ['active', 'closed', 'completed', 'recovered', 'approved'].includes(item.state)).length,
                  },
                ]}
              >
                <CartesianGrid stroke="rgba(17, 24, 39, 0.08)" />
                <XAxis dataKey="day" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Bar dataKey="created" fill="#2563EB" radius={[8, 8, 0, 0]} />
                <Bar dataKey="resolved" fill="#16A34A" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="治理待办" subtitle="以统一工作台视角收拢内容治理、申诉与恢复">
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
          </div>
        </SectionCard>
      </div>

      <div className="section-grid section-grid--two">
        <SectionCard title="Triage / Backlog" subtitle="主路径直接展示产品控制面的可执行待办，而不是停留在静态总览">
          <div className="stack-list">
            {backlogCandidates.map((item: ControlPlaneBacklogCandidate) => (
              <div className="policy-item" key={item.id}>
                <div>
                  <p className="item-title">{item.title}</p>
                  <p className="item-subtitle">
                    severity={item.severity} · category={item.category}
                    {item.summary ? ` · ${item.summary}` : ''}
                  </p>
                  <p className="item-subtitle">{item.nextAction}</p>
                </div>
                <div className="badge-row">
                  <span className={`badge badge--${item.severity === 'critical' ? 'warning' : item.severity === 'warning' ? 'warning' : 'neutral'}`}>
                    {item.severity}
                  </span>
                  {item.drilldownRoute ? (
                    <Link className="button" to={item.drilldownRoute}>进入 drilldown</Link>
                  ) : null}
                {item.runbookRoute ? (
                  <Link className="button" to={item.runbookRoute}>查看 runbook</Link>
                ) : null}
                {item.repairEntry ? (
                  <Link className="button button--primary" to={item.repairEntry}>进入修复入口</Link>
                ) : null}
                {item.auditRoute ? (
                  <Link className="button" to={item.auditRoute}>查看审计链</Link>
                ) : null}
                {item.alertId ? <span className="badge badge--neutral">alert={item.alertId}</span> : null}
                </div>
              </div>
            ))}
            {backlogCandidates.length === 0 ? (
              <div className="policy-item">
                <div>
                  <p className="item-title">暂无 backlog</p>
                  <p className="item-subtitle">当前产品 triage 未生成新的修复待办。</p>
                </div>
                <span className="badge badge--success">quiet</span>
              </div>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="实时告警与覆盖" subtitle="与 L1-L4 页面共享同一实时语义，避免 dashboard 继续伪装静态趋势">
          <div className="stack-list">
            <div className="policy-item">
              <div>
                <p className="item-title">实时元数据</p>
                <p className="item-subtitle">
                  source={metricsPayload?.source ?? 'snapshot'} · freshness={metricsPayload?.freshness ?? 'n/a'} · window={metricsPayload?.window ?? 'n/a'}
                </p>
                <p className="item-subtitle">
                  coverage={metricsPayload?.coverage.liveMetrics ?? 0}/{metricsPayload?.coverage.totalMetrics ?? 0} live
                </p>
              </div>
              <span className="badge badge--neutral">{metricsPayload?.coverage.eventSignals ?? 0} signals</span>
            </div>
            {alertStates.map((item) => (
              <div className="policy-item" key={item.id}>
                <div>
                  <p className="item-title">{item.metric}</p>
                  <p className="item-subtitle">
                    level={item.level} · severity={item.severity} · source={item.source}
                  </p>
                  <p className="item-subtitle">{item.summary}</p>
                </div>
                <div className="badge-row">
                  <span className={`badge badge--${item.state === 'firing' ? 'warning' : item.state === 'warning' ? 'warning' : 'success'}`}>
                    {item.state}
                  </span>
                  <span className="badge badge--neutral">{item.value}</span>
                </div>
              </div>
            ))}
            {alertStates.length === 0 ? (
              <div className="policy-item">
                <div>
                  <p className="item-title">暂无实时告警</p>
                  <p className="item-subtitle">当前实时聚合没有生成新的告警态。</p>
                </div>
                <span className="badge badge--success">quiet</span>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <SectionCard title="推荐运营策略池" subtitle="覆盖召回、粗排、精排 / 重排的受控干预空间">
        <div className="stack-list">
          {policies.map((policy) => (
            <div className="policy-item" key={policy.id}>
              <div>
                <p className="item-title">{policy.name}</p>
                <p className="item-subtitle">
                  policy={policy.policyVersion} · status={policy.status}
                </p>
              </div>
              <span className={`badge badge--${policy.status === 'active' ? 'success' : policy.status === 'simulated' ? 'warning' : 'neutral'}`}>
                {policy.status}
              </span>
            </div>
          ))}
          {policies.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">等待推荐策略接入</p>
                <p className="item-subtitle">产品控制面可达后将展示推荐策略池。</p>
              </div>
              <span className="badge badge--warning">offline</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard title="主路径联动" subtitle="Dashboard 与 L1-L4 页面共享同一份实时指标和 triage 数据源">
        <div className="stack-list">
          <div className="policy-item">
            <div>
              <p className="item-title">当前主指标</p>
              <p className="item-subtitle">
                {topMetric ? `${topMetric.level} / ${topMetric.metric} / source=${topMetric.source ?? 'snapshot'}` : '等待实时指标'}
              </p>
            </div>
            <Link className="button" to="/product/l1-l4/environment">打开 L1-L4 详情</Link>
          </div>
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
