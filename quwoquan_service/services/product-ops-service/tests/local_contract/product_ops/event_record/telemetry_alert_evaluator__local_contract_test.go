// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-003
// ES 聚合告警评估循环：product_telemetry_alerts.yaml 是唯一执行策略真相源；
// 本文件验证策略解析闭合、字段派生代数、group_by 分组与 Alertmanager 投递。
package local_contract

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

func loadContractAlertPolicy(t *testing.T) application.AlertPolicy {
	t.Helper()
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	repoRoot := filepath.Join(filepath.Dir(currentFile), "..", "..", "..", "..", "..", "..", "..")
	raw, err := os.ReadFile(filepath.Join(
		repoRoot,
		"quwoquan_ops", "observability", "elasticsearch", "product_telemetry_alerts.yaml",
	))
	if err != nil {
		t.Fatalf("read contract alert policy: %v", err)
	}
	policy, err := application.ParseAlertPolicy(raw)
	if err != nil {
		t.Fatalf("ParseAlertPolicy() error = %v", err)
	}
	return policy
}

func contractAlertRule(t *testing.T, policy application.AlertPolicy, name string) application.AlertRule {
	t.Helper()
	for _, rule := range policy.Alerts {
		if rule.Name == name {
			return rule
		}
	}
	t.Fatalf("alert %s missing from contract policy", name)
	return application.AlertRule{}
}

func TestContractAlertPolicyParsesWithClosedFieldDerivations(t *testing.T) {
	t.Parallel()
	policy := loadContractAlertPolicy(t)
	if len(policy.Alerts) < 30 {
		t.Fatalf("contract policy alerts = %d; want >= 30", len(policy.Alerts))
	}
	for _, rule := range policy.Alerts {
		if rule.WindowMinutes <= 0 {
			t.Fatalf("alert %s misses window_minutes", rule.Name)
		}
		if len(rule.Fields) == 0 {
			t.Fatalf("alert %s misses explicit field derivations", rule.Name)
		}
	}
}

func TestEvaluateAlertRuleDerivesP95AndRespectsSampleGuard(t *testing.T) {
	t.Parallel()
	policy := loadContractAlertPolicy(t)
	rule := contractAlertRule(t, policy, "product-video-ready-p95-high")
	slowVideoRow := func(readyCount int) map[string]any {
		buckets := []any{0, 100, 250, 500, 1000, 2000, 3000, 5000, 10000, 30000}
		counts := make([]any, len(buckets)+1)
		for index := range counts {
			counts[index] = 0
		}
		counts[8] = readyCount // 全部样本落在 5000-10000ms 桶
		return map[string]any{
			"rowKind":     "video_qoe",
			"bucketStart": time.Now().UTC().Truncate(time.Hour).Format(time.RFC3339Nano),
			"readyCount":  readyCount,
			"readyHistogram": map[string]any{
				"bucketsMs": buckets,
				"counts":    counts,
				"sum":       readyCount * 7000,
				"count":     readyCount,
			},
		}
	}
	firing, err := application.EvaluateAlertRule(
		rule,
		[]map[string]any{slowVideoRow(120)},
		application.EvaluatorRuntimeMetrics{},
	)
	if err != nil {
		t.Fatalf("EvaluateAlertRule() error = %v", err)
	}
	if len(firing) != 1 {
		t.Fatalf("slow video p95 must fire; got %d hits", len(firing))
	}
	if firing[0].FieldValues["p95Ms"] <= 3000 {
		t.Fatalf("derived p95Ms = %v; want > 3000", firing[0].FieldValues["p95Ms"])
	}
	// 样本量守卫：同样慢，但样本不足 100 时不得告警。
	quiet, err := application.EvaluateAlertRule(
		rule,
		[]map[string]any{slowVideoRow(20)},
		application.EvaluatorRuntimeMetrics{},
	)
	if err != nil {
		t.Fatalf("EvaluateAlertRule() error = %v", err)
	}
	if len(quiet) != 0 {
		t.Fatalf("insufficient samples must not fire; got %d hits", len(quiet))
	}
}

func TestEvaluateAlertRuleSplitsNumeratorAndDenominatorForRtcConnectRate(t *testing.T) {
	t.Parallel()
	policy := loadContractAlertPolicy(t)
	rule := contractAlertRule(t, policy, "product-rtc-media-connect-rate-low")
	bucketStart := time.Now().UTC().Truncate(time.Hour).Format(time.RFC3339Nano)
	row := func(mediaConnected string, result string, count int) map[string]any {
		return map[string]any{
			"rowKind":        "rtc_qoe",
			"bucketStart":    bucketStart,
			"mediaConnected": mediaConnected,
			"result":         result,
			"count":          count,
		}
	}
	firing, err := application.EvaluateAlertRule(
		rule,
		[]map[string]any{
			row("true", "success", 90),
			row("false", "failed", 10),
			// abandoned 由 filter 排除，不进分母。
			row("false", "abandoned", 400),
		},
		application.EvaluatorRuntimeMetrics{},
	)
	if err != nil {
		t.Fatalf("EvaluateAlertRule() error = %v", err)
	}
	if len(firing) != 1 {
		t.Fatalf("connect rate 0.90 must fire below 0.98; got %d hits", len(firing))
	}
	if got := firing[0].FieldValues["connectRate"]; got != 0.9 {
		t.Fatalf("connectRate = %v; want 0.9 (abandoned excluded from denominator)", got)
	}
	// 分母为 0（全部 abandoned）时 div 字段缺失，不得误告警。
	empty, err := application.EvaluateAlertRule(
		rule,
		[]map[string]any{row("false", "abandoned", 500)},
		application.EvaluatorRuntimeMetrics{},
	)
	if err != nil {
		t.Fatalf("EvaluateAlertRule() error = %v", err)
	}
	if len(empty) != 0 {
		t.Fatalf("zero denominator must not fire; got %d hits", len(empty))
	}
}

func TestEvaluateAlertRuleGroupsRuntimeFingerprintSpikes(t *testing.T) {
	t.Parallel()
	policy := loadContractAlertPolicy(t)
	rule := contractAlertRule(t, policy, "runtime-diagnostics-error-fingerprint-spike")
	bucketStart := time.Now().UTC().Truncate(time.Hour).Format(time.RFC3339Nano)
	row := func(fingerprint string, severity string, count int) map[string]any {
		return map[string]any{
			"rowKind":     "runtime_diagnostics",
			"bucketStart": bucketStart,
			"fingerprint": fingerprint,
			"severity":    severity,
			"count":       count,
		}
	}
	firing, err := application.EvaluateAlertRule(
		rule,
		[]map[string]any{
			row("fp-hot", "error", 8),
			row("fp-hot", "error", 5),
			row("fp-cold", "error", 3),
			// warning 不满足 severity=error filter，即使量大也不进分组。
			row("fp-warn", "warning", 100),
		},
		application.EvaluatorRuntimeMetrics{},
	)
	if err != nil {
		t.Fatalf("EvaluateAlertRule() error = %v", err)
	}
	if len(firing) != 1 {
		t.Fatalf("exactly the hot fingerprint must fire; got %d hits", len(firing))
	}
	if firing[0].GroupLabels["fingerprint"] != "fp-hot" {
		t.Fatalf("firing group labels = %v; want fingerprint=fp-hot", firing[0].GroupLabels)
	}
	if firing[0].FieldValues["count"] != 13 {
		t.Fatalf("grouped count = %v; want 13", firing[0].FieldValues["count"])
	}
}

type fakeAlertReader struct {
	rowsByRowKind    map[string][]map[string]any
	failingRowKinds  map[string]bool
	generatedThrough time.Time
	hasSamples       bool
}

func (r *fakeAlertReader) ListAggregateAlertRows(
	_ context.Context,
	rowKind string,
	_ time.Time,
	_ time.Time,
) ([]map[string]any, error) {
	if r.failingRowKinds[rowKind] {
		return nil, errors.New("simulated aggregate query failure")
	}
	return r.rowsByRowKind[rowKind], nil
}

func (r *fakeAlertReader) AggregateGeneratedThrough(
	context.Context,
) (time.Time, bool, error) {
	return r.generatedThrough, r.hasSamples, nil
}

type fakeRetentionInspector struct {
	rawDays     int
	runtimeDays int
}

func (r fakeRetentionInspector) RawRetentionDays(context.Context) (int, error) {
	return r.rawDays, nil
}

func (r fakeRetentionInspector) RuntimeRawRetentionDays(context.Context) (int, error) {
	return r.runtimeDays, nil
}

type fakeAlertNotifier struct {
	batches [][]application.AlertmanagerAlert
}

func (n *fakeAlertNotifier) PostAlerts(
	_ context.Context,
	alerts []application.AlertmanagerAlert,
) error {
	n.batches = append(n.batches, alerts)
	return nil
}

func TestAlertEvaluationLoopPostsControlPlaneDriftToAlertmanager(t *testing.T) {
	t.Parallel()
	policy := loadContractAlertPolicy(t)
	reader := &fakeAlertReader{
		rowsByRowKind: map[string][]map[string]any{},
		// performance 查询失败必须计入 failedTransformCount 并触发 transform-failed。
		failingRowKinds:  map[string]bool{"performance": true},
		generatedThrough: time.Now().UTC().Add(-3 * time.Hour),
		hasSamples:       true,
	}
	notifier := &fakeAlertNotifier{}
	loop, err := application.NewAlertEvaluationLoop(
		policy,
		reader,
		notifier,
		fakeRetentionInspector{rawDays: 7, runtimeDays: 3},
		time.Minute,
	)
	if err != nil {
		t.Fatalf("NewAlertEvaluationLoop() error = %v", err)
	}
	firing, err := loop.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce() error = %v", err)
	}
	byName := map[string]application.FiringAlert{}
	for _, hit := range firing {
		byName[hit.Rule.Name] = hit
	}
	for _, expected := range []string{
		"product-telemetry-transform-failed",  // performance 查询失败
		"product-telemetry-aggregate-stale",   // 3 小时水位 > 70 分钟
		"product-telemetry-raw-retention-drift", // 7 天 != 3 天
	} {
		if _, ok := byName[expected]; !ok {
			t.Fatalf("expected %s to fire; got %v", expected, alertNames(firing))
		}
	}
	// runtime 保留 3 天符合契约：不得误报。
	if _, ok := byName["runtime-diagnostics-raw-retention-drift"]; ok {
		t.Fatal("runtime retention 3d must not fire drift alert")
	}
	if len(notifier.batches) != 1 {
		t.Fatalf("Alertmanager batches = %d; want 1", len(notifier.batches))
	}
	for _, alert := range notifier.batches[0] {
		if alert.Labels["alertname"] == "" ||
			alert.Labels["severity"] == "" ||
			alert.Labels["source"] != "product-ops-es-evaluator" {
			t.Fatalf("alert labels incomplete: %v", alert.Labels)
		}
		if !alert.EndsAt.After(alert.StartsAt) {
			t.Fatalf("alert must carry a resolve horizon: %+v", alert)
		}
		if alert.Annotations["condition"] == "" {
			t.Fatalf("alert must annotate its condition: %v", alert.Annotations)
		}
	}
}

func TestAlertEvaluationLoopStaysQuietWhenEverythingIsHealthy(t *testing.T) {
	t.Parallel()
	policy := loadContractAlertPolicy(t)
	reader := &fakeAlertReader{
		rowsByRowKind:    map[string][]map[string]any{},
		generatedThrough: time.Now().UTC().Add(-10 * time.Minute),
		hasSamples:       true,
	}
	notifier := &fakeAlertNotifier{}
	loop, err := application.NewAlertEvaluationLoop(
		policy,
		reader,
		notifier,
		fakeRetentionInspector{rawDays: 3, runtimeDays: 3},
		time.Minute,
	)
	if err != nil {
		t.Fatalf("NewAlertEvaluationLoop() error = %v", err)
	}
	firing, err := loop.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce() error = %v", err)
	}
	if len(firing) != 0 {
		t.Fatalf("healthy telemetry must stay quiet; got %v", alertNames(firing))
	}
	if len(notifier.batches) != 0 {
		t.Fatalf("no alerts must be posted when quiet; got %d batches", len(notifier.batches))
	}
}

func alertNames(firing []application.FiringAlert) []string {
	names := make([]string, 0, len(firing))
	for _, hit := range firing {
		names = append(names, hit.Rule.Name)
	}
	return names
}
