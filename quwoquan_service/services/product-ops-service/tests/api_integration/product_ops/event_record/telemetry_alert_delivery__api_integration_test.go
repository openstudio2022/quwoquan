// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002
// ES 告警评估投递全链：真实 Elasticsearch 聚合行 -> 契约策略评估循环 ->
// 真实 Alertmanager v2 收到 firing。策略文件与生产同源，禁止测试专用策略。
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/alerting"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
	testsupport "quwoquan_service/services/product-ops-service/tests/support"
)

func TestTelemetryAlertLoopDeliversFingerprintSpikeToRealAlertmanager(
	t *testing.T,
) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	elasticsearchEndpoint, terminateElasticsearch := testsupport.StartElasticsearch(t, ctx)
	defer terminateElasticsearch()
	alertmanagerEndpoint, terminateAlertmanager := testsupport.StartAlertmanager(t, ctx)
	defer terminateAlertmanager()

	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	config := telemetrypersistence.ElasticsearchConfig{
		Endpoint:               elasticsearchEndpoint,
		RawIndex:               "qwq-alertchain-raw-" + suffix,
		StartupDiagnosticIndex: "qwq-alertchain-startup-" + suffix,
		RuntimeLogIndex:        "qwq-alertchain-runtime-" + suffix,
		AggregateIndex:         "qwq-alertchain-hourly-" + suffix,
		Timeout:                30 * time.Second,
	}
	store, err := telemetrypersistence.NewElasticsearchEventLogStore(config)
	if err != nil {
		t.Fatalf("NewElasticsearchEventLogStore() error = %v", err)
	}
	if err := store.EnsureIndices(ctx); err != nil {
		t.Fatalf("EnsureIndices() error = %v", err)
	}
	t.Cleanup(func() {
		for _, indexBase := range []string{
			config.RawIndex,
			config.StartupDiagnosticIndex,
			config.RuntimeLogIndex,
			config.AggregateIndex,
		} {
			for _, resource := range []string{
				"/" + indexBase + "-*",
				"/_index_template/" + indexBase + "-template",
			} {
				request, _ := http.NewRequest(
					http.MethodDelete,
					elasticsearchEndpoint+resource,
					nil,
				)
				response, requestErr := http.DefaultClient.Do(request)
				if requestErr == nil {
					_ = response.Body.Close()
				}
			}
		}
	})

	// 同一错误指纹 12 次：runtime_diagnostics 聚合行 count 超过
	// runtime-diagnostics-error-fingerprint-spike 的阈值（>= 10）。
	now := time.Now().UTC().Add(-2 * time.Minute)
	const hotFingerprint = "fp-alertchain-hot"
	records := make([]application.RuntimeLogRecord, 0, 12)
	batchKey := strings.Repeat("e", 64)
	for index := 0; index < 12; index++ {
		records = append(records, application.RuntimeLogRecord{
			Fields: map[string]string{
				"schema":             "observability.slim",
				"occurredAt":         now.Add(time.Duration(index) * time.Second).Format(time.RFC3339Nano),
				"observedAt":         now.Add(time.Duration(index+1) * time.Second).Format(time.RFC3339Nano),
				"logKind":            "error",
				"severity":           "error",
				"signal":             "app.runtime_exception",
				"message":            "alert chain drill failure",
				"fingerprint":        hotFingerprint,
				"resourceSourceType": "app",
				"resourceService":    "quwoquan_app",
				"resourceAppVersion": "1.0.0",
			},
			BatchKey:   batchKey,
			BatchIndex: index,
			IngestedAt: now.Add(time.Duration(index+20) * time.Second),
		})
	}
	if err := store.PutRuntimeLogBatch(ctx, batchKey, records); err != nil {
		t.Fatalf("PutRuntimeLogBatch() error = %v", err)
	}
	refreshTelemetryIndices(t, ctx, elasticsearchEndpoint)

	policy := loadProductionAlertPolicy(t)
	notifier, err := alerting.NewAlertmanagerClient(alertmanagerEndpoint, 10*time.Second)
	if err != nil {
		t.Fatalf("NewAlertmanagerClient() error = %v", err)
	}
	loop, err := application.NewAlertEvaluationLoop(
		policy, store, notifier, store, time.Minute,
	)
	if err != nil {
		t.Fatalf("NewAlertEvaluationLoop() error = %v", err)
	}
	firing, err := loop.RunOnce(ctx)
	if err != nil {
		t.Fatalf("RunOnce() error = %v", err)
	}
	spikeSeen := false
	for _, hit := range firing {
		switch hit.Rule.Name {
		case "runtime-diagnostics-error-fingerprint-spike":
			spikeSeen = true
			if hit.GroupLabels["fingerprint"] != hotFingerprint {
				t.Fatalf("spike group labels = %v", hit.GroupLabels)
			}
		case "product-telemetry-transform-failed",
			"product-telemetry-aggregate-stale",
			"product-telemetry-raw-retention-drift",
			"runtime-diagnostics-raw-retention-drift":
			// 健康环境（新鲜数据 + 契约 ILM）不得误报 control_plane 告警。
			t.Fatalf("healthy chain must not fire %s", hit.Rule.Name)
		}
	}
	if !spikeSeen {
		names := make([]string, 0, len(firing))
		for _, hit := range firing {
			names = append(names, hit.Rule.Name)
		}
		t.Fatalf("fingerprint spike must fire; got %v", names)
	}

	// Alertmanager v2 必须真实收到该告警并保留分组标签与派生字段注解。
	deadline := time.Now().Add(30 * time.Second)
	for {
		alerts := listAlertmanagerAlerts(t, ctx, alertmanagerEndpoint)
		if alert := findAlertmanagerAlert(
			alerts, "runtime-diagnostics-error-fingerprint-spike",
		); alert != nil {
			labels := alert["labels"].(map[string]any)
			if labels["fingerprint"] != hotFingerprint ||
				labels["source"] != "product-ops-es-evaluator" ||
				labels["severity"] != "warning" {
				t.Fatalf("Alertmanager alert labels = %v", labels)
			}
			annotations := alert["annotations"].(map[string]any)
			if annotations["condition"] != "count >= 10" ||
				annotations["field_count"] != "12" {
				t.Fatalf("Alertmanager alert annotations = %v", annotations)
			}
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf(
				"Alertmanager never exposed the fingerprint spike; got %v",
				alerts,
			)
		}
		time.Sleep(time.Second)
	}
}

func loadProductionAlertPolicy(t *testing.T) application.AlertPolicy {
	t.Helper()
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	repoRoot := filepath.Join(
		filepath.Dir(currentFile), "..", "..", "..", "..", "..", "..", "..",
	)
	raw, err := os.ReadFile(filepath.Join(
		repoRoot,
		"quwoquan_ops", "observability", "elasticsearch",
		"product_telemetry_alerts.yaml",
	))
	if err != nil {
		t.Fatalf("read production alert policy: %v", err)
	}
	policy, err := application.ParseAlertPolicy(raw)
	if err != nil {
		t.Fatalf("ParseAlertPolicy() error = %v", err)
	}
	return policy
}

func refreshTelemetryIndices(t *testing.T, ctx context.Context, endpoint string) {
	t.Helper()
	request, err := http.NewRequestWithContext(
		ctx, http.MethodPost, endpoint+"/_refresh", nil,
	)
	if err != nil {
		t.Fatalf("build Elasticsearch refresh request: %v", err)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("refresh Elasticsearch indices: %v", err)
	}
	_ = response.Body.Close()
}

func listAlertmanagerAlerts(
	t *testing.T,
	ctx context.Context,
	endpoint string,
) []map[string]any {
	t.Helper()
	request, err := http.NewRequestWithContext(
		ctx, http.MethodGet, endpoint+"/api/v2/alerts", nil,
	)
	if err != nil {
		t.Fatalf("build Alertmanager list request: %v", err)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("list Alertmanager alerts: %v", err)
	}
	defer func() { _ = response.Body.Close() }()
	var alerts []map[string]any
	if err := json.NewDecoder(response.Body).Decode(&alerts); err != nil {
		t.Fatalf("decode Alertmanager alerts: %v", err)
	}
	return alerts
}

func findAlertmanagerAlert(
	alerts []map[string]any,
	alertname string,
) map[string]any {
	for _, alert := range alerts {
		labels, ok := alert["labels"].(map[string]any)
		if ok && labels["alertname"] == alertname {
			return alert
		}
	}
	return nil
}
