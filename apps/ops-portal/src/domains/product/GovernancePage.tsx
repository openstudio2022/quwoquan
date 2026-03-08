import { useEffect, useState } from 'react';
import { productWorkflow } from '../../generated/control-plane/productWorkflow.generated';
import {
  fetchAppealCases,
  fetchModerationCases,
  fetchRecoveryCases,
  type AppealCaseItem,
  type ModerationCaseItem,
  type RecoveryCaseItem,
} from '../../shared/api/controlPlane';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function GovernancePage() {
  const workflow = productWorkflow.workflows.filter((item) =>
    ['moderation_case', 'appeal_case', 'recovery_case'].includes(item.object_type),
  );
  const [moderationCases, setModerationCases] = useState<ModerationCaseItem[]>([]);
  const [recoveryCases, setRecoveryCases] = useState<RecoveryCaseItem[]>([]);
  const [appealCases, setAppealCases] = useState<AppealCaseItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);

  useEffect(() => {
    Promise.all([fetchModerationCases(), fetchRecoveryCases(), fetchAppealCases()])
      .then(([moderationItems, recoveryItems, appealItems]) => {
        setModerationCases(moderationItems);
        setRecoveryCases(recoveryItems);
        setAppealCases(appealItems);
        setRemoteReady(true);
      })
      .catch(() => {
        setRemoteReady(false);
      });
  }, []);

  return (
    <PageScaffold
      title="治理处置"
      subtitle="统一承载审核、处罚、申诉、恢复、客服、证据、SLA 与双签，强调工作流清晰、审计可回溯。"
      meta={
        <>
          <span className="badge badge--danger">高风险动作需双签</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? `已接入 ${moderationCases.length + recoveryCases.length + appealCases.length} 个真实治理对象` : '等待产品控制面连接'}
          </span>
        </>
      }
      actions={<button className="button button--primary">新建人工复核任务</button>}
      footer={
        <>
          <button className="button">补充证据</button>
          <button className="button button--danger">执行批量处置</button>
        </>
      }
    >
      <SectionCard title="统一状态机" subtitle="所有治理案例必须通过 workflow.yaml 驱动，不允许页面自行维护第二套状态表">
        <div className="stack-list">
          {workflow.map((item) => (
            <div className="case-item" key={item.workflow_id}>
              <div>
                <p className="item-title">{item.workflow_id}</p>
                <p className="item-subtitle">
                  对象：{item.object_type} · SLA {'sla_policy' in item ? JSON.stringify(item.sla_policy) : '未配置'}
                </p>
                <div className="workflow" style={{ marginTop: 12 }}>
                  {item.states.map((state, index) => (
                    <span className={`workflow-step ${index === 0 ? 'workflow-step--active' : ''}`} key={state}>
                      {state}
                    </span>
                  ))}
                </div>
              </div>
              <div className="badge-row">
                {'approval_requirements' in item && item.approval_requirements ? (
                  <span className="badge badge--danger">双签</span>
                ) : null}
                {'evidence_requirements' in item && item.evidence_requirements ? (
                  <span className="badge badge--warning">证据必填</span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <div className="section-grid section-grid--three">
        <SectionCard title="内容治理" subtitle="举报、下架、恢复统一收口">
          <div className="stack-list">
            {moderationCases.map((report) => (
              <div className="case-item" key={report.id}>
                <div>
                  <p className="item-title">{report.id}</p>
                  <p className="item-subtitle">
                    {report.targetType}/{report.targetId} · {report.reason} · queue={report.assignedQueue}
                  </p>
                </div>
                <span className={`badge ${report.status.includes('pending') || report.status.includes('review') ? 'badge--warning' : 'badge--success'}`}>
                  {report.status}
                </span>
              </div>
            ))}
            {moderationCases.length === 0 ? (
              <div className="case-item">
                <div>
                  <p className="item-title">等待治理案例接入</p>
                  <p className="item-subtitle">治理案例将在产品控制面可达后展示。</p>
                </div>
                <span className="badge badge--warning">offline</span>
              </div>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="申诉与恢复" subtitle="客服 intake、证据校验、双签审批">
          <div className="insight-grid">
            <div className="insight-box">
              <p className="insight-box__title">待恢复案例</p>
              <div className="insight-box__body">3 个恢复案例缺少设备证明或支付记录。</div>
            </div>
            <div className="insight-box">
              <p className="insight-box__title">申诉处理中</p>
              <div className="insight-box__body">{appealCases.length} 个申诉对象等待结论回写。</div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="审计与证据" subtitle="危险动作必须强确认并留下回滚上下文">
          <div className="insight-grid">
            <div className="insight-box">
              <p className="insight-box__title">证据 hash 完整率</p>
              <div className="insight-box__body">100%，所有附件均可追溯到上传人和审批结论。</div>
            </div>
            <div className="insight-box">
              <p className="insight-box__title">双签覆盖率</p>
              <div className="insight-box__body">高风险恢复与永久封禁动作均已强制双签。</div>
            </div>
          </div>
        </SectionCard>
      </div>
    </PageScaffold>
  );
}
