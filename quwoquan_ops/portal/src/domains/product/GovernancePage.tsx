import { useEffect, useMemo, useState } from 'react';
import { productControlPlane } from '../../generated/control-plane/productControlPlane.generated.js';
import {
  beginReportReview,
  decidePostModerationCase,
  dismissReport,
  fetchCurrentPostModerationCase,
  fetchReports,
  reviewPostModerationCase,
  type PostModerationCaseItem,
  resolveReport,
  type ReportItem,
  type ReportResolution,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { KpiCard } from '../../shared/components/KpiCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

const resolutionOptions: Array<{ value: ReportResolution; label: string }> = [
  { value: 'warn', label: '警告作者' },
  { value: 'delete_content', label: '删除内容' },
  { value: 'suspend_user', label: '暂停账号' },
  { value: 'ban', label: '封禁账号' },
];

function reportTone(status: string): string {
  if (status === 'resolved' || status === 'dismissed') {
    return 'success';
  }
  if (status === 'reviewing') {
    return 'warning';
  }
  return 'danger';
}

export function GovernancePage() {
  const reportObject = productControlPlane.object_types.find((item) => item.object_type === 'report_queue');
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [resolutionDrafts, setResolutionDrafts] = useState<Record<string, ReportResolution>>({});
  const [moderationCases, setModerationCases] = useState<Record<string, PostModerationCaseItem>>({});
  const [moderationDecisions, setModerationDecisions] = useState<Record<string, 'approved' | 'rejected'>>({});
  const [moderationReasons, setModerationReasons] = useState<Record<string, string>>({});

  const loadReports = () =>
    fetchReports(50)
      .then((items) => {
        setReports(items);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });

  useEffect(() => {
    void loadReports();
  }, []);

  const counters = useMemo(() => {
    const byStatus = new Map<string, number>();
    reports.forEach((item) => byStatus.set(item.status, (byStatus.get(item.status) ?? 0) + 1));
    return {
      pending: byStatus.get('pending') ?? 0,
      reviewing: byStatus.get('reviewing') ?? 0,
      resolved: (byStatus.get('resolved') ?? 0) + (byStatus.get('dismissed') ?? 0),
    };
  }, [reports]);

  const handleBeginReview = async (reportId: string) => {
    try {
      await beginReportReview(reportId);
      setActionMessage(`举报 ${reportId} 已进入复核（reviewer 由登录 principal 派生）。`);
      setRuntimeError(null);
      await loadReports();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  const handleResolve = async (reportId: string) => {
    const resolution = resolutionDrafts[reportId] ?? 'warn';
    try {
      await resolveReport(reportId, resolution);
      setActionMessage(`举报 ${reportId} 已按 ${resolution} 结案并写入审计事实。`);
      setRuntimeError(null);
      await loadReports();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  const handleDismiss = async (reportId: string) => {
    try {
      await dismissReport(reportId);
      setActionMessage(`举报 ${reportId} 已驳回并通知举报人。`);
      setRuntimeError(null);
      await loadReports();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  const handleLoadModerationCase = async (report: ReportItem) => {
    try {
      const item = await fetchCurrentPostModerationCase(report.targetId);
      setModerationCases((current) => ({ ...current, [report.id]: item }));
      setRuntimeError(null);
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  const handleReviewModerationCase = async (reportId: string) => {
    const item = moderationCases[reportId];
    if (!item) return;
    try {
      const updated = await reviewPostModerationCase(item);
      setModerationCases((current) => ({ ...current, [reportId]: updated }));
      setActionMessage(`审核 Case ${updated.id} 已由当前 operator 领取。`);
      setRuntimeError(null);
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  const handleDecideModerationCase = async (reportId: string) => {
    const item = moderationCases[reportId];
    if (!item) return;
    const decision = moderationDecisions[reportId] ?? 'rejected';
    const decisionReason = (moderationReasons[reportId] ?? '').trim();
    if (!decisionReason) {
      setActionMessage('作出内容审核决定前必须填写可审计的决定原因。');
      return;
    }
    try {
      const updated = await decidePostModerationCase(item, decision, decisionReason);
      setModerationCases((current) => ({ ...current, [reportId]: updated }));
      setActionMessage(`审核 Case ${updated.id} 已作出 ${decision} 决定。`);
      setRuntimeError(null);
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    }
  };

  return (
    <PageScaffold
      title="治理处置"
      subtitle="直连 content-service 真实举报聚合（report_queue）：受理、复核、结案全部走命令幂等与审计事实，无第二套案例库。"
      meta={
        <>
          <span className="badge badge--neutral">content-service /content/reports</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? `已接入 ${reports.length} 条真实举报` : '等待内容服务连接'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      footer={actionMessage ? <span className="badge badge--warning">{actionMessage}</span> : undefined}
    >
      <div className="section-grid section-grid--cards">
        <KpiCard
          label="待受理"
          value={String(counters.pending)}
          icon={<span className="badge badge--danger">pending</span>}
          trendLabel="等待开始复核"
          trendTone={counters.pending > 0 ? 'warning' : 'positive'}
          description="用户上报后尚未进入复核的举报。"
        />
        <KpiCard
          label="复核中"
          value={String(counters.reviewing)}
          icon={<span className="badge badge--warning">reviewing</span>}
          trendLabel="已有 reviewer 认领"
          trendTone="warning"
          description="已开始复核、等待处置结论的举报。"
        />
        <KpiCard
          label="已结案"
          value={String(counters.resolved)}
          icon={<span className="badge badge--success">resolved</span>}
          trendLabel="含驳回"
          trendTone="positive"
          description="已给出处置结论并写入审计事实的举报。"
        />
      </div>

      <SectionCard title="举报队列" subtitle="开始复核与结案均为幂等命令；结案结论枚举来自 report 聚合定义">
        <div className="stack-list">
          {reports.map((report) => {
            const moderationCase = moderationCases[report.id];
            return (
            <div className="policy-item" key={report.id}>
              <div>
                <p className="item-title">
                  {report.targetType} / {report.targetId}
                </p>
                <p className="item-subtitle">
                  reason={report.reason} · id={report.id} · v{report.version} · updatedAt={report.updatedAt}
                </p>
                {moderationCase ? (
                  <div className="stack-list">
                    <p className="item-subtitle">
                      case={moderationCase.id} · revision={moderationCase.postVersion} ·
                      status={moderationCase.status}
                    </p>
                    {moderationCase.status === 'pending' ? (
                      <button className="button" onClick={() => void handleReviewModerationCase(report.id)}>
                        领取内容审核
                      </button>
                    ) : null}
                    {moderationCase.status === 'reviewed' ? (
                      <div className="badge-row">
                        <select
                          className="portal-select"
                          value={moderationDecisions[report.id] ?? 'rejected'}
                          onChange={(event) =>
                            setModerationDecisions((current) => ({
                              ...current,
                              [report.id]: event.target.value as 'approved' | 'rejected',
                            }))
                          }
                        >
                          <option value="rejected">内容违规</option>
                          <option value="approved">内容合规</option>
                        </select>
                        <input
                          className="portal-input"
                          value={moderationReasons[report.id] ?? ''}
                          placeholder="决定原因（必填）"
                          onChange={(event) =>
                            setModerationReasons((current) => ({
                              ...current,
                              [report.id]: event.target.value,
                            }))
                          }
                        />
                        <button className="button button--danger" onClick={() => void handleDecideModerationCase(report.id)}>
                          提交内容审核
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="badge-row">
                <span className={`badge badge--${reportTone(report.status)}`}>{report.status}</span>
                {report.status === 'pending' ? (
                  <button className="button" onClick={() => void handleBeginReview(report.id)}>
                    开始复核
                  </button>
                ) : null}
                {report.status === 'reviewing' ? (
                  <>
                    {report.targetType === 'post' && !moderationCase ? (
                      <button className="button" onClick={() => void handleLoadModerationCase(report)}>
                        查看审核 Case
                      </button>
                    ) : null}
                    {moderationCase?.status === 'approved' ? (
                      <button className="button" onClick={() => void handleDismiss(report.id)}>
                        驳回举报
                      </button>
                    ) : null}
                    <select
                      className="portal-select"
                      value={resolutionDrafts[report.id] ?? 'warn'}
                      onChange={(event) =>
                        setResolutionDrafts((current) => ({
                          ...current,
                          [report.id]: event.target.value as ReportResolution,
                        }))
                      }
                    >
                      {resolutionOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <button
                      className="button button--danger"
                      disabled={
                        report.targetType === 'post' &&
                        moderationCase?.status !== 'rejected'
                      }
                      onClick={() => void handleResolve(report.id)}
                    >
                      结案
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          );
          })}
          {reports.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">暂无待处理举报</p>
                <p className="item-subtitle">App 用户上报后会实时进入此队列。</p>
              </div>
              <span className="badge badge--success">clear</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard title="控制面能力" subtitle="来自 control_plane.yaml 的 report_queue 对象定义与受控动作">
        <div className="stack-list">
          <div className="policy-item">
            <div>
              <p className="item-title">{reportObject?.label}</p>
              <p className="item-subtitle">
                source={reportObject?.source_entity} · view={reportObject?.view_model} · risk={reportObject?.risk_level}
              </p>
            </div>
            <span className="badge badge--warning">{reportObject?.deployment_profile}</span>
          </div>
          {reportObject?.operations.map((operation) => (
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
    </PageScaffold>
  );
}
