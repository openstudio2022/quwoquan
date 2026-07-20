package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	experimenthttp "quwoquan_service/services/product-ops-service/internal/adapters/http/experiment"
	experimentapp "quwoquan_service/services/product-ops-service/internal/application/product_ops/experiment"
	experimentpersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/product_ops/experiment/persistence"
)

func TestExperimentControlPlaneUsesGeneratedOperatorGuardAndAtomicPostgres(t *testing.T) {
	handler := newRealExperimentHTTPHandler(t)
	guarded := realReadyExperimentAuthenticatedHandler(t, handler)
	experimentID := seedRealExperiment(t, "draft")

	unauthorized := performExperimentRequest(
		guarded, http.MethodGet, "/control-plane/product/experiments", experimentRequestOptions{},
	)
	assertExperimentError(t, unauthorized, http.StatusUnauthorized, "GATEWAY.USER.unauthorized")

	wrongScope := performExperimentRequest(
		guarded,
		http.MethodPost,
		"/control-plane/product/experiments/"+experimentID+":rollout",
		experimentRequestOptions{
			Body:       `{"status":"running","variants":[{"key":"control","allocationBasisPoints":4000},{"key":"treatment","allocationBasisPoints":6000}]}`,
			Credential: experimentAccessToken(t, "operator-1", "", []string{"operator"}),
			Headers:    experimentRolloutHeaders(),
		},
	)
	assertExperimentError(t, wrongScope, http.StatusForbidden, "GATEWAY.USER.forbidden")

	rolloutPath := "/control-plane/product/experiments/" + experimentID + ":rollout"
	rolloutBody := `{"status":"running","variants":[{"key":"control","allocationBasisPoints":4000},{"key":"treatment","allocationBasisPoints":6000}]}`
	writeToken := experimentAccessToken(t, "operator-1", "ops.experiment.write", []string{"operator"})
	created := performExperimentRequest(guarded, http.MethodPost, rolloutPath, experimentRequestOptions{
		Body: rolloutBody, Credential: writeToken, Headers: experimentRolloutHeaders(),
	})
	if created.Code != http.StatusOK {
		t.Fatalf("rollout status=%d body=%s", created.Code, created.Body.String())
	}
	var result experimenthttp.UpdateExperimentRolloutResult
	decodeExperimentResponse(t, created, &result)
	if result.ID != experimentID || result.Status != "running" || result.PolicyVersion != "2" {
		t.Fatalf("unexpected rollout result: %+v", result)
	}

	replayed := performExperimentRequest(guarded, http.MethodPost, rolloutPath, experimentRequestOptions{
		Body: rolloutBody, Credential: writeToken, Headers: experimentRolloutHeaders(),
	})
	if replayed.Code != http.StatusOK {
		t.Fatalf("rollout replay status=%d body=%s", replayed.Code, replayed.Body.String())
	}

	conflict := performExperimentRequest(
		guarded,
		http.MethodPost,
		rolloutPath,
		experimentRequestOptions{
			Body:       `{"status":"ended","variants":[{"key":"control","allocationBasisPoints":4000},{"key":"treatment","allocationBasisPoints":6000}]}`,
			Credential: writeToken,
			Headers:    experimentRolloutHeaders(),
		},
	)
	assertExperimentError(t, conflict, http.StatusConflict, "OPS.USER.idempotency_conflict")

	readToken := experimentAccessToken(t, "operator-1", "ops.experiment.read", []string{"operator"})
	listed := performExperimentRequest(
		guarded, http.MethodGet, "/control-plane/product/experiments",
		experimentRequestOptions{Credential: readToken},
	)
	if listed.Code != http.StatusOK || !strings.Contains(listed.Body.String(), experimentID) {
		t.Fatalf("experiment catalog status=%d body=%s", listed.Code, listed.Body.String())
	}

	var outboxCount int
	var leakedSeed bool
	err := controlPlanePGPool.QueryRow(context.Background(), `
SELECT COUNT(*), COALESCE(BOOL_OR(payload::text LIKE '%allocationSeed%'), false)
FROM product_ops_outbox WHERE aggregate_id=$1`, experimentID).Scan(&outboxCount, &leakedSeed)
	if err != nil {
		t.Fatalf("inspect experiment outbox: %v", err)
	}
	if outboxCount != 1 || leakedSeed {
		t.Fatalf("rollout outbox count=%d leakedAllocationSeed=%v", outboxCount, leakedSeed)
	}
}

func TestExperimentAssignmentDerivesSubjectAndRemainsCommerciallyBlocked(t *testing.T) {
	handler := newRealExperimentHTTPHandler(t)
	authenticated := realExperimentAuthenticatedHandler(t, false, handler)
	guarded := realExperimentAuthenticatedHandler(t, true, handler)
	experimentID := seedRealExperiment(t, "running")
	assignmentPath := "/ops/experiments/" + experimentID + "/assignment"
	personaToken := experimentAccessToken(t, "account-1", "", nil, "persona-1")

	spoofedBody := performExperimentRequest(
		authenticated, http.MethodPost, assignmentPath,
		experimentRequestOptions{
			Body: `{"subjectKey":"persona:victim"}`, Credential: personaToken,
		},
	)
	assertExperimentError(t, spoofedBody, http.StatusBadRequest, "OPS.USER.invalid_argument")

	assigned := performExperimentRequest(authenticated, http.MethodPost, assignmentPath, experimentRequestOptions{
		Credential: personaToken,
	})
	if assigned.Code != http.StatusCreated {
		t.Fatalf("assign status=%d body=%s", assigned.Code, assigned.Body.String())
	}
	var assignedFact struct {
		SubjectKey string `json:"subjectKey"`
		Variant    string `json:"variant"`
	}
	decodeExperimentResponse(t, assigned, &assignedFact)
	if assignedFact.SubjectKey != "persona:persona-1" || assignedFact.Variant == "" {
		t.Fatalf("assignment did not derive verified persona: %+v", assignedFact)
	}

	blocked := performExperimentRequest(guarded, http.MethodPost, assignmentPath, experimentRequestOptions{
		Credential: personaToken,
	})
	assertExperimentError(t, blocked, http.StatusForbidden, "GATEWAY.USER.forbidden")

	readOwn := performExperimentRequest(authenticated, http.MethodGet, assignmentPath, experimentRequestOptions{
		Credential: personaToken,
	})
	if readOwn.Code != http.StatusOK || !strings.Contains(readOwn.Body.String(), `"subjectKey":"persona:persona-1"`) {
		t.Fatalf("read own assignment status=%d body=%s", readOwn.Code, readOwn.Body.String())
	}

	deviceTicket := experimentDeviceTicket(t, "device-1")
	assignedDevice := performExperimentRequest(authenticated, http.MethodPost, assignmentPath, experimentRequestOptions{
		Credential: deviceTicket, UseDeviceTicket: true,
	})
	if assignedDevice.Code != http.StatusCreated || !strings.Contains(assignedDevice.Body.String(), `"subjectKey":"device:device-1"`) {
		t.Fatalf("device assignment status=%d body=%s", assignedDevice.Code, assignedDevice.Body.String())
	}

	unauthorized := performExperimentRequest(authenticated, http.MethodPost, assignmentPath, experimentRequestOptions{})
	assertExperimentError(t, unauthorized, http.StatusUnauthorized, "OPS.USER.unauthorized")

	var subjects []string
	rows, err := controlPlanePGPool.Query(context.Background(), `
SELECT subject_key FROM experiment_assignment_facts WHERE experiment_id=$1 ORDER BY subject_key`, experimentID)
	if err != nil {
		t.Fatalf("query assignment subjects: %v", err)
	}
	defer rows.Close()
	for rows.Next() {
		var subject string
		if err := rows.Scan(&subject); err != nil {
			t.Fatal(err)
		}
		subjects = append(subjects, subject)
	}
	if strings.Join(subjects, ",") != "device:device-1,persona:persona-1" {
		t.Fatalf("authoritative subjects=%v", subjects)
	}
}

func newRealExperimentHTTPHandler(t *testing.T) http.Handler {
	t.Helper()
	store, err := experimentpersistence.NewPostgresStore(controlPlanePGPool)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureSchema(context.Background()); err != nil {
		t.Fatal(err)
	}
	facade, err := experimentapp.NewFacade(store, store, store, store)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := experimenthttp.NewHandler(facade)
	if err != nil {
		t.Fatal(err)
	}
	return handler
}

func seedRealExperiment(t *testing.T, status string) string {
	t.Helper()
	id := fmt.Sprintf("experiment-http-%d", time.Now().UnixNano())
	now := time.Now().UTC().Truncate(time.Second)
	_, err := controlPlanePGPool.Exec(context.Background(), `
INSERT INTO experiments(
  id, key, version, status, variants, audience_rule, allocation_seed, created_at, updated_at
) VALUES ($1,$1,1,$2,$3,$4,$5,$6,$6)`,
		id,
		status,
		`[{"key":"control","allocationBasisPoints":5000},{"key":"treatment","allocationBasisPoints":5000}]`,
		`{"kind":"all"}`,
		"must-not-leave-aggregate",
		now,
	)
	if err != nil {
		t.Fatalf("seed experiment: %v", err)
	}
	return id
}

func realExperimentAuthenticatedHandler(t *testing.T, generatedGuard bool, next http.Handler) http.Handler {
	t.Helper()
	accessVerifier, err := rtauth.NewHS256Verifier(experimentTokenConfig(rtauth.TokenTypeAccess))
	if err != nil {
		t.Fatal(err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(experimentTokenConfig(rtauth.TokenTypeDevice))
	if err != nil {
		t.Fatal(err)
	}
	if generatedGuard {
		next = rtauth.RequireGeneratedOperationAuthorization(operationsecurity.ForDomain("ops"))(next)
	}
	return rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: accessVerifier, DeviceTicketVerifier: deviceVerifier,
	})(next)
}

func realReadyExperimentAuthenticatedHandler(t *testing.T, next http.Handler) http.Handler {
	t.Helper()
	descriptors := operationsecurity.ForDomain("ops")
	matched := 0
	for index := range descriptors {
		if strings.HasPrefix(
			descriptors[index].PathTemplate,
			"/control-plane/product/experiments",
		) {
			// 生产合同继续 blocked；这里只把同一 generated descriptor 的商用开关
			// 提升为 ready，以验证解冻后的鉴权与原子写边界。
			descriptors[index].CommercialStatus = "ready"
			matched++
		}
	}
	if matched == 0 {
		t.Fatal("missing generated experiment control-plane descriptors")
	}
	next = rtauth.RequireGeneratedOperationAuthorization(descriptors)(next)
	return realExperimentAuthenticatedHandler(t, false, next)
}

func experimentAccessToken(t *testing.T, accountID, scopes string, roles []string, personaID ...string) string {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(experimentTokenConfig(rtauth.TokenTypeAccess))
	if err != nil {
		t.Fatal(err)
	}
	persona := ""
	if len(personaID) > 0 {
		persona = personaID[0]
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: accountID, PersonaID: persona, Scopes: strings.Fields(scopes), Roles: roles,
	})
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func experimentDeviceTicket(t *testing.T, deviceActorID string) string {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(experimentTokenConfig(rtauth.TokenTypeDevice))
	if err != nil {
		t.Fatal(err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{DeviceActorID: deviceActorID})
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func experimentTokenConfig(tokenType rtauth.TokenType) rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret: []byte("product-ops-api-integration-secret-32-bytes"),
		Issuer: "product-ops-api-integration", Audience: "quwoquan-api",
		Type: tokenType, TokenVersion: 1, TTL: 5 * time.Minute, ClockSkew: time.Second,
	}
}

type experimentRequestOptions struct {
	Body            string
	Credential      string
	UseDeviceTicket bool
	Headers         http.Header
}

func experimentRolloutHeaders() http.Header {
	return http.Header{
		"Idempotency-Key": []string{"experiment-http-idempotency"},
		"If-Match":        []string{`"1"`},
	}
}

func performExperimentRequest(
	handler http.Handler,
	method, path string,
	options experimentRequestOptions,
) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(options.Body))
	request.Header.Set("Content-Type", "application/json")
	for key, values := range options.Headers {
		for _, value := range values {
			request.Header.Add(key, value)
		}
	}
	request.Header.Set("X-Client-Persona-Id", "victim")
	request.Header.Set("X-User-Id", "victim")
	if options.Credential != "" {
		if options.UseDeviceTicket {
			request.Header.Set(rtauth.DeviceTicketHeader, options.Credential)
		} else {
			request.Header.Set("Authorization", "Bearer "+options.Credential)
		}
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertExperimentError(t *testing.T, recorder *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("error status=%d want=%d body=%s", recorder.Code, status, recorder.Body.String())
	}
	var response rterr.ErrorResponse
	decodeExperimentResponse(t, recorder, &response)
	if response.Code != code {
		t.Fatalf("error code=%q want=%q body=%s", response.Code, code, recorder.Body.String())
	}
}

func decodeExperimentResponse(t *testing.T, recorder *httptest.ResponseRecorder, target any) {
	t.Helper()
	if err := json.Unmarshal(recorder.Body.Bytes(), target); err != nil {
		t.Fatalf("decode response: %v body=%s", err, recorder.Body.String())
	}
}
