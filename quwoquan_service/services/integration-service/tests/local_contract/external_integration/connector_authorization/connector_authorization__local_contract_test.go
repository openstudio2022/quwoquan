// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_authorization_test

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

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
	nativeCalls int
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

func (*proofVerifier) VerifyOAuth(
	context.Context,
	authorizationmodel.Authorization,
	string,
) (authorizationmodel.VerifiedProof, error) {
	return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrOAuthCallbackInvalid
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
