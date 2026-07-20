import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';

import { SectionCard } from '../../shared/components/SectionCard.js';
import { KpiCard } from '../../shared/components/KpiCard.js';
import {
  fetchConfigDomains,
  fetchConfigSnapshot,
  fetchEffectiveConfig,
  fetchPlatformConfigInstanceReports,
  fetchPlatformConfigKeys,
  type ConfigDomainItem,
  type ConfigInstanceReportItem,
  type ConfigKeyItem,
  type ConfigSnapshotView,
  type EffectiveConfigResponse,
} from '../../shared/api/controlPlane.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { usePortalScope } from '../../shared/layout/PortalContext.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

const configViewRoutes = [
  { id: 'snapshot', label: '配置快照（IaC 只读）', route: '/platform/config/snapshot' },
  { id: 'drift', label: '实例一致性', route: '/platform/config/drift' },
] as const;

type ConfigViewId = (typeof configViewRoutes)[number]['id'];

function resolveConfigView(pathname: string): ConfigViewId {
  if (pathname.endsWith('/drift')) {
    return 'drift';
  }
  return 'snapshot';
}

export function PlatformConfigPage() {
  const { environment } = usePortalScope();
  const { pathname } = useLocation();
  const [configKeys, setConfigKeys] = useState<ConfigKeyItem[]>([]);
  const [domains, setDomains] = useState<ConfigDomainItem[]>([]);
  const [instanceReports, setInstanceReports] = useState<ConfigInstanceReportItem[]>([]);
  const [snapshot, setSnapshot] = useState<ConfigSnapshotView | null>(null);
  const [effectiveConfig, setEffectiveConfig] = useState<EffectiveConfigResponse | null>(null);
  const [selectedService, setSelectedService] = useState<string>('');
  const [expandedFile, setExpandedFile] = useState<string>('');
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const activeTab = resolveConfigView(pathname);

  useEffect(() => {
    Promise.all([fetchPlatformConfigKeys(), fetchConfigDomains(), fetchPlatformConfigInstanceReports()])
      .then(([keyItems, domainItems, reportPayload]) => {
        setConfigKeys(keyItems);
        setDomains(domainItems);
        setInstanceReports(reportPayload.items);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRuntimeError(coerceRuntimeError(error));
      });
  }, []);

  useEffect(() => {
    if (!selectedService) {
      setSnapshot(null);
      setEffectiveConfig(null);
      return;
    }
    setExpandedFile('');
    Promise.all([
      fetchConfigSnapshot(environment, selectedService),
      fetchEffectiveConfig({ env: environment, service: selectedService }),
    ])
      .then(([snapshotView, resolved]) => {
        setSnapshot(snapshotView);
        setEffectiveConfig(resolved);
        setRuntimeError(null);
      })
      .catch((error) => {
        setSnapshot(null);
        setEffectiveConfig(null);
        setRuntimeError(coerceRuntimeError(error));
      });
  }, [environment, selectedService]);

  const serviceOptions = useMemo(() => {
    const options: { value: string; label: string }[] = [];
    for (const domain of domains) {
      for (const service of domain.services ?? []) {
        options.push({ value: service, label: `${domain.label} / ${service}` });
      }
    }
    return options;
  }, [domains]);

  const envReports = useMemo(
    () => instanceReports.filter((item) => item.environment === environment),
    [environment, instanceReports],
  );
  const outOfSyncCount = envReports.filter((item) => !item.inSync).length;
  const hotConfigCount = configKeys.filter((item) => item.reload === 'hot').length;
  const editableCount = configKeys.filter((item) => item.uiEditable).length;

  return (
    <PageScaffold
      title="Platform Ops / 配置快照（IaC）"
      subtitle="配置唯一真相源是版本化发布包：云侧服务、端侧 App、数据工程与平台自身全部只读可查，无任何在线编辑入口。云侧服务 release 配置只保留当前灰度与上一版本。"
      meta={
        <>
          <span className="badge badge--neutral">IaC read-only</span>
          <span className={`badge ${editableCount === 0 ? 'badge--success' : 'badge--warning'}`}>
            {editableCount === 0 ? '在线编辑已封禁' : `${editableCount} 个键仍可编辑`}
          </span>
          <span className="badge badge--success">env={environment}</span>
          <span className="badge badge--neutral">view={activeTab}</span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={
        <Link className="button button--primary" to="/platform/rollout">
          查看配置发布单
        </Link>
      }
    >
      <div className="section-grid section-grid--cards">
        <KpiCard
          label="配置键"
          value={String(configKeys.length)}
          icon={<span className="badge badge--neutral">keys</span>}
          trendLabel={`${hotConfigCount} 个热生效（值仍随发布包变化）`}
          trendTone="positive"
          description="codegen 键目录登记的 sys.* 治理语义。"
        />
        <KpiCard
          label="配置域"
          value={String(domains.length)}
          icon={<span className="badge badge--neutral">domains</span>}
          trendLabel="云侧服务 / 端侧 App / 数据工程"
          trendTone="positive"
          description="全部配置域均可只读查看发布包快照。"
        />
        <KpiCard
          label="实例漂移"
          value={String(outOfSyncCount)}
          icon={<span className="badge badge--warning">drift</span>}
          trendLabel={`${envReports.length} 个实例被观测`}
          trendTone={outOfSyncCount > 0 ? 'warning' : 'positive'}
          description="比较发布包 desired hash 与实例 ACK effective hash。"
        />
        <KpiCard
          label="release 版本保留"
          value="2"
          icon={<span className="badge badge--neutral">retention</span>}
          trendLabel="当前灰度 + 上一版本"
          trendTone="positive"
          description="门禁 prune_config_releases.py --check 阻断超限。"
        />
      </div>

      <SectionCard
        title="配置域与目标选择"
        subtitle="选择配置域内的服务查看该环境的发布包快照；端侧选 app，数据工程选 data"
      >
        <div className="toolbar-row">
          <label className="toolbar-field">
            <span>配置目标</span>
            <select value={selectedService} onChange={(event) => setSelectedService(event.target.value)}>
              <option value="">请选择</option>
              {serviceOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>配置域</th>
              <th>说明</th>
              <th>目标数</th>
            </tr>
          </thead>
          <tbody>
            {domains.map((item) => (
              <tr key={item.domain}>
                <td>{item.label}</td>
                <td>{item.description}</td>
                <td>{item.services?.length ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard
        title="配置视图"
        subtitle="snapshot / drift 拥有独立 URL"
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
        {activeTab === 'snapshot' ? (
          snapshot ? (
            <>
              <div className="inline-note">
                domain={snapshot.domain} · source={snapshot.snapshotSource} · mergedSha256=
                {snapshot.mergedSha256 ?? 'n/a'}
                {snapshot.releaseVersions.length > 0
                  ? ` · release=${snapshot.releaseVersions.join(' / ')}`
                  : null}
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>文件</th>
                    <th>角色</th>
                    <th>sha256</th>
                    <th>内容</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.files.map((file) => (
                    <tr key={file.path}>
                      <td>{file.path}</td>
                      <td>{file.role}</td>
                      <td>{file.sha256.slice(0, 12)}…</td>
                      <td>
                        <button
                          className="button"
                          onClick={() => setExpandedFile(expandedFile === file.path ? '' : file.path)}
                        >
                          {expandedFile === file.path ? '收起' : '查看'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {expandedFile ? (
                <pre className="code-block">
                  {snapshot.files.find((file) => file.path === expandedFile)?.content ?? ''}
                </pre>
              ) : null}
              {effectiveConfig ? (
                <>
                  <div className="inline-note">
                    sys.* 有效值（发布包解析）· desiredHash={effectiveConfig.desiredHash.slice(0, 12)}… ·
                    source={effectiveConfig.source}
                  </div>
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
                      {effectiveConfig.values.map((item) => (
                        <tr key={item.key}>
                          <td>{item.key}</td>
                          <td>{String(item.value)}</td>
                          <td>{item.scopeLevel}</td>
                          <td>{item.sourceLayer}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              ) : null}
            </>
          ) : (
            <div className="inline-note">选择配置目标后展示该环境的发布包快照与 sys.* 有效值。</div>
          )
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

      <SectionCard title="配置键目录" subtitle="metadata 驱动的 sys.* 键；IaC 收口后全部只读，值只随发布包变化">
        <table className="table">
          <thead>
            <tr>
              <th>配置项</th>
              <th>默认值</th>
              <th>scope</th>
              <th>reload</th>
              <th>risk</th>
              <th>在线编辑</th>
            </tr>
          </thead>
          <tbody>
            {configKeys.map((config) => (
              <tr key={config.key}>
                <td>{config.key}</td>
                <td>{String(config.default)}</td>
                <td>{config.scope}</td>
                <td>{config.reload}</td>
                <td>{config.riskLevel ?? 'n/a'}</td>
                <td>{config.uiEditable ? '可编辑（违规）' : '禁止'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </PageScaffold>
  );
}
