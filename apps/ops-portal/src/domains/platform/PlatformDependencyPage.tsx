import { useEffect, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated';
import {
  fetchCapacityProfiles,
  fetchDependencies,
  type CapacityProfileItem,
  type DependencyItem,
} from '../../shared/api/controlPlane';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function PlatformDependencyPage() {
  const dependencyObjects = platformControlPlane.object_types.filter((item) =>
    ['environment_topology', 'dependency_profile', 'capacity_profile'].includes(item.object_type),
  );
  const [dependencies, setDependencies] = useState<DependencyItem[]>([]);
  const [capacityProfiles, setCapacityProfiles] = useState<CapacityProfileItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);

  useEffect(() => {
    Promise.all([fetchDependencies(), fetchCapacityProfiles()])
      .then(([dependencyItems, capacityItems]) => {
        setDependencies(dependencyItems);
        setCapacityProfiles(capacityItems);
        setRemoteReady(true);
      })
      .catch(() => {
        setRemoteReady(false);
      });
  }, []);

  return (
    <PageScaffold
      title="Platform Ops / 环境与依赖"
      subtitle="统一观察环境拓扑、依赖画像和容量边界，支撑 user-plane 与 control-plane 的独立扩缩容。"
      meta={
        <>
          <span className="badge badge--neutral">topology / dependency / capacity</span>
          <span className="badge badge--success">plane split ready</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实拓扑服务已接入' : '当前展示回退到门户样例'}
          </span>
        </>
      }
      actions={<button className="button button--primary">查看拓扑变更</button>}
      footer={
        <>
          <button className="button">导出依赖清单</button>
          <button className="button button--primary">提交容量评审</button>
        </>
      }
    >
      <SectionCard title="控制面对象" subtitle="环境、依赖、容量三类对象共同定义平台拓扑真相源">
        <div className="stack-list">
          {dependencyObjects.map((item) => (
            <div className="policy-item" key={item.object_type}>
              <div>
                <p className="item-title">{item.label}</p>
                <p className="item-subtitle">
                  source={item.source_entity} · profile={item.deployment_profile}
                </p>
              </div>
              <span className="badge badge--neutral">{item.object_kind}</span>
            </div>
          ))}
        </div>
      </SectionCard>

      <div className="section-grid section-grid--two">
        <SectionCard title="依赖画像" subtitle="数据库、缓存、消息与外部依赖的统一观测视图">
          <div className="stack-list">
            {dependencies.map((item) => (
              <div className="policy-item" key={item.dependency}>
                <div>
                  <p className="item-title">{item.dependency}</p>
                  <p className="item-subtitle">
                    {item.profile} · latency={item.latency}
                  </p>
                </div>
                <span className={`badge badge--${item.status}`}>{item.status}</span>
              </div>
            ))}
            {dependencies.length === 0 ? (
              <div className="policy-item">
                <div>
                  <p className="item-title">等待依赖画像</p>
                  <p className="item-subtitle">平台控制面可达后将展示数据库、缓存与外部依赖。</p>
                </div>
                <span className="badge badge--warning">offline</span>
              </div>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="容量画像" subtitle="控制面与用户面的资源画像必须分开定义">
          <div className="stack-list">
            {capacityProfiles.map((item) => (
              <div className="policy-item" key={item.plane}>
                <div>
                  <p className="item-title">{item.plane}</p>
                  <p className="item-subtitle">
                    class={item.resourceClass} · scaling={item.scaling}
                  </p>
                  <p className="item-subtitle">split trigger: {item.splitTrigger}</p>
                </div>
              </div>
            ))}
            {capacityProfiles.length === 0 ? (
              <div className="policy-item">
                <div>
                  <p className="item-title">等待容量画像</p>
                  <p className="item-subtitle">控制面与用户面的资源画像将在平台控制面可达后展示。</p>
                </div>
                <span className="badge badge--warning">offline</span>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>
    </PageScaffold>
  );
}
