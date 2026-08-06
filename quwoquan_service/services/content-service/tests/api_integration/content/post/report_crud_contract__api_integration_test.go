package api_integration

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	rtoperation "quwoquan_service/runtime/operation"
	contenhttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	reporthttp "quwoquan_service/services/content-service/internal/trust_safety/report/adapters/inbound/http"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
	reportmessaging "quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/messaging"
	reportpersistence "quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/persistence"
)

func TestCreateReportPersistsPendingAggregateAndOutbox(t *testing.T) {
	suite := newReportPostgresSuite(t)
	defer suite.TearDown(t)
	suite.CleanPG(t)

	reportRepo, handler := newReportTestHandler(t, suite.PG)

	createReq := httptest.NewRequest(http.MethodPost, "/content/reports", strings.NewReader(`{
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
	var reporterAccountID string
	if err := suite.PG.QueryRow(
		`SELECT id, reporter_account_id FROM reports WHERE reporter_id = $1 AND target_type = $2 AND target_id = $3`,
		"persona-reporter",
		"post",
		"post_123",
	).Scan(&reportID, &reporterAccountID); err != nil {
		t.Fatalf("query created report ID: %v", err)
	}
	if reporterAccountID != "account-persona-reporter" {
		t.Fatalf("reporter account=%q want trusted account", reporterAccountID)
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
	assertReportOutboxCount(t, suite.PG, "content.report.ReportCreated", 1)

	dispatched := testinfra.NewEventSpy()
	relay := reportapp.NewOutboxRelay(
		reportRepo,
		reportRepo,
		reportmessaging.NewReportOutboxPublisher(dispatched),
		"api-integration-report-events",
	)
	if count, err := relay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("dispatch committed Report outbox: %v", err)
	} else if count != 1 {
		t.Fatalf("dispatched Report events=%d want=1", count)
	}
	events := dispatched.EventsOfType("content.report.ReportCreated")
	if len(events) != 1 || events[0].EventID == "" || events[0].AggregateID != reportID {
		t.Fatalf("stable Report fact not dispatched: %+v", events)
	}
	if got, _ := events[0].Payload["reporterAccountId"].(string); got != reporterAccountID {
		t.Fatalf(
			"published report fact account=%q want persisted trusted account %q",
			got,
			reporterAccountID,
		)
	}
	if count, err := relay.Drain(context.Background(), 100); err != nil {
		t.Fatalf("replay Report outbox: %v", err)
	} else if count != 0 || len(dispatched.EventsOfType("content.report.ReportCreated")) != 1 {
		t.Fatalf("Report checkpoint replay duplicated delivery: count=%d events=%d", count, len(dispatched.EventsOfType("content.report.ReportCreated")))
	}
}

func TestReportStoreRejectsNonCanonicalReporterAccountOwnership(t *testing.T) {
	suite := newReportPostgresSuite(t)
	defer suite.TearDown(t)
	suite.CleanPG(t)

	if _, err := reportpersistence.NewPGReportStore(suite.PG); err != nil {
		t.Fatalf("initialize report schema: %v", err)
	}
	if _, err := suite.PG.Exec(
		`ALTER TABLE reports ALTER COLUMN reporter_account_id DROP NOT NULL`,
	); err != nil {
		t.Fatalf("prepare invalid account ownership row: %v", err)
	}
	now := time.Now().UTC()
	if _, err := suite.PG.Exec(`
INSERT INTO reports (
  id, version, reporter_id, reporter_account_id, target_type, target_id,
  reason, description, status, created_at, updated_at
) VALUES ($1, 1, $2, NULL, 'post', 'invalid-target', 'spam',
  'invalid report ownership', 'pending', $3, $3)`,
		"invalid-report-1",
		"invalid-persona",
		now,
	); err != nil {
		t.Fatalf("insert invalid report: %v", err)
	}
	if _, err := suite.PG.Exec(`
INSERT INTO report_outbox (
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1, $2, 1, 'content.report.ReportCreated', $3::jsonb, $4)`,
		"invalid-report-event-1",
		"invalid-report-1",
		`{"reportId":"invalid-report-1","reporterId":"invalid-persona"}`,
		now,
	); err != nil {
		t.Fatalf("insert invalid report outbox: %v", err)
	}
	if _, err := suite.PG.Exec(`
INSERT INTO report_command_receipts (
  idempotency_key, aggregate_id, aggregate_version, command_name, command_digest,
  result_json, created_at, expires_at
) VALUES ($1, $2, 1, 'CreateReport', 'invalid-digest', $3::jsonb, $4, $5)`,
		"invalid-report-receipt-1",
		"invalid-report-1",
		`{"id":"invalid-report-1","reporterId":"invalid-persona"}`,
		now,
		now.Add(time.Hour),
	); err != nil {
		t.Fatalf("insert invalid report receipt: %v", err)
	}

	if _, err := reportpersistence.NewPGReportStore(suite.PG); err == nil ||
		!strings.Contains(err.Error(), "must be canonical before startup") {
		t.Fatalf("invalid report ownership error=%v; want fail-closed canonical error", err)
	}

	var reporterAccountID sql.NullString
	if err := suite.PG.QueryRow(
		`SELECT reporter_account_id FROM reports WHERE id = $1`,
		"invalid-report-1",
	).Scan(&reporterAccountID); err != nil {
		t.Fatalf("read rejected report account: %v", err)
	}
	if reporterAccountID.Valid {
		t.Fatalf("rejected reporter account was mutated to %q", reporterAccountID.String)
	}
	var outboxAccountID sql.NullString
	if err := suite.PG.QueryRow(
		`SELECT payload_json ->> 'reporterAccountId' FROM report_outbox WHERE event_id = $1`,
		"invalid-report-event-1",
	).Scan(&outboxAccountID); err != nil {
		t.Fatalf("read rejected report outbox: %v", err)
	}
	if outboxAccountID.Valid {
		t.Fatalf("rejected outbox account was mutated to %q", outboxAccountID.String)
	}
	var receiptAccountID sql.NullString
	if err := suite.PG.QueryRow(
		`SELECT result_json ->> 'reporterAccountId' FROM report_command_receipts WHERE idempotency_key = $1`,
		"invalid-report-receipt-1",
	).Scan(&receiptAccountID); err != nil {
		t.Fatalf("read rejected report receipt: %v", err)
	}
	if receiptAccountID.Valid {
		t.Fatalf("rejected receipt account was mutated to %q", receiptAccountID.String)
	}
}

func TestCreateReportRejectsForgedIdentityHeadersWithoutPersistence(t *testing.T) {
	suite := newReportPostgresSuite(t)
	defer suite.TearDown(t)
	suite.CleanPG(t)

	_, handler := newReportTestHandler(t, suite.PG)
	protected := newAuthenticatedReportHandler(t, handler)
	request := httptest.NewRequest(
		http.MethodPost,
		"/content/reports",
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
	request.Header.Set("X-Client-Persona-Id", "forged-persona")
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
	suite := newReportPostgresSuite(t)
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
		"/content/reports",
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
	var reporterAccountID string
	if err := suite.PG.QueryRow(
		`SELECT reporter_id, reporter_account_id FROM reports WHERE target_id = $1`,
		"post_trusted_actor",
	).Scan(&reporterID, &reporterAccountID); err != nil {
		t.Fatalf("query trusted report: %v", err)
	}
	if reporterID != trustedPersonaID {
		t.Fatalf("reporter id=%q want %q", reporterID, trustedPersonaID)
	}
	if reporterAccountID != "trusted-account" {
		t.Fatalf("reporter account=%q want trusted-account", reporterAccountID)
	}
}

func TestCreateReportIdempotencyReplaysWithoutDuplicatePersistence(t *testing.T) {
	suite := newReportPostgresSuite(t)
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
			"/content/reports",
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
		"content.report.ReportCreated",
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

func TestListMyReportsReturnsOnlyVerifiedPersonaReports(t *testing.T) {
	suite := newReportPostgresSuite(t)
	defer suite.TearDown(t)
	suite.CleanPG(t)

	_, handler := newReportTestHandler(t, suite.PG)
	protected := newAuthenticatedReportHandler(t, handler)
	ownerToken := newReportAccessToken(
		t,
		rtauth.TokenSubject{AccountID: "owner-account", PersonaID: "owner-persona"},
	)
	otherToken := newReportAccessToken(
		t,
		rtauth.TokenSubject{AccountID: "other-account", PersonaID: "other-persona"},
	)
	create := func(token, key, targetID string) {
		t.Helper()
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/reports",
			strings.NewReader(`{"targetType":"post","targetId":"`+targetID+`","reason":"spam"}`),
		)
		request.Header.Set("Authorization", "Bearer "+token)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("Idempotency-Key", key)
		response := httptest.NewRecorder()
		protected.ServeHTTP(response, request)
		if response.Code != http.StatusNoContent {
			t.Fatalf("create %s status=%d body=%s", targetID, response.Code, response.Body.String())
		}
	}
	create(ownerToken, "owner-report-1", "owner-post-1")
	create(otherToken, "other-report", "other-post")
	create(ownerToken, "owner-report-2", "owner-post-2")

	list := func(path string) map[string]any {
		t.Helper()
		request := httptest.NewRequest(http.MethodGet, path, nil)
		request.Header.Set("Authorization", "Bearer "+ownerToken)
		response := httptest.NewRecorder()
		protected.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("list status=%d body=%s", response.Code, response.Body.String())
		}
		var payload map[string]any
		if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
			t.Fatalf("decode list response: %v", err)
		}
		return payload
	}
	first := list("/content/users/me/reports?limit=1")
	firstItems, ok := first["items"].([]any)
	if !ok || len(firstItems) != 1 {
		t.Fatalf("unexpected first page: %#v", first)
	}
	firstItem, ok := firstItems[0].(map[string]any)
	if !ok || firstItem["targetId"] == "other-post" {
		t.Fatalf("other reporter leaked: %#v", firstItem)
	}
	if _, leaked := firstItem["reviewerId"]; leaked {
		t.Fatalf("reviewerId leaked to reporter: %#v", firstItem)
	}
	if _, leaked := firstItem["resolution"]; leaked {
		t.Fatalf("internal resolution leaked to reporter: %#v", firstItem)
	}
	cursor, ok := first["nextCursor"].(string)
	if !ok || strings.TrimSpace(cursor) == "" {
		t.Fatalf("first page cursor missing: %#v", first)
	}
	second := list(
		"/content/users/me/reports?limit=1&cursor=" + url.QueryEscape(cursor),
	)
	secondItems, ok := second["items"].([]any)
	if !ok || len(secondItems) != 1 {
		t.Fatalf("unexpected second page: %#v", second)
	}
	secondItem := secondItems[0].(map[string]any)
	if secondItem["id"] == firstItem["id"] || secondItem["targetId"] == "other-post" {
		t.Fatalf("unstable private pagination: first=%#v second=%#v", firstItem, secondItem)
	}

	anonymous := httptest.NewRecorder()
	protected.ServeHTTP(
		anonymous,
		httptest.NewRequest(http.MethodGet, "/content/users/me/reports", nil),
	)
	if anonymous.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous status=%d want=%d", anonymous.Code, http.StatusUnauthorized)
	}
}

func newReportTestHandler(
	t *testing.T,
	db *sql.DB,
) (*reportpersistence.PGReportStore, http.Handler) {
	t.Helper()
	reportRepo, err := reportpersistence.NewPGReportStore(db)
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
		reporthttp.NewHandler(reportapp.BindFacades(reportService)),
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
