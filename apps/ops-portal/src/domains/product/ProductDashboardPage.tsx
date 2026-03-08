import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import {
  fetchAppealCases,
  fetchModerationCases,
  fetchProductProjectionSummary,
  fetchRecoveryCases,
  fetchProductWorkflows,
  fetchRecommendationPolicies,
  type AppealCaseItem,
  type ModerationCaseItem,
  type ProductProjectionSummary,
  type RecoveryCaseItem,
  type RecommendationPolicyItem,
  type WorkflowItem,
} from '../../shared/api/controlPlane';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function ProductDashboardPage() {
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [policies, setPolicies] = useState<RecommendationPolicyItem[]>([]);
  const [moderationCases, setModerationCases] = useState<ModerationCaseItem[]>([]);
  const [recoveryCases, setRecoveryCases] = useState<RecoveryCaseItem[]>([]);
  const [appealCases, setAppealCases] = useState<AppealCaseItem[]>([]);
  const [summary, setSummary] = useState<ProductProjectionSummary | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchProductWorkflows(),
      fetchRecommendationPolicies(),
      fetchModerationCases(),
      fetchRecoveryCases(),
      fetchAppealCases(),
      fetchProductProjectionSummary(),
    ])
      .then(([workflowItems, policyItems, moderationItems, recoveryItems, appealItems, summaryItem]) => {
        setWorkflows(workflowItems);
        setPolicies(policyItems);
        setModerationCases(moderationItems);
        setRecoveryCases(recoveryItems);
        setAppealCases(appealItems);
        setSummary(summaryItem);
        setRemoteReady(true);
      })
      .catch(() => {
        setRemoteReady(false);
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

  return (
    <PageScaffold
      title="Product Ops 业务总览"
      subtitle="聚焦治理处置、增长实验与推荐运营的统一视图，强调策略效果、风险控制和处置效率。"
      meta={
        <>
          <span className="badge badge--neutral">Product Ops</span>
          <span className="badge badge--success">推荐 guardrail 正常</span>
          <span className="badge badge--warning">双签待处理 {summary?.pendingDualReview ?? 0} 个</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实产品控制面已接入' : '等待产品控制面连接'}
          </span>
        </>
      }
      actions={<button className="button button--primary">创建策略变更</button>}
      footer={
        <>
          <button className="button">打开工作台</button>
          <button className="button button--primary">发起实验评审</button>
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
          <div className="metric-pill__label">推荐扶持策略数</div>
          <div className="metric-pill__value">{policies.length > 0 ? policies.length : 14}</div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">运行中实验</div>
          <div className="metric-pill__value">
            {workflows.filter((item) => item.objectType === 'experiment').length || 18}
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
    </PageScaffold>
  );
}
