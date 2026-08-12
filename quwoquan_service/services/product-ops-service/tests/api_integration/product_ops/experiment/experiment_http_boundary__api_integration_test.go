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
	experimenthttp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/adapters/inbound/http"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	experimentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/infrastructure/persistence"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/infrastructure/persistence"
)

// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
// readiness_case: create-experiment-api
// readiness_case: list-experiments-api
// readiness_case: update-experiment-rollout-api
func TestExperimentControlPlaneUsesGeneratedOperatorGuardAndAtomicPostgres(t *testing.T) {
	handler := newRealExperimentHTTPHandler(t)
	guarded := realReadyExperimentAuthenticatedHandler(t, handler)
	experimentID := fmt.Sprintf("experiment-http-%d", time.Now().UnixNano())

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

	writeToken := experimentAccessToken(t, "operator-1", "ops.experiment.write", []string{"operator"})
	createBody := fmt.Sprintf(`{"id":%q,"key":%q,"status":"draft","variants":[{"key":"control","allocationBasisPoints":5000},{"key":"treatment","allocationBasisPoints":5000}],"audienceRule":{"kind":"all"}}`, experimentID, experimentID)
	createdExperiment := performExperimentRequest(
		guarded,
		http.MethodPost,
		"/control-plane/product/experiments",
		experimentRequestOptions{
			Body: createBody, Credential: writeToken,
			Headers: http.Header{"Idempotency-Key": []string{"experiment-http-create"}},
		},
	)
	if createdExperiment.Code != http.StatusCreated {
		t.Fatalf("create experiment status=%d body=%s", createdExperiment.Code, createdExperiment.Body.String())
	}
	var createResult experimenthttp.CreateExperimentResult
	decodeExperimentResponse(t, createdExperiment, &createResult)
	if createResult.ID != experimentID || createResult.ExperimentRevision != 1 || createResult.Status != "draft" {
		t.Fatalf("unexpected create result: %+v", createResult)
	}

	rolloutPath := "/control-plane/product/experiments/" + experimentID + ":rollout"
	rolloutBody := `{"status":"running","variants":[{"key":"control","allocationBasisPoints":4000},{"key":"treatment","allocationBasisPoints":6000}]}`
	created := performExperimentRequest(guarded, http.MethodPost, rolloutPath, experimentRequestOptions{
		Body: rolloutBody, Credential: writeToken, Headers: experimentRolloutHeaders(),
	})
	if created.Code != http.StatusOK {
		t.Fatalf("rollout status=%d body=%s", created.Code, created.Body.String())
	}
	var result experimenthttp.UpdateExperimentRolloutResult
	decodeExperimentResponse(t, created, &result)
	if result.ID != experimentID || result.Status != "running" || result.ExperimentRevision != 2 {
		t.Fatalf("unexpected rollout result: %+v", result)
	}

	replayed := performExperimentRequest(guarded, http.MethodPost, rolloutPath, experimentRequestOptions{
		Body: rolloutBody, Credential: writeToken, Headers: experimentRolloutHeaders(),
	})
	if replayed.Code != http.StatusOK {
		t.Fatalf("rollout replay status=%d body=%s", replayed.Code, replayed.Body.String())
	}

	liveReallocation := performExperimentRequest(
		guarded,
		http.MethodPost,
		rolloutPath,
		experimentRequestOptions{
			Body:       `{"status":"running","variants":[{"key":"control","allocationBasisPoints":0},{"key":"treatment","allocationBasisPoints":10000}]}`,
			Credential: writeToken,
			Headers: experimentRolloutHeadersFor(
				"experiment-http-live-reallocation",
				2,
			),
		},
	)
	if liveReallocation.Code != http.StatusOK {
		t.Fatalf(
			"live reallocation status=%d body=%s",
			liveReallocation.Code,
			liveReallocation.Body.String(),
		)
	}
	decodeExperimentResponse(t, liveReallocation, &result)
	if result.ID != experimentID || result.Status != "running" || result.ExperimentRevision != 3 {
		t.Fatalf("unexpected live reallocation result: %+v", result)
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
	var unexpectedEventType bool
	err := controlPlanePGPool.QueryRow(context.Background(), `
SELECT COUNT(*), COALESCE(BOOL_OR(event_type <> 'ExperimentPolicyActivated'), false)
FROM product_ops_outbox WHERE aggregate_id=$1`, experimentID).Scan(&outboxCount, &unexpectedEventType)
	if err != nil {
		t.Fatalf("inspect experiment outbox: %v", err)
	}
	if outboxCount != 3 || unexpectedEventType {
		t.Fatalf("policy activation outbox count=%d unexpectedEventType=%v", outboxCount, unexpectedEventType)
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
	assignmentStore, err := assignmentpersistence.NewPostgresStore(controlPlanePGPool)
	if err != nil {
		t.Fatal(err)
	}
	if err := assignmentStore.EnsureSchema(context.Background()); err != nil {
		t.Fatal(err)
	}
	facade, err := experimentapp.NewFacade(store, store)
	if err != nil {
		t.Fatal(err)
	}
	assignments, err := assignmentapp.NewFacade(facade, assignmentStore, assignmentStore)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := experimenthttp.NewHandler(facade, assignments)
	if err != nil {
		t.Fatal(err)
	}
	return handler
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
	return experimentRolloutHeadersFor("experiment-http-idempotency", 1)
}

func experimentRolloutHeadersFor(idempotencyKey string, expectedVersion int64) http.Header {
	return http.Header{
		"Idempotency-Key": []string{idempotencyKey},
		"If-Match":        []string{fmt.Sprintf(`"%d"`, expectedVersion)},
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
