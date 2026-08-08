// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002
// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/spec.md#sit-001
// readiness_case: get-runtime-log-summary-local
// readiness_case: get-runtime-log-drilldown-local
// readiness_case: report-runtime-log-batch-local
// readiness_case: get-event-summary-local
// readiness_case: get-event-drilldown-local
// readiness_case: get-rtc-media-qoe-summary-local
// readiness_case: list-l1-l4-metric-snapshots-local
// readiness_case: get-service-route-red-local
// readiness_case: get-growth-overview-local
// readiness_case: get-page-experience-local
// readiness_case: list-product-workflows-local
// readiness_case: list-product-audits-local
// readiness_case: list-product-approvals-local
// readiness_case: get-product-projection-summary-local
// readiness_case: get-product-triage-summary-local
package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	controlplanetest "quwoquan_service/runtime/controlplane/testsupport"
	"quwoquan_service/runtime/operation"
	eventhttp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/adapters/inbound/http"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	eventpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
	visitapp "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/application"
)

func TestEventRecordOperationFacadesExecuteAllCanonicalQueriesAndCommands(t *testing.T) {
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Second)
	telemetryStore := eventpersistence.NewMemoryTelemetryStore()
	telemetry := eventapp.NewTelemetryServiceWithStoresAndRtcMediaQoeReader(
		telemetryStore, telemetryStore, telemetryStore,
	)
	runtimeLogs := eventapp.NewRuntimeLogService(telemetryStore, telemetryStore)
	runtimeAck, err := runtimeLogs.ReportRuntimeLogBatch(
		ctx,
		strings.Repeat("a", 64),
		[]map[string]any{canonicalRuntimeOperationRecord(now)},
	)
	if err != nil || runtimeAck.AcceptedCount != 1 || runtimeAck.DuplicateBatch {
		t.Fatalf("ReportRuntimeLogBatch ack=%+v err=%v", runtimeAck, err)
	}
	runtimeSummary, err := runtimeLogs.GetRuntimeLogSummary(ctx, eventapp.RuntimeLogSummaryQuery{
		From: now.Add(-time.Minute), To: now.Add(time.Minute),
	})
	if err != nil || runtimeSummary.TotalCount != 1 {
		t.Fatalf("GetRuntimeLogSummary summary=%+v err=%v", runtimeSummary, err)
	}
	runtimeDrilldown, err := runtimeLogs.GetRuntimeLogDrilldown(ctx, eventapp.RuntimeLogDrilldownQuery{
		From: now.Add(-time.Minute), To: now.Add(time.Minute), Limit: 10,
	})
	if err != nil || runtimeDrilldown.TotalCount != 1 || len(runtimeDrilldown.Items) != 1 {
		t.Fatalf("GetRuntimeLogDrilldown drilldown=%+v err=%v", runtimeDrilldown, err)
	}

	eventSummary, err := telemetry.GetEventSummary(ctx, eventapp.EventSummaryQuery{})
	if err != nil || eventSummary.SourceKind == "" {
		t.Fatalf("GetEventSummary summary=%+v err=%v", eventSummary, err)
	}
	eventDrilldown, err := telemetry.GetEventDrilldown(ctx, eventapp.EventDrilldownQuery{
		From: now.Add(-time.Minute), To: now.Add(time.Minute), Limit: 10,
	})
	if err != nil || eventDrilldown.SourceKind == "" {
		t.Fatalf("GetEventDrilldown drilldown=%+v err=%v", eventDrilldown, err)
	}
	rtcSummary, err := telemetry.GetRtcMediaQoeSummary(ctx)
	if err != nil || rtcSummary.WindowHours != 24 {
		t.Fatalf("GetRtcMediaQoeSummary summary=%+v err=%v", rtcSummary, err)
	}

	prometheus := fixedPrometheusReader{}
	metrics := eventapp.NewMetricQueryService(telemetry, prometheus)
	l1l4, err := metrics.ListL1L4MetricSnapshots(ctx, eventapp.L1L4MetricsScope{
		Environment: "alpha", Service: "product-ops-service",
	})
	if err != nil {
		t.Fatalf("ListL1L4MetricSnapshots err=%v payload=%+v", err, l1l4)
	}
	red, err := metrics.GetServiceRouteRED(ctx, "product-ops-service")
	if err != nil || len(red.Items) != 1 || red.Items[0].Route != "/ops/events" {
		t.Fatalf("GetServiceRouteRED response=%+v err=%v", red, err)
	}

	growthStore := eventpersistence.NewMemoryGrowthStore()
	growth := eventapp.NewGrowthService(growthStore, telemetryStore)
	overview, err := growth.Overview(ctx, 7)
	if err != nil || overview.Source != "user_activity_daily" || len(overview.Days) != 7 {
		t.Fatalf("GetGrowthOverview overview=%+v err=%v", overview, err)
	}
	pageExperience, err := telemetry.GetPageExperience(ctx, eventapp.PageExperienceQuery{
		From: now.Add(-time.Minute), To: now.Add(time.Minute),
	})
	if err != nil || pageExperience == nil {
		t.Fatalf("GetPageExperience items=%+v err=%v", pageExperience, err)
	}

	controlStore := controlplanetest.NewFileStore(t.TempDir() + "/state.json")
	visits := visitapp.NewService(fixedVisitStore{})
	controlQueries := eventapp.NewControlPlaneQueryService(controlStore, telemetry, visits)
	workflows, err := controlQueries.ListProductWorkflows()
	if err != nil || len(workflows) != 0 {
		t.Fatalf("ListProductWorkflows items=%+v err=%v", workflows, err)
	}
	audits, err := controlQueries.ListProductAudits()
	if err != nil || len(audits) != 0 {
		t.Fatalf("ListProductAudits items=%+v err=%v", audits, err)
	}
	approvals, err := controlQueries.ListProductApprovals()
	if err != nil || len(approvals) != 0 {
		t.Fatalf("ListProductApprovals items=%+v err=%v", approvals, err)
	}
	projection, err := controlQueries.GetProductProjectionSummary()
	if err != nil || len(projection.L1L4Cards) != 4 {
		t.Fatalf("GetProductProjectionSummary summary=%+v err=%v", projection, err)
	}
	triage, err := controlQueries.GetProductTriageSummary(ctx, eventapp.ProductTriageQuery{})
	if err != nil || triage.Source != "control-plane" {
		t.Fatalf("GetProductTriageSummary summary=%+v err=%v", triage, err)
	}
}

func TestEventRecordRuntimeBoundaryUsesCanonicalErrorOwners(t *testing.T) {
	store := eventpersistence.NewMemoryTelemetryStore()
	handler := eventhttp.NewOperationsHandler(eventhttp.OperationsDependencies{
		Telemetry:       new(eventapp.TelemetryService),
		RuntimeLogs:     new(eventapp.RuntimeLogService),
		RuntimeLogStore: store,
		Growth:          new(eventapp.GrowthService),
		Metrics:         new(eventapp.MetricQueryService),
		ControlPlane:    new(eventapp.ControlPlaneQueryService),
	})
	mux := http.NewServeMux()
	handler.Register(mux)

	wrongMethod := httptest.NewRequest(http.MethodDelete, "/ops/runtime-logs", nil)
	wrongMethodResponse := httptest.NewRecorder()
	mux.ServeHTTP(wrongMethodResponse, wrongMethod)
	if wrongMethodResponse.Code != http.StatusNotFound ||
		!strings.Contains(
			wrongMethodResponse.Body.String(),
			`"code":"GATEWAY.USER.route_not_found"`,
		) {
		t.Fatalf(
			"wrong method status=%d body=%s",
			wrongMethodResponse.Code,
			wrongMethodResponse.Body.String(),
		)
	}

	invalidBody := httptest.NewRequest(
		http.MethodPost,
		"/ops/runtime-logs",
		strings.NewReader("{"),
	)
	invalidBody = invalidBody.WithContext(rtauth.WithPrincipal(
		invalidBody.Context(),
		rtauth.Principal{Actor: operation.ActorContext{PersonaID: "persona-error-owner"}},
	))
	invalidBodyResponse := httptest.NewRecorder()
	mux.ServeHTTP(invalidBodyResponse, invalidBody)
	if invalidBodyResponse.Code != http.StatusUnprocessableEntity ||
		!strings.Contains(
			invalidBodyResponse.Body.String(),
			`"code":"OPS.USER.runtime_log_batch_invalid"`,
		) {
		t.Fatalf(
			"invalid body status=%d body=%s",
			invalidBodyResponse.Code,
			invalidBodyResponse.Body.String(),
		)
	}
}

func canonicalRuntimeOperationRecord(now time.Time) map[string]any {
	return map[string]any{
		"schema": "observability.slim", "recordId": "r.event-record.operations.1",
		"occurredAt": now.Format(time.RFC3339Nano), "observedAt": now.Format(time.RFC3339Nano),
		"logKind": "exception", "severity": "ERROR", "signal": "app.exception.flutter",
		"message":    "redacted exception",
		"resource":   map[string]any{"sourceType": "app", "service": "quwoquan_app", "appVersion": "1.0.0"},
		"errorCode":  "APP.RUNTIME.uncaught_exception",
		"attributes": map[string]any{"source": "flutter", "exceptionType": "StateError"},
	}
}

type fixedPrometheusReader struct{}

func (fixedPrometheusReader) Query(context.Context, string) (float64, error) { return 99, nil }

func (fixedPrometheusReader) QueryVector(context.Context, string) ([]eventapp.PrometheusVectorSample, error) {
	return []eventapp.PrometheusVectorSample{{
		Labels: map[string]string{"route": "/ops/events"}, Value: 1,
	}}, nil
}

type fixedVisitStore struct{}

func (fixedVisitStore) CommitVisit(context.Context, visitapp.CommitCommand) (visitapp.RecordVisitReceipt, error) {
	return visitapp.RecordVisitReceipt{}, nil
}

func (fixedVisitStore) GetVisitStats(context.Context, visitapp.VisitStatsQuery) (visitapp.VisitStats, error) {
	return visitapp.VisitStats{Items: []visitapp.VisitRecord{}}, nil
}

var _ controlplane.StateStore = (*controlplanetest.FileStore)(nil)
