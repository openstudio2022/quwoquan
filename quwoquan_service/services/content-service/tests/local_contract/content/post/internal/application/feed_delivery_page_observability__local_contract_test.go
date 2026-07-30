// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002
package local_contract

import (
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

type feedDeliveryPageSLOContract struct {
	CommercialMaturity struct {
		Dimensions struct {
			ObservabilityMaturity struct {
				PrimarySLIs []string `yaml:"primary_slis"`
			} `yaml:"observability_maturity"`
		} `yaml:"dimensions"`
	} `yaml:"commercial_maturity"`
	Metrics map[string]string `yaml:"metrics"`
	Alerts  map[string]struct {
		Rules []string `yaml:"rules"`
	} `yaml:"alerts"`
	SLIs []struct {
		ID           string  `yaml:"id"`
		Source       string  `yaml:"source"`
		ObjectiveMax float64 `yaml:"objective_max"`
		Measured     bool    `yaml:"measured"`
	} `yaml:"slis"`
}

func TestFeedDeliveryPageObservabilityHasEmitterSLIAndAlerts(t *testing.T) {
	repoRoot := resolveRepoRoot(t)
	var slo feedDeliveryPageSLOContract
	mustLoadYAML(t, filepath.Join(
		repoRoot,
		"quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml",
	), &slo)

	for key, metric := range map[string]string{
		"feed_delivery_page_total":                 "content_feed_delivery_page_total",
		"feed_delivery_page_payload_bytes":         "content_feed_delivery_page_payload_bytes",
		"feed_delivery_page_quota_evictions_total": "content_feed_delivery_page_quota_evictions_total",
		"feed_delivery_page_shard_live_records":    "content_feed_delivery_page_shard_live_records",
		"feed_delivery_page_shard_live_bytes":      "content_feed_delivery_page_shard_live_bytes",
	} {
		if got := slo.Metrics[key]; got != metric {
			t.Fatalf("metric %s=%q, want %q", key, got, metric)
		}
	}
	primary := slo.CommercialMaturity.Dimensions.ObservabilityMaturity.PrimarySLIs
	for _, id := range []string{
		"feed_delivery_page_atomic_unavailable_rate",
		"feed_delivery_page_failure_rate",
		"feed_delivery_page_shard_key_rejection_rate",
		"feed_delivery_page_shard_byte_rejection_rate",
		"feed_delivery_page_repair_rejection_rate",
	} {
		if !slices.Contains(primary, id) {
			t.Fatalf("observability primary SLIs missing %q: %#v", id, primary)
		}
		found := false
		for _, sli := range slo.SLIs {
			if sli.ID != id {
				continue
			}
			found = true
			if !sli.Measured || !strings.Contains(sli.Source, "content_feed_delivery_page_total") {
				t.Fatalf("SLI %s is not backed by the delivery-page emitter: %#v", id, sli)
			}
		}
		if !found {
			t.Fatalf("SLI %q missing", id)
		}
	}

	alertNames := []string{
		"FeedDeliveryPageAtomicUnavailable",
		"FeedDeliveryPageFailureRateHigh",
		"FeedDeliveryPageShardKeyQuotaRejected",
		"FeedDeliveryPageShardByteQuotaRejected",
		"FeedDeliveryPageRepairBoundRejected",
	}
	declaredAlerts := slo.Alerts["recommendation_commercial_alerting"].Rules
	alertFile := filepath.Join(
		repoRoot,
		"quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml",
	)
	var alerts prometheusAlertsFile
	mustLoadYAML(t, alertFile, &alerts)
	rules := rulesForAlertGroup(alerts, "quwoquan_rec_model")
	for _, name := range alertNames {
		if !slices.Contains(declaredAlerts, name) {
			t.Fatalf("SLO alert list missing %q", name)
		}
		if !strings.Contains(rules[name], "content_feed_delivery_page_total") {
			t.Fatalf("alert %q does not use the real delivery-page emitter: %q", name, rules[name])
		}
	}

	source, err := os.ReadFile(filepath.Join(
		repoRoot,
		"quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis/store.go",
	))
	if err != nil {
		t.Fatalf("read delivery-page emitter source: %v", err)
	}
	for _, metric := range slo.Metrics {
		if strings.HasPrefix(metric, "content_feed_delivery_page_") &&
			!strings.Contains(string(source), `"`+metric+`"`) {
			t.Fatalf("metric %q has no source emitter declaration", metric)
		}
	}
}
