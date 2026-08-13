import { useEffect, useMemo, useState } from 'react';

import { productControlPlane } from '../../generated/control-plane/productControlPlane.generated.js';
import {
  fetchPremiumPoolEntries,
  fetchRecommendationBehaviorMetrics,
  rollbackPremiumPoolEntry,
  takedownPremiumPoolEntry,
  upsertPremiumPoolEntry,
  type PremiumPoolEntryItem,
  type PremiumPoolMutationResponse,
  type RecommendationBehaviorMetrics,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

function statusTone(status: string): string {
  if (status === 'active') {
    return 'success';
  }
  if (status === 'rolled_back') {
    return 'neutral';
  }
  return 'danger';
}

export function RecommendationPage() {
  const premiumPoolObject = productControlPlane.object_types.find(
    (item) => item.object_type === 'premium_pool_entry',
  );
  const [entries, setEntries] = useState<PremiumPoolEntryItem[]>([]);
  const [behaviorMetrics, setBehaviorMetrics] = useState<RecommendationBehaviorMetrics | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [draftContentId, setDraftContentId] = useState('');
  const [draftQualityScore, setDraftQualityScore] = useState('0.9');
  const [draftAuditId, setDraftAuditId] = useState('');

  const loadEntries = () =>
    fetchPremiumPoolEntries()
      .then((items) => {
        setEntries(items);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });

  useEffect(() => {
    void loadEntries();
    fetchRecommendationBehaviorMetrics()
      .then((metrics) => setBehaviorMetrics(metrics))
      .catch((error) => setRuntimeError(coerceRuntimeError(error)));
  }, []);

  const behaviorByState = useMemo(() => {
    const totals = new Map<string, number>();
    behaviorMetrics?.series.forEach((item) => {
      const state = item.labels.state || 'unknown';
      totals.set(state, (totals.get(state) ?? 0) + item.value);
    });
    return Array.from(totals.entries()).map(([state, value]) => ({ state, value }));
  }, [behaviorMetrics]);

  const activeCount = entries.filter((entry) => entry.status === 'active' && !entry.takedownEjected).length;

  const handleFeature = async () => {
    const contentId = draftContentId.trim();
    const auditId = draftAuditId.trim();
    const qualityScore = Number(draftQualityScore);
    if (!contentId || !auditId || Number.isNaN(qualityScore)) {
      setActionMessage('contentId、qualityScore 与 auditId 均为必填。');
      return;
    }
    try {
      const entry = await upsertPremiumPoolEntry({
        contentId,
        scope: 'global',
        qualityScore,
        qualityAdmission: 'approved',
        auditId,
        expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      });
      setActionMessage(`内容 ${entry.contentId} 已进入全局精选池（7 天有效期，事件已广播给 feed 投影）。`);
      setDraftContentId('');
      setDraftAuditId('');
      setRuntimeError(null);
      await loadEntries();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  const handleRollback = async (contentId: string) => {
    try {
      const entry = await rollbackPremiumPoolEntry(contentId);
      setActionMessage(`条目 ${entry.contentId} 已回滚出精选池。`);
      setRuntimeError(null);
      await loadEntries();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  const handleTakedown = async (contentId: string) => {
    try {
      const response: PremiumPoolMutationResponse = await takedownPremiumPoolEntry(contentId);
      if ('pending' in response && response.pending) {
        setActionMessage(
          `已记录第 ${response.approvalCount} 个审批主体，等待第二个不同 principal 复核（digest=${response.payloadDigest.slice(0, 12)}…）。`,
        );
      } else {
        setActionMessage(`条目 ${contentId} 已双签下架并广播 TakedownEjected 事件。`);
      }
      setRuntimeError(null);
      await loadEntries();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  return (
    <PageScaffold
      title="推荐运营"
      subtitle="以全局精选池为唯一受控干预面：入池、回滚、双签下架全部落审计并经事件广播给 content-service feed 投影。"
      meta={
        <>
          <span className="badge badge--neutral">premium-pool</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实精选池已接入' : '等待产品控制面连接'}
          </span>
          <span className="badge badge--neutral">active={activeCount}</span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      footer={actionMessage ? <span className="badge badge--warning">{actionMessage}</span> : undefined}
    >
      <SectionCard
        title="精选入池"
        subtitle="仅接受质量审核 approved 且 qualityScore ≥ 0.75 的内容；auditId 关联质量审核凭据"
      >
        <div className="toolbar-row">
          <label className="toolbar-field">
            <span>contentId</span>
            <input
              value={draftContentId}
              onChange={(event) => setDraftContentId(event.target.value)}
              placeholder="post_..."
            />
          </label>
          <label className="toolbar-field">
            <span>qualityScore</span>
            <input
              value={draftQualityScore}
              onChange={(event) => setDraftQualityScore(event.target.value)}
              placeholder="0.9"
            />
          </label>
          <label className="toolbar-field">
            <span>auditId</span>
            <input
              value={draftAuditId}
              onChange={(event) => setDraftAuditId(event.target.value)}
              placeholder="audit_..."
            />
          </label>
          <button className="button button--primary" onClick={() => void handleFeature()}>
            提交入池
          </button>
        </div>
      </SectionCard>

      <SectionCard title="精选池条目" subtitle="rollback 单签快速撤回；takedown 需两个不同 principal 双签">
        <div className="stack-list">
          {entries.map((entry) => (
            <div className="policy-item" key={entry.contentId}>
              <div>
                <p className="item-title">{entry.contentId}</p>
                <p className="item-subtitle">
                  score={entry.qualityScore} · audit={entry.auditId} · featuredAt={entry.featuredAt} · expiresAt=
                  {entry.expiresAt}
                </p>
              </div>
              <div className="badge-row">
                <span className={`badge badge--${statusTone(entry.status)}`}>{entry.status}</span>
                {entry.status === 'active' ? (
                  <>
                    <button className="button" onClick={() => void handleRollback(entry.contentId)}>
                      回滚
                    </button>
                    <button className="button button--danger" onClick={() => void handleTakedown(entry.contentId)}>
                      双签下架
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          ))}
          {entries.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">精选池为空</p>
                <p className="item-subtitle">经上方表单入池后，条目将广播给 content-service rm_premium_pool 投影供 feed 消费。</p>
              </div>
              <span className="badge badge--neutral">0</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <div className="section-grid section-grid--two">
        <SectionCard
          title="推荐反馈真实指标"
          subtitle="读取 content-service 进程内 recommendation_behavior_by_attribution_total（单副本口径；多副本聚合待中央 Prometheus 化）；不经过 /ops/events"
        >
          <div className="stack-list">
            {behaviorByState.map((item) => (
              <div className="policy-item" key={item.state}>
                <div>
                  <p className="item-title">{item.state}</p>
                  <p className="item-subtitle">source={behaviorMetrics?.source} · freshness={behaviorMetrics?.freshness}</p>
                </div>
                <span className="badge badge--neutral">{item.value}</span>
              </div>
            ))}
            {behaviorByState.length === 0 ? (
              <div className="policy-item">
                <div>
                  <p className="item-title">暂无推荐反馈</p>
                  <p className="item-subtitle">指标端点可达，但当前进程尚未接收 BehaviorSignal。</p>
                </div>
                <span className="badge badge--neutral">0</span>
              </div>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="控制面能力" subtitle="来自 control_plane.yaml 的对象定义和受控动作">
          <div className="stack-list">
            <div className="policy-item">
              <div>
                <p className="item-title">{premiumPoolObject?.label}</p>
                <p className="item-subtitle">
                  source={premiumPoolObject?.source_entity} · view={premiumPoolObject?.view_model} · risk=
                  {premiumPoolObject?.risk_level}
                </p>
              </div>
              <span className="badge badge--warning">{premiumPoolObject?.deployment_profile}</span>
            </div>
            {premiumPoolObject?.operations.map((operation) => (
              <div className="policy-item" key={operation.operation}>
                <div>
                  <p className="item-title">{operation.operation}</p>
                  <p className="item-subtitle">
                    {operation.method} {operation.path}
                  </p>
                </div>
                <div className="badge-row">
                  {'danger_level' in operation && operation.danger_level ? (
                    <span className="badge badge--danger">{operation.danger_level}</span>
                  ) : null}
                  {'approval_mode' in operation && operation.approval_mode ? (
                    <span className="badge badge--warning">{operation.approval_mode}</span>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    </PageScaffold>
  );
}
