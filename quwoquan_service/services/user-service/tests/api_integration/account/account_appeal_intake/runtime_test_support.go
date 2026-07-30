// Test-only real runtime support shared by the canonical API integration cases.
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	appealhttp "quwoquan_service/services/user-service/internal/account/account_appeal_intake/adapters/inbound/http"
	appealapp "quwoquan_service/services/user-service/internal/account/account_appeal_intake/application"
	appealidentity "quwoquan_service/services/user-service/internal/account/account_appeal_intake/infrastructure/identity"
	appealpersistence "quwoquan_service/services/user-service/internal/account/account_appeal_intake/infrastructure/persistence"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	credentialpersistence "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/persistence"
	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

var appealHTTPTokenConfig = rtauth.TokenConfig{
	Secret:       []byte("account-appeal-api-integration-secret-v1"),
	Issuer:       "https://auth.quwoquan.test",
	Audience:     "quwoquan-api",
	Type:         rtauth.TokenTypeAccess,
	TokenVersion: 1,
	TTL:          30 * time.Minute,
	ClockSkew:    30 * time.Second,
}

type realAppealRuntime struct {
	activatedServer  *httptest.Server
	productionServer *httptest.Server
	appeals          *appealapp.CommandFacade
	challenges       *challengeapp.AuthenticationChallengeCommandFacade
	credentials      *credentialapp.CredentialCommandFacade
	enforcement      *useraccountapp.AccountEnforcementCommandFacade
	productOpsAuth   rtauth.ServiceAuthorizationProvider
	otherServiceAuth rtauth.ServiceAuthorizationProvider
}

func newRealAppealRuntime(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
) *realAppealRuntime {
	t.Helper()
	credentialStore, err := credentialpersistence.NewPostgresStore(pool)
	if err != nil {
		t.Fatal(err)
	}
	challengeStore, err := challengepersistence.NewPostgresStore(pool)
	if err != nil {
		t.Fatal(err)
	}
	challenges := challengeapp.NewAuthenticationChallengeCommandFacade(
		challengeStore,
		challengeapp.OTPCredentialVerifier{},
	)
	appealStore, err := appealpersistence.NewPostgresStore(pool)
	if err != nil {
		t.Fatal(err)
	}
	appeals := appealapp.NewCommandFacade(
		appealStore,
		appealidentity.NewChallengeVerifier(challenges, credentialStore),
		nil,
	)
	handler, err := appealhttp.NewHandler(appeals)
	if err != nil {
		t.Fatal(err)
	}
	enforcementStore, err := useraccountpersistence.NewEnforcementStore(pool)
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := rtauth.NewHS256Verifier(appealHTTPTokenConfig)
	if err != nil {
		t.Fatal(err)
	}
	productOpsAuth, err := rtauth.NewHS256ServiceAuthorizationProvider(
		appealHTTPTokenConfig,
		"product-ops-service",
		[]string{"user.account.appeal_intake.claim"},
	)
	if err != nil {
		t.Fatal(err)
	}
	otherServiceAuth, err := rtauth.NewHS256ServiceAuthorizationProvider(
		appealHTTPTokenConfig,
		"other-service",
		[]string{"user.account.appeal_intake.claim"},
	)
	if err != nil {
		t.Fatal(err)
	}
	runtime := &realAppealRuntime{
		appeals: appeals, challenges: challenges,
		credentials:    credentialapp.NewCredentialCommandFacade(credentialStore),
		enforcement:    useraccountapp.NewAccountEnforcementCommandFacade(enforcementStore),
		productOpsAuth: productOpsAuth, otherServiceAuth: otherServiceAuth,
	}
	runtime.activatedServer = startAppealHTTPBoundary(t, handler, verifier, true)
	runtime.productionServer = startAppealHTTPBoundary(t, handler, verifier, false)
	t.Cleanup(func() {
		runtime.activatedServer.Close()
		runtime.productionServer.Close()
	})
	if err := pool.Ping(ctx); err != nil {
		t.Fatalf("real appeal PostgreSQL became unavailable: %v", err)
	}
	return runtime
}

func startAppealHTTPBoundary(
	t *testing.T,
	handler *appealhttp.Handler,
	verifier *rtauth.Verifier,
	activateBlockedPublicOperations bool,
) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	descriptors := appealOperationDescriptors(t, activateBlockedPublicOperations)
	guarded := rtauth.EnforceGeneratedOperationAuthorization(descriptors)(mux)
	return httptest.NewServer(rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: verifier,
	})(guarded))
}

func appealOperationDescriptors(
	t *testing.T,
	activateBlockedPublicOperations bool,
) []rtauth.OperationSecurityDescriptor {
	t.Helper()
	const (
		issue  = "user.account_appeal_intake.IssueAccountAppealCredential"
		submit = "user.account_appeal_intake.SubmitAccountAppealIntake"
		claim  = "user.account_appeal_intake.ClaimAccountAppealIntake"
	)
	descriptors := make([]rtauth.OperationSecurityDescriptor, 0, 3)
	for _, descriptor := range operationsecurity.ForDomain("user") {
		switch descriptor.CanonicalOperationID {
		case issue, submit, claim:
			// The public operations deliberately remain blocked in the canonical
			// descriptor until official Web/OTP/device evidence exists. This
			// controlled API-integration boundary flips only the copied status so
			// the real handler and stores can be accepted without misrepresenting
			// production commercial readiness.
			if activateBlockedPublicOperations &&
				(descriptor.CanonicalOperationID == issue ||
					descriptor.CanonicalOperationID == submit) {
				descriptor.CommercialStatus = "ready"
			}
			descriptors = append(descriptors, descriptor)
		}
	}
	if len(descriptors) != 3 {
		t.Fatalf("AccountAppealIntake requires three generated descriptors, got %d", len(descriptors))
	}
	return descriptors
}

func assertPublicOperationsRemainCommerciallyBlocked(
	t *testing.T,
	runtime *realAppealRuntime,
) {
	t.Helper()
	tests := []struct {
		path           string
		idempotencyKey string
		body           map[string]any
	}{
		{
			path: "/account-appeals/credentials",
			body: map[string]any{
				"phone": testAppealPhone, "otpCode": "123456",
				"challengeId": "commercial-block-probe",
			},
		},
		{
			path: "/account-appeals/intakes", idempotencyKey: "commercial-block-probe",
			body: map[string]any{"appealCredential": strings.Repeat("x", 64)},
		},
	}
	for _, test := range tests {
		response := postJSON(
			t, runtime.productionServer.Client(), runtime.productionServer.URL,
			test.path, test.idempotencyKey, "", test.body,
		)
		assertRuntimeError(t, response, http.StatusForbidden, "GATEWAY.USER.forbidden")
	}
	var credentialCount, intakeCount int
	if err := appealIntakePGPool.QueryRow(context.Background(), `
SELECT
  (SELECT COUNT(*) FROM account_appeal_credentials),
  (SELECT COUNT(*) FROM account_appeal_intakes)`).Scan(
		&credentialCount,
		&intakeCount,
	); err != nil {
		t.Fatalf("read blocked operation side effects: %v", err)
	}
	if credentialCount != 0 || intakeCount != 0 {
		t.Fatalf("commercially blocked operations wrote state: credentials=%d intakes=%d", credentialCount, intakeCount)
	}
}

func seedAppealChallenge(
	t *testing.T,
	ctx context.Context,
	runtime *realAppealRuntime,
	challengeID string,
	otp string,
) {
	t.Helper()
	phoneKey := credentialmodel.NormalizePhoneCredentialKey(testAppealPhone)
	destinationHash := challengeapp.SMSDestinationHash(phoneKey)
	now := time.Now().UTC()
	_, err := runtime.challenges.CreateChallenge(ctx, challengeapp.CreateChallengeCommand{
		ID: challengeID, AccountID: testAppealAccountID,
		Purpose: "account_appeal", Channel: "sms",
		DestinationHash: destinationHash,
		SecretRef: challengeapp.OTPSecretReference(
			challengeID, destinationHash, []byte(otp),
		),
		IdempotencyKey: "create-" + challengeID,
		ExpiresAt:      now.Add(5 * time.Minute),
	})
	if err != nil {
		t.Fatalf("create real appeal challenge %s: %v", challengeID, err)
	}
}

type httpResult struct {
	status int
	header http.Header
	body   []byte
}

func postJSON(
	t *testing.T,
	client *http.Client,
	baseURL string,
	path string,
	idempotencyKey string,
	authorization string,
	payload any,
) httpResult {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(
		http.MethodPost,
		strings.TrimRight(baseURL, "/")+path,
		bytes.NewReader(body),
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	request.Header.Set("X-Request-Id", "account-appeal-api-integration")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	if authorization != "" {
		request.Header.Set("Authorization", authorization)
	}
	response, err := client.Do(request)
	if err != nil {
		t.Fatalf("POST %s: %v", path, err)
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, 64*1024))
	if err != nil {
		t.Fatalf("read POST %s response: %v", path, err)
	}
	return httpResult{status: response.StatusCode, header: response.Header.Clone(), body: responseBody}
}

func assertStatus(t *testing.T, response httpResult, expected int) {
	t.Helper()
	if response.status != expected {
		t.Fatalf("HTTP status=%d want=%d body=%s", response.status, expected, response.body)
	}
}

func assertNoStore(t *testing.T, response httpResult) {
	t.Helper()
	if response.header.Get("Cache-Control") != "no-store" {
		t.Fatalf("secret-bearing response is cacheable: headers=%v", response.header)
	}
}

func decodeJSON[T any](t *testing.T, response httpResult) T {
	t.Helper()
	decoder := json.NewDecoder(bytes.NewReader(response.body))
	decoder.DisallowUnknownFields()
	var result T
	if err := decoder.Decode(&result); err != nil {
		t.Fatalf("decode response %s: %v", response.body, err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		t.Fatalf("response must contain one JSON object: %s", response.body)
	}
	return result
}

func assertRuntimeError(
	t *testing.T,
	response httpResult,
	status int,
	code string,
) {
	t.Helper()
	assertStatus(t, response, status)
	wire := decodeJSON[rterr.ErrorResponse](t, response)
	if wire.Code != code {
		t.Fatalf("runtime error code=%s want=%s body=%s", wire.Code, code, response.body)
	}
	if wire.RequestID == "" || wire.TraceID == "" ||
		response.header.Get("X-Request-Id") == "" ||
		response.header.Get("X-Trace-Id") == "" {
		t.Fatalf("runtime error lost request/trace correlation: body=%s headers=%v", response.body, response.header)
	}
}

func assertCredentialPersistedOnlyAsDigest(
	t *testing.T,
	ctx context.Context,
	challengeID string,
	rawCredential string,
) {
	t.Helper()
	var (
		storedID     string
		storedDigest string
		storedRaw    bool
		secretRef    string
	)
	if err := appealIntakePGPool.QueryRow(ctx, `
SELECT credential_id, credential_digest
FROM account_appeal_credentials
WHERE challenge_id=$1`, challengeID).Scan(&storedID, &storedDigest); err != nil {
		t.Fatalf("read persisted appeal credential: %v", err)
	}
	if storedDigest != credentialDigest(rawCredential) ||
		strings.Contains(storedID, rawCredential) || storedID == rawCredential {
		t.Fatalf("appeal credential was not reduced to its digest: id=%q digest=%q", storedID, storedDigest)
	}
	if err := appealIntakePGPool.QueryRow(ctx, `
SELECT EXISTS(
  SELECT 1 FROM account_appeal_credentials
  WHERE credential_id=$1 OR BTRIM(credential_digest)=$1 OR challenge_id=$1
     OR account_id=$1 OR COALESCE(intake_ref, '')=$1
)`, rawCredential).Scan(&storedRaw); err != nil {
		t.Fatalf("scan appeal credential plaintext: %v", err)
	}
	if storedRaw {
		t.Fatal("raw appeal credential leaked into PostgreSQL")
	}
	if err := appealIntakePGPool.QueryRow(ctx, `
SELECT code_hash FROM authentication_challenges WHERE challenge_id=$1`, challengeID).Scan(
		&secretRef,
	); err != nil {
		t.Fatalf("read authentication challenge secret reference: %v", err)
	}
	if secretRef == "123456" || strings.Contains(secretRef, "123456") {
		t.Fatal("raw OTP leaked into AuthenticationChallenge persistence")
	}
}

func assertCredentialConsumption(
	t *testing.T,
	ctx context.Context,
	rawCredential string,
	intakeRef string,
) {
	t.Helper()
	var consumed bool
	var storedIntakeRef string
	if err := appealIntakePGPool.QueryRow(ctx, `
SELECT consumed_at IS NOT NULL, intake_ref
FROM account_appeal_credentials
WHERE credential_digest=$1`, credentialDigest(rawCredential)).Scan(
		&consumed,
		&storedIntakeRef,
	); err != nil {
		t.Fatalf("read appeal credential consumption: %v", err)
	}
	if !consumed || storedIntakeRef != intakeRef {
		t.Fatalf("credential consumption is not atomic: consumed=%v intake=%q", consumed, storedIntakeRef)
	}
}

func assertCredentialStillUnused(
	t *testing.T,
	ctx context.Context,
	rawCredential string,
) {
	t.Helper()
	var consumed bool
	if err := appealIntakePGPool.QueryRow(ctx, `
SELECT consumed_at IS NOT NULL
FROM account_appeal_credentials
WHERE credential_digest=$1`, credentialDigest(rawCredential)).Scan(&consumed); err != nil {
		t.Fatalf("read appeal credential after idempotency conflict: %v", err)
	}
	if consumed {
		t.Fatal("idempotency conflict consumed a different appeal credential")
	}
}

func expireCredential(t *testing.T, ctx context.Context, rawCredential string) {
	t.Helper()
	tag, err := appealIntakePGPool.Exec(ctx, `
UPDATE account_appeal_credentials
SET issued_at=NOW() - INTERVAL '2 hours',
    expires_at=NOW() - INTERVAL '90 minutes',
    delete_after=NOW() + INTERVAL '5 minutes'
WHERE credential_digest=$1 AND consumed_at IS NULL`, credentialDigest(rawCredential))
	if err != nil || tag.RowsAffected() != 1 {
		t.Fatalf("expire appeal credential: affected=%d err=%v", tag.RowsAffected(), err)
	}
}

func assertCredentialRetentionPurge(
	t *testing.T,
	ctx context.Context,
	runtime *realAppealRuntime,
	rawCredential string,
) {
	t.Helper()
	tag, err := appealIntakePGPool.Exec(ctx, `
UPDATE account_appeal_credentials
SET delete_after=NOW() - INTERVAL '1 second'
WHERE credential_digest=$1 AND consumed_at IS NULL`, credentialDigest(rawCredential))
	if err != nil || tag.RowsAffected() != 1 {
		t.Fatalf("age appeal credential beyond retention: affected=%d err=%v", tag.RowsAffected(), err)
	}
	if err := runtime.appeals.PurgeExpired(ctx); err != nil {
		t.Fatalf("purge expired appeal credential: %v", err)
	}
	var count int
	if err := appealIntakePGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM account_appeal_credentials WHERE credential_digest=$1`,
		credentialDigest(rawCredential),
	).Scan(&count); err != nil {
		t.Fatalf("read appeal credential after retention purge: %v", err)
	}
	if count != 0 {
		t.Fatalf("appeal credential survived deleteAfter purge: count=%d", count)
	}
}

func assertClaimAuthorizationAndTupleSemantics(
	t *testing.T,
	runtime *realAppealRuntime,
	intakeRef string,
) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	path := "/internal/user/account-appeal-intakes/" + intakeRef + ":claim"
	payload := map[string]any{
		"accountId": testAppealAccountID,
		"caseId":    "appeal-case-real-1",
	}
	missingAuth := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-real-1", "", payload,
	)
	assertRuntimeError(t, missingAuth, http.StatusUnauthorized, "GATEWAY.USER.unauthorized")

	otherAuthorization, err := runtime.otherServiceAuth.AuthorizationHeader(ctx)
	if err != nil {
		t.Fatal(err)
	}
	wrongService := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-real-1", otherAuthorization, payload,
	)
	assertRuntimeError(t, wrongService, http.StatusForbidden, "USER.USER.forbidden")

	productAuthorization, err := runtime.productOpsAuth.AuthorizationHeader(ctx)
	if err != nil {
		t.Fatal(err)
	}
	malformedTuple := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-malformed", productAuthorization, map[string]any{
			"accountId": "transport-safe-but-not-canonical", "caseId": "appeal-case-real-1",
		},
	)
	assertRuntimeError(t, malformedTuple, http.StatusBadRequest, "USER.USER.invalid_argument")

	claimedResponse := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-real-1", productAuthorization, payload,
	)
	assertStatus(t, claimedResponse, http.StatusOK)
	assertNoStore(t, claimedResponse)
	claimed := decodeJSON[appealapp.IntakeClaimResult](t, claimedResponse)
	if claimed.IntakeRef != intakeRef || claimed.AccountID != testAppealAccountID ||
		claimed.CaseID != "appeal-case-real-1" || claimed.Status != "claimed" ||
		claimed.IdempotentReplay || claimed.ClaimedAt.IsZero() {
		t.Fatalf("first claim receipt is invalid: %+v", claimed)
	}

	exactReplayResponse := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-real-1", productAuthorization, payload,
	)
	assertStatus(t, exactReplayResponse, http.StatusOK)
	exactReplay := decodeJSON[appealapp.IntakeClaimResult](t, exactReplayResponse)
	if !exactReplay.IdempotentReplay || exactReplay.IntakeRef != claimed.IntakeRef ||
		!exactReplay.ClaimedAt.Equal(claimed.ClaimedAt) {
		t.Fatalf("exact claim replay changed its receipt: first=%+v replay=%+v", claimed, exactReplay)
	}

	tupleReplayResponse := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-real-2", productAuthorization, payload,
	)
	assertStatus(t, tupleReplayResponse, http.StatusOK)
	tupleReplay := decodeJSON[appealapp.IntakeClaimResult](t, tupleReplayResponse)
	if !tupleReplay.IdempotentReplay || tupleReplay.CaseID != claimed.CaseID {
		t.Fatalf("same tuple with a new request identity was not a stable replay: %+v", tupleReplay)
	}

	keyConflict := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-real-1", productAuthorization, map[string]any{
			"accountId": testAppealAccountID, "caseId": "appeal-case-real-2",
		},
	)
	assertRuntimeError(
		t, keyConflict, http.StatusConflict,
		"USER.ACCOUNT.account_appeal_idempotency_conflict",
	)

	crossCase := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-cross-case", productAuthorization, map[string]any{
			"accountId": testAppealAccountID, "caseId": "appeal-case-real-2",
		},
	)
	assertRuntimeError(
		t, crossCase, http.StatusConflict,
		"USER.ACCOUNT.account_appeal_intake_claimed",
	)

	crossAccount := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		path, "appeal-claim-cross-account", productAuthorization, map[string]any{
			"accountId": testOtherAccountID, "caseId": "appeal-case-real-1",
		},
	)
	assertRuntimeError(
		t, crossAccount, http.StatusConflict,
		"USER.ACCOUNT.account_appeal_intake_account_mismatch",
	)

	var (
		status      string
		accountID   string
		caseID      string
		claimKey    string
		claimDigest string
		claimedAt   time.Time
	)
	if err := appealIntakePGPool.QueryRow(ctx, `
SELECT status, account_id, claimed_case_id, claim_idempotency_key,
       claim_digest, claimed_at
FROM account_appeal_intakes
WHERE intake_ref=$1`, intakeRef).Scan(
		&status,
		&accountID,
		&caseID,
		&claimKey,
		&claimDigest,
		&claimedAt,
	); err != nil {
		t.Fatalf("read real appeal claim tuple: %v", err)
	}
	if status != "claimed" || accountID != testAppealAccountID ||
		caseID != "appeal-case-real-1" || claimKey != "appeal-claim-real-1" ||
		len(claimDigest) != 64 || claimedAt.IsZero() {
		t.Fatalf(
			"persisted appeal claim tuple drifted: status=%s account=%s case=%s key=%s digest=%s at=%s",
			status, accountID, caseID, claimKey, claimDigest, claimedAt,
		)
	}
}
