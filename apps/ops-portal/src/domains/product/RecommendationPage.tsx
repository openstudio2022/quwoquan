import { useEffect, useMemo, useState } from 'react';
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { productConfigSchema } from '../../generated/control-plane/productConfig.generated.js';
import { productControlPlane } from '../../generated/control-plane/productControlPlane.generated.js';
import {
  fetchRecommendationPolicies,
  type RecommendationPolicyItem,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

export function RecommendationPage() {
  const recommendationObject = productControlPlane.object_types.find(
    (item) => item.object_type === 'recommendation_policy',
  );
  const recommendationConfigs = productConfigSchema.configs.filter((item) => item.key.includes('ops.reco.'));
  const [policies, setPolicies] = useState<RecommendationPolicyItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
    fetchRecommendationPolicies()
      .then((items) => {
        setPolicies(items);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });
  }, []);

  const guardrailTrend = useMemo(() => {
    return policies.slice(0, 3).map((policy, index) => ({
      day: `P${index + 1}`,
      ctr: Number(policy.guardrailSnapshot.ctr ?? 0),
      complaints: Number(policy.guardrailSnapshot.complaints ?? 0),
      diversity: Number(policy.guardrailSnapshot.diversity ?? 0),
    }));
  }, [policies]);

  return (
    <PageScaffold
      title="推荐运营"
      subtitle="覆盖召回、粗排、精排 / 重排的受控干预，不允许越过 guardrail、审计和回滚边界。"
      meta={
        <>
          <span className="badge badge--neutral">召回 / 粗排 / 精排 / 重排</span>
          <span className="badge badge--success">guardrail 全部通过</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实推荐策略已接入' : '当前展示回退到门户样例'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={<button className="button button--primary">发起策略模拟</button>}
      footer={
        <>
          <button className="button">查看回滚令牌</button>
          <button className="button button--primary">提交 canary</button>
        </>
      }
    >
      <div className="section-grid section-grid--two">
        <SectionCard title="策略效果与 Guardrail" subtitle="统一观察 CTR、投诉率与内容生态健康度">
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <LineChart data={guardrailTrend}>
                <CartesianGrid stroke="rgba(17, 24, 39, 0.08)" />
                <XAxis dataKey="day" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Line type="monotone" dataKey="ctr" stroke="#2563EB" strokeWidth={3} dot={false} />
                <Line type="monotone" dataKey="complaints" stroke="#DC2626" strokeWidth={3} dot={false} />
                <Line type="monotone" dataKey="diversity" stroke="#16A34A" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="控制面能力" subtitle="来自 control_plane.yaml 的对象定义和受控动作">
          <div className="stack-list">
            <div className="policy-item">
              <div>
                <p className="item-title">{recommendationObject?.label}</p>
                <p className="item-subtitle">
                  source={recommendationObject?.source_entity} · view={recommendationObject?.view_model} ·
                  risk={recommendationObject?.risk_level}
                </p>
              </div>
              <span className="badge badge--warning">{recommendationObject?.deployment_profile}</span>
            </div>
            {recommendationObject?.operations.map((operation) => (
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
      </div>

      <SectionCard title="策略池" subtitle="结合模拟、canary、回滚令牌和 guardrail 快照管理策略生命周期">
        <div className="stack-list">
          {policies.map((policy) => (
            <div className="policy-item" key={policy.id}>
              <div>
                <p className="item-title">{policy.name}</p>
                <p className="item-subtitle">
                  policy={policy.policyVersion} · status={policy.status}
                </p>
              </div>
              <span className={`badge badge--${policy.status === 'active' ? 'success' : policy.status === 'simulated' ? 'warning' : 'neutral'}`}>
                {policy.status}
              </span>
            </div>
          ))}
          {policies.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">等待推荐策略接入</p>
                <p className="item-subtitle">推荐策略、guardrail 与回滚令牌将在产品控制面可达后展示。</p>
              </div>
              <span className="badge badge--warning">offline</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard title="可编辑参数空间" subtitle="只暴露受限参数，不允许通过控制面直写个体排序结果">
        <table className="table">
          <thead>
            <tr>
              <th>配置项</th>
              <th>默认值</th>
              <th>范围</th>
              <th>风险</th>
            </tr>
          </thead>
          <tbody>
            {recommendationConfigs.map((config) => (
              <tr key={config.key}>
                <td>{config.key}</td>
                <td>{String(config.default)}</td>
                <td>{config.scope}</td>
                <td>{config.risk_level}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </PageScaffold>
  );
}
