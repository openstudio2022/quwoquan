// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
// readiness_case: list-connector-invocations-local
// readiness_case: get-connector-invocation-local
// readiness_case: invoke-connector-capability-local
// readiness_case: continue-connector-invocation-local
package connector_invocation_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantcandidate "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/candidate"
	grantpersistence "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/persistence"
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	invocationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/application"
	invocationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
)

type definitionReader struct{ definition definitionmodel.Definition }

func (reader definitionReader) Get(context.Context, string) (definitionmodel.Definition, error) {
	return reader.definition, nil
}

func (reader definitionReader) List(context.Context, string, int) ([]definitionmodel.Definition, error) {
	return []definitionmodel.Definition{reader.definition}, nil
}

type connectionReader struct{ connection connectionmodel.Connection }

func (reader *connectionReader) Get(context.Context, string, string) (connectionmodel.Connection, error) {
	return reader.connection, nil
}

func (reader *connectionReader) List(context.Context, string, int) ([]connectionmodel.Connection, error) {
	return []connectionmodel.Connection{reader.connection}, nil
}

type invocationStore struct{ current invocationmodel.Invocation }

func (store *invocationStore) Get(_ context.Context, accountID string, invocationID string) (invocationmodel.Invocation, error) {
	if store.current.AccountID != accountID || store.current.InvocationID != invocationID {
		return invocationmodel.Invocation{}, invocationmodel.ErrNotFound
	}
	return store.current, nil
}

func (store *invocationStore) List(context.Context, string, string, int) ([]invocationmodel.Invocation, error) {
	return []invocationmodel.Invocation{store.current}, nil
}

func (store *invocationStore) Accept(_ context.Context, command invocationmodel.AcceptCommand) (invocationmodel.MutationResult, error) {
	store.current = command.Invocation
	return invocationmodel.MutationResult{Invocation: store.current}, nil
}

func (store *invocationStore) Continue(_ context.Context, input invocationmodel.ContinueInput) (invocationmodel.MutationResult, error) {
	store.current.Status = invocationmodel.StatusAccepted
	store.current.ConfirmationRef = input.ConfirmationRef
	store.current.Revision++
	store.current.UpdatedAt = input.OccurredAt
	return invocationmodel.MutationResult{Invocation: store.current}, nil
}

func TestInvocationBindsFinalAuthorizationAndRechecksRevocation(t *testing.T) {
	now := time.Date(2026, time.August, 2, 10, 0, 0, 0, time.UTC)
	connections := &connectionReader{connection: connectionmodel.Connection{
		ConnectionID: "connection-1", AccountID: "account-1", ConnectorID: "system_calendar",
		GrantedCapabilities: []string{"calendar.event.create"}, Status: connectionmodel.StatusActive,
		FreshnessAt: now, Revision: 1,
	}}
	store := &invocationStore{}
	grantStore, err := grantpersistence.NewRedisSessionStore(rtredis.NewMemoryClient())
	if err != nil {
		t.Fatal(err)
	}
	unavailable := grantcandidate.NewUnavailableSources("not used by connector invocation")
	grantSession := grantapp.NewCapabilityGrantSessionFacade(
		grantresolver.NewCandidateResolver(
			unavailable,
			grantcandidate.NewConnectorReaderSource(
				connections,
				definitionReader{definition: definitionmodel.Definition{
					ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
					Capabilities:          []string{"calendar.event.create"},
					SupportedSurfaceKinds: []string{"personal"},
					ReleaseDigest:         digestValue("calendar-contract"),
				}},
				func() time.Time { return now },
			),
			unavailable,
			unavailable,
			func() time.Time { return now },
		),
		grantStore,
		func() time.Time { return now },
	)
	facade := invocationapp.NewCommandFacade(
		store,
		grantSession,
		func() time.Time { return now },
		func() string { return "invocation-1" },
	)
	authorization, err := grantapp.NewTrustedRuntimeAuthorization("account-1", "assistant-service")
	if err != nil {
		t.Fatal(err)
	}
	accepted, err := facade.Accept(context.Background(), authorization, invocationmodel.AcceptInput{
		ResolutionID: "resolution-1", ConnectionID: "connection-1", AssistantRunID: "run-1",
		Capability: "calendar.event.create", PayloadRef: "artifact://payload-1",
		SurfaceKind: "personal", InputDigest: digestValue("final-input"),
		ConfirmationRef: "confirmation-1", PermitRef: "permit-1",
		ContinuationRef: "continuation-1", IdempotencyKey: "command-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	if accepted.Invocation.Status != invocationmodel.StatusAccepted ||
		accepted.Invocation.ResolutionID != "resolution-1" ||
		accepted.Invocation.InputDigest != digestValue("final-input") ||
		accepted.Invocation.BindingDigest == "" {
		t.Fatalf("final authorization was not bound: %#v", accepted.Invocation)
	}
	queries := invocationapp.NewQueryFacade(store)
	readback, err := queries.Get(context.Background(), "account-1", "invocation-1")
	if err != nil || readback.InvocationID != accepted.Invocation.InvocationID {
		t.Fatalf("invocation readback failed: invocation=%+v err=%v", readback, err)
	}
	listed, err := queries.List(context.Background(), "account-1", "connection-1", 10)
	if err != nil || len(listed) != 1 || listed[0].InvocationID != accepted.Invocation.InvocationID {
		t.Fatalf("invocation list failed: invocations=%+v err=%v", listed, err)
	}
	continued, err := facade.Continue(context.Background(), authorization, invocationmodel.ContinueInput{
		InvocationID:     "invocation-1",
		AccountID:        "account-1",
		ConfirmationRef:  "confirmation-1",
		ContinuationRef:  "continuation-1",
		ExpectedRevision: 1,
		IdempotencyKey:   "command-2",
	})
	if err != nil || continued.Invocation.Status != invocationmodel.StatusAccepted ||
		continued.Invocation.Revision != 2 {
		t.Fatalf("invocation continuation failed: result=%+v err=%v", continued, err)
	}
	connections.connection.Status = connectionmodel.StatusRevoked
	_, err = facade.Continue(context.Background(), authorization, invocationmodel.ContinueInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		ConfirmationRef: "confirmation-1", ContinuationRef: "continuation-1", ExpectedRevision: 2,
		IdempotencyKey: "command-3",
	})
	if !errors.Is(err, invocationmodel.ErrConnectionInactive) {
		t.Fatalf("revoked connection must fail closed, got %v", err)
	}
}

func digestValue(value string) string {
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
}
