import { useEffect, useMemo, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated.js';
import {
  fetchGrayRoutingPolicy,
  fetchReleases,
  type GrayRoutingPolicyResponse,
  type ReleaseItem,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

export function PlatformRolloutPage() {
  const releaseObject = platformControlPlane.object_types.find((item) => item.object_type === 'config_release');
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [routingPolicy, setRoutingPolicy] = useState<GrayRoutingPolicyResponse | null>(null);
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
    fetchGrayRoutingPolicy()
      .then((payload) => setRoutingPolicy(payload))
      .catch((error) => setRuntimeError(coerceRuntimeError(error)));
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
    };
  }, [primaryRelease]);

  return (
    <PageScaffold
      title="Platform Ops / 灰度与回滚"
      subtitle="只读展示 CI/CD 与 stackctl 产生的发布、灰度、SLO gate 和回滚事实；Portal 不提供第二执行入口。"
      meta={
        <>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实发布工作流 API 已接入' : '等待平台控制面连接'}
          </span>
          {rolloutSummary ? <span className="badge badge--neutral">stage={rolloutSummary.stageLabel}</span> : null}
          <RuntimeErrorBadge error={runtimeError} />
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
                  <span className="badge badge--danger">{String(operation.danger_level)}</span>
                ) : null}
                {'approval_mode' in operation && operation.approval_mode ? (
                  <span className="badge badge--warning">{String(operation.approval_mode)}</span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="灰度路由策略（IaC 只读）"
        subtitle="维度：端侧版本 / userId 白名单 / 省份（GB/T 2260）/ 运营商；命中任一维度的请求由公网边缘转发到灰度栈，未命中走稳定栈"
      >
        {routingPolicy ? (
          <>
            <div className="badge-row">
              <span className={`badge ${routingPolicy.policy.enabled ? 'badge--warning' : 'badge--neutral'}`}>
                {routingPolicy.policy.enabled ? '灰度路由已启用' : '灰度路由未启用'}
              </span>
              <span className="badge badge--neutral">upstream={routingPolicy.policy.grayUpstream}</span>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>维度</th>
                  <th>匹配请求头</th>
                  <th>命中值</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>端侧版本</td>
                  <td>X-Client-App-Version</td>
                  <td>{routingPolicy.policy.dimensions.appVersions.join(', ') || '（空 = 不匹配）'}</td>
                </tr>
                <tr>
                  <td>用户白名单</td>
                  <td>X-Client-User-Id</td>
                  <td>{routingPolicy.policy.dimensions.userIds.join(', ') || '（空 = 不匹配）'}</td>
                </tr>
                <tr>
                  <td>省份</td>
                  <td>X-Client-Region-Code</td>
                  <td>{routingPolicy.policy.dimensions.provinces.join(', ') || '（空 = 不匹配）'}</td>
                </tr>
                <tr>
                  <td>运营商</td>
                  <td>X-Client-Carrier</td>
                  <td>{routingPolicy.policy.dimensions.carriers.join(', ') || '（空 = 不匹配）'}</td>
                </tr>
              </tbody>
            </table>
            <div className="inline-note">
              真相源 {routingPolicy.sourcePath} · 随发布 PR 变更并由 render_prod_plane_stack.py 编译进边缘
              Caddyfile；无在线编辑入口。
            </div>
          </>
        ) : (
          <div className="inline-note">等待控制面返回灰度路由策略。</div>
        )}
      </SectionCard>

      <SectionCard title="工作流闭环" subtitle="审批、阶段状态和 rollback token 只读取 CI/CD 发布账本">
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
            </>
          ) : (
            <div className="config-item">
              <div>
                <p className="item-title">等待发布工作流</p>
                <p className="item-subtitle">CI/CD 发布账本产生 workflowRef / rollbackToken 后，这里显示真实状态。</p>
              </div>
              <span className="badge badge--warning">offline</span>
            </div>
          )}
        </div>
      </SectionCard>

      <SectionCard title="当前发布单" subtitle="Portal 只负责观察；发布、放量与回滚统一经受保护的 CI/CD + stackctl 执行面">
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
