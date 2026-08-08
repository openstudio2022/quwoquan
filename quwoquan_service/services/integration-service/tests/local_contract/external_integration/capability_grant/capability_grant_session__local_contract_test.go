// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
package capability_grant_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	grantpersistence "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/persistence"
)

type recordingSessionStore struct {
	mu     sync.Mutex
	grants []grantmodel.ResolvedCapabilityGrant
	err    error
}

func (store *recordingSessionStore) Save(
	_ context.Context,
	grant grantmodel.ResolvedCapabilityGrant,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.err != nil {
		return store.err
	}
	store.grants = append(store.grants, grant)
	return nil
}

func (store *recordingSessionStore) Load(
	_ context.Context,
	resolutionID string,
) (grantapp.StoredSession, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.err != nil {
		return grantapp.StoredSession{}, store.err
	}
	for _, grant := range store.grants {
		if grant.ResolutionID != resolutionID || grant.ExpiresAt == nil {
			continue
		}
		bindingDigest, err := grantmodel.BindingDigest(grant)
		if err != nil {
			return grantapp.StoredSession{}, err
		}
		return grantapp.StoredSession{
			ResolutionID:       grant.ResolutionID,
			AccountDigest:      grantmodel.OpaqueDigest(grant.AccountID),
			ServiceActorDigest: grant.ServiceActorDigest,
			CapabilityKey:      grant.CapabilityKey,
			SurfaceKind:        grant.SurfaceKind,
			BindingKind:        grant.BindingKind,
			BindingDigest:      bindingDigest,
			InputDigest:        grant.InputDigest,
			ConfirmationDigest: grant.ConfirmationDigest,
			PermitDigest:       grant.PermitDigest,
			IdempotencyDigest:  grant.IdempotencyDigest,
			ResolvedAt:         grant.ResolvedAt,
			ExpiresAt:          *grant.ExpiresAt,
		}, nil
	}
	return grantapp.StoredSession{}, grantapp.ErrCapabilityGrantSessionNotFound
}

func TestWorkerRevalidationRequiresAssistantAuthorizedSession(t *testing.T) {
	now := time.Date(2026, time.August, 8, 8, 30, 0, 0, time.UTC)
	source := recordingUserConnectorSource{values: []grantmodel.UserConnectorConnection{{
		CapabilityKey: "calendar.event.create", AccountID: "account-1",
		ConnectionID: "connection-1", ConnectorID: "calendar",
		ContractDigest:      digest("calendar-contract"),
		GrantedCapabilities: []string{"calendar.event.create"},
		GrantState:          grantmodel.ConnectorGrantActive,
		FreshnessAt:         now, Revision: 1,
	}}}
	store := &recordingSessionStore{}
	facade := grantapp.NewCapabilityGrantSessionFacade(
		userConnectorOnlyResolver{source: &source, now: now},
		store,
		func() time.Time { return now },
	)
	transportAuthorization, err := grantapp.NewTrustedRuntimeAuthorization(
		"account-1", grantapp.AssistantServiceActorID,
	)
	if err != nil {
		t.Fatal(err)
	}
	input := grantapp.FinalAuthorizationInput{
		ResolutionID: "resolution-worker-1", CapabilityKey: "calendar.event.create",
		SurfaceKind: "personal", ConnectionRefs: []string{"connection-1"},
		BindingKind: grantmodel.BindingUserConnector, InputDigest: digest("input"),
		ConfirmationRef: "confirmation", PermitRef: "permit", IdempotencyKey: "invoke-1",
	}
	if _, err := facade.AuthorizeFinalInput(
		context.Background(), transportAuthorization, input,
	); err != nil {
		t.Fatal(err)
	}
	workerAuthorization, err := grantapp.NewTrustedRuntimeWorkerAuthorization(
		"account-1", grantapp.IntegrationServiceWorkerActorID,
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := facade.RevalidateFinalAuthorizationForWorker(
		context.Background(), workerAuthorization, input,
	); err != nil {
		t.Fatalf("worker revalidation of assistant session: %v", err)
	}

	store.mu.Lock()
	store.grants[0].ServiceActorDigest = grantmodel.OpaqueDigest("other-service")
	store.mu.Unlock()
	if _, err := facade.RevalidateFinalAuthorizationForWorker(
		context.Background(), workerAuthorization, input,
	); !errors.Is(err, grantapp.ErrFinalAuthorizationMismatch) {
		t.Fatalf("foreign service session reached worker: %v", err)
	}
	if _, err := grantapp.NewTrustedRuntimeWorkerAuthorization(
		"account-1", "other-worker",
	); !errors.Is(err, grantapp.ErrRuntimeAuthorizationInvalid) {
		t.Fatalf("foreign worker actor accepted: %v", err)
	}
}

func (store *recordingSessionStore) count() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return len(store.grants)
}

func TestFinalAuthorizationRevalidatesAllDigestsAndCurrentBinding(t *testing.T) {
	now := time.Date(2026, time.August, 8, 8, 0, 0, 0, time.UTC)
	clock := now
	source := recordingUserConnectorSource{values: []grantmodel.UserConnectorConnection{{
		CapabilityKey:                "calendar.event.create",
		AccountID:                    "account-1",
		ConnectionID:                 "connection-1",
		ConnectorID:                  "calendar",
		ContractDigest:               digest("calendar-contract-v1"),
		GrantedCapabilities:          []string{"calendar.event.create"},
		GrantState:                   grantmodel.ConnectorGrantActive,
		ProviderAccountSubjectDigest: digest("provider-account"),
		FreshnessAt:                  now,
		Revision:                     1,
	}}}
	store := &recordingSessionStore{}
	facade := grantapp.NewCapabilityGrantSessionFacade(
		userConnectorOnlyResolver{source: &source, now: now},
		store,
		func() time.Time { return clock },
	)
	authorization, err := grantapp.NewTrustedRuntimeAuthorization(
		"account-1",
		"assistant-service",
	)
	if err != nil {
		t.Fatal(err)
	}
	input := grantapp.FinalAuthorizationInput{
		ResolutionID:    "resolution-final-1",
		CapabilityKey:   "calendar.event.create",
		SurfaceKind:     "personal",
		ConnectionRefs:  []string{"connection-1"},
		BindingKind:     grantmodel.BindingUserConnector,
		InputDigest:     digest("final-input"),
		ConfirmationRef: "protected://confirmation/1",
		PermitRef:       "protected://permit/1",
		IdempotencyKey:  "invoke-calendar-1",
	}
	if _, err := facade.AuthorizeFinalInput(
		context.Background(), authorization, input,
	); err != nil {
		t.Fatal(err)
	}
	if _, err := facade.RevalidateFinalAuthorization(
		context.Background(), authorization, input,
	); err != nil {
		t.Fatalf("revalidate current final authorization: %v", err)
	}

	mismatch := input
	mismatch.PermitRef = "protected://permit/different"
	if _, err := facade.RevalidateFinalAuthorization(
		context.Background(), authorization, mismatch,
	); !errors.Is(err, grantapp.ErrFinalAuthorizationMismatch) {
		t.Fatalf("permit mismatch error=%v", err)
	}

	source.values[0].ContractDigest = digest("calendar-contract-v2")
	if _, err := facade.RevalidateFinalAuthorization(
		context.Background(), authorization, input,
	); !errors.Is(err, grantapp.ErrFinalAuthorizationMismatch) {
		t.Fatalf("contract digest drift error=%v", err)
	}
	source.values[0].ContractDigest = digest("calendar-contract-v1")
	clock = now.Add(grantmodel.GrantTTL)
	if _, err := facade.RevalidateFinalAuthorization(
		context.Background(), authorization, input,
	); !errors.Is(err, grantapp.ErrCapabilityGrantSessionExpired) {
		t.Fatalf("expired session error=%v", err)
	}
}

func TestRedisSessionLoadRejectsUnknownFieldsAndNeverRenews(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	store, err := grantpersistence.NewRedisSessionStore(client)
	if err != nil {
		t.Fatal(err)
	}
	key := "integration:capability-grant:corrupt-session"
	if err := client.Set(
		ctx,
		key,
		`{"resolutionId":"corrupt-session","unknown":true}`,
		grantmodel.GrantTTL,
	); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Load(ctx, "corrupt-session"); !errors.Is(err, grantmodel.ErrInvalidResolvedGrant) {
		t.Fatalf("unknown session field error=%v", err)
	}
	if _, err := store.Load(ctx, "missing-session"); !errors.Is(err, grantapp.ErrCapabilityGrantSessionNotFound) {
		t.Fatalf("missing session error=%v", err)
	}
}
