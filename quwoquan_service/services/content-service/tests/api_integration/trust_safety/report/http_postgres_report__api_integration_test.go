// readiness_case: create-report-api
// readiness_case: list-my-reports-api
// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/content-action-intent-contract/spec.md#gwt-001
// readiness_case: list-reports-api
// readiness_case: get-report-api
// readiness_case: begin-report-review-api
// readiness_case: dismiss-report-api
// readiness_case: resolve-report-api
// readiness_case: grant-gathering-safety-termination-api
// readiness_case: revoke-gathering-safety-termination-api
// readiness_case: authorize-gathering-safety-termination-api
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	posthttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	reporthttp "quwoquan_service/services/content-service/internal/trust_safety/report/adapters/inbound/http"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportpersistence "quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/persistence"
)

func reportAPITokenConfig() rtauth.TokenConfig {
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

func authenticatedReportAPIRequest(
	t *testing.T,
	method string,
	target string,
	body string,
	subject rtauth.TokenSubject,
	idempotencyKey string,
) *http.Request {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(reportAPITokenConfig())
	if err != nil {
		t.Fatalf("build Report API signer: %v", err)
	}
	token, err := signer.Sign(subject)
	if err != nil {
		t.Fatalf("sign Report API token: %v", err)
	}
	request := httptest.NewRequest(method, target, bytes.NewBufferString(body))
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	return request
}

func newRealPostgresReportHTTPHandler(
	t *testing.T,
	store *reportpersistence.PGReportStore,
) http.Handler {
	t.Helper()
	base := posthttp.NewContentHandler(
		nil, nil, nil, nil, nil,
		reporthttp.NewHandler(reportapp.BindFacades(
			reportapp.NewReportService(reportapp.BindDataPorts(store)),
		)),
		nil,
	).Routes()
	verifier, err := rtauth.NewHS256Verifier(reportAPITokenConfig())
	if err != nil {
		t.Fatalf("build Report API verifier: %v", err)
	}
	return rtauth.Middleware(rtauth.MiddlewareConfig{AccessTokenVerifier: verifier})(
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("content"),
		)(base),
	)
}

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

	performCreate := func(requestID string) *httptest.ResponseRecorder {
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/reports",
			strings.NewReader(`{"targetType":"post","targetId":"post-report-1","reason":"spam"}`),
		)
		request.Header.Set("Idempotency-Key", "report-http-postgres-1")
		request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
			OperationID:    "content.report.CreateReport",
			RequestID:      requestID,
			TraceID:        "trace-report-1",
			IdempotencyKey: "report-http-postgres-1",
			Actor: operation.ActorContext{
				AccountID: "account-reporter-1",
				PersonaID: "persona-reporter-1",
			},
		}))
		response := httptest.NewRecorder()
		handler.Create(response, request)
		return response
	}
	first := performCreate("request-report-1")
	if first.Code != http.StatusOK {
		t.Fatalf("first status=%d body=%s", first.Code, first.Body.String())
	}
	var firstResult reportapp.ReportCommandResult
	if err := json.Unmarshal(first.Body.Bytes(), &firstResult); err != nil {
		t.Fatalf("decode first report result: %v", err)
	}
	if firstResult.ID == "" || firstResult.Version != 1 || firstResult.Status != "pending" || firstResult.Replayed {
		t.Fatalf("first report result=%+v", firstResult)
	}
	replay := performCreate("request-report-2")
	if replay.Code != http.StatusOK {
		t.Fatalf("replay status=%d body=%s", replay.Code, replay.Body.String())
	}
	var replayResult reportapp.ReportCommandResult
	if err := json.Unmarshal(replay.Body.Bytes(), &replayResult); err != nil {
		t.Fatalf("decode replay report result: %v", err)
	}
	if replayResult.ID != firstResult.ID || replayResult.Version != firstResult.Version ||
		replayResult.Status != firstResult.Status || !replayResult.Replayed {
		t.Fatalf("replay report result=%+v first=%+v", replayResult, firstResult)
	}

	counts := map[string]int{}
	for name, query := range map[string]string{
		"aggregate": `SELECT COUNT(*) FROM reports WHERE target_id='post-report-1'`,
		"receipt":   `SELECT COUNT(*) FROM report_command_receipts WHERE idempotency_key='report-http-postgres-1'`,
		"outbox":    `SELECT COUNT(*) FROM report_outbox WHERE event_type='content.report.ReportCreated'`,
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

func TestReportHTTPRealPostgresQueryReviewResolveAndDismissLifecycle(t *testing.T) {
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
	handler := newRealPostgresReportHTTPHandler(t, store)
	reporter := rtauth.TokenSubject{
		AccountID: "report-api-account", PersonaID: "report-api-persona",
	}
	readOperator := rtauth.TokenSubject{
		AccountID: "report-api-operator", Roles: []string{"operator"},
		Scopes: []string{"ops.case.read"}, Permissions: []string{"content.report.read"},
	}
	writeOperator := rtauth.TokenSubject{
		AccountID: "report-api-operator", Roles: []string{"operator"},
		Scopes:      []string{"ops.case.write"},
		Permissions: []string{"content.report.review", "content.report.resolve"},
	}
	perform := func(request *http.Request) *httptest.ResponseRecorder {
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		return recorder
	}
	create := func(targetID, key string) reportapp.ReportCommandResult {
		response := perform(authenticatedReportAPIRequest(
			t, http.MethodPost, "/content/reports",
			`{"targetType":"post","targetId":"`+targetID+`","reason":"spam"}`,
			reporter, key,
		))
		if response.Code != http.StatusOK {
			t.Fatalf("CreateReport %s status=%d body=%s", targetID, response.Code, response.Body.String())
		}
		var result reportapp.ReportCommandResult
		if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		return result
	}

	first := create("post-report-lifecycle-1", "create-report-lifecycle-1")
	mine := perform(authenticatedReportAPIRequest(
		t, http.MethodGet, "/content/users/me/reports?limit=20", "", reporter, "",
	))
	if mine.Code != http.StatusOK || !strings.Contains(mine.Body.String(), first.ID) {
		t.Fatalf("ListMyReports status=%d body=%s", mine.Code, mine.Body.String())
	}
	queue := perform(authenticatedReportAPIRequest(
		t, http.MethodGet, "/content/reports?limit=20", "", readOperator, "",
	))
	if queue.Code != http.StatusOK || !strings.Contains(queue.Body.String(), first.ID) {
		t.Fatalf("ListReports status=%d body=%s", queue.Code, queue.Body.String())
	}
	detail := perform(authenticatedReportAPIRequest(
		t, http.MethodGet, "/content/reports/"+first.ID, "", readOperator, "",
	))
	if detail.Code != http.StatusOK || !strings.Contains(detail.Body.String(), first.ID) {
		t.Fatalf("GetReport status=%d body=%s", detail.Code, detail.Body.String())
	}
	begin := perform(authenticatedReportAPIRequest(
		t, http.MethodPost, "/content/reports/"+first.ID+"/review", "{}",
		writeOperator, "begin-report-lifecycle-1",
	))
	if begin.Code != http.StatusOK || !strings.Contains(begin.Body.String(), `"status":"reviewing"`) {
		t.Fatalf("BeginReportReview status=%d body=%s", begin.Code, begin.Body.String())
	}
	resolve := perform(authenticatedReportAPIRequest(
		t, http.MethodPatch, "/content/reports/"+first.ID,
		`{"resolution":"warn"}`, writeOperator, "resolve-report-lifecycle-1",
	))
	if resolve.Code != http.StatusOK || !strings.Contains(resolve.Body.String(), `"status":"resolved"`) {
		t.Fatalf("ResolveReport status=%d body=%s", resolve.Code, resolve.Body.String())
	}

	second := create("post-report-lifecycle-2", "create-report-lifecycle-2")
	secondBegin := perform(authenticatedReportAPIRequest(
		t, http.MethodPost, "/content/reports/"+second.ID+"/review", "{}",
		writeOperator, "begin-report-lifecycle-2",
	))
	if secondBegin.Code != http.StatusOK {
		t.Fatalf("begin second report status=%d body=%s", secondBegin.Code, secondBegin.Body.String())
	}
	dismiss := perform(authenticatedReportAPIRequest(
		t, http.MethodPost, "/content/reports/"+second.ID+":dismiss", "{}",
		writeOperator, "dismiss-report-lifecycle-2",
	))
	if dismiss.Code != http.StatusOK || !strings.Contains(dismiss.Body.String(), `"status":"dismissed"`) {
		t.Fatalf("DismissReport status=%d body=%s", dismiss.Code, dismiss.Body.String())
	}

	var resolvedCount, dismissedCount int
	if err := fixture.DB.QueryRowContext(ctx, `SELECT COUNT(*) FROM reports WHERE status='resolved'`).Scan(&resolvedCount); err != nil {
		t.Fatalf("count resolved reports: %v", err)
	}
	if err := fixture.DB.QueryRowContext(ctx, `SELECT COUNT(*) FROM reports WHERE status='dismissed'`).Scan(&dismissedCount); err != nil {
		t.Fatalf("count dismissed reports: %v", err)
	}
	if resolvedCount != 1 || dismissedCount != 1 {
		t.Fatalf("real PostgreSQL lifecycle counts resolved=%d dismissed=%d", resolvedCount, dismissedCount)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
func TestReportHTTPRealPostgresGatheringSafetyAuthorityLifecycle(t *testing.T) {
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
	handler := newRealPostgresReportHTTPHandler(t, store)
	perform := func(request *http.Request) *httptest.ResponseRecorder {
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		return recorder
	}
	reporter := rtauth.TokenSubject{
		AccountID: "report-safety-account", PersonaID: "report-safety-persona",
	}
	operator := rtauth.TokenSubject{
		AccountID: "report-safety-operator",
		Roles:     []string{"operator"},
		Scopes:    []string{"ops.case.write"},
		Permissions: []string{
			"content.report.review",
			"content.report.resolve",
			"content.report.gathering_safety_grant",
		},
	}
	service := rtauth.TokenSubject{
		AccountID: "service:circle-service",
		Roles:     []string{"service"},
		Scopes:    []string{"content.gathering.safety.authorize"},
	}
	createdResponse := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/content/reports",
		`{"targetType":"gathering","targetId":"gathering-1","reason":"violence"}`,
		reporter,
		"gathering-safety-create",
	))
	if createdResponse.Code != http.StatusOK {
		t.Fatalf(
			"CreateReport status=%d body=%s",
			createdResponse.Code,
			createdResponse.Body.String(),
		)
	}
	var created reportapp.ReportCommandResult
	if err := json.Unmarshal(createdResponse.Body.Bytes(), &created); err != nil {
		t.Fatal(err)
	}
	begin := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/content/reports/"+created.ID+"/review",
		"{}",
		operator,
		"gathering-safety-review",
	))
	if begin.Code != http.StatusOK {
		t.Fatalf("BeginReportReview status=%d body=%s", begin.Code, begin.Body.String())
	}
	resolvedResponse := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPatch,
		"/content/reports/"+created.ID,
		`{"resolution":"terminate_gathering"}`,
		operator,
		"gathering-safety-resolve",
	))
	if resolvedResponse.Code != http.StatusOK {
		t.Fatalf(
			"ResolveReport status=%d body=%s",
			resolvedResponse.Code,
			resolvedResponse.Body.String(),
		)
	}
	var resolved reportapp.ReportCommandResult
	if err := json.Unmarshal(resolvedResponse.Body.Bytes(), &resolved); err != nil {
		t.Fatal(err)
	}
	expiresAt := time.Now().UTC().Add(3 * time.Minute)
	grantBody, err := json.Marshal(map[string]any{
		"expectedReportVersion": resolved.Version,
		"actorPersonaId":        "persona-safety",
		"expiresAt":             expiresAt,
	})
	if err != nil {
		t.Fatal(err)
	}
	grantResponse := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/content/reports/"+created.ID+":grant-gathering-safety-termination",
		string(grantBody),
		operator,
		"gathering-safety-grant",
	))
	if grantResponse.Code != http.StatusOK {
		t.Fatalf(
			"GrantGatheringSafetyTermination status=%d body=%s",
			grantResponse.Code,
			grantResponse.Body.String(),
		)
	}
	var grant reportapp.GatheringSafetyTerminationGrantResult
	if err := json.Unmarshal(grantResponse.Body.Bytes(), &grant); err != nil {
		t.Fatal(err)
	}
	if grant.ActorPersonaID != "persona-safety" ||
		grant.GatheringID != "gathering-1" ||
		grant.Action != reportapp.GatheringSafetyActionTerminate ||
		grant.DecisionVersion != resolved.Version ||
		grant.DecisionDigest == "" ||
		grant.DecisionRef == "" {
		t.Fatalf("grant omitted canonical decision binding: %+v", grant)
	}
	grantReplayResponse := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/content/reports/"+created.ID+":grant-gathering-safety-termination",
		string(grantBody),
		operator,
		"gathering-safety-grant",
	))
	var grantReplay reportapp.GatheringSafetyTerminationGrantResult
	if grantReplayResponse.Code != http.StatusOK ||
		json.Unmarshal(grantReplayResponse.Body.Bytes(), &grantReplay) != nil ||
		!grantReplay.Replayed ||
		grantReplay.DecisionRef != grant.DecisionRef ||
		grantReplay.DecisionDigest != grant.DecisionDigest {
		t.Fatalf(
			"Gathering safety grant replay diverged: status=%d result=%+v body=%s",
			grantReplayResponse.Code,
			grantReplay,
			grantReplayResponse.Body.String(),
		)
	}
	authorizeBody := func(actorPersonaID string) string {
		t.Helper()
		body, marshalErr := json.Marshal(map[string]any{
			"actorPersonaId": actorPersonaID,
			"gatheringId":    grant.GatheringID,
			"action":         grant.Action,
			"evidenceRef":    grant.EvidenceRef,
			"decisionRef":    grant.DecisionRef,
		})
		if marshalErr != nil {
			t.Fatal(marshalErr)
		}
		return string(body)
	}
	allowed := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/internal/content/gathering-safety-termination:authorize",
		authorizeBody("persona-safety"),
		service,
		"",
	))
	if allowed.Code != http.StatusOK ||
		!strings.Contains(allowed.Body.String(), `"allowed":true`) ||
		!strings.Contains(allowed.Body.String(), grant.DecisionDigest) {
		t.Fatalf(
			"AuthorizeGatheringSafetyTermination status=%d body=%s",
			allowed.Code,
			allowed.Body.String(),
		)
	}
	mismatch := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/internal/content/gathering-safety-termination:authorize",
		authorizeBody("persona-attacker"),
		service,
		"",
	))
	if mismatch.Code != http.StatusOK ||
		mismatch.Body.String() != "{\"allowed\":false}\n" {
		t.Fatalf(
			"identity mismatch leaked authority detail: status=%d body=%s",
			mismatch.Code,
			mismatch.Body.String(),
		)
	}
	revokeBody, err := json.Marshal(map[string]any{"decisionRef": grant.DecisionRef})
	if err != nil {
		t.Fatal(err)
	}
	revoke := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/content/reports/"+created.ID+":revoke-gathering-safety-termination",
		string(revokeBody),
		operator,
		"gathering-safety-revoke",
	))
	if revoke.Code != http.StatusOK ||
		!strings.Contains(revoke.Body.String(), `"revokedAt"`) {
		t.Fatalf(
			"RevokeGatheringSafetyTermination status=%d body=%s",
			revoke.Code,
			revoke.Body.String(),
		)
	}
	revokeReplay := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/content/reports/"+created.ID+":revoke-gathering-safety-termination",
		string(revokeBody),
		operator,
		"gathering-safety-revoke",
	))
	var replayedRevocation reportapp.GatheringSafetyTerminationGrantResult
	if revokeReplay.Code != http.StatusOK ||
		json.Unmarshal(revokeReplay.Body.Bytes(), &replayedRevocation) != nil ||
		!replayedRevocation.Replayed ||
		replayedRevocation.RevokedAt == nil {
		t.Fatalf(
			"Gathering safety revoke replay diverged: status=%d result=%+v body=%s",
			revokeReplay.Code,
			replayedRevocation,
			revokeReplay.Body.String(),
		)
	}
	revoked := perform(authenticatedReportAPIRequest(
		t,
		http.MethodPost,
		"/internal/content/gathering-safety-termination:authorize",
		authorizeBody("persona-safety"),
		service,
		"",
	))
	if revoked.Code != http.StatusOK ||
		revoked.Body.String() != "{\"allowed\":false}\n" {
		t.Fatalf(
			"revoked authority did not fail closed: status=%d body=%s",
			revoked.Code,
			revoked.Body.String(),
		)
	}
	var authorizationCount int
	if err := fixture.DB.QueryRowContext(
		ctx,
		`SELECT COUNT(*) FROM report_gathering_safety_authorizations
		  WHERE decision_ref=$1 AND revoked_at IS NOT NULL`,
		grant.DecisionRef,
	).Scan(&authorizationCount); err != nil {
		t.Fatalf("query Gathering safety authority: %v", err)
	}
	if authorizationCount != 1 {
		t.Fatalf("authority lifecycle was not persisted atomically: count=%d", authorizationCount)
	}
}
