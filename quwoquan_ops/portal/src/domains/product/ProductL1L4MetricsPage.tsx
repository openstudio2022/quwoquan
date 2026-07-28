import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, ShieldCheck, Sparkles } from 'lucide-react';
import { Link, NavLink, useLocation } from 'react-router-dom';

import {
  fetchPlatformConfigInstanceReports,
  fetchProductL1L4Metrics,
  type ProductL1L4AlertState,
  fetchProductProjectionSummary,
  fetchRuntimeServices,
  fetchServiceRouteRED,
  type ConfigInstanceReportItem,
  type ProductL1L4MetricsResponse,
  type ProductMetricItem,
  type ProductProjectionSummary,
  type RuntimeServiceItem,
  type ServiceRouteREDResponse,
} from '../../shared/api/controlPlane.js';
import { KpiCard } from '../../shared/components/KpiCard.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { usePortalScope } from '../../shared/layout/PortalContext.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

// 单机 prod-hosted 拓扑没有多集群维度：下钻收敛为 environment + service，
// 实例一致性由 config ACK 报告承载，不再提供独立 instance 路由。
const l1l4RouteViews = [
  { id: 'environment', label: '环境总览', route: '/product/l1-l4/environment', defaultLevel: 'all' },
  { id: 'service', label: '服务下钻', route: '/product/l1-l4/service', defaultLevel: 'L3' },
] as const;

type L1L4RouteViewId = (typeof l1l4RouteViews)[number]['id'];

function resolveL1L4Route(pathname: string): L1L4RouteViewId {
  if (pathname.endsWith('/service')) {
    return 'service';
  }
  return 'environment';
}

export function ProductL1L4MetricsPage() {
  const { environment } = usePortalScope();
  const { pathname } = useLocation();
  const [summary, setSummary] = useState<ProductProjectionSummary | null>(null);
  const [metrics, setMetrics] = useState<ProductMetricItem[]>([]);
  const [metricsPayload, setMetricsPayload] = useState<ProductL1L4MetricsResponse | null>(null);
  const [instanceReports, setInstanceReports] = useState<ConfigInstanceReportItem[]>([]);
  const [services, setServices] = useState<RuntimeServiceItem[]>([]);
  const [selectedService, setSelectedService] = useState<string>('');
  const [activeLevel, setActiveLevel] = useState<'all' | 'L1' | 'L2' | 'L3' | 'L4'>('all');
  const [routeRED, setRouteRED] = useState<ServiceRouteREDResponse | null>(null);
  const [routeREDError, setRouteREDError] = useState<RuntimeError | null>(null);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);
  const activeRoute = resolveL1L4Route(pathname);
  const activeRouteMeta = l1l4RouteViews.find((item) => item.id === activeRoute) ?? l1l4RouteViews[0];

  useEffect(() => {
    Promise.all([
      fetchProductProjectionSummary(),
      fetchPlatformConfigInstanceReports(),
      fetchRuntimeServices(),
    ])
      .then(([summaryItem, reportPayload, serviceItems]) => {
        setSummary(summaryItem);
        setInstanceReports(reportPayload.items);
        setServices(serviceItems);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRuntimeError(coerceRuntimeError(error));
      });
  }, []);

  useEffect(() => {
    const nextRouteLevel = l1l4RouteViews.find((item) => item.id === activeRoute)?.defaultLevel ?? 'all';
    setActiveLevel(nextRouteLevel);
  }, [activeRoute]);

  useEffect(() => {
    fetchProductL1L4Metrics({
      env: environment,
      service: selectedService || undefined,
      level: activeLevel === 'all' ? undefined : activeLevel,
    })
      .then((payload: ProductL1L4MetricsResponse) => {
        setMetricsPayload(payload);
        setMetrics(payload.items);
        setRuntimeError(null);
      })
      .catch((error) => {
        setMetricsPayload(null);
        setRuntimeError(coerceRuntimeError(error));
      });
  }, [activeLevel, environment, selectedService]);

  useEffect(() => {
    if (!selectedService) {
      setRouteRED(null);
      setRouteREDError(null);
      return;
    }
    fetchServiceRouteRED(selectedService)
      .then((payload) => {
        setRouteRED(payload);
        setRouteREDError(null);
      })
      .catch((error) => {
        setRouteRED(null);
        setRouteREDError(coerceRuntimeError(error));
      });
  }, [selectedService]);

  const cardRegistry = useMemo(
    () => summary?.l1l4Cards ?? [],
    [summary?.l1l4Cards],
  );
  const envServices = useMemo(
    () => services.filter((item) => item.environment === environment),
    [environment, services],
  );
  const metricByLevel = useMemo(() => {
    const map = new Map<string, ProductMetricItem>();
    metrics.forEach((item) => {
      if (!map.has(item.level)) {
        map.set(item.level, item);
      }
    });
    return map;
  }, [metrics]);
  const scopedReports = useMemo(
    () =>
      instanceReports.filter(
        (item) =>
          item.environment === environment &&
          (!selectedService || item.service === selectedService),
      ),
    [environment, instanceReports, selectedService],
  );

  return (
    <PageScaffold
      title="四层指标 / L1-L4"
      subtitle={`围绕环境体验、业务健康、服务 RED 和基础设施实例一致性做统一收口。当前路由视图：${activeRouteMeta.label}`}
      meta={
        <>
          <span className="badge badge--neutral">l1-l4 metrics</span>
          <span className="badge badge--success">{cardRegistry.length} 个层级指标</span>
          <span className="badge badge--success">env={environment}</span>
          <span className="badge badge--neutral">view={activeRouteMeta.label}</span>
          <span className="badge badge--neutral">source={metricsPayload?.source ?? 'n/a'}</span>
          <span className="badge badge--neutral">{metrics.length} 条指标</span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={
        <>
          <Link className="button" to="/product/recommendation">
            看推荐 surface
          </Link>
          <Link className="button button--primary" to="/platform/observability">
            看平台可观测
          </Link>
        </>
      }
    >
      <SectionCard title="维度选择器" subtitle="L1/L2 先看环境整体，L3 按服务下钻；实例一致性由 config ACK 报告承载">
        <div className="toolbar-row">
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
            <span>层级</span>
            <select value={activeLevel} onChange={(event) => setActiveLevel(event.target.value as 'all' | 'L1' | 'L2' | 'L3' | 'L4')}>
              <option value="all">全部</option>
              <option value="L1">L1</option>
              <option value="L2">L2</option>
              <option value="L3">L3</option>
              <option value="L4">L4</option>
            </select>
          </label>
        </div>
      </SectionCard>

      <SectionCard
        title="二级路由"
        subtitle="环境总览与服务下钻分别有独立 URL，便于分享和回放"
        aside={
          <div className="tab-strip">
            {l1l4RouteViews.map((item) => (
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
        <div className="inline-note">
          当前路由只决定视图焦点，不会替代上面的 `service` / `层级` 过滤器。
        </div>
      </SectionCard>

      <div className="section-grid section-grid--cards">
        {cardRegistry.map((card) => (
          <KpiCard
            key={card.level}
            label={`${card.level} ${card.label}`}
            value={
              metricByLevel.has(card.level)
                ? `${metricByLevel.get(card.level)?.value ?? 'n/a'}${metricByLevel.get(card.level)?.unit ?? ''}`
                : 'n/a'
            }
            icon={
              card.level === 'L1' ? (
                <Sparkles size={20} color="#2563EB" />
              ) : card.level === 'L2' ? (
                <Activity size={20} color="#16A34A" />
              ) : card.level === 'L3' ? (
                <ShieldCheck size={20} color="#2563EB" />
              ) : (
                <AlertTriangle size={20} color="#F59E0B" />
              )
            }
            trendLabel={metricByLevel.get(card.level)?.trend ?? card.metric}
            trendTone={
              metricByLevel.get(card.level)?.status === 'warning'
                ? 'warning'
                : metricByLevel.get(card.level)?.status === 'success'
                  ? 'positive'
                  : card.level === 'L3' || card.level === 'L4'
                    ? 'warning'
                    : 'positive'
            }
            description={metricByLevel.get(card.level)?.description ?? '统一指标注册表。'}
          />
        ))}
      </div>

      <SectionCard title="实时元数据" subtitle="L1-L4 与 dashboard 共用同一份 live telemetry / alert / coverage 口径">
        <div className="section-grid section-grid--cards">
          <KpiCard
            label="数据来源"
            value={metricsPayload?.source ?? 'n/a'}
            icon={<Activity size={20} color="#2563EB" />}
            trendLabel={`window=${metricsPayload?.window ?? 'n/a'}`}
            trendTone="positive"
            description={`freshness=${metricsPayload?.freshness ?? 'n/a'}`}
          />
          <KpiCard
            label="实时覆盖"
            value={metricsPayload ? `${metricsPayload.coverage.liveMetrics}/${metricsPayload.coverage.totalMetrics}` : '—'}
            icon={<ShieldCheck size={20} color="#16A34A" />}
            trendLabel={metricsPayload ? `unavailable=${metricsPayload.coverage.unavailableMetrics}` : '等待指标投影'}
            trendTone={metricsPayload ? (metricsPayload.coverage.unavailableMetrics > 0 ? 'warning' : 'positive') : 'warning'}
            description={metricsPayload ? `eventSignals=${metricsPayload.coverage.eventSignals}` : '等待指标投影'}
          />
          <KpiCard
            label="告警态"
            value={metricsPayload ? String(metricsPayload.alerts.length) : '—'}
            icon={<AlertTriangle size={20} color="#F59E0B" />}
            trendLabel={metricsPayload?.alerts[0]?.state ?? (metricsPayload ? 'quiet' : '等待告警投影')}
            trendTone={metricsPayload ? (metricsPayload.alerts[0]?.state === 'firing' ? 'warning' : 'positive') : 'warning'}
            description={metricsPayload?.alerts[0]?.metric ?? (metricsPayload ? '当前无实时告警' : '等待告警投影')}
          />
          <KpiCard
            label="当前主指标"
            value={metrics[0] ? `${metrics[0].value}${metrics[0].unit}` : 'n/a'}
            icon={<Sparkles size={20} color="#2563EB" />}
            trendLabel={metrics[0]?.metric ?? '等待指标'}
            trendTone={metrics[0]?.status === 'warning' ? 'warning' : 'positive'}
            description={metrics[0]?.source ? `source=${metrics[0].source}` : 'n/a'}
          />
        </div>
        <div className="stack-list" style={{ marginTop: 12 }}>
          {(metricsPayload?.alerts ?? []).map((item: ProductL1L4AlertState) => (
            <div className="policy-item" key={item.id}>
              <div>
                <p className="item-title">{item.metric}</p>
                <p className="item-subtitle">
                  level={item.level} · severity={item.severity} · source={item.source}
                </p>
                <p className="item-subtitle">{item.summary}</p>
              </div>
              <div className="badge-row">
                <span className={`badge badge--${item.state === 'firing' ? 'warning' : item.state === 'warning' ? 'warning' : 'success'}`}>
                  {item.state}
                </span>
                <span className="badge badge--neutral">{item.value}</span>
                {item.repairEntry ? <Link className="button button--primary" to={item.repairEntry}>进入修复入口</Link> : null}
                {item.auditRoute ? <Link className="button" to={item.auditRoute}>查看审计链</Link> : null}
                {item.alertId ? <span className="badge badge--neutral">alert={item.alertId}</span> : null}
              </div>
            </div>
          ))}
          {(metricsPayload?.alerts ?? []).length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">暂无实时告警</p>
                <p className="item-subtitle">当前实时聚合没有产生新的 alert state。</p>
              </div>
              <span className="badge badge--success">quiet</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <div className="section-grid section-grid--two">
        <SectionCard title="四层指标明细" subtitle="来自 product-ops control plane 的真实四层指标响应">
          <table className="table">
            <thead>
              <tr>
                <th>层级</th>
                <th>标签</th>
                <th>主指标</th>
                <th>值</th>
                <th>状态</th>
                <th>source</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((item) => (
                <tr key={item.id}>
                  <td>{item.level}</td>
                  <td>{item.label}</td>
                  <td>{item.metric}</td>
                  <td>{item.value}{item.unit}</td>
                  <td>{item.status}</td>
                  <td>{item.source ?? 'n/a'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </SectionCard>

        <SectionCard
          title="每接口 RED 下钻"
          subtitle="选择服务后按 route 展示 QPS、平均/P99 延迟与成功率（Prometheus service+route 维度，5m 窗口）"
        >
          {routeREDError ? <RuntimeErrorBadge error={routeREDError} /> : null}
          {selectedService && routeRED ? (
            <table className="table">
              <thead>
                <tr>
                  <th>接口（route）</th>
                  <th>QPS</th>
                  <th>平均 ms</th>
                  <th>P99 ms</th>
                  <th>成功率</th>
                </tr>
              </thead>
              <tbody>
                {routeRED.items.map((item) => (
                  <tr key={item.route}>
                    <td>{item.route}</td>
                    <td>{item.qps.toFixed(2)}</td>
                    <td>{item.avgMs.toFixed(1)}</td>
                    <td>{item.p99Ms.toFixed(1)}</td>
                    <td>{item.successRatePercent.toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="inline-note">
              在上方维度选择器选定服务后展示该服务每接口 RED 指标；数据源 window=
              {routeRED?.window ?? '5m'}。
            </div>
          )}
        </SectionCard>

        <SectionCard title="实例一致性联动" subtitle="L4 指标与平台配置中心实例报告共用同一批实例对象">
          <table className="table">
            <thead>
              <tr>
                <th>实例</th>
                <th>服务</th>
                <th>状态</th>
                <th>source</th>
                <th>error</th>
              </tr>
            </thead>
            <tbody>
              {scopedReports.map((item) => (
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
        </SectionCard>
      </div>

      <SectionCard
        title="二级下钻视图"
        subtitle="将四层指标拆成独立层级视图，避免继续停留在“只有一个页面”的样例态"
        aside={
          <div className="tab-strip">
            {['all', 'L1', 'L2', 'L3', 'L4'].map((level) => (
              <button
                key={level}
                className={`tab-chip ${activeLevel === level ? 'tab-chip--active' : ''}`}
                onClick={() => setActiveLevel(level as 'all' | 'L1' | 'L2' | 'L3' | 'L4')}
                type="button"
              >
                {level === 'all' ? '总览' : level}
              </button>
            ))}
          </div>
        }
      >
        <div className="stack-list">
          {metrics.map((item) => (
            <div className="policy-item" key={`detail-${item.id}`}>
              <div>
                <p className="item-title">
                  {item.level} / {item.label}
                </p>
                <p className="item-subtitle">
                  metric={item.metric} · env={item.environment}
                  {item.cluster ? ` · cluster=${item.cluster}` : ''}
                  {item.service ? ` · service=${item.service}` : ''}
                  {item.instanceId ? ` · instance=${item.instanceId}` : ''}
                  {item.source ? ` · source=${item.source}` : ''}
                </p>
              </div>
              <div className="badge-row">
                <span className={`badge badge--${item.status === 'success' ? 'success' : item.status === 'warning' ? 'warning' : 'neutral'}`}>
                  {item.status}
                </span>
                <span className="badge badge--neutral">{item.value}{item.unit}</span>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
