package main

import (
	"context"
	"sort"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
)

type l1l4MetricsScope struct {
	Environment string
	Cluster     string
	Service     string
	InstanceID  string
	Level       string
}

type l1l4MetricAlertState struct {
	ID           string  `json:"id"`
	Level        string  `json:"level"`
	Metric       string  `json:"metric"`
	State        string  `json:"state"`
	Severity     string  `json:"severity"`
	Summary      string  `json:"summary"`
	Value        float64 `json:"value"`
	Threshold    float64 `json:"threshold"`
	Source       string  `json:"source"`
	Owner        string  `json:"owner,omitempty"`
	RunbookID    string  `json:"runbookId,omitempty"`
	RunbookRoute string  `json:"runbookRoute,omitempty"`
	RepairEntry  string  `json:"repairEntry,omitempty"`
	AlertID      string  `json:"alertId,omitempty"`
	AuditRoute   string  `json:"auditRoute,omitempty"`
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
	items, err := s.store.ListDocuments("l1l4_metric_snapshots")
	if err != nil {
		return l1l4MetricsResponse{}, err
	}
	levelFilter := strings.TrimSpace(scope.Level)
	if strings.EqualFold(levelFilter, "all") {
		levelFilter = ""
	}

	out := make([]metricSnapshot, 0, len(items))
	for _, item := range items {
		snapshot, err := decodeDocument[metricSnapshot](item)
		if err != nil {
			return l1l4MetricsResponse{}, err
		}
		if scope.Environment != "" && snapshot.Environment != scope.Environment {
			continue
		}
		if levelFilter != "" && snapshot.Level != levelFilter {
			continue
		}
		isInfraLevel := snapshot.Level == "L3" || snapshot.Level == "L4"
		if scope.Cluster != "" && isInfraLevel && snapshot.Cluster != scope.Cluster {
			continue
		}
		if scope.Service != "" && isInfraLevel && snapshot.Service != scope.Service {
			continue
		}
		if scope.InstanceID != "" && isInfraLevel && snapshot.InstanceID != scope.InstanceID {
			continue
		}
		out = append(out, snapshot)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Level == out[j].Level {
			return out[i].ID < out[j].ID
		}
		return out[i].Level < out[j].Level
	})

	telemetrySnapshot, err := s.telemetry.SnapshotEvents(ctx, application.EventSummaryQuery{}, 1000)
	if err != nil {
		return l1l4MetricsResponse{}, err
	}

	latestObservedAt := time.Time{}
	for _, item := range telemetrySnapshot.Drilldown.Items {
		if observedAt := parseFlexibleTelemetryTime(item.OccurredAt); !observedAt.IsZero() && observedAt.After(latestObservedAt) {
			latestObservedAt = observedAt
		}
	}

	derivedCount := 0
	alerts := make([]l1l4MetricAlertState, 0, len(out))
	for i := range out {
		if derived, ok := deriveL1L4MetricState(out[i], telemetrySnapshot); ok {
			out[i].Value = derived.Value
			if derived.Unit != "" {
				out[i].Unit = derived.Unit
			}
			if derived.Status != "" {
				out[i].Status = derived.Status
			}
			if derived.Trend != "" {
				out[i].Trend = derived.Trend
			}
			out[i].Source = derived.Source
			derivedCount++
			if !derived.ObservedAt.IsZero() && derived.ObservedAt.After(latestObservedAt) {
				latestObservedAt = derived.ObservedAt
			}
			if derived.Alert != nil {
				alerts = append(alerts, *derived.Alert)
			}
		} else {
			out[i].Source = "snapshot"
		}
	}

	sort.Slice(alerts, func(i, j int) bool {
		if alertSeverityRank(alerts[i].Severity) == alertSeverityRank(alerts[j].Severity) {
			return alerts[i].Metric < alerts[j].Metric
		}
		return alertSeverityRank(alerts[i].Severity) > alertSeverityRank(alerts[j].Severity)
	})

	source := "snapshot"
	switch {
	case derivedCount == 0:
		source = "snapshot"
	case derivedCount == len(out):
		source = "live-telemetry"
	default:
		source = "hybrid"
	}

	freshness := ""
	if !latestObservedAt.IsZero() {
		freshness = latestObservedAt.UTC().Format(time.RFC3339)
	}
	if freshness == "" {
		freshness = nowRFC3339()
	}

	coverage := map[string]any{
		"totalMetrics":    len(out),
		"liveMetrics":     derivedCount,
		"fallbackMetrics": len(out) - derivedCount,
		"eventSignals":    telemetrySnapshot.Summary.TotalCount,
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

func deriveL1L4MetricState(snapshot metricSnapshot, telemetrySnapshot application.EventTelemetrySnapshot) (l1l4DerivedMetricState, bool) {
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
				ID:           "L1JourneyCompletionRateLow",
				Level:        snapshot.Level,
				Metric:       snapshot.Metric,
				State:        state,
				Severity:     severity,
				Summary:      "L1 旅程完成率正在由 page_open/page_return 事件实时计算",
				Value:        value,
				Threshold:    90,
				Source:       "telemetry",
				Owner:        "product-ops",
				RunbookID:    "cfg-rollback-drill",
				RunbookRoute: "/platform/runbook",
				RepairEntry:  "/product/dashboard",
				AlertID:      "L1JourneyCompletionRateLow",
				AuditRoute:   "/audit",
			},
			ObservedAt: latestEventTime(telemetrySnapshot.Drilldown.Items),
		}, true
	case "core_business_ctr":
		// 推荐曝光/点击只允许来自 content-service 的 BehaviorSignal 与
		// recommendation Prometheus 指标，不能再伪装成 Ops event。
		return l1l4DerivedMetricState{}, false
	case "http_request_p95_ms":
		samples := collectLatencySamples(telemetrySnapshot.Drilldown.Items)
		if len(samples) == 0 {
			return l1l4DerivedMetricState{}, false
		}
		value := percentile(samples, 0.95)
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
			Source: "telemetry",
			Alert: &l1l4MetricAlertState{
				ID:           "L3HttpRequestP95High",
				Level:        snapshot.Level,
				Metric:       snapshot.Metric,
				State:        state,
				Severity:     severity,
				Summary:      "L3 请求 P95 由 page_return_perf / durationMs 实时计算",
				Value:        value,
				Threshold:    800,
				Source:       "telemetry",
				Owner:        "app-observability",
				RunbookID:    "cfg-rollback-drill",
				RunbookRoute: "/platform/runbook",
				RepairEntry:  "/product/l1-l4/environment",
				AlertID:      "HighP95Latency",
				AuditRoute:   "/audit",
			},
			ObservedAt: latestEventTime(telemetrySnapshot.Drilldown.Items),
		}, true
	case "http_error_rate":
		total := telemetrySnapshot.Summary.TotalCount
		if total == 0 {
			return l1l4DerivedMetricState{}, false
		}
		errorCount := countDimensionValues(telemetrySnapshot.Summary, "errorCode")
		value := float64(errorCount) / float64(total) * 100
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
			Source: "telemetry",
			Alert: &l1l4MetricAlertState{
				ID:           "L3HttpErrorRateHigh",
				Level:        snapshot.Level,
				Metric:       snapshot.Metric,
				State:        state,
				Severity:     severity,
				Summary:      "L3 错误率由 errorCode 维度实时计算",
				Value:        value,
				Threshold:    1,
				Source:       "telemetry",
				Owner:        "app-observability",
				RunbookID:    "cfg-rollback-drill",
				RunbookRoute: "/platform/runbook",
				RepairEntry:  "/product/dashboard",
				AlertID:      "HighErrorRate",
				AuditRoute:   "/audit",
			},
			ObservedAt: latestEventTime(telemetrySnapshot.Drilldown.Items),
		}, true
	default:
		return l1l4DerivedMetricState{}, false
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
