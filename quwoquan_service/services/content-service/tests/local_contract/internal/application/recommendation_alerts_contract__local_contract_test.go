package local_contract

import (
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

type recommendationCommercialAlertingSLO struct {
	Alerts map[string]struct {
		Source string   `yaml:"source"`
		Rules  []string `yaml:"rules"`
	} `yaml:"alerts"`
	AlertsSource string            `yaml:"alerts_source"`
	Metrics      map[string]string `yaml:"metrics"`
	SLIs         []struct {
		ID           string  `yaml:"id"`
		Source       string  `yaml:"source"`
		ObjectiveMax float64 `yaml:"objective_max"`
		ObjectiveMin float64 `yaml:"objective_min"`
		Measured     bool    `yaml:"measured"`
	} `yaml:"slis"`
}

func TestRecommendationCommercialAlertingLocalContract(t *testing.T) {
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

	var slo recommendationCommercialAlertingSLO
	mustLoadYAML(t, sloPath, &slo)
	var alerts prometheusAlertsFile
	mustLoadYAML(t, alertsPath, &alerts)

	if got := slo.AlertsSource; got != "deploy/monitoring/alerts/quwoquan_alerts.yaml#quwoquan_rec_model" {
		t.Fatalf("alerts_source=%q, want quwoquan_rec_model", got)
	}
	alerting := slo.Alerts["recommendation_commercial_alerting"]
	if alerting.Source != "deploy/monitoring/alerts/quwoquan_alerts.yaml#quwoquan_rec_model" {
		t.Fatalf("recommendation_commercial_alerting source drifted: %q", alerting.Source)
	}

	requiredAlerts := []string{
		"RecommendationAttributionUnknownRateHigh",
		"RecommendationAttributionNegativeFeedbackBySupplySourceHigh",
		"RecommendationAttributionCTRByRecallPathLow",
		"RecommendationScenarioConsumptionRateLow",
		"RecommendationSupplySourceShareImbalance",
	}
	for _, name := range requiredAlerts {
		if !slices.Contains(alerting.Rules, name) {
			t.Fatalf("recommendation_commercial_alerting rules missing %q: %#v", name, alerting.Rules)
		}
	}

	recModelRules := rulesForAlertGroup(alerts, "quwoquan_rec_model")
	for _, name := range requiredAlerts {
		if _, ok := recModelRules[name]; !ok {
			t.Fatalf("alert %q missing from quwoquan_rec_model", name)
		}
	}

	expressions := strings.Join(alertExpressions(recModelRules, requiredAlerts), "\n")
	for _, required := range []string{
		"recommendation_feed_served_by_attribution_total",
		"recommendation_behavior_by_attribution_total",
		"channel",
		"vertical",
		"supply_source",
		"recall_path",
		"state=\"negative\"",
		"state=\"impressed\"",
		"state=\"click\"",
		"channel=\"unknown\"",
		"recall_path=\"unknown\"",
		"travel|premium_stream",
		"ugc|data_engineering",
		"> 0.05",
		"> 0.08",
		"< 0.03",
		"< 0.02",
	} {
		if !strings.Contains(expressions, required) {
			t.Fatalf("commercial alert expressions missing %q:\n%s", required, expressions)
		}
	}
	for _, forbidden := range []string{
		"recommendation_offline_eval_metric_value",
		"eligible_feed_item_count",
		"collaborative_recall_lift",
		"recommendation_feed_ab_valid_experiments_total",
	} {
		if strings.Contains(expressions, forbidden) {
			t.Fatalf("commercial alert must not use objective-only metric %q:\n%s", forbidden, expressions)
		}
	}

	for _, requiredSLI := range []string{
		"recommendation_attribution_bucket_coverage",
		"attribution_negative_feedback_rate",
		"attribution_ctr_by_recall_path",
		"scenario_consumption_rate",
		"supply_source_share_floor",
	} {
		sli := findCommercialAlertingSLI(t, slo.SLIs, requiredSLI)
		if !sli.Measured {
			t.Fatalf("%s must be measured=true", requiredSLI)
		}
		if !strings.Contains(sli.Source, "recommendation_behavior_by_attribution_total") &&
			!strings.Contains(sli.Source, "recommendation_feed_served_by_attribution_total") {
			t.Fatalf("%s source must reference P0+ attribution metrics: %q", requiredSLI, sli.Source)
		}
	}

	if got := slo.Metrics["feed_served_by_attribution_total"]; got != "recommendation_feed_served_by_attribution_total" {
		t.Fatalf("feed_served_by_attribution_total metric drifted: %q", got)
	}
	if got := slo.Metrics["behavior_by_attribution_total"]; got != "recommendation_behavior_by_attribution_total" {
		t.Fatalf("behavior_by_attribution_total metric drifted: %q", got)
	}
}

func rulesForAlertGroup(file prometheusAlertsFile, groupName string) map[string]string {
	for _, group := range file.Groups {
		if group.Name != groupName {
			continue
		}
		rules := map[string]string{}
		for _, rule := range group.Rules {
			rules[rule.Alert] = rule.Expr
		}
		return rules
	}
	return map[string]string{}
}

func alertExpressions(rules map[string]string, names []string) []string {
	expressions := make([]string, 0, len(names))
	for _, name := range names {
		expressions = append(expressions, rules[name])
	}
	return expressions
}

func findCommercialAlertingSLI(t *testing.T, slis []struct {
	ID           string  `yaml:"id"`
	Source       string  `yaml:"source"`
	ObjectiveMax float64 `yaml:"objective_max"`
	ObjectiveMin float64 `yaml:"objective_min"`
	Measured     bool    `yaml:"measured"`
}, target string) struct {
	ID           string  `yaml:"id"`
	Source       string  `yaml:"source"`
	ObjectiveMax float64 `yaml:"objective_max"`
	ObjectiveMin float64 `yaml:"objective_min"`
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
		ObjectiveMin float64 `yaml:"objective_min"`
		Measured     bool    `yaml:"measured"`
	}{}
}
