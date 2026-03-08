import { useEffect, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated';
import { fetchGateRules, type GateRuleItem } from '../../shared/api/controlPlane';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function PlatformGatePage() {
  const gateObject = platformControlPlane.object_types.find((item) => item.object_type === 'gate_rule');
  const [gateRules, setGateRules] = useState<GateRuleItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);

  useEffect(() => {
    fetchGateRules()
      .then((items) => {
        setGateRules(items);
        setRemoteReady(true);
      })
      .catch(() => {
        setRemoteReady(false);
      });
  }, []);

  return (
    <PageScaffold
      title="Platform Ops / CI/CD 门禁"
      subtitle="统一收口配置灰度、依赖健康、SLO 预算与回滚准备度，让发布放量不再依赖人工口口相传。"
      meta={
        <>
          <span className="badge badge--neutral">gate / approval / rollback</span>
          <span className="badge badge--warning">高风险放量需要双签</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实门禁规则已接入' : '当前展示回退到门户样例'}
          </span>
        </>
      }
      actions={<button className="button button--primary">新增门禁规则</button>}
      footer={
        <>
          <button className="button">查看失败记录</button>
          <button className="button button--danger">发起门禁放行</button>
        </>
      }
    >
      <SectionCard title="门禁对象" subtitle="平台发布门禁的规则模型来自 control_plane.yaml，而不是页面内硬编码">
        <div className="policy-item">
          <div>
            <p className="item-title">{gateObject?.label}</p>
            <p className="item-subtitle">
              kind={gateObject?.object_kind} · risk={gateObject?.risk_level}
            </p>
          </div>
          <span className="badge badge--warning">{gateObject?.deployment_profile}</span>
        </div>
        <div className="stack-list" style={{ marginTop: 12 }}>
          {gateObject?.operations.map((operation) => (
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

      <SectionCard title="当前门禁规则" subtitle="统一覆盖发布成功率、延迟、依赖健康与回滚准备度">
        <table className="table">
          <thead>
            <tr>
              <th>规则</th>
              <th>阶段</th>
              <th>状态</th>
              <th>摘要</th>
            </tr>
          </thead>
          <tbody>
            {gateRules.map((item) => (
              <tr key={item.rule}>
                <td>{item.rule}</td>
                <td>{item.stage}</td>
                <td>{item.status}</td>
                <td>{item.summary}</td>
              </tr>
            ))}
            {gateRules.length === 0 ? (
              <tr>
                <td colSpan={4}>等待平台门禁规则接入</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </SectionCard>
    </PageScaffold>
  );
}
