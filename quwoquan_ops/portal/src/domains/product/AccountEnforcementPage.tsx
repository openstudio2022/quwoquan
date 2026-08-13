import { useState } from 'react';

import {
  fetchAccountEnforcementCase,
  retryAccountEnforcementDelivery,
  reviewAccountEnforcementCase,
  type AccountEnforcementCaseView,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

function statusTone(status: string): string {
  if (status === 'approved' || status === 'delivered') {
    return 'success';
  }
  if (status === 'pending_approval') {
    return 'warning';
  }
  if (status === 'rejected') {
    return 'neutral';
  }
  return 'danger';
}

export function AccountEnforcementPage() {
  const [caseIdInput, setCaseIdInput] = useState('');
  const [caseView, setCaseView] = useState<AccountEnforcementCaseView | null>(null);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const loadCase = (caseId: string) =>
    fetchAccountEnforcementCase(caseId)
      .then((view) => {
        setCaseView(view);
        setRuntimeError(null);
      })
      .catch((error) => {
        setCaseView(null);
        setRuntimeError(coerceRuntimeError(error));
      });

  const review = (verdict: 'approve' | 'reject') => {
    if (!caseView) {
      return;
    }
    reviewAccountEnforcementCase(caseView.caseId, verdict)
      .then((view) => {
        setCaseView(view);
        setActionMessage(`case ${view.caseId} 已记录 ${verdict} 复核（双签制）`);
        setRuntimeError(null);
      })
      .catch((error) => setRuntimeError(coerceRuntimeError(error)));
  };

  const retryDelivery = () => {
    if (!caseView) {
      return;
    }
    retryAccountEnforcementDelivery(caseView.caseId)
      .then((view) => {
        setCaseView(view);
        setActionMessage(`case ${view.caseId} 已重试处置投递`);
        setRuntimeError(null);
      })
      .catch((error) => setRuntimeError(coerceRuntimeError(error)));
  };

  return (
    <PageScaffold
      title="账号治理处置"
      subtitle="moderation/appeal case 的双签复核与处置投递；决定经 HTTP outbox 单轨送 UserAccount 执行，Portal 不落第二处置真相源。"
      meta={
        <>
          <span className="badge badge--neutral">Product Ops</span>
          <span className="badge badge--warning">review 为双签高危动作</span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
    >
      {actionMessage ? <div className="inline-note">{actionMessage}</div> : null}
      <SectionCard
        title="按 caseId 检索"
        subtitle="caseId 来自告警、审计链或治理队列 drilldown；本页只消费真实 case 事实。"
      >
        <div className="form-row">
          <label>
            caseId
            <input
              value={caseIdInput}
              onChange={(event) => setCaseIdInput(event.target.value)}
              placeholder="例如 case_000000000001"
            />
          </label>
          <button
            className="button button--primary"
            disabled={!caseIdInput.trim()}
            onClick={() => void loadCase(caseIdInput.trim())}
          >
            读取 case
          </button>
        </div>
      </SectionCard>

      {caseView ? (
        <SectionCard title={`case ${caseView.caseId}`} subtitle="真实治理事实回读；复核与重试动作带幂等键。">
          <div className="badge-row">
            <span className={`badge badge--${statusTone(caseView.status)}`}>{caseView.status}</span>
            <span className="badge badge--neutral">kind={caseView.caseKind}</span>
            <span className="badge badge--neutral">version={caseView.version}</span>
            <span className="badge badge--neutral">approvals={caseView.approvalCount}/2</span>
            {caseView.decisionId ? (
              <span className="badge badge--success">decision={caseView.decisionId}</span>
            ) : null}
            {caseView.deliveryStatus ? (
              <span className="badge badge--neutral">delivery={caseView.deliveryStatus}</span>
            ) : null}
            <span className="badge badge--neutral">updatedAt={caseView.updatedAt}</span>
          </div>
          <div className="form-row" style={{ marginTop: 8 }}>
            <button
              className="button button--primary"
              disabled={caseView.status !== 'pending_approval'}
              onClick={() => review('approve')}
            >
              复核通过（approve）
            </button>
            <button
              className="button"
              disabled={caseView.status !== 'pending_approval'}
              onClick={() => review('reject')}
            >
              复核驳回（reject）
            </button>
            <button className="button" onClick={retryDelivery}>
              重试处置投递
            </button>
            <button className="button" onClick={() => void loadCase(caseView.caseId)}>
              刷新
            </button>
          </div>
        </SectionCard>
      ) : (
        <SectionCard title="尚未载入 case" subtitle="输入 caseId 后读取；未取得真实事实时不显示合成状态。">
          <div className="inline-note">
            开案（moderation/appeal intake）由治理管线与申诉入口生产；本页承接复核与投递运营动作。
          </div>
        </SectionCard>
      )}
    </PageScaffold>
  );
}
