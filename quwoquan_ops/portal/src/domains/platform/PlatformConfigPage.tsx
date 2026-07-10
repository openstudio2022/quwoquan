import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';

import { SectionCard } from '../../shared/components/SectionCard.js';
import { KpiCard } from '../../shared/components/KpiCard.js';
import {
  fetchEffectiveConfig,
  fetchPlatformConfigInstanceReports,
  fetchPlatformConfigKeys,
  fetchPlatformConfigLayers,
  fetchPlatformConfigPackages,
  fetchRuntimeClusters,
  fetchRuntimeInstances,
  fetchRuntimeServices,
  type ConfigInstanceReportItem,
  type ConfigLayerItem,
  type ConfigPackageItem,
  type ConfigKeyItem,
  type EffectiveConfigResponse,
  type RuntimeClusterItem,
  type RuntimeInstanceItem,
  type RuntimeServiceItem,
} from '../../shared/api/controlPlane.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { usePortalScope } from '../../shared/layout/PortalContext.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

const configViewRoutes = [
  { id: 'layers', label: '配置中心', route: '/platform/config/layers' },
  { id: 'packages', label: '配置包', route: '/platform/config/packages' },
  { id: 'drift', label: '实例一致性', route: '/platform/config/drift' },
] as const;

type ConfigViewId = (typeof configViewRoutes)[number]['id'];

function resolveConfigView(pathname: string): ConfigViewId {
  if (pathname.endsWith('/packages')) {
    return 'packages';
  }
  if (pathname.endsWith('/drift')) {
    return 'drift';
  }
  return 'layers';
}

export function PlatformConfigPage() {
  const { environment } = usePortalScope();
  const { pathname } = useLocation();
  const [configKeys, setConfigKeys] = useState<ConfigKeyItem[]>([]);
  const [configLayers, setConfigLayers] = useState<ConfigLayerItem[]>([]);
  const [configPackages, setConfigPackages] = useState<ConfigPackageItem[]>([]);
  const [instanceReports, setInstanceReports] = useState<ConfigInstanceReportItem[]>([]);
  const [clusters, setClusters] = useState<RuntimeClusterItem[]>([]);
  const [services, setServices] = useState<RuntimeServiceItem[]>([]);
  const [instances, setInstances] = useState<RuntimeInstanceItem[]>([]);
  const [effectiveConfig, setEffectiveConfig] = useState<EffectiveConfigResponse | null>(null);
  const [selectedCluster, setSelectedCluster] = useState<string>('');
  const [selectedService, setSelectedService] = useState<string>('');
  const [selectedInstance, setSelectedInstance] = useState<string>('');
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const activeTab = resolveConfigView(pathname);

  useEffect(() => {
    Promise.all([
      fetchPlatformConfigKeys(),
      fetchPlatformConfigLayers(),
      fetchPlatformConfigPackages(),
      fetchPlatformConfigInstanceReports(),
      fetchRuntimeClusters(),
      fetchRuntimeServices(),
      fetchRuntimeInstances(),
    ])
      .then(([keyItems, layerItems, packageItems, reportPayload, clusterItems, serviceItems, instanceItems]) => {
        setConfigKeys(keyItems);
        setConfigLayers(layerItems);
        setConfigPackages(packageItems);
        setInstanceReports(reportPayload.items);
        setClusters(clusterItems);
        setServices(serviceItems);
        setInstances(instanceItems);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRuntimeError(coerceRuntimeError(error));
      });
  }, []);

  useEffect(() => {
    fetchEffectiveConfig({
      env: environment,
      cluster: selectedCluster || undefined,
      service: selectedService || undefined,
    })
      .then((payload) => {
        setEffectiveConfig(payload);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRuntimeError(coerceRuntimeError(error));
      });
  }, [environment, selectedCluster, selectedService]);

  const envClusters = useMemo(
    () => clusters.filter((item) => item.environment === environment),
    [clusters, environment],
  );
  const envServices = useMemo(
    () =>
      services.filter(
        (item) =>
          item.environment === environment && (!selectedCluster || item.cluster === selectedCluster),
      ),
    [environment, selectedCluster, services],
  );
  const envInstances = useMemo(
    () =>
      instances.filter(
        (item) =>
          item.environment === environment &&
          (!selectedCluster || item.cluster === selectedCluster) &&
          (!selectedService || item.service === selectedService),
      ),
    [environment, instances, selectedCluster, selectedService],
  );
  const envLayers = useMemo(
    () => configLayers.filter((item) => item.environment === environment || item.scopeLevel === 'global'),
    [configLayers, environment],
  );
  const envPackages = useMemo(
    () =>
      configPackages.filter(
        (item) =>
          item.environment === environment &&
          (!selectedCluster || item.cluster === selectedCluster) &&
          (!selectedService || item.service === selectedService),
      ),
    [configPackages, environment, selectedCluster, selectedService],
  );
  const envReports = useMemo(
    () =>
      instanceReports.filter(
        (item) =>
          item.environment === environment &&
          (!selectedCluster || item.cluster === selectedCluster) &&
          (!selectedService || item.service === selectedService) &&
          (!selectedInstance || item.instanceId === selectedInstance),
      ),
    [environment, instanceReports, selectedCluster, selectedInstance, selectedService],
  );
  const outOfSyncCount = envReports.filter((item) => !item.inSync).length;
  const hotConfigCount = configKeys.filter((item) => item.reload === 'hot').length;
  const criticalConfigCount = configKeys.filter((item) => item.risk_level === 'high').length;

  return (
    <PageScaffold
      title="Platform Ops / 配置与可靠性"
      subtitle="统一管理全局、环境、集群、服务四层配置。服务终点之下不再把实例当作独立配置层，实例只用于一致性报告。"
      meta={
        <>
          <span className="badge badge--neutral">sys.* only</span>
          <span className="badge badge--warning">高风险项必须灰度</span>
          <span className="badge badge--success">env={environment}</span>
          <span className="badge badge--neutral">view={activeTab}</span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={
        <Link className="button button--primary" to="/platform/rollout">
          创建配置发布单
        </Link>
      }
      footer={
        <>
          <Link className="button" to="/platform/rollout">
            查看变更 diff
          </Link>
          <Link className="button button--primary" to="/platform/rollout">
            提交灰度申请
          </Link>
        </>
      }
    >
      <div className="section-grid section-grid--cards">
        <KpiCard
          label="配置键"
          value={String(configKeys.length)}
          icon={<span className="badge badge--neutral">keys</span>}
          trendLabel={`${hotConfigCount} 个热生效`}
          trendTone="positive"
          description="统一配置中心中的可管理系统参数。"
        />
        <KpiCard
          label="四层配置包"
          value={String(envPackages.length)}
          icon={<span className="badge badge--neutral">pkg</span>}
          trendLabel={`${envLayers.length} 个有效层`}
          trendTone="positive"
          description="全局、环境、集群、服务四层共同生成的发布包。"
        />
        <KpiCard
          label="实例漂移"
          value={String(outOfSyncCount)}
          icon={<span className="badge badge--warning">drift</span>}
          trendLabel={`${envReports.length} 个实例被观测`}
          trendTone={outOfSyncCount > 0 ? 'warning' : 'positive'}
          description="比较配置中心 desired hash 与实例 effective hash。"
        />
        <KpiCard
          label="高风险配置"
          value={String(criticalConfigCount)}
          icon={<span className="badge badge--warning">risk</span>}
          trendLabel="必须走灰度与审计"
          trendTone="warning"
          description="restart 或链路关键超时类配置需要重点治理。"
        />
      </div>

      <SectionCard title="四层选择器" subtitle="环境体验面向全局，有效配置只解析到 service；实例仅用于漂移和观测">
        <div className="toolbar-row">
          <label className="toolbar-field">
            <span>集群</span>
            <select value={selectedCluster} onChange={(event) => setSelectedCluster(event.target.value)}>
              <option value="">全部</option>
              {envClusters.map((item) => (
                <option key={item.id} value={item.cluster}>
                  {item.cluster}
                </option>
              ))}
            </select>
          </label>
          <label className="toolbar-field">
            <span>服务</span>
            <select value={selectedService} onChange={(event) => setSelectedService(event.target.value)}>
              <option value="">全部</option>
              {envServices.map((item) => (
                <option key={item.id} value={item.service}>
                  {item.service}
                </option>
              ))}
            </select>
          </label>
          <label className="toolbar-field">
            <span>实例</span>
            <select value={selectedInstance} onChange={(event) => setSelectedInstance(event.target.value)}>
              <option value="">全部</option>
              {envInstances.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id}
                </option>
              ))}
            </select>
          </label>
        </div>
      </SectionCard>

      <div className="section-grid section-grid--two">
        <SectionCard title="配置键清单" subtitle="metadata 驱动的 sys.* 键，禁止前端维护第二套表">
          <table className="table">
            <thead>
              <tr>
                <th>配置项</th>
                <th>默认值</th>
                <th>scope</th>
                <th>reload</th>
                <th>risk</th>
              </tr>
            </thead>
            <tbody>
              {configKeys.map((config) => (
                <tr key={config.key}>
                  <td>{config.key}</td>
                  <td>{String(config.default)}</td>
                  <td>{config.scope}</td>
                  <td>{config.reload}</td>
                  <td>{config.risk_level ?? 'n/a'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </SectionCard>

        <SectionCard title="当前有效配置" subtitle="按 service > cluster > environment > global 解析，instance 只用于漂移观测">
          <table className="table">
            <thead>
              <tr>
                <th>配置项</th>
                <th>值</th>
                <th>层级</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              {effectiveConfig?.values.map((item) => (
                <tr key={item.key}>
                  <td>{item.key}</td>
                  <td>{String(item.value)}</td>
                  <td>{item.scopeLevel}</td>
                  <td>{item.sourceLayer}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {effectiveConfig ? (
            <div className="inline-note">
              effectiveHash={effectiveConfig.effectiveHash} · source={effectiveConfig.source}
            </div>
          ) : null}
        </SectionCard>
      </div>

      <SectionCard
        title="配置中心二级视图"
        subtitle="layers / packages / drift 拥有独立 URL，避免所有信息继续堆在一个单页"
        aside={
          <div className="tab-strip">
            {configViewRoutes.map((item) => (
              <NavLink
                key={item.id}
                to={item.route}
                className={({ isActive }) => `tab-chip ${isActive ? 'tab-chip--active' : ''}`}
                end
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        }
      >
        {activeTab === 'layers' ? (
          <table className="table">
            <thead>
              <tr>
                <th>层级</th>
                <th>对象</th>
                <th>标题</th>
                <th>覆盖键</th>
              </tr>
            </thead>
            <tbody>
              {envLayers.map((item) => (
                <tr key={item.id}>
                  <td>{item.scopeLevel}</td>
                  <td>{item.scopeID}</td>
                  <td>{item.title ?? item.id}</td>
                  <td>{Object.keys(item.values).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}

        {activeTab === 'packages' ? (
          <table className="table">
            <thead>
              <tr>
                <th>包</th>
                <th>集群</th>
                <th>服务</th>
                <th>配置版本</th>
                <th>分发</th>
              </tr>
            </thead>
            <tbody>
              {envPackages.map((item) => (
                <tr key={item.id}>
                  <td>{item.packageId}</td>
                  <td>{item.cluster}</td>
                  <td>{item.service}</td>
                  <td>{item.configVersion}</td>
                  <td>{item.distribution}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}

        {activeTab === 'drift' ? (
          <table className="table">
            <thead>
              <tr>
                <th>实例</th>
                <th>服务</th>
                <th>状态</th>
                <th>source</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              {envReports.map((item) => (
                <tr key={item.id}>
                  <td>{item.instanceId}</td>
                  <td>{item.service}</td>
                  <td>{item.inSync ? 'in-sync' : 'drift'}</td>
                  <td>{item.source ?? 'n/a'}</td>
                  <td>{item.lastError ?? 'n/a'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </SectionCard>
    </PageScaffold>
  );
}
