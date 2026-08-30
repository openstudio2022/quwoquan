import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import {
  applyHumanAuthorityAction,
  fetchHumanAuthorityDecisionUnits,
  fetchHumanAuthorityReadback,
  submitHumanAuthorityRound,
  type HumanAuthorityAction,
  type HumanAuthorityDecisionUnit,
  type HumanAuthorityReadback,
  type HumanAuthorityRoleTask,
} from '../../shared/api/controlPlane.js';
import { usePortalAuth } from '../../shared/auth/portalAuth.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import {
  RuntimeError,
  RuntimeErrorBadge,
  coerceRuntimeError,
  fallbackRuntimeErrorResponse,
} from '../../shared/runtime/errors/index.js';

const readPermission = 'ops.platform.delivery_decision.read';
const writePermission = 'ops.platform.delivery_decision.write';
const recommendationForbiddenDecisionKinds = new Set([
  'product_scope',
  'experience_direction',
  'commercial_readiness',
  'outcome_acceptance',
]);

const roleLabels: Record<string, string> = {
  business_sponsor: '业务发起人',
  product_owner: '产品负责人',
  business_acceptance_representative: '业务验收代表',
  experience_design_owner: '体验设计负责人',
  domain_solution_architecture_owner: '领域方案负责人',
  engineering_delivery_owner: '工程交付负责人',
  quality_owner: '质量负责人',
  security_privacy_legal_compliance_owner: '安全、隐私与合规负责人',
  release_owner: '发布负责人',
  environment_reliability_owner: '环境可靠性负责人',
  operations_support_market_channel_owner: '运营与渠道负责人',
};

const cardLabels: Record<string, string> = {
  intake: '第一轮：确认事实',
  choice: '第二轮：独立评估影响',
  authorization: '决定与授权',
  exception: '异常处理',
  post_check: '结果复核',
};

function clientRuntimeError(code: string, cause?: unknown): RuntimeError {
  return new RuntimeError(fallbackRuntimeErrorResponse({ code, cause }));
}

function commaLines(value: string): string[] {
  return value.split(/\n+/).map((item) => item.trim()).filter(Boolean);
}

function isTimedOut(task: HumanAuthorityRoleTask): boolean {
  return Boolean(task.dueAt && Date.parse(task.dueAt) <= Date.now());
}

function isRecommendationVisible(task: HumanAuthorityRoleTask): boolean {
  return Boolean(
    task.card.agentRecommendation
      && !recommendationForbiddenDecisionKinds.has(task.decisionKind),
  );
}

function statusMessage(readback: HumanAuthorityReadback): string {
  if (readback.replayed) {
    return `服务器已确认这是重复请求，并返回原有记录：${readback.message || readback.status}`;
  }
  return readback.message || `服务器已回读状态：${readback.status}`;
}

export function HumanAuthorityPage() {
  const { hasPermission } = usePortalAuth();
  const canRead = hasPermission(readPermission);
  const canWrite = hasPermission(writePermission);
  const [units, setUnits] = useState<HumanAuthorityDecisionUnit[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState('');
  const [factsText, setFactsText] = useState('');
  const [impactsText, setImpactsText] = useState('');
  const [unknownsText, setUnknownsText] = useState('');
  const [selectedOptionId, setSelectedOptionId] = useState('');
  const [actionNote, setActionNote] = useState('');
  const [transferRole, setTransferRole] = useState('');
  const [pending, setPending] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const [readback, setReadback] = useState<HumanAuthorityReadback | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const errorFocusRef = useRef<HTMLDivElement>(null);
  const inFlightRef = useRef(false);
  const idempotencyKeysRef = useRef(new Map<string, string>());

  const selectedUnit = useMemo(
    () => units.find((unit) => unit.decisionUnitId === selectedUnitId) ?? units[0],
    [selectedUnitId, units],
  );
  const task = selectedUnit?.currentTask;

  const setFailure = (error: unknown) => {
    setRuntimeError(coerceRuntimeError(error));
    setAnnouncement('提交未成功。当前页面不会把未确认请求显示为成功，请按恢复建议重试。');
    requestAnimationFrame(() => errorFocusRef.current?.focus());
  };

  const loadUnits = async () => {
    if (!canRead) {
      setUnits([]);
      setFailure(clientRuntimeError('HAD.PERMISSION_REQUIRED'));
      return;
    }
    try {
      const nextUnits = await fetchHumanAuthorityDecisionUnits();
      setUnits(nextUnits);
      setSelectedUnitId((current) => current || nextUnits[0]?.decisionUnitId || '');
      setRuntimeError(null);
    } catch (error) {
      setUnits([]);
      setFailure(error);
    }
  };

  useEffect(() => {
    void loadUnits();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canRead]);

  useEffect(() => {
    setFactsText('');
    setImpactsText('');
    setUnknownsText('');
    setSelectedOptionId('');
    setActionNote('');
    setTransferRole('');
    setReadback(selectedUnit?.readback ?? null);
  }, [selectedUnit?.decisionUnitId, selectedUnit?.readback]);

  const updateTask = (nextTask: HumanAuthorityRoleTask) => {
    setUnits((current) => current.map((unit) => (
      unit.decisionUnitId === nextTask.decisionUnitId
        ? { ...unit, state: nextTask.state, currentTask: nextTask }
        : unit
    )));
  };

  const mutationKey = (operation: string) => {
    if (!task) return '';
    const cacheKey = `${task.taskId}:${operation}`;
    const existing = idempotencyKeysRef.current.get(cacheKey);
    if (existing) return existing;
    const next = `portal-human-authority-${cacheKey}-${globalThis.crypto.randomUUID()}`;
    idempotencyKeysRef.current.set(cacheKey, next);
    return next;
  };

  const completeMutation = (operation: string, nextTask: HumanAuthorityRoleTask, nextReadback: HumanAuthorityReadback) => {
    idempotencyKeysRef.current.delete(`${nextTask.taskId}:${operation}`);
    updateTask(nextTask);
    setReadback(nextReadback);
    setRuntimeError(null);
    setAnnouncement(statusMessage(nextReadback));
  };

  const submitRound = async (event: FormEvent, round: 1 | 2) => {
    event.preventDefault();
    if (!task || inFlightRef.current || pending) return;
    if (!canWrite) {
      setFailure(clientRuntimeError('HAD.PERMISSION_REQUIRED'));
      return;
    }
    if (round === 2 && task.card.options.length > 0 && !selectedOptionId) {
      setFailure(clientRuntimeError('HAD.OPTION_REQUIRED'));
      return;
    }
    const operation = `round-${round}`;
    inFlightRef.current = true;
    setPending(true);
    setAnnouncement('正在提交，等待服务器回读。');
    try {
      const result = await submitHumanAuthorityRound(task.taskId, {
        round,
        facts: commaLines(factsText),
        impacts: commaLines(impactsText),
        unknowns: commaLines(unknownsText),
        selectedOptionId: selectedOptionId || undefined,
      }, mutationKey(operation));
      completeMutation(operation, result.task, result.readback);
    } catch (error) {
      setFailure(error);
    } finally {
      setPending(false);
      inFlightRef.current = false;
    }
  };

  const applyAction = async (action: Exclude<HumanAuthorityAction, 'submit_round_1' | 'submit_round_2'>) => {
    if (!task || inFlightRef.current || pending) return;
    if (!canWrite) {
      setFailure(clientRuntimeError('HAD.PERMISSION_REQUIRED'));
      return;
    }
    if (action === 'transfer' && !transferRole) {
      setFailure(clientRuntimeError('HAD.TRANSFER_ROLE_REQUIRED'));
      return;
    }
    if ((action === 'authorize' || action === 'post_check') && task.card.options.length > 0 && !selectedOptionId) {
      setFailure(clientRuntimeError('HAD.OPTION_REQUIRED'));
      return;
    }
    inFlightRef.current = true;
    setPending(true);
    setAnnouncement('正在提交，等待服务器回读。');
    try {
      const result = await applyHumanAuthorityAction(task.taskId, {
        action,
        note: actionNote,
        targetRole: action === 'transfer' ? transferRole : undefined,
        selectedOptionId: selectedOptionId || undefined,
      }, mutationKey(action));
      completeMutation(action, result.task, result.readback);
    } catch (error) {
      setFailure(error);
    } finally {
      setPending(false);
      inFlightRef.current = false;
    }
  };

  const refreshReadback = async () => {
    if (!selectedUnit) return;
    try {
      const nextReadback = await fetchHumanAuthorityReadback(selectedUnit.decisionUnitId);
      setReadback(nextReadback);
      setRuntimeError(null);
      setAnnouncement(statusMessage(nextReadback));
    } catch (error) {
      setFailure(error);
    }
  };

  return (
    <PageScaffold
      title="Platform Ops / 交付决策"
      subtitle="面向当前职责展示需要你确认的事实、影响与决定。Portal 只提交决定输入并显示服务器回读，不执行发布、代码或生产动作。"
      meta={
        <>
          <span className="badge badge--neutral">Human Authority</span>
          <span className={`badge ${canRead ? 'badge--success' : 'badge--danger'}`}>
            {canRead ? '可读取职责内任务' : '缺少读取权限'}
          </span>
          <span className={`badge ${canWrite ? 'badge--success' : 'badge--warning'}`}>
            {canWrite ? '可提交职责内输入' : '只读'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
    >
      <div
        ref={errorFocusRef}
        tabIndex={-1}
        className="human-authority-status"
        aria-live="assertive"
        aria-atomic="true"
      >
        {runtimeError ? (
          <>
            <strong>当前操作未完成。</strong>
            <span>请确认登录权限、当前职责与网络，再重试或转交给正确负责人。</span>
          </>
        ) : null}
      </div>
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</div>

      <SectionCard
        title="当前职责与待办"
        subtitle="职责由服务器端身份映射决定；页面不允许从登录信息中自报或切换角色。"
      >
        {units.length ? (
          <label className="human-authority-field">
            <span>选择待办</span>
            <select value={selectedUnit?.decisionUnitId ?? ''} onChange={(event) => setSelectedUnitId(event.target.value)}>
              {units.map((unit) => (
                <option key={unit.decisionUnitId} value={unit.decisionUnitId}>
                  {unit.currentTask ? roleLabels[unit.currentTask.role] ?? unit.currentTask.role : '等待角色任务'} · {unit.currentTask?.card.question ?? unit.decisionKind}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="item-subtitle">未从服务器取得职责内待办；不会在本地生成示例决定或 authority 状态。</p>
        )}
      </SectionCard>

      {task ? (
        <>
          <SectionCard
            title={cardLabels[task.card.cardType] ?? '交付决定'}
            subtitle={`当前职责：${roleLabels[task.role] ?? task.role}。${task.card.roleResponsibility}`}
            aside={<span className="badge badge--neutral">{task.state}</span>}
          >
            <div className="human-authority-summary-grid">
              <article><h3>发生了什么</h3><p>{task.card.whatHappened}</p></article>
              <article><h3>业务 / 用户影响</h3><p>{task.card.userOrBusinessImpact}</p></article>
              <article><h3>最安全默认</h3><p>{task.card.safestDefault || '暂停并等待具名负责人确认，不作隐式批准。'}</p></article>
            </div>
            {isTimedOut(task) ? (
              <div className="human-authority-callout" role="alert">
                <strong>本任务已超时。</strong>
                <span>系统不会把超时当作同意；请选择暂停、补证据或转交。</span>
              </div>
            ) : null}
            {task.sodPolicy === 'independent-principal-required' ? (
              <div className="human-authority-callout">
                <strong>职责分离要求</strong>
                <span>{task.sodMessage || '本任务需要不同的已认证人员分别完成适用职责，当前人员不能代替另一职责。'}</span>
              </div>
            ) : null}
            <div className="human-authority-fact-grid">
              <section><h3>已知</h3><ul>{task.card.knownFacts.map((item) => <li key={item}>{item}</li>)}</ul></section>
              <section><h3>未知</h3><ul>{task.card.unknowns.map((item) => <li key={item}>{item}</li>)}</ul></section>
              <section><h3>硬约束</h3><ul>{task.card.hardConstraints.map((item) => <li key={item}>{item}</li>)}</ul></section>
              <section><h3>后果</h3><ul>{task.card.consequences.map((item) => <li key={item}>{item}</li>)}</ul></section>
            </div>
            {isRecommendationVisible(task) ? (
              <div className="inline-note">工程参考：{task.card.agentRecommendation}</div>
            ) : null}
          </SectionCard>

          {task.card.options.length ? (
            <SectionCard
              title="中性选项"
              subtitle="没有预选，也不突出任何方案。所有方案按相同字段展示；请在独立评估后选择。"
            >
              <fieldset className="human-authority-options">
                <legend>{task.card.question}</legend>
                {task.card.options.map((option) => (
                  <label className="human-authority-option" key={option.optionId}>
                    <span className="human-authority-option__choice">
                      <input
                        type="radio"
                        name={`decision-option-${task.taskId}`}
                        value={option.optionId}
                        checked={selectedOptionId === option.optionId}
                        onChange={(event) => setSelectedOptionId(event.target.value)}
                      />
                      <strong>{option.neutralLabel}</strong>
                    </span>
                    <dl>
                      <div><dt>用户结果</dt><dd>{option.userOutcome}</dd></div>
                      <div><dt>业务结果</dt><dd>{option.businessOutcome}</dd></div>
                      <div><dt>成本</dt><dd>{option.cost}</dd></div>
                      <div><dt>生效时间</dt><dd>{option.timeToEffect}</dd></div>
                      <div><dt>风险</dt><dd>{option.risk}</dd></div>
                      <div><dt>可逆性</dt><dd>{option.reversibility}</dd></div>
                      <div><dt>范围变化</dt><dd>{option.scopeChange}</dd></div>
                      <div><dt>未知</dt><dd>{option.unknowns.join('；') || '无新增未知项'}</dd></div>
                      <div><dt>下一步</dt><dd>{option.nextStep}</dd></div>
                    </dl>
                  </label>
                ))}
              </fieldset>
            </SectionCard>
          ) : null}

          <SectionCard title="提交当前职责输入" subtitle="每次提交使用幂等键；只有服务器回读成功后才显示完成。断网后可用同一输入重试。">
            <form className="human-authority-form" onSubmit={(event) => void submitRound(event, task.card.cardType === 'choice' ? 2 : 1)}>
              {task.card.cardType === 'choice' ? (
                <label className="human-authority-field">
                  <span>第二轮独立影响（一行一项）</span>
                  <textarea value={impactsText} onChange={(event) => setImpactsText(event.target.value)} rows={4} />
                </label>
              ) : (
                <label className="human-authority-field">
                  <span>第一轮事实（一行一项）</span>
                  <textarea value={factsText} onChange={(event) => setFactsText(event.target.value)} rows={4} />
                </label>
              )}
              <label className="human-authority-field">
                <span>仍未知（一行一项）</span>
                <textarea value={unknownsText} onChange={(event) => setUnknownsText(event.target.value)} rows={3} />
              </label>
              <button className="button" type="submit" disabled={pending || !canWrite}>
                {task.card.cardType === 'choice' ? '提交第二轮独立影响' : '提交第一轮事实'}
              </button>
            </form>

            <div className="human-authority-form human-authority-actions">
              <label className="human-authority-field">
                <span>补充说明</span>
                <textarea value={actionNote} onChange={(event) => setActionNote(event.target.value)} rows={3} />
              </label>
              <label className="human-authority-field">
                <span>转交给</span>
                <select value={transferRole} onChange={(event) => setTransferRole(event.target.value)}>
                  <option value="">选择正确职责</option>
                  {Object.entries(roleLabels).map(([role, label]) => <option key={role} value={role}>{label}</option>)}
                </select>
              </label>
              <div className="human-authority-button-row">
                {task.card.actions.includes('request_evidence') ? <button type="button" className="button" disabled={pending || !canWrite} onClick={() => void applyAction('request_evidence')}>补证据</button> : null}
                {task.card.actions.includes('transfer') ? <button type="button" className="button" disabled={pending || !canWrite} onClick={() => void applyAction('transfer')}>转交</button> : null}
                {task.card.actions.includes('pause') ? <button type="button" className="button" disabled={pending || !canWrite} onClick={() => void applyAction('pause')}>暂停</button> : null}
                {task.card.actions.includes('authorize') ? <button type="button" className="button" disabled={pending || !canWrite} onClick={() => void applyAction('authorize')}>提交决定</button> : null}
                {task.card.actions.includes('post_check') ? <button type="button" className="button" disabled={pending || !canWrite} onClick={() => void applyAction('post_check')}>提交结果复核</button> : null}
                <button type="button" className="button" disabled={pending} onClick={() => void refreshReadback()}>刷新回读</button>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="服务器回读" subtitle="这里只展示服务端确认的追加记录；pending 或网络失败不会显示成成功。">
            {readback ? (
              <div className="human-authority-readback" role="status">
                <strong>{readback.status}</strong>
                <span>{statusMessage(readback)}</span>
                {readback.recordedAt ? <time dateTime={readback.recordedAt}>{readback.recordedAt}</time> : null}
              </div>
            ) : <p className="item-subtitle">尚无服务器确认的回读。</p>}
            {task.card.auditDetails ? (
              <details className="human-authority-audit-details">
                <summary>审计详情</summary>
                <pre>{JSON.stringify(task.card.auditDetails, null, 2)}</pre>
              </details>
            ) : null}
          </SectionCard>
        </>
      ) : null}
    </PageScaffold>
  );
}
