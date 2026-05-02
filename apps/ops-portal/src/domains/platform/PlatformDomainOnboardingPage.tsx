import { useEffect, useState } from 'react';

import { domainOnboardingDomains } from '../../generated/control-plane/domainOnboardingDomains.generated.js';
import { domainOnboardingSchema } from '../../generated/control-plane/domainOnboardingSchema.generated.js';
import { fetchOnboardingDomains, type OnboardingDomainItem } from '../../shared/api/controlPlane.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

type DomainEntry = OnboardingDomainItem;

function toBadgeTone(status: string) {
  if (status === 'minimum_test_ready' || status === 'deploy_bound' || status === 'integration_pass') {
    return 'success';
  }
  if (status === 'gate_ready' || status === 'integration_pass_with_gaps') {
    return 'warning';
  }
  if (status === 'metadata_ready' || status === 'codegen_ready' || status === 'schema_frozen') {
    return 'neutral';
  }
  return 'danger';
}

export function PlatformDomainOnboardingPage() {
  const [remoteDomains, setRemoteDomains] = useState<DomainEntry[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
    fetchOnboardingDomains()
      .then((items) => {
        setRemoteDomains(items);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });
  }, []);

  const fallbackDomains = Object.values(domainOnboardingDomains) as unknown as DomainEntry[];
  const statusOrder = new Map<string, number>(
    domainOnboardingSchema.schema.acceptance_statuses.map((status, index) => [status, index]),
  );
  const domains = (remoteDomains.length > 0
    ? remoteDomains
    : fallbackDomains
  ).sort((a, b) => {
    const statusDiff =
      (statusOrder.get(a.acceptance_status) ?? 999) - (statusOrder.get(b.acceptance_status) ?? 999);
    if (statusDiff !== 0) {
      return statusDiff;
    }
    return a.domain.localeCompare(b.domain);
  });

  const statusCounts = domainOnboardingSchema.schema.acceptance_statuses.map((status) => ({
    status,
    count: domains.filter((item) => item.acceptance_status === status).length,
  })).filter((item) => item.count > 0);

  const waveGroups = Array.from(
    domains.reduce((acc, item) => {
      const list = acc.get(item.rollout_group) ?? [];
      list.push(item);
      acc.set(item.rollout_group, list);
      return acc;
    }, new Map<string, DomainEntry[]>()),
  );

  const readyCount = domains.filter((item) => item.acceptance_status === 'minimum_test_ready').length;
  const blockedCount = domains.filter((item) => item.blocking_gaps.length > 0).length;

  return (
    <PageScaffold
      title="Platform Ops / 领域接入矩阵"
      subtitle="把 domain_onboarding schema、逐域实例、plane-aware binding 与门禁聚合统一收口为同一张状态矩阵，避免再靠人工对表。"
      meta={
        <>
          <span className="badge badge--neutral">domain_onboarding</span>
          <span className="badge badge--success">{readyCount} 个领域已达 minimum_test_ready</span>
          <span className="badge badge--warning">{blockedCount} 个领域仍有 blocker</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实接入矩阵已接入' : '当前展示回退到 codegen 快照'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={<button className="button button--primary">导出接入报告</button>}
      footer={
        <>
          <button className="button">查看 plane binding</button>
          <button className="button button--primary">发起统一收口评审</button>
        </>
      }
    >
      <div className="metric-strip">
        <div className="metric-pill">
          <div className="metric-pill__label">模板域</div>
          <div className="metric-pill__value">{domainOnboardingSchema.minimum_package.template_domain}</div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">首批复制域</div>
          <div className="metric-pill__value">
            {domainOnboardingSchema.minimum_package.first_wave_replica_domains.join(', ')}
          </div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">状态分布</div>
          <div className="metric-pill__value">
            {statusCounts.map((item) => `${item.status}:${item.count}`).join(' / ')}
          </div>
        </div>
      </div>

      <SectionCard title="统一接入状态" subtitle="逐域展示当前完成度、绑定服务和剩余阻塞项">
        <div className="stack-list">
          {domains.map((item) => (
            <div className="onboarding-item" key={item.domain}>
              <div className="onboarding-item__main">
                <div className="onboarding-item__title-row">
                  <p className="item-title">{item.display_name}</p>
                  <span className={`badge badge--${toBadgeTone(item.acceptance_status)}`}>
                    {item.acceptance_status}
                  </span>
                  <span className="badge badge--neutral">{item.template_role}</span>
                  <span className="badge badge--neutral">{item.rollout_group}</span>
                </div>
                <p className="item-subtitle">
                  domain={item.domain} · services={item.service_names.join(', ')} · metadata=
                  {item.metadata_paths.join(', ')}
                </p>
                <div className="badge-row">
                  {Object.entries(item.control_planes).map(([plane, config]) => (
                    <span className={`badge ${config.enabled ? 'badge--success' : 'badge--danger'}`} key={plane}>
                      {plane} · {config.object_types.length} objects
                    </span>
                  ))}
                </div>
                <div className="onboarding-evidence">
                  <span>T1 {item.minimum_package.test_evidence.t1.length}</span>
                  <span>T2 {item.minimum_package.test_evidence.t2.length}</span>
                  <span>T3 {item.minimum_package.test_evidence.t3.length}</span>
                  <span>T4 {item.minimum_package.test_evidence.t4.length}</span>
                </div>
                {item.blocking_gaps.length ? (
                  <ul className="onboarding-blockers">
                    {item.blocking_gaps.map((gap) => (
                      <li key={gap}>{gap}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="item-subtitle">当前没有 blocker，可直接继续统一复制或收口。</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <div className="section-grid section-grid--two">
        <SectionCard title="按批次推进" subtitle="按模板域、复制域、回填域组织统一推进节奏">
          <div className="stack-list">
            {waveGroups.map(([wave, items]) => (
              <div className="policy-item" key={wave}>
                <div>
                  <p className="item-title">{wave}</p>
                  <p className="item-subtitle">{items.map((item) => item.domain).join(', ')}</p>
                </div>
                <span className="badge badge--neutral">{items.length} 个领域</span>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="统一规则基线" subtitle="所有领域共享的 schema 约束和必备 codegen 目标">
          <div className="stack-list">
            <div className="policy-item">
              <div>
                <p className="item-title">必备测试层</p>
                <p className="item-subtitle">
                  {domainOnboardingSchema.schema.required_test_layers.join(', ')}
                </p>
              </div>
            </div>
            <div className="policy-item">
              <div>
                <p className="item-title">必备 codegen 目标</p>
                <p className="item-subtitle">
                  {domainOnboardingSchema.schema.required_codegen_targets.join(', ')}
                </p>
              </div>
            </div>
            <div className="policy-item">
              <div>
                <p className="item-title">部署真相源</p>
                <p className="item-subtitle">
                  current={domainOnboardingSchema.minimum_package.required_deploy_sources.current}
                </p>
                <p className="item-subtitle">
                  plane-aware={domainOnboardingSchema.minimum_package.required_deploy_sources.plane_aware}
                </p>
              </div>
            </div>
          </div>
        </SectionCard>
      </div>
    </PageScaffold>
  );
}
