package local_contract

// N1-1 契约：quwoquan_rec_model 组内所有推荐告警引用的指标必须有真实 emitter。
// 历史教训：rec_score_value / recommendation_feed_policy_takedown_ejection_seconds /
// recommendation_offline_eval_metric_value（无调度）曾以"预置告警"名义存在，
// 从未可求值——死告警比无告警更危险（给出已被监控的假象）。
//
// 双向断言：
//  1. 每条告警 expr 引用的 rec_*/recommendation_* 指标 ∈ 注册指标集；
//  2. 注册指标集内的每个名字都能在 runtime 源码中找到 Name 声明证据。

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

// runtimeRegisteredRecMetrics 是 runtime/recommendation 注册的、允许出现在
// 告警表达式中的指标基名（histogram 归一化到基名，不带 _bucket/_sum/_count）。
// 新增告警指标时必须：先在 observability.go/metrics 注册 emitter，再登记到此。
var runtimeRegisteredRecMetrics = map[string]bool{
	// pipeline（Namespace rec / Subsystem pipeline）
	"rec_pipeline_requests_total":        true,
	"rec_pipeline_model_hits_total":      true,
	"rec_pipeline_rule_hits_total":       true,
	"rec_pipeline_model_fallback_total":  true,
	"rec_pipeline_empty_results_total":   true,
	"rec_pipeline_model_timeouts_total":  true,
	"rec_pipeline_total_latency_seconds": true,
	// feed 七态与曝光治理
	"recommendation_feed_served_total":                       true,
	"recommendation_feed_served_by_attribution_total":        true,
	"recommendation_feed_impressed_total":                    true,
	"recommendation_feed_engagement_total":                   true,
	"recommendation_feed_completion_total":                   true,
	"recommendation_feed_negative_feedback_total":            true,
	"recommendation_feed_duplicate_exposure_total":           true,
	"recommendation_behavior_ingest_total":                   true,
	"recommendation_behavior_ingest_dropped_total":           true,
	"recommendation_behavior_by_attribution_total":           true,
	"rec_hotpath_dropped_total":                              true,
	"recommendation_exposure_filter_smembers_fallback_total": true,
	"recommendation_feed_ab_experiment_validity_total":       true,
}

var recMetricNamePattern = regexp.MustCompile(`\b(rec_[a-z0-9_]+|recommendation_[a-z0-9_]+)\b`)

func normalizeHistogramMetric(name string) string {
	for _, suffix := range []string{"_bucket", "_sum", "_count"} {
		if strings.HasSuffix(name, suffix) {
			return strings.TrimSuffix(name, suffix)
		}
	}
	return name
}

func TestRecommendationAlertMetricsAllHaveEmitters(t *testing.T) {
	repoRoot := resolveRepoRoot(t)
	alertsPath := filepath.Join(
		repoRoot, "quwoquan_ops", "observability", "monitoring", "alerts", "quwoquan_alerts.yaml",
	)
	var alerts prometheusAlertsFile
	mustLoadYAML(t, alertsPath, &alerts)

	rules := rulesForAlertGroup(alerts, "quwoquan_rec_model")
	if len(rules) == 0 {
		t.Fatal("quwoquan_rec_model alert group not found")
	}

	for name, expr := range rules {
		for _, match := range recMetricNamePattern.FindAllString(expr, -1) {
			metric := normalizeHistogramMetric(match)
			if !runtimeRegisteredRecMetrics[metric] {
				t.Errorf(
					"alert %s references metric %q with no registered emitter; "+
						"register the emitter in runtime/recommendation and add it to runtimeRegisteredRecMetrics",
					name, metric,
				)
			}
		}
	}
}

func TestRuntimeRegisteredRecMetricsHaveSourceEvidence(t *testing.T) {
	repoRoot := resolveRepoRoot(t)
	runtimeDir := filepath.Join(repoRoot, "quwoquan_service", "runtime", "recommendation")

	var sourceText strings.Builder
	for _, file := range []string{"observability.go", "metrics.go"} {
		content, err := os.ReadFile(filepath.Join(runtimeDir, file))
		if err != nil {
			t.Fatalf("read %s: %v", file, err)
		}
		sourceText.Write(content)
	}
	source := sourceText.String()

	for metric := range runtimeRegisteredRecMetrics {
		// promauto 注册可能是全名（Name: "recommendation_..."）或
		// Namespace rec + Subsystem pipeline + Name 短名两种形态。
		fullDecl := `"` + metric + `"`
		shortName := strings.TrimPrefix(metric, "rec_pipeline_")
		shortDecl := `"` + shortName + `"`
		if !strings.Contains(source, fullDecl) && !strings.Contains(source, shortDecl) {
			t.Errorf(
				"metric %q registered in test allowlist but no Name declaration found in runtime/recommendation sources",
				metric,
			)
		}
	}
}

// 死告警不得回潮：这些告警此前引用不存在的指标，已在 N1-1 删除；
// 若重新引入必须先接真实 emitter 并从本清单移除。
func TestRemovedDeadAlertsDoNotReturn(t *testing.T) {
	repoRoot := resolveRepoRoot(t)
	alertsPath := filepath.Join(
		repoRoot, "quwoquan_ops", "observability", "monitoring", "alerts", "quwoquan_alerts.yaml",
	)
	var alerts prometheusAlertsFile
	mustLoadYAML(t, alertsPath, &alerts)
	rules := rulesForAlertGroup(alerts, "quwoquan_rec_model")

	for _, dead := range []string{
		"RecScoreDistributionAnomaly",
		"RecommendationContentCoverageLow",
		"RecommendationPolicyTakedownEjectionSlow",
	} {
		if _, exists := rules[dead]; exists {
			t.Errorf("dead alert %s returned without a real emitter (N1-1 regression)", dead)
		}
	}

	// RecModelFallbackRateHigh 必须使用真实降级计数（N0-1），不得回退 rule_hits 占比。
	fallbackExpr, ok := rules["RecModelFallbackRateHigh"]
	if !ok {
		t.Fatal("RecModelFallbackRateHigh alert missing")
	}
	if !strings.Contains(fallbackExpr, "rec_pipeline_model_fallback_total") {
		t.Errorf("RecModelFallbackRateHigh must use rec_pipeline_model_fallback_total, got:\n%s", fallbackExpr)
	}
}
