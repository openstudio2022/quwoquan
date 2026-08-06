// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: start-connector-authorization-local
// readiness_case: get-connector-authorization-local
// readiness_case: complete-native-connector-authorization-local
// readiness_case: complete-oauth-connector-authorization-local
package connector_authorization_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	authorizationhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/adapters/inbound/http"
	authorizationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/application"
	authorizationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

type definitionReader struct {
	definition definitionmodel.Definition
}

func (reader definitionReader) Get(context.Context, string) (definitionmodel.Definition, error) {
	return reader.definition, nil
}

func (reader definitionReader) List(context.Context, string, int) ([]definitionmodel.Definition, error) {
	return []definitionmodel.Definition{reader.definition}, nil
}

type fixedIssuer struct{}

func (fixedIssuer) Issue(kind string) (string, string, error) {
	value := kind + "_opaque-secret"
	return value, authorizationmodel.Hash(value), nil
}

type proofVerifier struct {
	nativeCalls        int
	oauthCalls         int
	oauthVerification  *authorizationmodel.OAuthVerification
	oauthSubjectDigest string
}

func (verifier *proofVerifier) VerifyNative(
	_ context.Context,
	authorization authorizationmodel.Authorization,
	proofRef string,
) (authorizationmodel.VerifiedProof, error) {
	verifier.nativeCalls++
	if proofRef != "native-proof-ref" {
		return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrNativeProofInvalid
	}
	credentialExpiry := authorization.CreatedAt.Add(24 * time.Hour)
	return authorizationmodel.VerifiedProof{
		CredentialRef:       "protected://calendar/account-1",
		ProofDigest:         authorizationmodel.Hash(proofRef),
		GrantedCapabilities: append([]string(nil), authorization.RequestedCapabilities...),
		CredentialExpiresAt: &credentialExpiry,
	}, nil
}

func (verifier *proofVerifier) VerifyOAuth(
	_ context.Context,
	authorization authorizationmodel.Authorization,
	proofRef string,
) (authorizationmodel.VerifiedProof, error) {
	verifier.oauthCalls++
	if proofRef != "oauth-callback-ref" {
		return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrOAuthCallbackInvalid
	}
	credentialExpiry := authorization.CreatedAt.Add(24 * time.Hour)
	verification := verifier.oauthVerification
	if verification == nil {
		verification = &authorizationmodel.OAuthVerification{
			StateVerified:           true,
			NonceVerified:           true,
			PKCEVerified:            true,
			AccountSubjectVerified:  true,
			CapabilityProbeVerified: true,
		}
	}
	subjectDigest := verifier.oauthSubjectDigest
	if subjectDigest == "" {
		subjectDigest = authorizationmodel.Hash("google-subject-account-1")
	}
	return authorizationmodel.VerifiedProof{
		CredentialRef:                "protected://oauth/calendar/account-1",
		ProviderAccountSubjectDigest: subjectDigest,
		ProofDigest:                  authorizationmodel.Hash(proofRef),
		GrantedCapabilities:          append([]string(nil), authorization.RequestedCapabilities...),
		CredentialExpiresAt:          &credentialExpiry,
		OAuthVerification:            verification,
	}, nil
}

type memoryStore struct {
	authorization authorizationmodel.Authorization
	receipts      map[string]storedReceipt
}

type storedReceipt struct {
	kind   string
	digest string
	result authorizationmodel.MutationResult
}

func newMemoryStore() *memoryStore {
	return &memoryStore{receipts: map[string]storedReceipt{}}
}

func (store *memoryStore) Get(_ context.Context, accountID, authorizationID string) (authorizationmodel.Authorization, error) {
	if store.authorization.AccountID != accountID || store.authorization.AuthorizationID != authorizationID {
		return authorizationmodel.Authorization{}, authorizationmodel.ErrNotFound
	}
	return store.authorization, nil
}

func (store *memoryStore) GetByID(_ context.Context, authorizationID string) (authorizationmodel.Authorization, error) {
	if store.authorization.AuthorizationID != authorizationID {
		return authorizationmodel.Authorization{}, authorizationmodel.ErrNotFound
	}
	return store.authorization, nil
}

func (store *memoryStore) Replay(
	_ context.Context,
	accountID string,
	key string,
	kind string,
	digest string,
) (authorizationmodel.MutationResult, bool, error) {
	receipt, exists := store.receipts[accountID+":"+key]
	if !exists {
		return authorizationmodel.MutationResult{}, false, nil
	}
	if receipt.kind != kind || receipt.digest != digest {
		return authorizationmodel.MutationResult{}, true, authorizationmodel.ErrIdempotencyConflict
	}
	result := receipt.result
	result.Replayed = true
	return result, true, nil
}

func (store *memoryStore) Start(_ context.Context, command authorizationmodel.StartCommand) (authorizationmodel.MutationResult, error) {
	if replay, found, err := store.Replay(
		context.Background(), command.Authorization.AccountID, command.IdempotencyKey,
		"start", command.CommandDigest,
	); found || err != nil {
		return replay, err
	}
	store.authorization = command.Authorization
	result := authorizationmodel.MutationResult{
		Authorization:   command.Authorization,
		ContinuationRef: command.ContinuationRef,
	}
	store.receipts[command.Authorization.AccountID+":"+command.IdempotencyKey] = storedReceipt{
		kind: "start", digest: command.CommandDigest, result: result,
	}
	return result, nil
}

func (store *memoryStore) Verify(_ context.Context, command authorizationmodel.VerifyCommand) (authorizationmodel.MutationResult, error) {
	store.authorization = command.Authorization
	result := authorizationmodel.MutationResult{
		Authorization:   command.Authorization,
		GrantReceiptRef: command.GrantReceiptRef,
	}
	store.receipts[command.Authorization.AccountID+":"+command.IdempotencyKey] = storedReceipt{
		kind: "verify", digest: command.CommandDigest, result: result,
	}
	return result, nil
}

func (*memoryStore) Consume(context.Context, string, string, string, string, string, time.Time) error {
	return nil
}

func (*memoryStore) Revoke(context.Context, string, string, string, time.Time) error {
	return nil
}

func TestAuthorizationCreatesOpaqueIntentAndReplaysVerifiedGrantWithoutSecretLeak(t *testing.T) {
	now := time.Date(2026, time.August, 3, 9, 0, 0, 0, time.UTC)
	store := newMemoryStore()
	verifier := &proofVerifier{}
	facade := authorizationapp.NewCommandFacade(
		store,
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID:       "system_calendar",
			Capabilities:      []string{"calendar.event.create"},
			AuthorizationMode: definitionmodel.AuthorizationDeviceNative,
			Status:            definitionmodel.StatusActive,
		}},
		fixedIssuer{},
		verifier,
		func() time.Time { return now },
		func() string { return "authorization-1" },
	)
	started, err := facade.Start(context.Background(), authorizationmodel.StartInput{
		AccountID:             "account-1",
		ConnectorID:           "system_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		IdempotencyKey:        "start-1",
	})
	if err != nil || started.Authorization.Status != authorizationmodel.StatusPending ||
		started.ContinuationRef == "" {
		t.Fatalf("start failed: result=%+v err=%v", started, err)
	}
	readback, err := authorizationapp.NewQueryFacade(store).Get(
		context.Background(),
		"account-1",
		"authorization-1",
	)
	if err != nil || readback.AuthorizationID != started.Authorization.AuthorizationID ||
		readback.Status != authorizationmodel.StatusPending {
		t.Fatalf("authorization readback failed: authorization=%+v err=%v", readback, err)
	}
	completed, err := facade.CompleteNative(context.Background(), authorizationmodel.CompleteInput{
		AccountID:        "account-1",
		AuthorizationID:  "authorization-1",
		ExpectedRevision: 1,
		ProofRef:         "native-proof-ref",
		IdempotencyKey:   "complete-1",
	})
	if err != nil || completed.Authorization.Status != authorizationmodel.StatusVerified ||
		completed.GrantReceiptRef == "" {
		t.Fatalf("complete failed: result=%+v err=%v", completed, err)
	}
	replayed, err := facade.CompleteNative(context.Background(), authorizationmodel.CompleteInput{
		AccountID:        "account-1",
		AuthorizationID:  "authorization-1",
		ExpectedRevision: 1,
		ProofRef:         "native-proof-ref",
		IdempotencyKey:   "complete-1",
	})
	if err != nil || !replayed.Replayed || replayed.GrantReceiptRef != completed.GrantReceiptRef {
		t.Fatalf("completion replay failed: result=%+v err=%v", replayed, err)
	}
	if verifier.nativeCalls != 1 {
		t.Fatalf("proof verifier called %d times; replay must not reverify", verifier.nativeCalls)
	}
	encoded, err := json.Marshal(completed)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{
		"protected://",
		"native-proof-ref",
		"connector-grant_opaque-secret",
		"grantReceiptDigest",
		"proofDigest",
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("authorization response leaked %q: %s", forbidden, encoded)
		}
	}
}

func TestAuthorizationCompletesOAuthThroughCommandFacadeWithoutLeakingCallback(t *testing.T) {
	now := time.Date(2026, time.August, 3, 10, 0, 0, 0, time.UTC)
	store := newMemoryStore()
	verifier := &proofVerifier{}
	facade := authorizationapp.NewCommandFacade(
		store,
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID:       "oauth_calendar",
			Capabilities:      []string{"calendar.event.create"},
			AuthorizationMode: definitionmodel.AuthorizationOAuth2,
			Status:            definitionmodel.StatusActive,
		}},
		fixedIssuer{},
		verifier,
		func() time.Time { return now },
		func() string { return "authorization-oauth-1" },
	)
	started, err := facade.Start(context.Background(), authorizationmodel.StartInput{
		AccountID:             "account-1",
		ConnectorID:           "oauth_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		IdempotencyKey:        "start-oauth-1",
	})
	if err != nil || started.Authorization.Status != authorizationmodel.StatusPending {
		t.Fatalf("start OAuth authorization failed: result=%+v err=%v", started, err)
	}
	completed, err := facade.CompleteOAuth(context.Background(), authorizationmodel.CompleteInput{
		AuthorizationID:  started.Authorization.AuthorizationID,
		ExpectedRevision: 1,
		ProofRef:         "oauth-callback-ref",
		IdempotencyKey:   "complete-oauth-1",
	})
	if err != nil || completed.Authorization.Status != authorizationmodel.StatusVerified ||
		completed.Authorization.Revision != 2 || completed.GrantReceiptRef == "" ||
		completed.Authorization.ProviderAccountSubjectDigest !=
			authorizationmodel.Hash("google-subject-account-1") ||
		verifier.oauthCalls != 1 {
		t.Fatalf("complete OAuth authorization failed: result=%+v calls=%d err=%v", completed, verifier.oauthCalls, err)
	}
	encoded, err := json.Marshal(completed)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{
		"oauth-callback-ref",
		"protected://oauth/",
		"google-subject-account-1",
		"grantReceiptDigest",
		"proofDigest",
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("OAuth authorization response leaked %q: %s", forbidden, encoded)
		}
	}
}

func TestAuthorizationRejectsOAuthCallbackWithoutEveryTrustedProof(t *testing.T) {
	now := time.Date(2026, time.August, 3, 10, 30, 0, 0, time.UTC)
	valid := authorizationmodel.OAuthVerification{
		StateVerified:           true,
		NonceVerified:           true,
		PKCEVerified:            true,
		AccountSubjectVerified:  true,
		CapabilityProbeVerified: true,
	}
	cases := []struct {
		name          string
		verification  authorizationmodel.OAuthVerification
		subjectDigest string
	}{
		{name: "state", verification: withOAuthProof(valid, func(value *authorizationmodel.OAuthVerification) {
			value.StateVerified = false
		}), subjectDigest: authorizationmodel.Hash("google-subject-account-1")},
		{name: "nonce", verification: withOAuthProof(valid, func(value *authorizationmodel.OAuthVerification) {
			value.NonceVerified = false
		}), subjectDigest: authorizationmodel.Hash("google-subject-account-1")},
		{name: "pkce", verification: withOAuthProof(valid, func(value *authorizationmodel.OAuthVerification) {
			value.PKCEVerified = false
		}), subjectDigest: authorizationmodel.Hash("google-subject-account-1")},
		{name: "account_subject", verification: withOAuthProof(valid, func(value *authorizationmodel.OAuthVerification) {
			value.AccountSubjectVerified = false
		}), subjectDigest: authorizationmodel.Hash("google-subject-account-1")},
		{name: "capability_probe", verification: withOAuthProof(valid, func(value *authorizationmodel.OAuthVerification) {
			value.CapabilityProbeVerified = false
		}), subjectDigest: authorizationmodel.Hash("google-subject-account-1")},
		{name: "empty_subject", verification: valid, subjectDigest: " "},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			store := newMemoryStore()
			verifier := &proofVerifier{
				oauthVerification:  &testCase.verification,
				oauthSubjectDigest: testCase.subjectDigest,
			}
			facade := authorizationapp.NewCommandFacade(
				store,
				definitionReader{definition: definitionmodel.Definition{
					ConnectorID:       "oauth_calendar",
					Capabilities:      []string{"calendar.event.create"},
					AuthorizationMode: definitionmodel.AuthorizationOAuth2,
					Status:            definitionmodel.StatusActive,
				}},
				fixedIssuer{},
				verifier,
				func() time.Time { return now },
				func() string { return "authorization-oauth-invalid-" + testCase.name },
			)
			started, err := facade.Start(context.Background(), authorizationmodel.StartInput{
				AccountID:             "account-1",
				ConnectorID:           "oauth_calendar",
				RequestedCapabilities: []string{"calendar.event.create"},
				IdempotencyKey:        "start-oauth-invalid-" + testCase.name,
			})
			if err != nil {
				t.Fatal(err)
			}
			_, err = facade.CompleteOAuth(context.Background(), authorizationmodel.CompleteInput{
				AuthorizationID:  started.Authorization.AuthorizationID,
				ExpectedRevision: 1,
				ProofRef:         "oauth-callback-ref",
				IdempotencyKey:   "complete-oauth-invalid-" + testCase.name,
			})
			if !errors.Is(err, authorizationmodel.ErrOAuthCallbackInvalid) {
				t.Fatalf("incomplete OAuth proof error = %v", err)
			}
			if store.authorization.Status != authorizationmodel.StatusPending {
				t.Fatalf("incomplete OAuth proof changed state: %+v", store.authorization)
			}
		})
	}
}

func TestOAuthCallbackBodyAccountIDCannotGrantAuthority(t *testing.T) {
	now := time.Date(2026, time.August, 3, 10, 45, 0, 0, time.UTC)
	store := newMemoryStore()
	facade := authorizationapp.NewCommandFacade(
		store,
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID:       "oauth_calendar",
			Capabilities:      []string{"calendar.event.create"},
			AuthorizationMode: definitionmodel.AuthorizationOAuth2,
			Status:            definitionmodel.StatusActive,
		}},
		fixedIssuer{},
		&proofVerifier{},
		func() time.Time { return now },
		func() string { return "authorization-oauth-body-account" },
	)
	started, err := facade.Start(context.Background(), authorizationmodel.StartInput{
		AccountID:             "account-1",
		ConnectorID:           "oauth_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		IdempotencyKey:        "start-oauth-body-account",
	})
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	authorizationhttp.NewHandler(
		facade,
		authorizationapp.NewQueryFacade(store),
	).RegisterRoutes(mux)
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/integrations/connector-authorizations/"+
			started.Authorization.AuthorizationID+"/complete-oauth",
		bytes.NewBufferString(`{"accountId":"attacker-account","expectedRevision":1,"oauthCallbackRef":"oauth-callback-ref"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "complete-oauth-body-account")
	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("body accountId status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if store.authorization.AccountID != "account-1" ||
		store.authorization.Status != authorizationmodel.StatusPending {
		t.Fatalf("body accountId changed authorization authority: %+v", store.authorization)
	}
}

func TestAuthorizationRejectsPublicLinkAndUnapprovedCapability(t *testing.T) {
	store := newMemoryStore()
	newFacade := func(definition definitionmodel.Definition) *authorizationapp.CommandFacade {
		return authorizationapp.NewCommandFacade(
			store, definitionReader{definition: definition}, fixedIssuer{}, &proofVerifier{},
			time.Now, func() string { return "authorization-2" },
		)
	}
	input := authorizationmodel.StartInput{
		AccountID: "account-1", ConnectorID: "travel-link",
		RequestedCapabilities: []string{"calendar.event.create"}, IdempotencyKey: "start-2",
	}
	_, err := newFacade(definitionmodel.Definition{
		ConnectorID:       "travel-link",
		Capabilities:      []string{"calendar.event.create"},
		AuthorizationMode: definitionmodel.AuthorizationPublicLink,
		Status:            definitionmodel.StatusActive,
	}).Start(context.Background(), input)
	if !errors.Is(err, authorizationmodel.ErrModeUnsupported) {
		t.Fatalf("public_link must not create authorization, got %v", err)
	}
	_, err = newFacade(definitionmodel.Definition{
		ConnectorID:       "travel-link",
		Capabilities:      []string{"calendar.event.read"},
		AuthorizationMode: definitionmodel.AuthorizationDeviceNative,
		Status:            definitionmodel.StatusActive,
	}).Start(context.Background(), input)
	if !errors.Is(err, authorizationmodel.ErrCapabilityDenied) {
		t.Fatalf("unapproved capability must fail closed, got %v", err)
	}
}

func withOAuthProof(
	value authorizationmodel.OAuthVerification,
	mutate func(*authorizationmodel.OAuthVerification),
) authorizationmodel.OAuthVerification {
	mutate(&value)
	return value
}
