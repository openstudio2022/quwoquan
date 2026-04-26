import { useEffect, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated.js';
import { fetchReleases, type ReleaseItem } from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

export function PlatformRolloutPage() {
  const releaseObject = platformControlPlane.object_types.find((item) => item.object_type === 'config_release');
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
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
  }, []);

  return (
    <PageScaffold
      title="Platform Ops / 灰度与回滚"
      subtitle="配置发布、SLO gate、灰度步进和 rollback 上下文统一纳入控制面，不再散落在脚本和人工流程里。"
      meta={
        <>
          <span className="badge badge--neutral">5% → 25% → 50% → 100%</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实发布脚本 API 已接入' : '当前展示回退到门户样例'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={<button className="button button--primary">发起回滚演练</button>}
      footer={
        <>
          <button className="button">查看 SLO gate</button>
          <button className="button button--danger">执行紧急回滚</button>
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

      <SectionCard title="当前发布单" subtitle="与现有 config release 脚本语义保持一致，门户只负责统一观察和审批入口">
        <div className="stack-list">
          {releases.map((release) => (
            <div className="config-item" key={release.releaseId}>
              <div>
                <p className="item-title">{release.service} / {release.releaseId}</p>
                <p className="item-subtitle">{release.releaseState || release.configPath}</p>
              </div>
              <span className="badge badge--success">ready</span>
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
