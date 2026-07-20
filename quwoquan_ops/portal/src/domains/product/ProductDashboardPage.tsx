import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  fetchPageExperience,
  fetchPremiumPoolEntries,
  fetchProductL1L4Metrics,
  fetchProductProjectionSummary,
  fetchRtcMediaQoeSummary,
  fetchProductTriageSummary,
  fetchProductWorkflows,
  fetchReports,
  type ControlPlaneBacklogCandidate,
  type PageExperienceStat,
  type PremiumPoolEntryItem,
  type ProductL1L4MetricsResponse,
  type ProductProjectionSummary,
  type RtcMediaQoeSummary,
  type ProductTriageSummaryResponse,
  type ReportItem,
  type WorkflowItem,
} from '../../shared/api/controlPlane.js';
import { appPages } from '../../generated/telemetry/appPages.generated.js';
import { SectionCard } from '../../shared/components/SectionCard.js';
import { PageScaffold } from '../../shared/layout/PageScaffold.js';
import { RuntimeErrorBadge, coerceRuntimeError, type RuntimeError } from '../../shared/runtime/errors/index.js';

function formatRatio(value: number | null | undefined): string {
  return value == null ? 'n/a' : `${(value * 100).toFixed(1)}%`;
}

function formatMilliseconds(value: number | null | undefined): string {
  return value == null ? 'n/a' : `${Math.round(value)}ms`;
}

export function ProductDashboardPage() {
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [premiumEntries, setPremiumEntries] = useState<PremiumPoolEntryItem[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [summary, setSummary] = useState<ProductProjectionSummary | null>(null);
  const [triage, setTriage] = useState<ProductTriageSummaryResponse | null>(null);
  const [metricsPayload, setMetricsPayload] = useState<ProductL1L4MetricsResponse | null>(null);
  const [rtcMediaQoe, setRtcMediaQoe] = useState<RtcMediaQoeSummary | null>(null);
  const [rtcMediaQoeError, setRtcMediaQoeError] = useState<RuntimeError | null>(null);
  const [pageExperience, setPageExperience] = useState<PageExperienceStat[]>([]);
  const [pageExperienceError, setPageExperienceError] = useState<RuntimeError | null>(null);
  const [remoteReady, setRemoteReady] = useState(false);
  const [runtimeError, setRuntimeError] = useState<RuntimeError | null>(null);

  useEffect(() => {
    Promise.all([
      fetchProductWorkflows(),
      fetchPremiumPoolEntries(),
      fetchReports(50),
      fetchProductProjectionSummary(),
      fetchProductTriageSummary(),
      fetchProductL1L4Metrics(),
    ])
      .then(([workflowItems, premiumItems, reportItems, summaryItem, triageItem, metricsItem]) => {
        setWorkflows(workflowItems);
        setPremiumEntries(premiumItems);
        setReports(reportItems);
        setSummary(summaryItem);
        setTriage(triageItem);
        setMetricsPayload(metricsItem);
        setRemoteReady(true);
        setRuntimeError(null);
      })
      .catch((error) => {
        setRemoteReady(false);
        setRuntimeError(coerceRuntimeError(error));
      });
    fetchPageExperience()
      .then((payload) => {
        setPageExperience(payload.items);
        setPageExperienceError(null);
      })
      .catch((error) => {
        setPageExperience([]);
        setPageExperienceError(coerceRuntimeError(error));
      });
    fetchRtcMediaQoeSummary()
      .then((payload) => {
        setRtcMediaQoe(payload);
        setRtcMediaQoeError(null);
      })
      .catch((error) => {
        setRtcMediaQoe(null);
        setRtcMediaQoeError(coerceRuntimeError(error));
      });
  }, []);

  const queueItems = useMemo(() => {
    return workflows
      .slice(0, 4)
      .map((item) => ({
        title: `${item.objectType} / ${item.objectId}`,
        subtitle: `workflow=${item.workflowId} · state=${item.state}`,
        status: item.state.includes('pending') || item.state.includes('review') ? 'warning' : 'success',
      }));
  }, [workflows]);

  const backlogCandidates = triage?.backlogCandidates ?? [];
  const alertStates = metricsPayload?.alerts ?? [];
  const topAlert = alertStates[0];
  const highlightBacklog = backlogCandidates[0];
  const topMetric = metricsPayload?.items[0];

  // 页面矩阵热力图：行 = metadata 登记页面全集（含 internal），列 = 真实遥测
  // 聚合；登记但无数据的页面显示 0（防 fake），未登记但出现遥测的页面标注 unregistered。
  const pageHeatmapRows = useMemo(() => {
    const registered = new Set<string>();
    for (const page of appPages.pages) {
      registered.add(page.page_name);
    }
    for (const page of appPages.internal_pages) {
      registered.add(page.page_name);
    }
    const statByPage = new Map(pageExperience.map((item) => [item.pageName, item]));
    const maxOpens = Math.max(1, ...pageExperience.map((item) => item.opens));
    const rows = [...registered].map((pageName) => {
      const stat = statByPage.get(pageName);
      return {
        pageName,
        registered: true,
        opens: stat?.opens ?? 0,
        avgReadyMs: stat?.avgReadyMs ?? 0,
        readySamples: stat?.readySamples ?? 0,
        avgStayMs: stat?.avgStayMs ?? 0,
        runtimeErrors: stat?.runtimeErrors ?? 0,
        heat: (stat?.opens ?? 0) / maxOpens,
      };
    });
    for (const item of pageExperience) {
      if (!registered.has(item.pageName)) {
        rows.push({
          pageName: `${item.pageName}（未登记）`,
          registered: false,
          opens: item.opens,
          avgReadyMs: item.avgReadyMs,
          readySamples: item.readySamples,
          avgStayMs: item.avgStayMs,
          runtimeErrors: item.runtimeErrors,
          heat: item.opens / maxOpens,
        });
      }
    }
    rows.sort((left, right) => right.opens - left.opens);
    return rows;
  }, [pageExperience]);
  const openReports = reports.filter((item) => item.status === 'pending' || item.status === 'reviewing').length;
  const resolvedReports = reports.filter((item) => item.status === 'resolved' || item.status === 'dismissed').length;
  const reportCloseRate =
    reports.length > 0 ? `${((resolvedReports / reports.length) * 100).toFixed(1)}%` : 'n/a';
  const activePremium = premiumEntries.filter((item) => item.status === 'active' && !item.takedownEjected).length;

  return (
    <PageScaffold
      title="Product Ops 业务总览"
      subtitle="聚焦举报治理、精选池运营与实时 L1-L4 的统一视图；全部指标来自真实投影，无静态样例。"
      meta={
        <>
          <span className="badge badge--neutral">Product Ops</span>
          <span className={`badge ${topAlert?.state === 'firing' ? 'badge--warning' : 'badge--success'}`}>
            {topAlert ? `告警=${topAlert.state}` : metricsPayload ? '暂无告警' : '等待告警数据'}
          </span>
          <span className="badge badge--warning">双签待处理 {summary?.pendingDualReview ?? 0} 个</span>
          <span className="badge badge--neutral">backlog={backlogCandidates.length}</span>
          <span className={`badge ${remoteReady ? 'badge--success' : 'badge--warning'}`}>
            {remoteReady ? '真实产品控制面已接入' : '等待产品控制面连接'}
          </span>
          <RuntimeErrorBadge error={runtimeError} />
        </>
      }
      actions={
        <>
          <Link className="button" to="/product/l1-l4/environment">查看实时 L1-L4</Link>
          <Link className="button button--primary" to={highlightBacklog?.drilldownRoute ?? '/product/governance'}>
            {highlightBacklog ? '处理首条 backlog' : '打开治理工作台'}
          </Link>
        </>
      }
      footer={
        <>
          <Link className="button" to="/product/governance">打开治理工作台</Link>
          <Link className="button button--primary" to="/product/recommendation">管理精选池</Link>
        </>
      }
    >
      <div className="metric-strip">
        <div className="metric-pill">
          <div className="metric-pill__label">举报结案率</div>
          <div className="metric-pill__value">{reportCloseRate}</div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">待处理举报</div>
          <div className="metric-pill__value">{openReports}</div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">精选池 active</div>
          <div className="metric-pill__value">{activePremium}</div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">实时指标来源</div>
          <div className="metric-pill__value">{metricsPayload?.source ?? 'n/a'}</div>
        </div>
        <div className="metric-pill">
          <div className="metric-pill__label">最新 triage 事件量</div>
          <div className="metric-pill__value">{triage?.eventSummary.totalCount ?? 0}</div>
        </div>
      </div>

      <SectionCard
        title="RTC 媒体 QoE（最近 24 小时）"
        subtitle="直接读取 rtc_media_qoe 权威原始事实；abandoned 不进入有效分母，空分母保持 n/a，不合成成功率。"
      >
        {rtcMediaQoeError ? <RuntimeErrorBadge error={rtcMediaQoeError} /> : null}
        <div className="badge-row">
          <span className="badge badge--neutral">
            source={rtcMediaQoe?.sourceKind ?? '等待回读'}
          </span>
          <span
            className={`badge ${
              rtcMediaQoe?.freshness === 'near_realtime'
                ? 'badge--success'
                : 'badge--warning'
            }`}
          >
            freshness={rtcMediaQoe?.freshness ?? 'unknown'}
          </span>
          <span className="badge badge--neutral">
            waterline={rtcMediaQoe?.generatedThrough ?? 'n/a'}
          </span>
          <span className="badge badge--neutral">
            lag={rtcMediaQoe?.lagSeconds == null ? 'n/a' : `${rtcMediaQoe.lagSeconds}s`}
          </span>
        </div>
        <div className="metric-strip">
          <div className="metric-pill">
            <div className="metric-pill__label">有效样本</div>
            <div className="metric-pill__value">
              {rtcMediaQoe?.hasSamples ? rtcMediaQoe.effectiveSampleCount : 'n/a'}
            </div>
          </div>
          <div className="metric-pill">
            <div className="metric-pill__label">媒体接通率</div>
            <div className="metric-pill__value">
              {formatRatio(rtcMediaQoe?.mediaConnectedRate)}
            </div>
          </div>
          <div className="metric-pill">
            <div className="metric-pill__label">建连 P95</div>
            <div className="metric-pill__value">
              {formatMilliseconds(rtcMediaQoe?.connectP95Ms)}
            </div>
          </div>
          <div className="metric-pill">
            <div className="metric-pill__label">异常断连率</div>
            <div className="metric-pill__value">
              {formatRatio(rtcMediaQoe?.connectionLostRate)}
            </div>
          </div>
          <div className="metric-pill">
            <div className="metric-pill__label">重连次数</div>
            <div className="metric-pill__value">
              {rtcMediaQoe?.hasSamples ? rtcMediaQoe.reconnectCount : 'n/a'}
            </div>
          </div>
        </div>
        <div className="stack-list">
          {(rtcMediaQoe?.series ?? []).slice(-6).map((point) => (
            <div className="policy-item" key={point.bucketStart}>
              <div>
                <p className="item-title">
                  {point.bucketStart}{point.partial ? '（当前部分桶）' : ''}
                </p>
                <p className="item-subtitle">
                  samples={point.effectiveSampleCount} · connected=
                  {formatRatio(point.mediaConnectedRate)} · p95=
                  {formatMilliseconds(point.connectP95Ms)} · lost=
                  {formatRatio(point.connectionLostRate)}
                </p>
              </div>
              <span className={`badge ${point.hasSamples ? 'badge--neutral' : 'badge--warning'}`}>
                {point.hasSamples ? `${point.reconnectCount} reconnects` : 'no samples'}
              </span>
            </div>
          ))}
          {!rtcMediaQoeError && rtcMediaQoe == null ? (
            <div className="policy-item">
              <div>
                <p className="item-title">正在读取 RTC QoE</p>
                <p className="item-subtitle">等待 product-ops 权威查询响应。</p>
              </div>
              <span className="badge badge--neutral">loading</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <div className="section-grid section-grid--two">
        <SectionCard title="治理队列快照" subtitle="来自 content-service 真实举报聚合，处置入口在治理工作台">
          <div className="stack-list">
            {reports.slice(0, 4).map((item) => (
              <div className="case-item" key={item.id}>
                <div>
                  <p className="item-title">
                    {item.targetType} / {item.targetId}
                  </p>
                  <p className="item-subtitle">reason={item.reason} · updatedAt={item.updatedAt}</p>
                </div>
                <span className={`badge badge--${item.status === 'pending' ? 'danger' : item.status === 'reviewing' ? 'warning' : 'success'}`}>
                  {item.status}
                </span>
              </div>
            ))}
            {reports.length === 0 ? (
              <div className="case-item">
                <div>
                  <p className="item-title">暂无举报</p>
                  <p className="item-subtitle">App 用户上报后会实时进入治理队列。</p>
                </div>
                <span className="badge badge--success">clear</span>
              </div>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="控制面工作流" subtitle="精选池入池 / 双签下架等危险动作的 workflow 留痕">
          <div className="stack-list">
            {queueItems.map((item) => (
              <div className="case-item" key={item.title}>
                <div>
                  <p className="item-title">{item.title}</p>
                  <p className="item-subtitle">{item.subtitle}</p>
                </div>
                <span className={`badge badge--${item.status}`}>{item.status}</span>
              </div>
            ))}
            {queueItems.length === 0 ? (
              <div className="case-item">
                <div>
                  <p className="item-title">暂无工作流</p>
                  <p className="item-subtitle">精选池与其他受控动作执行后会在此留痕。</p>
                </div>
                <span className="badge badge--neutral">idle</span>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <div className="section-grid section-grid--two">
        <SectionCard title="Triage / Backlog" subtitle="主路径直接展示产品控制面的可执行待办，而不是停留在静态总览">
          <div className="stack-list">
            {backlogCandidates.map((item: ControlPlaneBacklogCandidate) => (
              <div className="policy-item" key={item.id}>
                <div>
                  <p className="item-title">{item.title}</p>
                  <p className="item-subtitle">
                    severity={item.severity} · category={item.category}
                    {item.summary ? ` · ${item.summary}` : ''}
                  </p>
                  <p className="item-subtitle">{item.nextAction}</p>
                </div>
                <div className="badge-row">
                  <span className={`badge badge--${item.severity === 'critical' ? 'warning' : item.severity === 'warning' ? 'warning' : 'neutral'}`}>
                    {item.severity}
                  </span>
                  {item.drilldownRoute ? (
                    <Link className="button" to={item.drilldownRoute}>进入 drilldown</Link>
                  ) : null}
                  {item.repairEntry ? (
                    <Link className="button button--primary" to={item.repairEntry}>进入修复入口</Link>
                  ) : null}
                  {item.auditRoute ? (
                    <Link className="button" to={item.auditRoute}>查看审计链</Link>
                  ) : null}
                  {item.alertId ? <span className="badge badge--neutral">alert={item.alertId}</span> : null}
                </div>
              </div>
            ))}
            {backlogCandidates.length === 0 ? (
              <div className="policy-item">
                <div>
                  <p className="item-title">暂无 backlog</p>
                  <p className="item-subtitle">当前产品 triage 未生成新的修复待办。</p>
                </div>
                <span className="badge badge--success">quiet</span>
              </div>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="实时告警与覆盖" subtitle="与 L1-L4 页面共享同一实时语义，避免 dashboard 继续伪装静态趋势">
          <div className="stack-list">
            <div className="policy-item">
              <div>
                <p className="item-title">实时元数据</p>
                <p className="item-subtitle">
                  source={metricsPayload?.source ?? 'n/a'} · freshness={metricsPayload?.freshness ?? 'n/a'} · window={metricsPayload?.window ?? 'n/a'}
                </p>
                <p className="item-subtitle">
                  coverage={metricsPayload?.coverage.liveMetrics ?? 0}/{metricsPayload?.coverage.totalMetrics ?? 0} live
                </p>
              </div>
              <span className="badge badge--neutral">{metricsPayload?.coverage.eventSignals ?? 0} signals</span>
            </div>
            {alertStates.map((item) => (
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
                </div>
              </div>
            ))}
            {alertStates.length === 0 ? (
              <div className="policy-item">
                <div>
                  <p className="item-title">暂无实时告警</p>
                  <p className="item-subtitle">当前实时聚合没有生成新的告警态。</p>
                </div>
                <span className="badge badge--success">quiet</span>
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <SectionCard title="全局精选池" subtitle="入池 / 回滚 / 双签下架经事件广播给 feed 投影；操作入口在推荐运营页">
        <div className="stack-list">
          {premiumEntries.slice(0, 5).map((entry) => (
            <div className="policy-item" key={entry.id}>
              <div>
                <p className="item-title">{entry.contentId}</p>
                <p className="item-subtitle">
                  score={entry.qualityScore} · featuredAt={entry.featuredAt} · expiresAt={entry.expiresAt}
                </p>
              </div>
              <span className={`badge badge--${entry.status === 'active' ? 'success' : 'neutral'}`}>{entry.status}</span>
            </div>
          ))}
          {premiumEntries.length === 0 ? (
            <div className="policy-item">
              <div>
                <p className="item-title">精选池为空</p>
                <p className="item-subtitle">经推荐运营页入池后条目会在此展示。</p>
              </div>
              <span className="badge badge--neutral">0</span>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        title="页面矩阵热力图（最近 24h）"
        subtitle="行 = metadata 登记页面全集；列 = 真实遥测聚合（打开 / 逐页 TTI / 停留 / 运行错误）。登记但无数据的页面显示 0，不合成任何数值。"
      >
        {pageExperienceError ? <RuntimeErrorBadge error={pageExperienceError} /> : null}
        <table className="table">
          <thead>
            <tr>
              <th>页面（pageName）</th>
              <th>打开次数</th>
              <th>TTI 均值 ms</th>
              <th>停留均值 ms</th>
              <th>运行错误</th>
            </tr>
          </thead>
          <tbody>
            {pageHeatmapRows.slice(0, 40).map((row) => (
              <tr key={row.pageName}>
                <td>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 10,
                      height: 10,
                      borderRadius: 2,
                      marginRight: 8,
                      background: row.opens === 0
                        ? '#E5E7EB'
                        : `rgba(37, 99, 235, ${Math.max(0.15, row.heat)})`,
                    }}
                  />
                  {row.pageName}
                </td>
                <td>{row.opens}</td>
                <td>{row.readySamples > 0 ? row.avgReadyMs.toFixed(0) : '无采样'}</td>
                <td>{row.avgStayMs > 0 ? row.avgStayMs.toFixed(0) : '无采样'}</td>
                <td>{row.runtimeErrors}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="inline-note">
          共 {pageHeatmapRows.length} 个登记页面（展示打开次数前 40）；ANR / 卡顿明细在平台可观测页按
          signal=app.performance.anr / app.performance.frame 检索。
        </div>
      </SectionCard>

      <SectionCard title="主路径联动" subtitle="Dashboard 与 L1-L4 页面共享同一份实时指标和 triage 数据源">
        <div className="stack-list">
          <div className="policy-item">
            <div>
              <p className="item-title">当前主指标</p>
              <p className="item-subtitle">
                {topMetric ? `${topMetric.level} / ${topMetric.metric} / source=${topMetric.source ?? 'n/a'}` : '等待实时指标'}
              </p>
            </div>
            <Link className="button" to="/product/l1-l4/environment">打开 L1-L4 详情</Link>
          </div>
        </div>
      </SectionCard>
    </PageScaffold>
  );
}
