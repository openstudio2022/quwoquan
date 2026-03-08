import { useEffect, useState } from 'react';
import { platformControlPlane } from '../../generated/control-plane/platformControlPlane.generated';
import {
  fetchPlaneBindings,
  fetchServiceCatalog,
  type PlaneBindingItem,
  type ServiceCatalogItem,
} from '../../shared/api/controlPlane';
import { SectionCard } from '../../shared/components/SectionCard';
import { PageScaffold } from '../../shared/layout/PageScaffold';

export function PlatformServiceCatalogPage() {
  const catalogObjects = platformControlPlane.object_types.filter((item) =>
    ['service_catalog_entry', 'plane_binding'].includes(item.object_type),
  );
  const [services, setServices] = useState<ServiceCatalogItem[]>([]);
  const [bindings, setBindings] = useState<PlaneBindingItem[]>([]);
  const [remoteReady, setRemoteReady] = useState(false);

  useEffect(() => {
    Promise.all([fetchServiceCatalog(), fetchPlaneBindings()])
      .then(([items, bindingItems]) => {
        setServices(items);
        setBindings(bindingItems);
        setRemoteReady(true);
      })
      .catch(() => {
        setRemoteReady(false);
      });
  }, []);

  return (
    <PageScaffold
      title="Platform Ops / 服务目录"
      subtitle="统一展示领域、plane、部署绑定与责任边界，确保平台接入不依赖当前 Pod 组合形态。"
      meta={
        <>
          <span className="badge badge--neutral">catalog / plane binding</span>
          <span className="badge badge--success">支持独立扩缩容演进</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实目录服务已接入' : '当前展示回退到门户样例'}
          </span>
        </>
      }
      actions={<button className="button button--primary">新增领域接入评审</button>}
      footer={
        <>
          <button className="button">查看拓扑 diff</button>
          <button className="button button--primary">导出责任边界</button>
        </>
      }
    >
      <SectionCard title="控制面对象" subtitle="来自 platform control_plane.yaml 的目录与绑定对象">
        <div className="stack-list">
          {catalogObjects.map((item) => (
            <div className="policy-item" key={item.object_type}>
              <div>
                <p className="item-title">{item.label}</p>
                <p className="item-subtitle">
                  kind={item.object_kind} · source={item.source_entity} · view={item.view_model}
                </p>
              </div>
              <span className="badge badge--neutral">{item.deployment_profile}</span>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="当前服务目录" subtitle="作为 platform-ops 接入清单、责任边界与后续自动发现的门户承接层">
        <div className="stack-list">
          {services.map((item) => {
            const matchedBindings = bindings.filter((binding) => binding.process === item.service);
            const planeText =
              matchedBindings.length > 0
                ? Array.from(new Set(matchedBindings.flatMap((binding) => binding.planes))).join(' / ')
                : item.plane;
            return (
            <div className="policy-item" key={item.service}>
              <div>
                <p className="item-title">{item.service}</p>
                <p className="item-subtitle">
                  {planeText} · owner={item.owner}
                </p>
                <p className="item-subtitle">{item.summary}</p>
              </div>
              <span className={`badge badge--${item.health}`}>{item.health}</span>
            </div>
            );
          })}
          {services.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">等待平台控制面连接</p>
                <p className="item-subtitle">服务目录与 plane 绑定将在后端可达后展示。</p>
              </div>
              <span className="badge badge--warning">offline</span>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
