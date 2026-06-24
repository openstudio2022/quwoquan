package local_contract

import (
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

type recommendationSLOContract struct {
	CommercialMaturity struct {
		Dimensions struct {
			ObservabilityMaturity struct {
				PrimarySLIs []string `yaml:"primary_slis"`
			} `yaml:"observability_maturity"`
		} `yaml:"dimensions"`
	} `yaml:"commercial_maturity"`
	Metrics map[string]string `yaml:"metrics"`
	SLIs    []struct {
		ID           string  `yaml:"id"`
		Source       string  `yaml:"source"`
		ObjectiveMax float64 `yaml:"objective_max"`
		Measured     bool    `yaml:"measured"`
	} `yaml:"slis"`
	RollbackLayers []string `yaml:"rollback_layers"`
	AlertsSource   string   `yaml:"alerts_source"`
}

type prometheusAlertsFile struct {
	Groups []struct {
		Name  string `yaml:"name"`
		Rules []struct {
			Alert string `yaml:"alert"`
			Expr  string `yaml:"expr"`
		} `yaml:"rules"`
	} `yaml:"groups"`
}

func TestExposureObservabilityCapacityLocalContract(t *testing.T) {
	repoRoot := resolveRepoRoot(t)
	sloPath := filepath.Join(
		repoRoot,
		"quwoquan_service",
		"services",
		"content-service",
		"configs",
		"observability",
		"recommendation_slo.yaml",
	)
	alertsPath := filepath.Join(
		repoRoot,
		"deploy",
		"monitoring",
		"alerts",
		"quwoquan_alerts.yaml",
	)

	var slo recommendationSLOContract
	mustLoadYAML(t, sloPath, &slo)
	var alerts prometheusAlertsFile
	mustLoadYAML(t, alertsPath, &alerts)

	observabilitySLIs := slo.CommercialMaturity.Dimensions.ObservabilityMaturity.PrimarySLIs
	for _, required := range []string{"behavior_ingest_drop_rate", "hotpath_buffer_drop_total", "recommendation_feed_availability"} {
		if !slices.Contains(observabilitySLIs, required) {
			t.Fatalf("observability primary_slis missing %q: %#v", required, observabilitySLIs)
		}
	}

	if got := slo.Metrics["behavior_ingest_dropped_total"]; got != "recommendation_behavior_ingest_dropped_total" {
		t.Fatalf("behavior_ingest_dropped_total=%q, want recommendation_behavior_ingest_dropped_total", got)
	}
	if got := slo.Metrics["hotpath_dropped_total"]; got != "rec_hotpath_dropped_total" {
		t.Fatalf("hotpath_dropped_total=%q, want rec_hotpath_dropped_total", got)
	}

	behaviorDrop := findSLI(t, slo.SLIs, "behavior_ingest_drop_rate")
	if !behaviorDrop.Measured {
		t.Fatalf("behavior_ingest_drop_rate must be measured=true: %#v", behaviorDrop)
	}
	if !strings.Contains(behaviorDrop.Source, "recommendation_behavior_ingest_dropped_total") ||
		!strings.Contains(behaviorDrop.Source, "recommendation_behavior_ingest_total") {
		t.Fatalf("behavior_ingest_drop_rate source drift: %q", behaviorDrop.Source)
	}

	hotPathDrop := findSLI(t, slo.SLIs, "hotpath_buffer_drop_total")
	if !hotPathDrop.Measured {
		t.Fatalf("hotpath_buffer_drop_total must be measured=true: %#v", hotPathDrop)
	}
	if hotPathDrop.Source != "rec_hotpath_dropped_total" {
		t.Fatalf("hotpath_buffer_drop_total source=%q, want rec_hotpath_dropped_total", hotPathDrop.Source)
	}
	if hotPathDrop.ObjectiveMax != 0 {
		t.Fatalf("hotpath_buffer_drop_total objective_max=%v, want 0", hotPathDrop.ObjectiveMax)
	}

	for _, required := range []string{
		"force_rule_scorer",
		"disable_exposure_dynamic_budget",
		"disable_resurface_source",
		"fallback_to_hot_and_new_content_sources",
	} {
		if !slices.Contains(slo.RollbackLayers, required) {
			t.Fatalf("rollback_layers missing %q: %#v", required, slo.RollbackLayers)
		}
	}
	if got := slo.AlertsSource; got != "deploy/monitoring/alerts/quwoquan_alerts.yaml#quwoquan_rec_model" {
		t.Fatalf("alerts_source=%q drifted", got)
	}

	requiredAlerts := map[string]string{
		"RecommendationBehaviorIngestDropHigh":     "recommendation_behavior_ingest_dropped_total",
		"RecommendationHotPathBufferDropHigh":      "rec_hotpath_dropped_total",
		"RecommendationRepeatExposureRateHigh":     "recommendation_feed_duplicate_exposure_total",
		"RecommendationContentCoverageLow":         "eligible_feed_item_count",
		"RecommendationPolicyTakedownEjectionSlow": "recommendation_feed_policy_takedown_ejection_seconds_bucket",
	}
	rules := flattenAlerts(alerts)
	for alertName, metricFragment := range requiredAlerts {
		expr, ok := rules[alertName]
		if !ok {
			t.Fatalf("alert %q missing from quwoquan_alerts.yaml", alertName)
		}
		if !strings.Contains(expr, metricFragment) {
			t.Fatalf("alert %q expr drifted, missing %q: %s", alertName, metricFragment, expr)
		}
	}
}

func findSLI(t *testing.T, slis []struct {
	ID           string  `yaml:"id"`
	Source       string  `yaml:"source"`
	ObjectiveMax float64 `yaml:"objective_max"`
	Measured     bool    `yaml:"measured"`
}, target string) struct {
	ID           string  `yaml:"id"`
	Source       string  `yaml:"source"`
	ObjectiveMax float64 `yaml:"objective_max"`
	Measured     bool    `yaml:"measured"`
} {
	t.Helper()
	for _, item := range slis {
		if item.ID == target {
			return item
		}
	}
	t.Fatalf("missing sli %q", target)
	return struct {
		ID           string  `yaml:"id"`
		Source       string  `yaml:"source"`
		ObjectiveMax float64 `yaml:"objective_max"`
		Measured     bool    `yaml:"measured"`
	}{}
}

func flattenAlerts(file prometheusAlertsFile) map[string]string {
	out := map[string]string{}
	for _, group := range file.Groups {
		for _, rule := range group.Rules {
			out[rule.Alert] = rule.Expr
		}
	}
	return out
}

func mustLoadYAML(t *testing.T, path string, target any) {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	if err := yaml.Unmarshal(payload, target); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
}

func resolveRepoRoot(t *testing.T) string {
	t.Helper()
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	current := cwd
	for {
		if _, err := os.Stat(filepath.Join(current, "docs", "outstanding_risks_backlog.md")); err == nil {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			t.Fatalf("repo root not found from %s", cwd)
		}
		current = parent
	}
}
