package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

type grafanaDashboardEnvelope struct {
	Dashboard struct {
		Title       string   `json:"title"`
		UID         string   `json:"uid"`
		Description string   `json:"description"`
		Tags        []string `json:"tags"`
		Templating  struct {
			List []struct {
				Name  string `json:"name"`
				Query string `json:"query"`
			} `json:"list"`
		} `json:"templating"`
		Panels []struct {
			Title   string `json:"title"`
			Targets []struct {
				Expr string `json:"expr"`
			} `json:"targets"`
		} `json:"panels"`
	} `json:"dashboard"`
}

type recommendationDashboardSLO struct {
	Dashboards map[string]string `yaml:"dashboards"`
	Metrics    map[string]string `yaml:"metrics"`
	SLIs       []struct {
		ID       string `yaml:"id"`
		Source   string `yaml:"source"`
		Measured bool   `yaml:"measured"`
	} `yaml:"slis"`
}

func TestRecommendationCommercialDashboardLocalContract(t *testing.T) {
	repoRoot := resolveRepoRoot(t)
	dashboardPath := filepath.Join(
		repoRoot,
		"deploy",
		"monitoring",
		"dashboards",
		"l2_recommendation_commercial_maturity.json",
	)
	sloPath := filepath.Join(
		repoRoot,
		"quwoquan_service",
		"services",
		"content-service",
		"configs",
		"observability",
		"recommendation_slo.yaml",
	)

	dashboard := mustLoadGrafanaDashboard(t, dashboardPath)
	var slo recommendationDashboardSLO
	mustLoadYAML(t, sloPath, &slo)

	if dashboard.Dashboard.UID != "qwq-l2-recommendation-commercial" {
		t.Fatalf("dashboard uid drifted: %q", dashboard.Dashboard.UID)
	}
	for _, tag := range []string{"recommendation", "commercial-maturity", "attribution"} {
		if !slices.Contains(dashboard.Dashboard.Tags, tag) {
			t.Fatalf("dashboard tags missing %q: %#v", tag, dashboard.Dashboard.Tags)
		}
	}
	if len(dashboard.Dashboard.Panels) < 8 {
		t.Fatalf("dashboard must expose commercial review panels, got %d", len(dashboard.Dashboard.Panels))
	}

	expressions := strings.Join(appendDashboardExpressions(dashboard), "\n")
	for _, required := range []string{
		"recommendation_feed_served_by_attribution_total",
		"recommendation_behavior_by_attribution_total",
		"channel",
		"vertical",
		"supply_source",
		"recall_path",
		"ranking_version",
		"reason_version",
		"intersection_class",
		"state=\"click\"",
		"state=\"impressed\"",
		"state=\"negative\"",
		"channel=\"unknown\"",
		"recall_path=\"unknown\"",
		"travel_photography",
		"premium_stream",
		"fact|affinity",
	} {
		if !strings.Contains(expressions, required) {
			t.Fatalf("dashboard expressions missing %q:\n%s", required, expressions)
		}
	}
	for _, forbidden := range []string{
		"recommendation_offline_eval_metric_value",
		"eligible_feed_item_count",
		"collaborative_recall_lift",
	} {
		if strings.Contains(expressions, forbidden) {
			t.Fatalf("dashboard must not use objective-only metric %q:\n%s", forbidden, expressions)
		}
	}

	if got := slo.Dashboards["recommendation_commercial_maturity"]; got != "deploy/monitoring/dashboards/l2_recommendation_commercial_maturity.json" {
		t.Fatalf("recommendation_commercial_maturity dashboard source=%q", got)
	}
	if got := slo.Metrics["feed_served_by_attribution_total"]; got != "recommendation_feed_served_by_attribution_total" {
		t.Fatalf("feed_served_by_attribution_total=%q", got)
	}
	if got := slo.Metrics["behavior_by_attribution_total"]; got != "recommendation_behavior_by_attribution_total" {
		t.Fatalf("behavior_by_attribution_total=%q", got)
	}
	sli := findDashboardSLI(t, slo.SLIs, "recommendation_attribution_bucket_coverage")
	if !sli.Measured {
		t.Fatalf("recommendation_attribution_bucket_coverage must be measured")
	}
	if !strings.Contains(sli.Source, "recommendation_behavior_by_attribution_total") ||
		!strings.Contains(sli.Source, "channel=\"unknown\"") ||
		!strings.Contains(sli.Source, "recall_path=\"unknown\"") {
		t.Fatalf("recommendation_attribution_bucket_coverage source drifted: %q", sli.Source)
	}
}

func mustLoadGrafanaDashboard(t *testing.T, path string) grafanaDashboardEnvelope {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var dashboard grafanaDashboardEnvelope
	if err := json.Unmarshal(payload, &dashboard); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	return dashboard
}

func appendDashboardExpressions(dashboard grafanaDashboardEnvelope) []string {
	expressions := make([]string, 0, len(dashboard.Dashboard.Panels))
	for _, item := range dashboard.Dashboard.Templating.List {
		expressions = append(expressions, item.Query)
	}
	for _, panel := range dashboard.Dashboard.Panels {
		for _, target := range panel.Targets {
			expressions = append(expressions, target.Expr)
		}
	}
	return expressions
}

func findDashboardSLI(t *testing.T, slis []struct {
	ID       string `yaml:"id"`
	Source   string `yaml:"source"`
	Measured bool   `yaml:"measured"`
}, target string) struct {
	ID       string `yaml:"id"`
	Source   string `yaml:"source"`
	Measured bool   `yaml:"measured"`
} {
	t.Helper()
	for _, item := range slis {
		if item.ID == target {
			return item
		}
	}
	t.Fatalf("missing sli %q", target)
	return struct {
		ID       string `yaml:"id"`
		Source   string `yaml:"source"`
		Measured bool   `yaml:"measured"`
	}{}
}
