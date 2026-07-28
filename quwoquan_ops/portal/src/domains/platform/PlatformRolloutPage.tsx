import { useEffect, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated.js';
import {
  fetchGrayRoutingPolicy,
  fetchReleases,
  type GrayRoutingPolicyResponse,
  type GrayRoutingStage,
  type ReleaseItem,
} from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

const grayRoutingStages: Array<{ stage: GrayRoutingStage; label: string }> = [
  { stage: 'gray-initial', label: '初始灰度' },
  { stage: 'carry-on', label: '持续放量' },
  { stage: 'full', label: '全量' },
];

const grayRoutingDimensions = [
  { key: 'appVersions', label: '端侧版本', header: 'X-Client-App-Version' },
  { key: 'userIds', label: '用户白名单', header: 'X-Client-User-Id' },
  { key: 'provinces', label: '省份（可信边缘接入前禁用）', header: 'X-Client-Region-Code' },
  { key: 'carriers', label: '运营商（可信边缘接入前禁用）', header: 'X-Client-Carrier' },
] as const;

function reportedValue(value: string | undefined): string {
  return value?.trim() || '未报告';
}

function releaseStateBadgeTone(state: string): string {
  if (state === 'rolled_back' || state === 'drift' || state === 'failed') {
    return 'badge--danger';
  }
  if (state === 'paused' || state === '未报告') {
    return 'badge--warning';
  }
  return 'badge--success';
}

export function PlatformRolloutPage() {
  const releaseObject = platformControlPlane.object_types.find((item) => item.object_type === 'release_candidate');
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

  const candidateDigest = releases[0]?.releaseId;

  return (
    <PageScaffold
      title="Platform Ops / 灰度与配置候选"
      subtitle="只读展示控制面已声明、实例实际 ACK 的候选摘要与 IaC 灰度策略；Portal 不提供第二执行入口。"
      meta={
        <>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实发布工作流 API 已接入' : '等待平台控制面连接'}
          </span>
          {candidateDigest ? <span className="badge badge--neutral">candidate={candidateDigest.slice(0, 16)}</span> : null}
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
        subtitle="当前仅按端侧版本和 userId 白名单分流。province/carrier 在可信边缘 attestation 与 hosted UAT 到位前保持空值且不参与路由；未知或未命中均走稳定栈。"
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
                  <th>发布阶段</th>
                  <th>维度</th>
                  <th>匹配请求头</th>
                  <th>命中值</th>
                </tr>
              </thead>
              <tbody>
                {grayRoutingStages.flatMap(({ stage, label }) => {
                  const dimensions = routingPolicy.policy.stageDimensions[stage];
                  return grayRoutingDimensions.map(({ key, label: dimensionLabel, header }) => (
                    <tr key={`${stage}-${key}`}>
                      <td>{label}</td>
                      <td>{dimensionLabel}</td>
                      <td>{header}</td>
                      <td>{dimensions[key].join(', ') || '（空 = 不匹配）'}</td>
                    </tr>
                  ));
                })}
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

      <SectionCard title="实例 ACK 候选摘要" subtitle="每行来自当前控制面候选摘要下的实例 ACK 聚合；未声明候选或无 ACK 时不显示合成发布状态。">
        <div className="stack-list">
          {releases.map((release) => (
            <div className="config-item" key={`${release.releaseId}-${release.service}`}>
              <div>
                <p className="item-title">{release.service} / {release.releaseId}</p>
                <p className="item-subtitle">
                  configVersion={reportedValue(release.configVersion)}
                  {release.updatedAt ? ` · updatedAt=${release.updatedAt}` : ''}
                </p>
              </div>
              <span className={`badge ${releaseStateBadgeTone(reportedValue(release.releaseState))}`}>
                {reportedValue(release.releaseState)}
              </span>
            </div>
          ))}
          {releases.length === 0 ? (
            <div className="config-item">
              <div>
                <p className="item-title">尚无可验证候选 ACK</p>
                <p className="item-subtitle">控制面候选摘要和实例 ACK 同时存在后才显示；不会从本地文件、默认阶段或伪造 token 推断状态。</p>
              </div>
              <span className="badge badge--warning">not_reported</span>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
