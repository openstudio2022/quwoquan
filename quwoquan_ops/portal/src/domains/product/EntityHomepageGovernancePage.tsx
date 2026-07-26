import { useEffect, useMemo, useState } from 'react';

import {
  fetchHomepageCandidates,
  fetchHomepageClaimRequests,
  fetchHomepageStatusReports,
  intakeHomepageCandidate,
  publishHomepageCandidate,
  reviewHomepageClaimRequest,
  reviewHomepageStatusReport,
  type HomepageCandidateItem,
  type HomepageClaimRequestItem,
  type HomepageStatusReportItem,
  type IntakeHomepageCandidatePayload,
} from '../../shared/api/controlPlane.js';
import { KpiCard } from '../../shared/components/KpiCard.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import {
  RuntimeErrorBadge,
  coerceRuntimeError,
  type RuntimeError,
} from '../../shared/runtime/errors/index.js';

const emptyCandidateDraft: IntakeHomepageCandidatePayload = {
  title: '',
  homepageType: 'place',
  canonicalEntityId: '',
  city: '',
};

export function EntityHomepageGovernancePage() {
  const [candidates, setCandidates] = useState<HomepageCandidateItem[]>([]);
  const [claims, setClaims] = useState<HomepageClaimRequestItem[]>([]);
  const [statusReports, setStatusReports] = useState<HomepageStatusReportItem[]>([]);
  const [candidateDraft, setCandidateDraft] =
    useState<IntakeHomepageCandidatePayload>(emptyCandidateDraft);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);

  const loadQueues = async () => {
    try {
      const [candidatePage, claimPage, reportPage] = await Promise.all([
        fetchHomepageCandidates({ limit: 50 }),
        fetchHomepageClaimRequests({ status: 'pending_review', limit: 50 }),
        fetchHomepageStatusReports({ status: 'pending_review', limit: 50 }),
      ]);
      setCandidates(candidatePage.items);
      setClaims(claimPage.items);
      setStatusReports(reportPage.items);
      setRuntimeError(null);
      setRemoteReady(true);
    } catch (error) {
      setRemoteReady(false);
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  useEffect(() => {
    void loadQueues();
  }, []);

  const counters = useMemo(
    () => ({
      candidates: candidates.length,
      claims: claims.length,
      statusReports: statusReports.length,
      total: candidates.length + claims.length + statusReports.length,
    }),
    [candidates, claims, statusReports],
  );

  const runAction = async (key: string, action: () => Promise<void>) => {
    setBusyAction(key);
    try {
      await action();
      setRuntimeError(null);
      await loadQueues();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    } finally {
      setBusyAction(null);
    }
  };

  const submitCandidate = async () => {
    const payload = {
      ...candidateDraft,
      title: candidateDraft.title.trim(),
      canonicalEntityId: candidateDraft.canonicalEntityId.trim(),
      homepageType: candidateDraft.homepageType.trim(),
      city: candidateDraft.city?.trim(),
    };
    if (!payload.title || !payload.canonicalEntityId || !payload.homepageType) {
      setActionMessage('候选主页名称、canonicalEntityId 与主页类型为必填项。');
      return;
    }
    await runAction('candidate:intake', async () => {
      const created = await intakeHomepageCandidate(payload);
      setCandidateDraft(emptyCandidateDraft);
      setActionMessage(`候选主页 ${created.homepageId} 已进入治理队列。`);
    });
  };

  const publishCandidate = async (item: HomepageCandidateItem) => {
    await runAction(`candidate:${item.homepageId}`, async () => {
      await publishHomepageCandidate(item.homepageId);
      setActionMessage(`候选主页 ${item.homepageId} 已发布。`);
    });
  };

  const reviewClaim = async (
    item: HomepageClaimRequestItem,
    status: 'approved' | 'rejected',
  ) => {
    const note = (reviewNotes[item.claimRequestId] ?? '').trim();
    if (!note) {
      setActionMessage(`认领申请 ${item.claimRequestId} 必须填写审核意见。`);
      return;
    }
    await runAction(`claim:${item.claimRequestId}`, async () => {
      await reviewHomepageClaimRequest(item, status, note);
      setActionMessage(`认领申请 ${item.claimRequestId} 已${status === 'approved' ? '通过' : '驳回'}。`);
    });
  };

  const reviewStatusReport = async (
    item: HomepageStatusReportItem,
    status: 'confirmed_offline' | 'dismissed',
  ) => {
    const note = (reviewNotes[item.reportId] ?? '').trim();
    if (!note) {
      setActionMessage(`状态上报 ${item.reportId} 必须填写审核意见。`);
      return;
    }
    await runAction(`report:${item.reportId}`, async () => {
      await reviewHomepageStatusReport(item, status, note);
      setActionMessage(
        `状态上报 ${item.reportId} 已${status === 'confirmed_offline' ? '确认下线' : '驳回'}。`,
      );
    });
  };

  return (
    <PageScaffold
      title="实体主页治理"
      subtitle="候选发布、认领审核与状态上报共用 entity-service 权威对象、幂等命令和生命周期事件；审核结果由通知服务回传申请人。"
      meta={
        <>
          <span className="badge badge--neutral">entity-service / Homepage</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? `待治理 ${counters.total} 项` : '等待实体服务连接'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={
        <button className="button" disabled={busyAction !== null} onClick={() => void loadQueues()}>
          刷新队列
        </button>
      }
      footer={actionMessage ? <span className="badge badge--warning">{actionMessage}</span> : undefined}
    >
      <div className="section-grid section-grid--cards">
        <KpiCard
          label="候选主页"
          value={String(counters.candidates)}
          icon={<span className="badge badge--neutral">candidate</span>}
          trendLabel="等待运营核验"
          trendTone={counters.candidates > 0 ? 'warning' : 'positive'}
          description="核验通过后发布到共享主页阅读链路。"
        />
        <KpiCard
          label="认领申请"
          value={String(counters.claims)}
          icon={<span className="badge badge--neutral">claim</span>}
          trendLabel="等待资质复核"
          trendTone={counters.claims > 0 ? 'warning' : 'positive'}
          description="核验申请主体与主页归属材料。"
        />
        <KpiCard
          label="状态上报"
          value={String(counters.statusReports)}
          icon={<span className="badge badge--neutral">status</span>}
          trendLabel="等待证据复核"
          trendTone={counters.statusReports > 0 ? 'warning' : 'positive'}
          description="确认下线或驳回不成立的上报。"
        />
      </div>

      <SectionCard title="录入候选主页" subtitle="canonicalEntityId 是跨域实体身份；重复命令按该身份幂等。">
        <div className="badge-row">
          <input
            aria-label="主页名称"
            className="portal-input"
            placeholder="主页名称"
            value={candidateDraft.title}
            onChange={(event) =>
              setCandidateDraft((current) => ({ ...current, title: event.target.value }))
            }
          />
          <input
            aria-label="canonicalEntityId"
            className="portal-input"
            placeholder="canonicalEntityId"
            value={candidateDraft.canonicalEntityId}
            onChange={(event) =>
              setCandidateDraft((current) => ({
                ...current,
                canonicalEntityId: event.target.value,
              }))
            }
          />
          <input
            aria-label="主页类型"
            className="portal-input"
            placeholder="主页类型"
            value={candidateDraft.homepageType}
            onChange={(event) =>
              setCandidateDraft((current) => ({ ...current, homepageType: event.target.value }))
            }
          />
          <input
            aria-label="城市"
            className="portal-input"
            placeholder="城市（可选）"
            value={candidateDraft.city ?? ''}
            onChange={(event) =>
              setCandidateDraft((current) => ({ ...current, city: event.target.value }))
            }
          />
          <button
            className="button button--primary"
            disabled={busyAction !== null}
            onClick={() => void submitCandidate()}
          >
            录入候选
          </button>
        </div>
      </SectionCard>

      <SectionCard title="候选发布队列" subtitle="发布后才进入 App 搜索与共享主页阅读链路。">
        <div className="stack-list">
          {candidates.map((item) => (
            <div className="policy-item" key={item.homepageId}>
              <div>
                <p className="item-title">{item.title}</p>
                <p className="item-subtitle">
                  {item.homepageType} · {item.city || '城市未填'} · {item.canonicalEntityId} · {item.homepageId}
                </p>
              </div>
              <button
                className="button button--primary"
                disabled={busyAction !== null}
                onClick={() => void publishCandidate(item)}
              >
                核验并发布
              </button>
            </div>
          ))}
          <QueueEmpty visible={candidates.length === 0} label="暂无候选主页" />
        </div>
      </SectionCard>

      <SectionCard title="认领审核队列" subtitle="敏感材料只在受控治理面展示；审核人来自登录 principal。">
        <div className="stack-list">
          {claims.map((item) => (
            <div className="policy-item" key={item.claimRequestId}>
              <div>
                <p className="item-title">{item.claimTier} 认领 · {item.homepageId}</p>
                <p className="item-subtitle">
                  applicant={item.requesterPersonaId} · phone={item.contactPhone || '未提供'} · {item.note || '无补充说明'}
                </p>
                <EvidenceLink href={item.businessLicenseUrl} label="营业执照" />
                <EvidenceLink href={item.identityCardFrontUrl} label="身份证正面" />
                <EvidenceLink href={item.identityCardBackUrl} label="身份证反面" />
              </div>
              <ReviewActions
                id={item.claimRequestId}
                note={reviewNotes[item.claimRequestId] ?? ''}
                disabled={busyAction !== null}
                onNoteChange={(value) =>
                  setReviewNotes((current) => ({ ...current, [item.claimRequestId]: value }))
                }
                primaryLabel="通过"
                secondaryLabel="驳回"
                onPrimary={() => void reviewClaim(item, 'approved')}
                onSecondary={() => void reviewClaim(item, 'rejected')}
              />
            </div>
          ))}
          <QueueEmpty visible={claims.length === 0} label="暂无待审核认领申请" />
        </div>
      </SectionCard>

      <SectionCard title="状态上报队列" subtitle="确认下线会经事件投影更新主页状态并移出公开搜索。">
        <div className="stack-list">
          {statusReports.map((item) => (
            <div className="policy-item" key={item.reportId}>
              <div>
                <p className="item-title">{item.reason} · {item.homepageId}</p>
                <p className="item-subtitle">
                  reporter={item.reporterPersonaId} · {item.description || '无补充说明'}
                </p>
                {(item.evidenceUrls ?? []).map((url, index) => (
                  <EvidenceLink key={url} href={url} label={`证据 ${index + 1}`} />
                ))}
              </div>
              <ReviewActions
                id={item.reportId}
                note={reviewNotes[item.reportId] ?? ''}
                disabled={busyAction !== null}
                onNoteChange={(value) =>
                  setReviewNotes((current) => ({ ...current, [item.reportId]: value }))
                }
                primaryLabel="确认下线"
                secondaryLabel="驳回"
                onPrimary={() => void reviewStatusReport(item, 'confirmed_offline')}
                onSecondary={() => void reviewStatusReport(item, 'dismissed')}
              />
            </div>
          ))}
          <QueueEmpty visible={statusReports.length === 0} label="暂无待审核状态上报" />
        </div>
      </SectionCard>
    </PageScaffold>
  );
}

function EvidenceLink({ href, label }: { href?: string; label: string }) {
  const safeHref = safeExternalEvidenceURL(href);
  if (!safeHref) return null;
  return (
    <a className="badge badge--neutral" href={safeHref} rel="noreferrer" target="_blank">
      {label}
    </a>
  );
}

function safeExternalEvidenceURL(value?: string): string | null {
  if (!value || value.trim() !== value) return null;
  try {
    const parsed = new URL(value);
    if (
      parsed.protocol !== 'https:' ||
      !parsed.hostname ||
      parsed.username ||
      parsed.password
    ) {
      return null;
    }
    return parsed.href;
  } catch {
    return null;
  }
}

function ReviewActions({
  id,
  note,
  disabled,
  onNoteChange,
  primaryLabel,
  secondaryLabel,
  onPrimary,
  onSecondary,
}: {
  id: string;
  note: string;
  disabled: boolean;
  onNoteChange: (value: string) => void;
  primaryLabel: string;
  secondaryLabel: string;
  onPrimary: () => void;
  onSecondary: () => void;
}) {
  return (
    <div className="stack-list">
      <input
        aria-label={`${id} 审核意见`}
        className="portal-input"
        placeholder="审核意见（必填）"
        value={note}
        onChange={(event) => onNoteChange(event.target.value)}
      />
      <div className="badge-row">
        <button className="button button--primary" disabled={disabled} onClick={onPrimary}>
          {primaryLabel}
        </button>
        <button className="button button--danger" disabled={disabled} onClick={onSecondary}>
          {secondaryLabel}
        </button>
      </div>
    </div>
  );
}

function QueueEmpty({ visible, label }: { visible: boolean; label: string }) {
  if (!visible) return null;
  return (
    <div className="policy-item">
      <p className="item-title">{label}</p>
      <span className="badge badge--success">clear</span>
    </div>
  );
}
