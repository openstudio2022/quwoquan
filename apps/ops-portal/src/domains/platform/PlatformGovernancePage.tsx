import { useEffect, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated.js';
import {
  fetchGovernanceBindings,
  fetchGovernanceTemplates,
  type GovernanceBindingItem,
  type GovernanceTemplateItem,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

export function PlatformGovernancePage() {
  const governanceObjects = platformControlPlane.object_types.filter((item) =>
    ['governance_policy_template', 'governance_policy_binding'].includes(item.object_type),
  );
  const [policies, setPolicies] = useState<GovernanceBindingItem[]>([]);
  const [templates, setTemplates] = useState<GovernanceTemplateItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
    Promise.all([fetchGovernanceBindings(), fetchGovernanceTemplates()])
      .then(([bindingItems, templateItems]) => {
        setPolicies(bindingItems);
        setTemplates(templateItems);
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
      title="Platform Ops / 治理策略"
      subtitle="统一管理超时、重试、熔断、限流、降级与健康策略模板，避免规则散落在服务代码和部署脚本中。"
      meta={
        <>
          <span className="badge badge--neutral">policy template / binding</span>
          <span className="badge badge--warning">高风险变更需审批</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实治理绑定已接入' : '当前展示回退到门户样例'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={<button className="button button--primary">创建策略模板</button>}
      footer={
        <>
          <button className="button">查看绑定 diff</button>
          <button className="button button--primary">提交策略变更</button>
        </>
      }
    >
      <SectionCard title="治理对象" subtitle="所有策略模板与绑定对象都必须经由 control_plane.yaml 暴露">
        <div className="stack-list">
          {governanceObjects.map((item) => (
            <div className="policy-item" key={item.object_type}>
              <div>
                <p className="item-title">{item.label}</p>
                <p className="item-subtitle">
                  risk={item.risk_level} · {item.operations.length} 个受控动作
                </p>
              </div>
              <span className="badge badge--warning">{item.object_kind}</span>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="当前策略池" subtitle="先由门户承接策略观察与审批，后续再接入真实策略编辑器">
        <div className="stack-list">
          {templates.map((item) => (
            <div className="policy-item" key={item.id}>
              <div>
                <p className="item-title">{item.title}</p>
                <p className="item-subtitle">{item.summary}</p>
              </div>
              <span className={`badge badge--${item.status}`}>{item.status}</span>
            </div>
          ))}
          {policies.map((item) => (
            <div className="policy-item" key={item.title}>
              <div>
                <p className="item-title">{item.title}</p>
                <p className="item-subtitle">{item.subtitle}</p>
              </div>
              <span className={`badge badge--${item.status}`}>{item.status}</span>
            </div>
          ))}
          {templates.length === 0 && policies.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">等待治理策略接入</p>
                <p className="item-subtitle">模板与绑定将在平台控制面可达后展示。</p>
              </div>
              <span className="badge badge--warning">offline</span>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
