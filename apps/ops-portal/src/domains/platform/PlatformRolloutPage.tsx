import { useEffect, useMemo, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated.js';
import {
  applyPlatformRelease,
  fetchReleases,
  type PlatformReleaseMutationResponse,
  rollbackPlatformRelease,
  type ReleaseItem,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

export function PlatformRolloutPage() {
  const releaseObject = platformControlPlane.object_types.find((item) => item.object_type === 'config_release');
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [lastMutation, setLastMutation] = useState<PlatformReleaseMutationResponse | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  const loadReleases = () => {
    fetchReleases()
      .then((items) => {
        setReleases(items);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });
  };

  useEffect(() => {
    loadReleases();
  }, []);

  const primaryRelease = releases[0] ?? null;
  const rolloutSummary = useMemo(() => {
    if (!primaryRelease) {
      return null;
    }
    return {
      stageLabel: primaryRelease.currentStage ? `${primaryRelease.currentStage}%` : 'pending',
      workflowRef: primaryRelease.workflowRef ?? 'n/a',
      rollbackToken: primaryRelease.rollbackToken ?? 'n/a',
      releaseState: primaryRelease.releaseState || 'ready',
      stageState: primaryRelease.stageState || 'pending',
      ackOutOfSync: lastMutation?.ackSummary.outOfSyncInstances ?? 0,
      ackTotal: lastMutation?.ackSummary.totalInstances ?? 0,
      sloSource: String(lastMutation?.observedSlo?.source ?? 'control-plane-observability'),
    };
  }, [lastMutation, primaryRelease]);

  const handleApply = async () => {
    if (!primaryRelease || isMutating) {
      return;
    }
    setIsMutating(true);
    try {
      const payload = await applyPlatformRelease(primaryRelease.releaseId, {
        service: primaryRelease.service,
        fromConfig: primaryRelease.fromConfig,
        toConfig: primaryRelease.toConfig ?? primaryRelease.releaseId,
        step: primaryRelease.currentStage && primaryRelease.currentStage >= 25 ? primaryRelease.currentStage : 25,
      });
      setLastMutation(payload);
      setRuntimeError(null);
      loadReleases();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    } finally {
      setIsMutating(false);
    }
  };

  const handleRollback = async () => {
    if (!primaryRelease || isMutating) {
      return;
    }
    setIsMutating(true);
    try {
      const payload = await rollbackPlatformRelease(primaryRelease.releaseId, {
        service: primaryRelease.service,
        targetConfigVersion: primaryRelease.fromConfig ?? primaryRelease.releaseId,
        workflowRef: lastMutation?.workflowRef ?? primaryRelease.workflowRef,
        rollbackToken: lastMutation?.rollbackToken ?? primaryRelease.rollbackToken,
      });
      setLastMutation(payload);
      setRuntimeError(null);
      loadReleases();
    } catch (error) {
      setRuntimeError(coerceRuntimeError(error));
    } finally {
      setIsMutating(false);
    }
  };

  return (
    <PageScaffold
      title="Platform Ops / 灰度与回滚"
      subtitle="配置发布、SLO gate、灰度步进和 rollback 上下文统一纳入控制面，不再散落在脚本和人工流程里。"
      meta={
        <>
          <span className="badge badge--neutral">5% → 25% → 50% → 100%</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实发布工作流 API 已接入' : '当前展示回退到门户样例'}
          </span>
          {rolloutSummary ? <span className="badge badge--neutral">stage={rolloutSummary.stageLabel}</span> : null}
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={
        <button className="button button--primary" onClick={handleApply} disabled={!primaryRelease || isMutating}>
          {isMutating ? '提交中...' : '发起灰度阶段'}
        </button>
      }
      footer={
        <>
          <button className="button" disabled={!primaryRelease}>
            查看 SLO gate
          </button>
          <button className="button button--danger" onClick={handleRollback} disabled={!primaryRelease || isMutating}>
            执行紧急回滚
          </button>
        </>
      }
    >
      <SectionCard title="发布对象能力" subtitle="来源于 platform control_plane.yaml 的受控动作定义">
        <div className="stack-list">
          <div className="policy-item">
            <div>
              <p className="item-title">{releaseObject?.label}</p>
              <p className="item-subtitle">
                source={releaseObject?.source_entity} · view={releaseObject?.view_model} · risk={releaseObject?.risk_level}
              </p>
            </div>
            <span className="badge badge--danger">{releaseObject?.deployment_profile}</span>
          </div>
          {releaseObject?.operations.map((operation) => (
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

      <SectionCard title="工作流闭环" subtitle="审批前置、阶段 ACK、SLO gate 与 rollback token 使用同一份控制面返回值">
        <div className="stack-list">
          {rolloutSummary ? (
            <>
              <div className="policy-item">
                <div>
                  <p className="item-title">workflowRef</p>
                  <p className="item-subtitle">{rolloutSummary.workflowRef}</p>
                </div>
                <span className="badge badge--neutral">{rolloutSummary.releaseState}</span>
              </div>
              <div className="policy-item">
                <div>
                  <p className="item-title">rollbackToken</p>
                  <p className="item-subtitle">{rolloutSummary.rollbackToken}</p>
                </div>
                <span className="badge badge--warning">{rolloutSummary.stageState}</span>
              </div>
              <div className="policy-item">
                <div>
                  <p className="item-title">ACK 收敛</p>
                  <p className="item-subtitle">
                    outOfSync={rolloutSummary.ackOutOfSync} / total={rolloutSummary.ackTotal}
                  </p>
                </div>
                <span className={`badge ${rolloutSummary.ackOutOfSync > 0 ? 'badge--warning' : 'badge--success'}`}>
                  {rolloutSummary.ackOutOfSync > 0 ? 'ack_pending' : 'ack_ready'}
                </span>
              </div>
              <div className="policy-item">
                <div>
                  <p className="item-title">SLO 观测源</p>
                  <p className="item-subtitle">{rolloutSummary.sloSource}</p>
                </div>
                <span className="badge badge--success">live</span>
              </div>
            </>
          ) : (
            <div className="config-item">
              <div>
                <p className="item-title">等待发布工作流</p>
                <p className="item-subtitle">当平台控制面返回 workflowRef / rollbackToken / ackSummary 后，这里会显示真实闭环状态。</p>
              </div>
              <span className="badge badge--warning">offline</span>
            </div>
          )}
        </div>
      </SectionCard>

      <SectionCard title="当前发布单" subtitle="与现有 config release 脚本语义保持一致，门户只负责统一观察和审批入口">
        <div className="stack-list">
          {releases.map((release) => (
            <div className="config-item" key={release.releaseId}>
              <div>
                <p className="item-title">{release.service} / {release.releaseId}</p>
                <p className="item-subtitle">
                  {release.releaseState || release.configPath}
                  {release.stageState ? ` · stage=${release.stageState}` : ''}
                  {release.workflowRef ? ` · workflow=${release.workflowRef}` : ''}
                </p>
              </div>
              <span className={`badge ${release.releaseState === 'paused' ? 'badge--warning' : release.releaseState === 'rolled_back' ? 'badge--danger' : 'badge--success'}`}>
                {release.releaseState || 'ready'}
              </span>
            </div>
          ))}
          {releases.length === 0 ? (
            <div className="config-item">
              <div>
                <p className="item-title">等待发布单接入</p>
                <p className="item-subtitle">平台控制面可达后将展示配置发布与回滚状态。</p>
              </div>
              <span className="badge badge--warning">offline</span>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
