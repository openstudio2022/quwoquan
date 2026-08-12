package observability

import (
	"net"
	"regexp"
	"strings"
	"sync"

	"github.com/prometheus/client_golang/prometheus"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
)

const maxDetailedDecisionSeries = 2048

var (
	semanticMetricValuePattern = regexp.MustCompile(`^[a-z0-9][a-z0-9._+-]{0,31}$`)
	stageValues                = valueSet("inactive", "canary", "5", "20", "50", "100", "unknown")
	targetValues               = valueSet("stable", "candidate", "unavailable", "unknown")
	platformValues             = valueSet("android", "ios", "web", "unknown")
	reasonValues               = valueSet(
		"campaign_inactive",
		"missing_rollout_subject",
		"existing_assignment",
		"bucket_outside_threshold",
		"audience_not_eligible",
		"percentage_threshold",
		"internal_canary",
		"assignment_store_failure",
		"evaluation_failure",
		"unknown",
	)
)

type Metrics struct {
	decisions *prometheus.CounterVec

	mu                 sync.Mutex
	detailedSeriesKeys map[string]struct{}
}

var _ application.Observer = (*Metrics)(nil)

func NewMetrics(registerer prometheus.Registerer) *Metrics {
	if registerer == nil {
		registerer = prometheus.DefaultRegisterer
	}
	metrics := &Metrics{
		decisions: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "api_edge_rollout_decisions_total",
				Help: "Rollout routing decisions using bounded, non-identifying labels.",
			},
			[]string{
				"stage", "target", "platform", "app_version", "app_build",
				"region", "carrier", "reason",
			},
		),
		detailedSeriesKeys: make(map[string]struct{}),
	}
	registerer.MustRegister(metrics.decisions)
	return metrics
}

func (metrics *Metrics) ObserveDecision(observation application.DecisionObservation) {
	if metrics == nil {
		return
	}
	labels := []string{
		closedValue(observation.Stage, stageValues),
		closedValue(observation.Target, targetValues),
		closedValue(observation.Platform, platformValues),
		semanticValue(observation.AppVersion),
		application.NormalizeBuildMetricValue(observation.AppBuild),
		semanticValue(observation.Region),
		semanticValue(observation.Carrier),
		closedValue(observation.Reason, reasonValues),
	}
	labels = metrics.enforceSeriesLimit(labels)
	metrics.decisions.WithLabelValues(labels...).Inc()
}

func (metrics *Metrics) enforceSeriesLimit(labels []string) []string {
	key := strings.Join(labels, "\x00")
	metrics.mu.Lock()
	defer metrics.mu.Unlock()
	if _, exists := metrics.detailedSeriesKeys[key]; exists {
		return labels
	}
	if len(metrics.detailedSeriesKeys) < maxDetailedDecisionSeries {
		metrics.detailedSeriesKeys[key] = struct{}{}
		return labels
	}
	bounded := append([]string(nil), labels...)
	for _, index := range []int{3, 4, 5, 6} {
		bounded[index] = "overflow"
	}
	return bounded
}

func closedValue(value string, allowed map[string]struct{}) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if _, exists := allowed[value]; exists {
		return value
	}
	return "unknown"
}

func semanticValue(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "" {
		return "missing"
	}
	if net.ParseIP(value) != nil {
		return "invalid"
	}
	if !semanticMetricValuePattern.MatchString(value) {
		return "invalid"
	}
	return value
}

func valueSet(values ...string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		result[value] = struct{}{}
	}
	return result
}
