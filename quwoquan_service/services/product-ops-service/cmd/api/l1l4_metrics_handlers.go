package main

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

type l1l4MetricsScope struct {
	Environment string
	Cluster     string
	Service     string
	InstanceID  string
	Level       string
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

func (s *productService) buildL1L4MetricsResponse(ctx context.Context, scope l1l4MetricsScope) (l1l4MetricsResponse, error) {
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

	telemetrySnapshot, err := s.telemetry.SnapshotEvents(ctx, application.EventSummaryQuery{}, 1000)
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
		if derived, ok := deriveL1L4MetricState(definition, telemetrySnapshot, prometheusValues); ok {
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
// 持久化快照。实际数值只能由 telemetry 或 Prometheus 在请求时派生；没有样本时
// 响应会保留 unavailable coverage 而不是返回零值/成功态。
func canonicalL1L4MetricDefinitions(scope l1l4MetricsScope) []metricSnapshot {
	environment := strings.TrimSpace(scope.Environment)
	if environment == "" {
		environment = "prod"
	}
	return []metricSnapshot{
		{
			ID:          "L1:" + environment,
			Level:       "L1",
			Environment: environment,
			Label:       "主旅程完成率",
			Metric:      "five_tab_journey_completion_rate",
			Unit:        "%",
			Trend:       "live",
			Description: "page_open 到 page_return 的产品旅程完成率。",
		},
		{
			ID:          "L2:" + environment,
			Level:       "L2",
			Environment: environment,
			Label:       "推荐 CTR",
			Metric:      "core_business_ctr",
			Unit:        "%",
			Trend:       "live",
			Description: "recommendation impression/click 的实时转化率。",
		},
		{
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
		{
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
		{
			ID:          "L4:" + environment,
			Level:       "L4",
			Environment: environment,
			Label:       "服务平面可用性",
			Metric:      "service_plane_up",
			Unit:        "%",
			Trend:       "live",
			Description: "Prometheus up 指标的服务平面可用性。",
		},
	}
}

func (s *productService) queryL3L4Metrics(
	ctx context.Context,
	scope l1l4MetricsScope,
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
		"core_business_ctr": `100 * sum(rate(recommendation_feed_click_total[5m])) / (sum(rate(recommendation_feed_impressed_total[5m])) + 0.001)`,
		"service_plane_up":  `100 * min(up{job=~"quwoquan-service-plane|recommendation-service"})`,
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

func deriveL1L4MetricState(
	snapshot metricSnapshot,
	telemetrySnapshot application.EventTelemetrySnapshot,
	prometheusValues map[string]float64,
) (l1l4DerivedMetricState, bool) {
	switch snapshot.Metric {
	case "five_tab_journey_completion_rate":
		openCount := countEventTypes(telemetrySnapshot.Summary, "page_open")
		returnCount := countEventTypes(telemetrySnapshot.Summary, "page_return")
		if openCount == 0 {
			return l1l4DerivedMetricState{}, false
		}
		value := float64(returnCount) / float64(openCount) * 100
		state := "quiet"
		severity := "info"
		if value < 80 {
			state = "firing"
			severity = "critical"
		} else if value < 90 {
			state = "warning"
			severity = "warning"
		}
		return l1l4DerivedMetricState{
			Metric: snapshot.Metric,
			Value:  value,
			Unit:   "%",
			Status: mapMetricStatus(state),
			Trend:  "live",
			Source: "telemetry",
			Alert: &l1l4MetricAlertState{
				ID:        "L1JourneyCompletionRateLow",
				Level:     snapshot.Level,
				Metric:    snapshot.Metric,
				State:     state,
				Severity:  severity,
				Summary:   "L1 旅程完成率正在由 page_open/page_return 事件实时计算",
				Value:     value,
				Threshold: 90,
				Source:    "telemetry",
				Owner:     "product-ops",

				RepairEntry: "/product/dashboard",
				AlertID:     "L1JourneyCompletionRateLow",
				AuditRoute:  "/audit",
			},
			ObservedAt: latestEventTime(telemetrySnapshot.Drilldown.Items),
		}, true
	case "core_business_ctr":
		// 推荐曝光/点击只允许来自 content-service 的 BehaviorSignal 与
		// recommendation Prometheus 指标，不能再伪装成 Ops event。
		value, ok := prometheusValues["core_business_ctr"]
		if !ok {
			return l1l4DerivedMetricState{}, false
		}
		return prometheusMetricState(snapshot, value, "%", 3, "L2 推荐曝光/点击 CTR 由 recommendation Prometheus 计数器计算"), true
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
	case "core_business_ctr":
		if value < 1 {
			state = "firing"
			severity = "critical"
		} else if value < threshold {
			state = "warning"
			severity = "warning"
		}
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

func countEventTypes(summary application.EventSummary, eventType string) int {
	return countDimensionValue(summary, "eventType", eventType)
}

func countDimensionValue(summary application.EventSummary, dimension, value string) int {
	if summary.DimensionCounters == nil {
		return 0
	}
	if counters, ok := summary.DimensionCounters[dimension]; ok {
		return counters[value]
	}
	return 0
}

func countDimensionValues(summary application.EventSummary, dimension string) int {
	if summary.DimensionCounters == nil {
		return 0
	}
	counters, ok := summary.DimensionCounters[dimension]
	if !ok {
		return 0
	}
	total := 0
	for key, count := range counters {
		if strings.TrimSpace(key) == "" {
			continue
		}
		total += count
	}
	return total
}

func collectLatencySamples(items []application.EventDrilldownItem) []float64 {
	samples := make([]float64, 0, len(items))
	for _, item := range items {
		if item.DurationMS != nil {
			samples = append(samples, float64(*item.DurationMS))
		}
	}
	return samples
}

func latestEventTime(items []application.EventDrilldownItem) time.Time {
	var latest time.Time
	for _, item := range items {
		if observedAt := parseFlexibleTelemetryTime(item.OccurredAt); !observedAt.IsZero() && observedAt.After(latest) {
			latest = observedAt
		}
	}
	return latest
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

func percentile(samples []float64, quantile float64) float64 {
	if len(samples) == 0 {
		return 0
	}
	sorted := append([]float64(nil), samples...)
	sort.Float64s(sorted)
	if quantile <= 0 {
		return sorted[0]
	}
	if quantile >= 1 {
		return sorted[len(sorted)-1]
	}
	index := int(float64(len(sorted)-1) * quantile)
	if index < 0 {
		index = 0
	}
	if index >= len(sorted) {
		index = len(sorted) - 1
	}
	return sorted[index]
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
