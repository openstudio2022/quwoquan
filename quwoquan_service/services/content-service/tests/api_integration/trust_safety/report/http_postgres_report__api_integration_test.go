package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/operation"
	reporthttp "quwoquan_service/services/content-service/internal/trust_safety/report/adapters/inbound/http"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportpersistence "quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/persistence"
)

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
func TestReportHTTPRealPostgresAtomicAggregateReceiptAndOutbox(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	fixture, err := testinfra.StartPostgresFixture(t.TempDir()+"/postgres", 0)
	if err != nil {
		t.Fatalf("start embedded PostgreSQL: %v", err)
	}
	t.Cleanup(func() { _ = fixture.Close() })
	store, err := reportpersistence.NewPGReportStore(fixture.DB)
	if err != nil {
		t.Fatalf("initialize Report store: %v", err)
	}
	handler := reporthttp.NewHandler(reportapp.BindFacades(
		reportapp.NewReportService(reportapp.BindDataPorts(store)),
	))

	request := httptest.NewRequest(
		http.MethodPost,
		"/content/reports",
		strings.NewReader(`{"targetType":"post","targetId":"post-report-1","reason":"spam"}`),
	)
	request.Header.Set("Idempotency-Key", "report-http-postgres-1")
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID:    "content.report.create",
		RequestID:      "request-report-1",
		TraceID:        "trace-report-1",
		IdempotencyKey: "report-http-postgres-1",
		Actor: operation.ActorContext{
			AccountID: "account-reporter-1",
			PersonaID: "persona-reporter-1",
		},
	}))
	response := httptest.NewRecorder()
	handler.Create(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}

	counts := map[string]int{}
	for name, query := range map[string]string{
		"aggregate": `SELECT COUNT(*) FROM reports WHERE target_id='post-report-1'`,
		"receipt":   `SELECT COUNT(*) FROM report_command_receipts WHERE idempotency_key='report-http-postgres-1'`,
		"outbox":    `SELECT COUNT(*) FROM report_outbox WHERE event_type='content.report.created'`,
	} {
		var count int
		if err := fixture.DB.QueryRowContext(ctx, query).Scan(&count); err != nil {
			t.Fatalf("count %s: %v", name, err)
		}
		counts[name] = count
	}
	if counts["aggregate"] != 1 || counts["receipt"] != 1 || counts["outbox"] != 1 {
		t.Fatalf("non-atomic report packet: %#v", counts)
	}
}
