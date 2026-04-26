import { useEffect, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated.js';
import { fetchRunbooks, type RunbookItem } from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

export function PlatformRunbookPage() {
  const runbookObject = platformControlPlane.object_types.find((item) => item.object_type === 'runbook');
  const [runbooks, setRunbooks] = useState<RunbookItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
    fetchRunbooks()
      .then((items) => {
        setRunbooks(items);
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
      title="Platform Ops / Runbook 与演练"
      subtitle="把配置回滚、依赖切换、控制面拆分和故障恢复沉淀成可执行 runbook 与定期演练计划。"
      meta={
        <>
          <span className="badge badge--neutral">runbook / drill</span>
          <span className="badge badge--success">rollback ready</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实演练对象已接入' : '当前展示回退到门户样例'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={<button className="button button--primary">创建演练计划</button>}
      footer={
        <>
          <button className="button">查看历史演练</button>
          <button className="button button--primary">执行演练</button>
        </>
      }
    >
      <SectionCard title="Runbook 对象" subtitle="演练入口与对象定义必须由控制面契约统一暴露">
        <div className="policy-item">
          <div>
            <p className="item-title">{runbookObject?.label}</p>
            <p className="item-subtitle">
              kind={runbookObject?.object_kind} · risk={runbookObject?.risk_level}
            </p>
          </div>
          <span className="badge badge--neutral">{runbookObject?.deployment_profile}</span>
        </div>
        <div className="stack-list" style={{ marginTop: 12 }}>
          {runbookObject?.operations.map((operation) => (
            <div className="policy-item" key={operation.operation}>
              <div>
                <p className="item-title">{operation.operation}</p>
                <p className="item-subtitle">
                  {operation.method} {operation.path}
                </p>
              </div>
              <div className="badge-row">
                {'danger_level' in operation && operation.danger_level ? (
                  <span className="badge badge--warning">{operation.danger_level}</span>
                ) : null}
                {'approval_mode' in operation && operation.approval_mode ? (
                  <span className="badge badge--neutral">{operation.approval_mode}</span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="当前 runbook 清单" subtitle="作为统一运维操作手册和演练调度入口的第一版骨架">
        <div className="stack-list">
          {runbooks.map((item) => (
            <div className="policy-item" key={item.title}>
              <div>
                <p className="item-title">{item.title}</p>
                <p className="item-subtitle">{item.subtitle}</p>
              </div>
              <span className={`badge badge--${item.status}`}>{item.status}</span>
            </div>
          ))}
          {runbooks.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">等待 runbook 接入</p>
                <p className="item-subtitle">平台控制面可达后将展示演练计划与最近执行记录。</p>
              </div>
              <span className="badge badge--warning">offline</span>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
