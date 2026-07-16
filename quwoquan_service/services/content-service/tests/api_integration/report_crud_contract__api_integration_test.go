package api_integration

import (
	"context"
	"database/sql"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	contenhttp "quwoquan_service/services/content-service/internal/adapters/http"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	contentmessaging "quwoquan_service/services/content-service/internal/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

func TestCreateReportPersistsPendingAggregateAndOutbox(t *testing.T) {
	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	reportRepo, handler := newReportTestHandler(t, suite.PG)

	createReq := httptest.NewRequest(http.MethodPost, "/v1/content/reports", strings.NewReader(`{
	  "targetType":"post",
	  "targetId":"post_123",
	  "reason":"spam",
	  "description":"重复营销内容"
	}`))
	createReq.Header.Set("Content-Type", "application/json")
	createReq.Header.Set("Idempotency-Key", "create-report-post-123")
	createReq = withReportActor(createReq, "persona-reporter")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d: %s", createRec.Code, createRec.Body.String())
	}
	if got := createRec.Body.Len(); got != 0 {
		t.Fatalf("expected empty create response body, got %q", createRec.Body.String())
	}
	var reportID string
	if err := suite.PG.QueryRow(
		`SELECT id FROM reports WHERE reporter_id = $1 AND target_type = $2 AND target_id = $3`,
		"persona-reporter",
		"post",
		"post_123",
	).Scan(&reportID); err != nil {
		t.Fatalf("query created report ID: %v", err)
	}

	report, ok, err := reportRepo.FindByID(context.Background(), reportID)
	if err != nil {
		t.Fatalf("query created report: %v", err)
	}
	if !ok {
		t.Fatalf("report not found after create")
	}
	if report.Status != reportmodel.StatusPending {
		t.Fatalf("expected pending, got %s", report.Status)
	}
	assertReportOutboxCount(t, suite.PG, "content.report.created", 1)

	dispatched := testinfra.NewEventSpy()
	relay := reportapp.NewOutboxRelay(
		reportRepo,
		reportRepo,
		contentmessaging.NewReportOutboxPublisher(dispatched),
		"api-integration-report-events",
	)
	if count, err := relay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("dispatch committed Report outbox: %v", err)
	} else if count != 1 {
		t.Fatalf("dispatched Report events=%d want=1", count)
	}
	events := dispatched.EventsOfType("content.report.created")
	if len(events) != 1 || events[0].EventID == "" || events[0].AggregateID != reportID {
		t.Fatalf("stable Report fact not dispatched: %+v", events)
	}
	if count, err := relay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("replay Report outbox: %v", err)
	} else if count != 0 || len(dispatched.EventsOfType("content.report.created")) != 1 {
		t.Fatalf("Report checkpoint replay duplicated delivery: count=%d events=%d", count, len(dispatched.EventsOfType("content.report.created")))
	}
}

func TestCreateReportRejectsForgedIdentityHeadersWithoutPersistence(t *testing.T) {
	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	_, handler := newReportTestHandler(t, suite.PG)
	protected := newAuthenticatedReportHandler(t, handler)
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/reports",
		strings.NewReader(`{
		  "targetType":"post",
		  "targetId":"post_unauthorized",
		  "reason":"spam"
		}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "forged-report-identity")
	request.Header.Set("X-Client-User-Id", "forged-account")
	request.Header.Set("X-Client-Account-Id", "forged-account")
	request.Header.Set("X-Client-Sub-Account-Id", "forged-persona")
	request.Header.Set("X-Client-Persona-Id", "forged-persona")

	response := httptest.NewRecorder()
	protected.ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf(
			"forged identity request status=%d want=%d body=%s",
			response.Code,
			http.StatusUnauthorized,
			response.Body.String(),
		)
	}
	var reportCount, outboxCount int
	if err := suite.PG.QueryRow("SELECT COUNT(*) FROM reports").Scan(&reportCount); err != nil {
		t.Fatalf("count reports: %v", err)
	}
	if err := suite.PG.QueryRow("SELECT COUNT(*) FROM report_outbox").Scan(&outboxCount); err != nil {
		t.Fatalf("count report outbox: %v", err)
	}
	if reportCount != 0 || outboxCount != 0 {
		t.Fatalf(
			"forged identity produced report side effects reports=%d outbox=%d",
			reportCount,
			outboxCount,
		)
	}
}

func TestCreateReportPersistsVerifiedPersonaInsteadOfClientHeaders(t *testing.T) {
	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	_, handler := newReportTestHandler(t, suite.PG)
	protected := newAuthenticatedReportHandler(t, handler)
	const trustedPersonaID = "us_01_0c9a_01kxegteth3ed7apy3ev1tqfnx"
	token := newReportAccessToken(
		t,
		rtauth.TokenSubject{
			AccountID: "trusted-account",
			PersonaID: trustedPersonaID,
		},
	)
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/reports",
		strings.NewReader(`{
		  "targetType":"post",
		  "targetId":"post_trusted_actor",
		  "reason":"spam"
		}`),
	)
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "trusted-persona-report")
	request.Header.Set("X-Client-User-Id", "forged-account")
	request.Header.Set("X-Client-Persona-Id", "forged-persona")

	response := httptest.NewRecorder()
	protected.ServeHTTP(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf(
			"trusted report status=%d want=%d body=%s",
			response.Code,
			http.StatusNoContent,
			response.Body.String(),
		)
	}
	var reporterID string
	if err := suite.PG.QueryRow(
		`SELECT reporter_id FROM reports WHERE target_id = $1`,
		"post_trusted_actor",
	).Scan(&reporterID); err != nil {
		t.Fatalf("query trusted report: %v", err)
	}
	if reporterID != trustedPersonaID {
		t.Fatalf("reporter id=%q want %q", reporterID, trustedPersonaID)
	}
}

func TestCreateReportIdempotencyReplaysWithoutDuplicatePersistence(t *testing.T) {
	suite := testinfra.NewSuite(t, testinfra.WithPostgres())
	defer suite.TearDown(t)
	suite.CleanPG(t)

	_, handler := newReportTestHandler(t, suite.PG)
	protected := newAuthenticatedReportHandler(t, handler)
	token := newReportAccessToken(
		t,
		rtauth.TokenSubject{
			AccountID: "replay-account",
			PersonaID: "replay-persona",
		},
	)
	for attempt := 0; attempt < 2; attempt++ {
		request := httptest.NewRequest(
			http.MethodPost,
			"/v1/content/reports",
			strings.NewReader(`{
			  "targetType":"post",
			  "targetId":"post_idempotency_replay",
			  "reason":"spam"
			}`),
		)
		request.Header.Set("Authorization", "Bearer "+token)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("Idempotency-Key", "report-replay-key")
		response := httptest.NewRecorder()
		protected.ServeHTTP(response, request)
		if response.Code != http.StatusNoContent {
			t.Fatalf(
				"attempt=%d status=%d want=%d body=%s",
				attempt,
				response.Code,
				http.StatusNoContent,
				response.Body.String(),
			)
		}
	}
	var reportCount, outboxCount int
	if err := suite.PG.QueryRow(
		`SELECT COUNT(*) FROM reports WHERE target_id = $1`,
		"post_idempotency_replay",
	).Scan(&reportCount); err != nil {
		t.Fatalf("count replayed reports: %v", err)
	}
	if err := suite.PG.QueryRow(
		`SELECT COUNT(*) FROM report_outbox WHERE event_type = $1`,
		"content.report.created",
	).Scan(&outboxCount); err != nil {
		t.Fatalf("count replayed report outbox: %v", err)
	}
	if reportCount != 1 || outboxCount != 1 {
		t.Fatalf(
			"idempotent create persisted reports=%d outbox=%d want one each",
			reportCount,
			outboxCount,
		)
	}
}

func newReportTestHandler(
	t *testing.T,
	db *sql.DB,
) (*persistence.PGReportStore, http.Handler) {
	t.Helper()
	reportRepo, err := persistence.NewPGReportStore(db)
	if err != nil {
		t.Fatalf("init pg report store: %v", err)
	}
	reportService := reportapp.NewReportService(
		reportapp.BindDataPorts(reportRepo),
	)
	handler := contenhttp.NewContentHandler(
		nil,
		nil,
		nil,
		nil,
		nil,
		reportapp.BindFacades(reportService),
		nil,
	).Routes()
	return reportRepo, handler
}

func newAuthenticatedReportHandler(
	t *testing.T,
	next http.Handler,
) http.Handler {
	t.Helper()
	verifier, err := rtauth.NewHS256Verifier(reportAccessTokenConfig())
	if err != nil {
		t.Fatalf("build access verifier: %v", err)
	}
	return rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: verifier,
	})(
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("content"),
		)(next),
	)
}

func newReportAccessToken(t *testing.T, subject rtauth.TokenSubject) string {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(reportAccessTokenConfig())
	if err != nil {
		t.Fatalf("build access signer: %v", err)
	}
	token, err := signer.Sign(subject)
	if err != nil {
		t.Fatalf("sign access token: %v", err)
	}
	return token
}

func reportAccessTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "https://auth.quwoquan.test",
		Audience:     "quwoquan-api",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          30 * time.Minute,
		ClockSkew:    30 * time.Second,
	}
}

func withReportActor(
	request *http.Request,
	personaID string,
) *http.Request {
	current := rtoperation.Context{
		OperationID: "content.report.test",
		RequestID:   "request-" + personaID,
		TraceID:     "trace-" + personaID,
		Actor: rtoperation.ActorContext{
			AccountID: "account-" + personaID,
			PersonaID: personaID,
		},
	}
	return request.WithContext(
		rtoperation.WithContext(request.Context(), current),
	)
}

func assertReportOutboxCount(
	t *testing.T,
	db *sql.DB,
	eventType string,
	want int,
) {
	t.Helper()
	var count int
	if err := db.QueryRow(
		"SELECT COUNT(*) FROM report_outbox WHERE event_type = $1",
		eventType,
	).Scan(&count); err != nil {
		t.Fatalf("query report outbox: %v", err)
	}
	if count != want {
		t.Fatalf("event %s count=%d want=%d", eventType, count, want)
	}
}
