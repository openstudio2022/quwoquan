package application

import (
	"context"
	"fmt"
	"log"
	"sort"
	"strconv"
	"strings"
	"time"

	generated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
)

type L1L4MetricsScope struct {
	Environment string
	Cluster     string
	Service     string
	InstanceID  string
	Level       string
}

type metricSnapshot struct {
	ID          string  `json:"id"`
	Level       string  `json:"level"`
	Environment string  `json:"environment"`
	Cluster     string  `json:"cluster,omitempty"`
	Service     string  `json:"service,omitempty"`
	InstanceID  string  `json:"instanceId,omitempty"`
	Label       string  `json:"label"`
	Metric      string  `json:"metric"`
	Value       float64 `json:"value"`
	Unit        string  `json:"unit"`
	Status      string  `json:"status"`
	Trend       string  `json:"trend"`
	Source      string  `json:"source,omitempty"`
	Description string  `json:"description"`
}

type l1l4MetricAlertState struct {
	ID          string  `json:"id"`
	Level       string  `json:"level"`
	Metric      string  `json:"metric"`
	State       string  `json:"state"`
	Severity    string  `json:"severity"`
	Summary     string  `json:"summary"`
	Value       float64 `json:"value"`
	Threshold   float64 `json:"threshold"`
	Source      string  `json:"source"`
	Owner       string  `json:"owner,omitempty"`
	RepairEntry string  `json:"repairEntry,omitempty"`
	AlertID     string  `json:"alertId,omitempty"`
	AuditRoute  string  `json:"auditRoute,omitempty"`
}

type l1l4MetricsResponse struct {
	Scope     map[string]string      `json:"scope"`
	Source    string                 `json:"source"`
	Freshness string                 `json:"freshness"`
	Window    string                 `json:"window"`
	Coverage  map[string]any         `json:"coverage"`
	Alerts    []l1l4MetricAlertState `json:"alerts"`
	Items     []metricSnapshot       `json:"items"`
}

type l1l4DerivedMetricState struct {
	Metric     string
	Value      float64
	Unit       string
	Status     string
	Trend      string
	Source     string
	Alert      *l1l4MetricAlertState
	ObservedAt time.Time
}

type MetricQueryService struct {
	telemetry  *TelemetryService
	prometheus PrometheusQuery
}

func BuildL1L4Cards() ([]map[string]any, error) {
	priority := map[string]int{"L1": 1, "L2": 2, "L3": 3, "L4": 4}
	seen := map[string]bool{}
	type card struct {
		level, label, metric string
		priority             int
	}
	cards := make([]card, 0, 4)
	for _, definition := range canonicalL1L4MetricDefinitions(L1L4MetricsScope{Environment: "prod"}) {
		level := strings.TrimSpace(definition.Level)
		rank, supported := priority[level]
		if level == "" || seen[level] || !supported {
			continue
		}
		seen[level] = true
		cards = append(cards, card{
			level: level, label: strings.TrimSpace(definition.Label),
			metric: strings.TrimSpace(definition.Metric), priority: rank,
		})
	}
	sort.Slice(cards, func(i, j int) bool { return cards[i].priority < cards[j].priority })
	out := make([]map[string]any, 0, len(cards))
	for _, item := range cards {
		out = append(out, map[string]any{
			"level": item.level, "label": item.label, "metric": item.metric,
		})
	}
	return out, nil
}

func NewMetricQueryService(
	telemetry *TelemetryService,
	prometheus PrometheusQuery,
) *MetricQueryService {
	if telemetry == nil {
		panic("metric query service requires telemetry")
	}
	return &MetricQueryService{telemetry: telemetry, prometheus: prometheus}
}

func (s *MetricQueryService) ListL1L4MetricSnapshots(ctx context.Context, scope L1L4MetricsScope) (l1l4MetricsResponse, error) {
	levelFilter := strings.TrimSpace(scope.Level)
	if strings.EqualFold(levelFilter, "all") {
		levelFilter = ""
	}

	definitions := make([]metricSnapshot, 0, 5)
	for _, candidate := range canonicalL1L4MetricDefinitions(scope) {
		if levelFilter != "" && candidate.Level != levelFilter {
			continue
		}
		if scope.Cluster != "" && (candidate.Level == "L3" || candidate.Level == "L4") && candidate.Cluster != scope.Cluster {
			continue
		}
		if scope.Service != "" && (candidate.Level == "L3" || candidate.Level == "L4") && candidate.Service != scope.Service {
			continue
		}
		if scope.InstanceID != "" && (candidate.Level == "L3" || candidate.Level == "L4") && candidate.InstanceID != scope.InstanceID {
			continue
		}
		definitions = append(definitions, candidate)
	}

	telemetrySnapshot, err := s.telemetry.SnapshotEvents(ctx, EventSummaryQuery{}, 1000)
	if err != nil {
		return l1l4MetricsResponse{}, err
	}
	prometheusValues, err := s.queryL3L4Metrics(ctx, scope)
	if err != nil {
		return l1l4MetricsResponse{}, err
	}

	latestObservedAt := time.Time{}
	for _, item := range telemetrySnapshot.Drilldown.Items {
		if observedAt := parseFlexibleTelemetryTime(item.OccurredAt); !observedAt.IsZero() && observedAt.After(latestObservedAt) {
			latestObservedAt = observedAt
		}
	}

	out := make([]metricSnapshot, 0, len(definitions))
	alerts := make([]l1l4MetricAlertState, 0, len(definitions))
	for _, definition := range definitions {
		var derived l1l4DerivedMetricState
		var ok bool
		if golden, isGolden := goldenMetricByID(definition.Metric); isGolden {
			derived, ok, err = s.deriveGoldenMetricState(ctx, definition, golden)
			if err != nil {
				// 单个黄金指标派生失败（如个别字段 mapping 漂移）降级为该指标
				// unavailable，不拖垮整页快照；日志存储整体不可用仍由上方
				// SnapshotEvents 的错误路径返回 503。
				log.Printf(
					"product-ops l1l4 golden metric %s derivation degraded: %v",
					definition.Metric, err,
				)
				ok = false
			}
		} else {
			derived, ok = deriveL1L4MetricState(definition, prometheusValues)
		}
		if ok {
			definition.Value = derived.Value
			if derived.Unit != "" {
				definition.Unit = derived.Unit
			}
			if derived.Status != "" {
				definition.Status = derived.Status
			}
			if derived.Trend != "" {
				definition.Trend = derived.Trend
			}
			definition.Source = derived.Source
			out = append(out, definition)
			if !derived.ObservedAt.IsZero() && derived.ObservedAt.After(latestObservedAt) {
				latestObservedAt = derived.ObservedAt
			}
			if derived.Alert != nil {
				alerts = append(alerts, *derived.Alert)
			}
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Level == out[j].Level {
			return out[i].ID < out[j].ID
		}
		return out[i].Level < out[j].Level
	})

	sort.Slice(alerts, func(i, j int) bool {
		if alertSeverityRank(alerts[i].Severity) == alertSeverityRank(alerts[j].Severity) {
			return alerts[i].Metric < alerts[j].Metric
		}
		return alertSeverityRank(alerts[i].Severity) > alertSeverityRank(alerts[j].Severity)
	})

	source := "no-data"
	switch {
	case len(out) == 0:
		source = "no-data"
	case len(out) == len(definitions):
		source = "telemetry-and-prometheus"
	default:
		source = "partial-live"
	}

	freshness := ""
	if !latestObservedAt.IsZero() {
		freshness = latestObservedAt.UTC().Format(time.RFC3339)
	}
	if freshness == "" {
		freshness = "unavailable"
	}

	coverage := map[string]any{
		"totalMetrics":       len(definitions),
		"liveMetrics":        len(out),
		"unavailableMetrics": len(definitions) - len(out),
		"eventSignals":       telemetrySnapshot.Summary.TotalCount,
	}

	return l1l4MetricsResponse{
		Scope: map[string]string{
			"env":      scope.Environment,
			"cluster":  scope.Cluster,
			"service":  scope.Service,
			"instance": scope.InstanceID,
			"level":    scope.Level,
		},
		Source:    source,
		Freshness: freshness,
		Window:    "24h",
		Coverage:  coverage,
		Alerts:    alerts,
		Items:     out,
	}, nil
}

// canonicalL1L4MetricDefinitions 只描述可查询的权威指标，绝不承载样例数值或
// 持久化快照。L1/L2 成员由 golden_metric_catalog（generated）驱动；L3/L4 属于
// 契约 SLI 轨与基础设施轨，不进入黄金字典，仍在此声明。实际数值只能由
// telemetry 或 Prometheus 在请求时派生；没有样本时响应会保留 unavailable
// coverage 而不是返回零值/成功态。
func canonicalL1L4MetricDefinitions(scope L1L4MetricsScope) []metricSnapshot {
	environment := strings.TrimSpace(scope.Environment)
	if environment == "" {
		environment = "prod"
	}
	out := make([]metricSnapshot, 0, len(generated.GoldenMetricCatalog)+3)
	for _, metric := range generated.GoldenMetricCatalog {
		if metric.PortalLevel == "" {
			continue
		}
		out = append(out, metricSnapshot{
			ID:          metric.PortalLevel + ":" + environment + ":" + metric.MetricID,
			Level:       metric.PortalLevel,
			Environment: environment,
			Label:       metric.PortalLabel,
			Metric:      metric.MetricID,
			Unit:        goldenMetricUnit(metric),
			Trend:       "live",
			Description: goldenMetricDescription(metric),
		})
	}
	out = append(out,
		metricSnapshot{
			ID:          "L3:" + environment + ":" + scope.Service,
			Level:       "L3",
			Environment: environment,
			Service:     strings.TrimSpace(scope.Service),
			Label:       "HTTP 请求 P95",
			Metric:      "http_request_p95_ms",
			Unit:        "ms",
			Trend:       "live",
			Description: "HTTP server duration histogram 的 P95。",
		},
		metricSnapshot{
			ID:          "L3-error:" + environment + ":" + scope.Service,
			Level:       "L3",
			Environment: environment,
			Service:     strings.TrimSpace(scope.Service),
			Label:       "HTTP 5xx 错误率",
			Metric:      "http_error_rate",
			Unit:        "%",
			Trend:       "live",
			Description: "HTTP server request counter 的 5xx 比率。",
		},
		metricSnapshot{
			ID:          "L4:" + environment,
			Level:       "L4",
			Environment: environment,
			Label:       "服务平面可用性",
			Metric:      "service_plane_up",
			Unit:        "%",
			Trend:       "live",
			Description: "Prometheus up 指标的服务平面可用性。",
		},
	)
	return out
}

func goldenMetricByID(metricID string) (generated.GoldenMetricDefinition, bool) {
	for _, metric := range generated.GoldenMetricCatalog {
		if metric.MetricID == metricID {
			return metric, true
		}
	}
	return generated.GoldenMetricDefinition{}, false
}

func goldenMetricUnit(metric generated.GoldenMetricDefinition) string {
	switch metric.Source.Aggregation {
	case "percentile_p50", "percentile_p95", "percentile_p99":
		return "ms"
	default:
		return "%"
	}
}

func goldenMetricDescription(metric generated.GoldenMetricDefinition) string {
	switch metric.Source.Aggregation {
	case "event_ratio":
		return fmt.Sprintf(
			"%s / %s 事件计数比值（ES 权威回读）。",
			metric.Source.NumeratorEventType, metric.Source.DenominatorEventType,
		)
	case "unique_session_ratio":
		return fmt.Sprintf(
			"%s / %s 去重会话比值（ES 权威回读）。",
			metric.Source.NumeratorEventType, metric.Source.DenominatorEventType,
		)
	case "series_rate_ratio":
		return fmt.Sprintf(
			"%s / %s Prometheus rate 比值。",
			metric.Source.NumeratorSeries, metric.Source.DenominatorSeries,
		)
	case "percentile_p50", "percentile_p95", "percentile_p99":
		return fmt.Sprintf(
			"%s.%s 原始样本分位数（ES 权威回读）。",
			metric.Source.EventType, metric.Source.ValueField,
		)
	default:
		return "黄金指标（golden_metric_catalog）。"
	}
}

func (s *MetricQueryService) queryL3L4Metrics(
	ctx context.Context,
	scope L1L4MetricsScope,
) (map[string]float64, error) {
	values := map[string]float64{}
	if s.prometheus == nil {
		return values, nil
	}
	serviceMatcher := prometheusLabelSelector(scope.Service, "")
	errorMatcher := prometheusLabelSelector(scope.Service, `status=~"5.."`)
	queries := map[string]string{
		"http_request_p95_ms": `histogram_quantile(0.95, sum(rate(http_server_duration_seconds_bucket` +
			serviceMatcher + `[5m])) by (le)) * 1000`,
		"http_error_rate": `100 * sum(rate(http_server_requests_total` + errorMatcher +
			`[5m])) / (sum(rate(http_server_requests_total` + serviceMatcher + `[5m])) + 0.001)`,
		"service_plane_up": `100 * min(up{job=~"quwoquan-service-plane|recommendation-service"})`,
	}
	for metric, query := range queries {
		value, err := s.prometheus.Query(ctx, query)
		if err != nil {
			return nil, fmt.Errorf("query prometheus metric %s: %w", metric, err)
		}
		values[metric] = value
	}
	return values, nil
}

func prometheusLabelSelector(service, extra string) string {
	labels := make([]string, 0, 2)
	if service = strings.TrimSpace(service); service != "" {
		labels = append(labels, "service="+strconv.Quote(service))
	}
	if extra = strings.TrimSpace(extra); extra != "" {
		labels = append(labels, extra)
	}
	return "{" + strings.Join(labels, ",") + "}"
}

// deriveGoldenMetricState 按注册表 source 形态派生黄金指标实时状态。
// 可实时计算的形态：
//   - product_telemetry + event_ratio/unique_session_ratio，且过滤器只含
//     EventSummaryQuery 支持的 result 维度；
//   - product_telemetry + percentile_p95/sum_ratio（raw 原始样本统计门面）；
//   - behavior_attribution + series_rate_ratio（需 Prometheus）。
//
// 其余形态（扩展字段过滤）在实时卡片上显式 unavailable，绝不合成数值。
func (s *MetricQueryService) deriveGoldenMetricState(
	ctx context.Context,
	snapshot metricSnapshot,
	golden generated.GoldenMetricDefinition,
) (l1l4DerivedMetricState, bool, error) {
	switch {
	case golden.Source.Track == "product_telemetry" &&
		(golden.Source.Aggregation == "event_ratio" ||
			golden.Source.Aggregation == "unique_session_ratio"):
		return s.deriveEventRatioMetricState(ctx, snapshot, golden)
	case golden.Source.Track == "product_telemetry" &&
		(golden.Source.Aggregation == "percentile_p95" ||
			golden.Source.Aggregation == "sum_ratio"):
		return s.deriveValueStatsMetricState(ctx, snapshot, golden)
	case golden.Source.Track == "behavior_attribution" &&
		golden.Source.Aggregation == "series_rate_ratio":
		return s.deriveSeriesRatioMetricState(ctx, snapshot, golden)
	default:
		return l1l4DerivedMetricState{}, false, nil
	}
}

// deriveValueStatsMetricState 承载 percentile_p95 / sum_ratio 形态：
// 从 raw 原始样本统计门面读取 P95 或分子分母求和；无样本或零分母
// 显式 unavailable。
func (s *MetricQueryService) deriveValueStatsMetricState(
	ctx context.Context,
	snapshot metricSnapshot,
	golden generated.GoldenMetricDefinition,
) (l1l4DerivedMetricState, bool, error) {
	resultFilter, supported := goldenSingleResultFilter(golden.Source.NumeratorFilters)
	if !supported {
		// 扩展字段过滤超出统计门面能力，显式不可算而不是丢过滤伪造口径。
		return l1l4DerivedMetricState{}, false, nil
	}
	query := EventValueStatsQuery{Result: resultFilter}
	if golden.Source.Aggregation == "percentile_p95" {
		query.EventType = golden.Source.EventType
		query.ValueField = golden.Source.ValueField
	} else {
		if golden.Source.NumeratorEventType != golden.Source.DenominatorEventType {
			// sum_ratio 的原始样本口径要求同一事件承载分子分母字段。
			return l1l4DerivedMetricState{}, false, nil
		}
		query.EventType = golden.Source.NumeratorEventType
		query.NumeratorField = golden.Source.NumeratorValueField
		query.DenominatorField = golden.Source.DenominatorValueField
	}
	stats, err := s.telemetry.GetEventValueStats(ctx, query)
	if err != nil {
		return l1l4DerivedMetricState{}, false, fmt.Errorf(
			"query golden metric %s value stats: %w", golden.MetricID, err,
		)
	}
	if stats.SampleCount == 0 {
		return l1l4DerivedMetricState{}, false, nil
	}
	var value float64
	if golden.Source.Aggregation == "percentile_p95" {
		value = stats.P95
	} else {
		if stats.DenominatorSum == 0 {
			return l1l4DerivedMetricState{}, false, nil
		}
		value = stats.NumeratorSum / stats.DenominatorSum * 100
	}
	return goldenMetricState(snapshot, golden, value, "telemetry", time.Now().UTC()), true, nil
}

func goldenSingleResultFilter(filters map[string]string) (string, bool) {
	if len(filters) == 0 {
		return "", true
	}
	if result, only := filters["result"]; only && len(filters) == 1 {
		return result, true
	}
	return "", false
}

func summaryQueryFromGoldenFilters(
	eventType string,
	filters map[string]string,
) (EventSummaryQuery, bool) {
	query := EventSummaryQuery{EventType: eventType}
	for field, value := range filters {
		if field == "result" {
			query.Result = value
			continue
		}
		// 扩展字段过滤（如 publicationStage）超出 summary 查询门面能力，
		// 实时卡片显式 unavailable 而不是丢掉过滤条件伪造口径。
		return EventSummaryQuery{}, false
	}
	return query, true
}

func (s *MetricQueryService) deriveEventRatioMetricState(
	ctx context.Context,
	snapshot metricSnapshot,
	golden generated.GoldenMetricDefinition,
) (l1l4DerivedMetricState, bool, error) {
	numeratorQuery, ok := summaryQueryFromGoldenFilters(
		golden.Source.NumeratorEventType, golden.Source.NumeratorFilters,
	)
	if !ok {
		return l1l4DerivedMetricState{}, false, nil
	}
	denominatorQuery, ok := summaryQueryFromGoldenFilters(
		golden.Source.DenominatorEventType, golden.Source.DenominatorFilters,
	)
	if !ok {
		return l1l4DerivedMetricState{}, false, nil
	}
	numerator, err := s.telemetry.GetEventSummary(ctx, numeratorQuery)
	if err != nil {
		return l1l4DerivedMetricState{}, false, fmt.Errorf(
			"query golden metric %s numerator: %w", golden.MetricID, err,
		)
	}
	denominator, err := s.telemetry.GetEventSummary(ctx, denominatorQuery)
	if err != nil {
		return l1l4DerivedMetricState{}, false, fmt.Errorf(
			"query golden metric %s denominator: %w", golden.MetricID, err,
		)
	}
	var numeratorCount, denominatorCount int64
	if golden.Source.Aggregation == "unique_session_ratio" {
		numeratorCount, denominatorCount = numerator.SessionCount, denominator.SessionCount
	} else {
		numeratorCount, denominatorCount = numerator.TotalCount, denominator.TotalCount
	}
	if denominatorCount == 0 {
		return l1l4DerivedMetricState{}, false, nil
	}
	value := float64(numeratorCount) / float64(denominatorCount) * 100
	observedAt := parseFlexibleTelemetryTime(numerator.GeneratedThrough)
	if denominatorObserved := parseFlexibleTelemetryTime(denominator.GeneratedThrough); denominatorObserved.After(observedAt) {
		observedAt = denominatorObserved
	}
	return goldenMetricState(snapshot, golden, value, "telemetry", observedAt), true, nil
}

func (s *MetricQueryService) deriveSeriesRatioMetricState(
	ctx context.Context,
	snapshot metricSnapshot,
	golden generated.GoldenMetricDefinition,
) (l1l4DerivedMetricState, bool, error) {
	if s.prometheus == nil {
		return l1l4DerivedMetricState{}, false, nil
	}
	value, err := s.prometheus.Query(ctx, seriesRateRatioQuery(golden.Source))
	if err != nil {
		return l1l4DerivedMetricState{}, false, fmt.Errorf(
			"query prometheus golden metric %s: %w", golden.MetricID, err,
		)
	}
	return goldenMetricState(snapshot, golden, value, "prometheus", time.Now().UTC()), true, nil
}

func seriesRateRatioQuery(source generated.GoldenMetricSource) string {
	selector := ""
	if len(source.NumeratorSeriesLabels) > 0 {
		names := make([]string, 0, len(source.NumeratorSeriesLabels))
		for name := range source.NumeratorSeriesLabels {
			names = append(names, name)
		}
		sort.Strings(names)
		pairs := make([]string, 0, len(names))
		for _, name := range names {
			pairs = append(pairs, name+"="+strconv.Quote(source.NumeratorSeriesLabels[name]))
		}
		selector = "{" + strings.Join(pairs, ",") + "}"
	}
	return "100 * sum(rate(" + source.NumeratorSeries + selector +
		"[5m])) / (sum(rate(" + source.DenominatorSeries + "[5m])) + 0.001)"
}

// goldenMetricState 用注册表 target/alerting 阈值派生卡片状态：越过告警绑定
// 阈值为 firing，仅违反体验目标为 warning。阈值真相源只有注册表一处。
func goldenMetricState(
	snapshot metricSnapshot,
	golden generated.GoldenMetricDefinition,
	value float64,
	source string,
	observedAt time.Time,
) l1l4DerivedMetricState {
	scale := 100.0
	switch golden.Source.Aggregation {
	case "percentile_p50", "percentile_p95", "percentile_p99":
		scale = 1.0
	}
	targetValue := golden.TargetValue * scale
	state, severity := "quiet", "info"
	if golden.Alerting != nil && targetViolated(value, golden.TargetOperator, golden.Alerting.Threshold*scale) {
		state, severity = "firing", "critical"
	} else if targetViolated(value, golden.TargetOperator, targetValue) {
		state, severity = "warning", "warning"
	}
	alertID := golden.MetricID + "TargetState"
	if golden.Alerting != nil {
		alertID = golden.Alerting.AlertName
	}
	return l1l4DerivedMetricState{
		Metric: snapshot.Metric,
		Value:  value,
		Unit:   goldenMetricUnit(golden),
		Status: mapMetricStatus(state),
		Trend:  "live",
		Source: source,
		Alert: &l1l4MetricAlertState{
			ID:          golden.MetricID + "TargetState",
			Level:       snapshot.Level,
			Metric:      snapshot.Metric,
			State:       state,
			Severity:    severity,
			Summary:     snapshot.Label + " 由 golden_metric_catalog 唯一口径实时计算",
			Value:       value,
			Threshold:   targetValue,
			Source:      source,
			Owner:       golden.Owner,
			RepairEntry: "/product/l1-l4/environment",
			AlertID:     alertID,
			AuditRoute:  "/audit",
		},
		ObservedAt: observedAt,
	}
}

// targetViolated 判断取值是否落在 target 健康侧之外。
func targetViolated(value float64, operator string, bound float64) bool {
	switch operator {
	case "less_than":
		return value >= bound
	case "less_than_or_equal":
		return value > bound
	case "greater_than":
		return value <= bound
	case "greater_than_or_equal":
		return value < bound
	default:
		return false
	}
}

func deriveL1L4MetricState(
	snapshot metricSnapshot,
	prometheusValues map[string]float64,
) (l1l4DerivedMetricState, bool) {
	switch snapshot.Metric {
	case "http_request_p95_ms":
		value, ok := prometheusValues["http_request_p95_ms"]
		if !ok {
			return l1l4DerivedMetricState{}, false
		}
		// 告警结构沿用统一派生模型，但数值来自 Prometheus，而非产品事件。
		state := "quiet"
		severity := "info"
		if value > 1200 {
			state = "firing"
			severity = "critical"
		} else if value > 800 {
			state = "warning"
			severity = "warning"
		}
		return l1l4DerivedMetricState{
			Metric: snapshot.Metric,
			Value:  value,
			Unit:   "ms",
			Status: mapMetricStatus(state),
			Trend:  "live",
			Source: "prometheus",
			Alert: &l1l4MetricAlertState{
				ID:        "L3HttpRequestP95High",
				Level:     snapshot.Level,
				Metric:    snapshot.Metric,
				State:     state,
				Severity:  severity,
				Summary:   "L3 请求 P95 由 http_server_duration_seconds Prometheus histogram 计算",
				Value:     value,
				Threshold: 800,
				Source:    "prometheus",
				Owner:     "app-observability",

				RepairEntry: "/product/l1-l4/environment",
				AlertID:     "HighP95Latency",
				AuditRoute:  "/audit",
			},
			ObservedAt: time.Now().UTC(),
		}, true
	case "http_error_rate":
		value, ok := prometheusValues["http_error_rate"]
		if !ok {
			return l1l4DerivedMetricState{}, false
		}
		// 错误率由 HTTP RED 计数器计算，不能从 App 错误事件总量推导。
		state := "quiet"
		severity := "info"
		if value > 1 {
			state = "warning"
			severity = "warning"
		}
		return l1l4DerivedMetricState{
			Metric: snapshot.Metric,
			Value:  value,
			Unit:   "%",
			Status: mapMetricStatus(state),
			Trend:  "live",
			Source: "prometheus",
			Alert: &l1l4MetricAlertState{
				ID:        "L3HttpErrorRateHigh",
				Level:     snapshot.Level,
				Metric:    snapshot.Metric,
				State:     state,
				Severity:  severity,
				Summary:   "L3 HTTP 5xx 错误率由 http_server_requests_total Prometheus 计数器计算",
				Value:     value,
				Threshold: 1,
				Source:    "prometheus",
				Owner:     "app-observability",

				RepairEntry: "/product/dashboard",
				AlertID:     "HighErrorRate",
				AuditRoute:  "/audit",
			},
			ObservedAt: time.Now().UTC(),
		}, true
	case "service_plane_up":
		value, ok := prometheusValues["service_plane_up"]
		if !ok {
			return l1l4DerivedMetricState{}, false
		}
		return prometheusMetricState(snapshot, value, "%", 100, "L4 服务平面可用性由 Prometheus up 指标计算"), true
	default:
		return l1l4DerivedMetricState{}, false
	}
}

func prometheusMetricState(
	snapshot metricSnapshot,
	value float64,
	unit string,
	threshold float64,
	summary string,
) l1l4DerivedMetricState {
	state := "quiet"
	severity := "info"
	switch snapshot.Metric {
	case "http_request_p95_ms":
		if value > 1200 {
			state = "firing"
			severity = "critical"
		} else if value > threshold {
			state = "warning"
			severity = "warning"
		}
	case "http_error_rate":
		if value > 5 {
			state = "firing"
			severity = "critical"
		} else if value > threshold {
			state = "warning"
			severity = "warning"
		}
	case "service_plane_up":
		if value < 90 {
			state = "firing"
			severity = "critical"
		} else if value < threshold {
			state = "warning"
			severity = "warning"
		}
	}
	return l1l4DerivedMetricState{
		Metric: snapshot.Metric,
		Value:  value,
		Unit:   unit,
		Status: mapMetricStatus(state),
		Trend:  "live",
		Source: "prometheus",
		Alert: &l1l4MetricAlertState{
			ID:        snapshot.Metric + "PrometheusAlert",
			Level:     snapshot.Level,
			Metric:    snapshot.Metric,
			State:     state,
			Severity:  severity,
			Summary:   summary,
			Value:     value,
			Threshold: threshold,
			Source:    "prometheus",
			Owner:     "platform-observability",

			RepairEntry: "/product/l1-l4/environment",
			AlertID:     snapshot.Metric + "PrometheusAlert",
			AuditRoute:  "/audit",
		},
		ObservedAt: time.Now().UTC(),
	}
}

func parseFlexibleTelemetryTime(raw string) time.Time {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return time.Time{}
	}
	if parsed, err := time.Parse(time.RFC3339Nano, trimmed); err == nil {
		return parsed
	}
	if parsed, err := time.Parse(time.RFC3339, trimmed); err == nil {
		return parsed
	}
	return time.Time{}
}

func alertSeverityRank(severity string) int {
	switch strings.ToLower(strings.TrimSpace(severity)) {
	case "critical":
		return 3
	case "warning":
		return 2
	case "info":
		return 1
	default:
		return 0
	}
}

func mapMetricStatus(state string) string {
	switch state {
	case "firing":
		return "warning"
	case "warning":
		return "warning"
	case "quiet":
		return "success"
	default:
		return "neutral"
	}
}
