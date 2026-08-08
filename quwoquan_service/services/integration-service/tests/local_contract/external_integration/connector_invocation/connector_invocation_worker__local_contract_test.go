// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
package connector_invocation_test

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	grantcandidate "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/candidate"
	grantpersistence "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/persistence"
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	invocationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/application"
	invocationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
)

type workerStore struct {
	claim     invocationmodel.ExecutionClaim
	found     bool
	completed invocationmodel.CompleteInput
}

func (store *workerStore) ClaimNext(
	context.Context,
	string,
	time.Time,
	time.Duration,
) (invocationmodel.ExecutionClaim, bool, error) {
	return store.claim, store.found, nil
}

func (store *workerStore) Complete(
	_ context.Context,
	input invocationmodel.CompleteInput,
) (invocationmodel.MutationResult, error) {
	store.completed = input
	return invocationmodel.MutationResult{}, nil
}

type recordingExecutor struct {
	called  bool
	request invocationapp.CapabilityExecution
	outcome invocationapp.CapabilityOutcome
	err     error
}

type recordingExecutionAuthority struct {
	called bool
	permit invocationapp.ExecutionPermit
	err    error
}

func (authority *recordingExecutionAuthority) AuthorizeExecution(
	_ context.Context,
	_ invocationapp.ExecutionAuthorityInput,
) (invocationapp.ExecutionPermit, error) {
	authority.called = true
	return authority.permit, authority.err
}

func (executor *recordingExecutor) Execute(
	_ context.Context,
	request invocationapp.CapabilityExecution,
) (invocationapp.CapabilityOutcome, error) {
	executor.called = true
	executor.request = request
	return executor.outcome, executor.err
}

func TestInvocationWorkerRechecksRevocationBeforeProviderExecution(t *testing.T) {
	now := time.Date(2026, time.August, 2, 14, 0, 0, 0, time.UTC)
	store := &workerStore{found: true, claim: invocationmodel.ExecutionClaim{
		Invocation: invocationmodel.Invocation{
			InvocationID: "invocation-1", AccountID: "account-1",
			ConnectionID: "connection-1", Capability: "calendar.event.create",
			ResolutionID: "resolution-1", SurfaceKind: "personal",
			InputDigest: digestValue("input-1"), ConfirmationRef: "confirmation-1",
			PermitRef: "permit-1", IdempotencyKey: "invoke-1",
			Status: invocationmodel.StatusExecuting, Revision: 2,
		},
		PayloadRef: "protected://payload-1",
	}}
	connections := &connectionReader{connection: connectionmodel.Connection{
		ConnectionID: "connection-1", AccountID: "account-1",
		ConnectorID: "system_calendar", Status: connectionmodel.StatusActive,
		GrantedCapabilities: []string{"calendar.event.create"},
		Revision:            1,
	}}
	definition := definitionmodel.Definition{
		ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
		Capabilities:          []string{"calendar.event.create"},
		SupportedSurfaceKinds: []string{"personal"},
		ReleaseDigest:         digestValue("calendar-contract"),
	}
	grantSession, _ := authorizeWorkerInvocation(t, now, connections, definition, &store.claim.Invocation)
	connections.connection.Status = connectionmodel.StatusRevoked
	executor := &recordingExecutor{}
	authority := &recordingExecutionAuthority{}
	worker := invocationapp.NewInvocationWorker(
		store,
		grantSession,
		connections,
		definitionReader{definition: definition},
		authority,
		executor,
		"worker-1",
		time.Minute,
		func() time.Time { return now },
	)
	processed, err := worker.RunOnce(context.Background())
	if err != nil || !processed {
		t.Fatalf("run worker: processed=%v err=%v", processed, err)
	}
	if executor.called || authority.called {
		t.Fatal("revoked connection reached provider executor")
	}
	if store.completed.Status != invocationmodel.StatusFailed ||
		store.completed.NormalizedFailureCode != "connection_inactive" ||
		store.completed.RecoveryAction != "reconnect" {
		t.Fatalf("unexpected fail-closed terminal: %#v", store.completed)
	}
}

func TestInvocationWorkerPassesProtectedRefsOnlyToIntegrationExecutor(t *testing.T) {
	now := time.Date(2026, time.August, 2, 14, 5, 0, 0, time.UTC)
	store := &workerStore{found: true, claim: invocationmodel.ExecutionClaim{
		Invocation: invocationmodel.Invocation{
			InvocationID: "invocation-2", AccountID: "account-1",
			ConnectionID: "connection-1", Capability: "calendar.event.create",
			ResolutionID: "resolution-2", SurfaceKind: "personal",
			InputDigest: digestValue("input-2"), ConfirmationRef: "confirmation-2",
			PermitRef: "permit-2", IdempotencyKey: "invoke-2",
			ContinuationRef: "continuation-2",
			Status:          invocationmodel.StatusExecuting, Revision: 3,
		},
		PayloadRef: "protected://payload-2",
	}}
	connections := &connectionReader{connection: connectionmodel.Connection{
		ConnectionID: "connection-1", AccountID: "account-1",
		ConnectorID: "system_calendar", Status: connectionmodel.StatusActive,
		CredentialRef:       "protected://credential-1",
		GrantedCapabilities: []string{"calendar.event.create"},
		Revision:            1,
	}}
	definition := definitionmodel.Definition{
		ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
		Capabilities:          []string{"calendar.event.create"},
		SupportedSurfaceKinds: []string{"personal"},
		ReleaseDigest:         digestValue("calendar-contract"),
	}
	grantSession, _ := authorizeWorkerInvocation(t, now, connections, definition, &store.claim.Invocation)
	authority := &recordingExecutionAuthority{permit: invocationapp.ExecutionPermit{
		PermitRef: "permit-2", Digest: grantmodel.OpaqueDigest("permit-2"),
		ExpiresAt: now.Add(time.Minute),
	}}
	executor := &recordingExecutor{outcome: invocationapp.CapabilityOutcome{
		ResultRef:       "protected://result-2",
		ResultDigest:    "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		ContinuationRef: "protected://continuation/receipt-2",
	}}
	worker := invocationapp.NewInvocationWorker(
		store,
		grantSession,
		connections,
		definitionReader{definition: definition},
		authority,
		executor,
		"worker-1",
		time.Minute,
		func() time.Time { return now },
	)
	processed, err := worker.RunOnce(context.Background())
	if err != nil || !processed {
		t.Fatalf("run worker: processed=%v err=%v", processed, err)
	}
	if !executor.called || executor.request.CredentialRef != "protected://credential-1" ||
		executor.request.PayloadRef != "protected://payload-2" {
		t.Fatalf("protected executor request mismatch: %#v", executor.request)
	}
	if store.completed.Status != invocationmodel.StatusCompleted ||
		store.completed.ResultRef != "protected://result-2" ||
		store.completed.ContinuationRef != "protected://continuation/receipt-2" ||
		store.completed.RecoveryAction != "none" {
		t.Fatalf("unexpected completion: %#v", store.completed)
	}
}

func TestInvocationWorkerAuthorityFailureNeverCallsExecutor(t *testing.T) {
	now := time.Date(2026, time.August, 2, 14, 10, 0, 0, time.UTC)
	store := &workerStore{found: true, claim: invocationmodel.ExecutionClaim{
		Invocation: invocationmodel.Invocation{
			InvocationID: "invocation-3", AccountID: "account-1",
			ResolutionID: "resolution-3", ConnectionID: "connection-1",
			Capability: "calendar.event.create", SurfaceKind: "personal",
			InputDigest: digestValue("input-3"), ConfirmationRef: "confirmation-3",
			PermitRef: "permit-3", IdempotencyKey: "invoke-3",
			Status: invocationmodel.StatusExecuting, Revision: 2,
		},
		PayloadRef: "protected://payload-3",
	}}
	connections := &connectionReader{connection: connectionmodel.Connection{
		ConnectionID: "connection-1", AccountID: "account-1",
		ConnectorID: "system_calendar", Status: connectionmodel.StatusActive,
		CredentialRef:       "protected://credential-1",
		GrantedCapabilities: []string{"calendar.event.create"}, Revision: 1,
	}}
	definition := definitionmodel.Definition{
		ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
		Capabilities:          []string{"calendar.event.create"},
		SupportedSurfaceKinds: []string{"personal"},
		ReleaseDigest:         digestValue("calendar-contract"),
	}
	session, _ := authorizeWorkerInvocation(t, now, connections, definition, &store.claim.Invocation)
	authority := &recordingExecutionAuthority{err: errors.New("permit consumer unavailable")}
	executor := &recordingExecutor{}
	worker := invocationapp.NewInvocationWorker(
		store,
		session,
		connections,
		definitionReader{definition: definition},
		authority,
		executor,
		"worker-1",
		time.Minute,
		func() time.Time { return now },
	)
	processed, err := worker.RunOnce(context.Background())
	if err != nil || !processed {
		t.Fatalf("run worker: processed=%v err=%v", processed, err)
	}
	if !authority.called || executor.called {
		t.Fatalf("authority_called=%v executor_called=%v", authority.called, executor.called)
	}
	if store.completed.Status != invocationmodel.StatusFailed ||
		store.completed.NormalizedFailureCode != "provider_unavailable" {
		t.Fatalf("unexpected authority failure terminal: %#v", store.completed)
	}
}

func authorizeWorkerInvocation(
	t *testing.T,
	now time.Time,
	connections *connectionReader,
	definition definitionmodel.Definition,
	invocation *invocationmodel.Invocation,
) (*grantapp.CapabilityGrantSessionFacade, rtredis.Client) {
	t.Helper()
	client := rtredis.NewMemoryClient()
	store, err := grantpersistence.NewRedisSessionStore(client)
	if err != nil {
		t.Fatal(err)
	}
	unavailable := grantcandidate.NewUnavailableSources("not used by worker test")
	session := grantapp.NewCapabilityGrantSessionFacade(
		grantresolver.NewCandidateResolver(
			unavailable,
			grantcandidate.NewConnectorReaderSource(
				connections,
				definitionReader{definition: definition},
				func() time.Time { return now },
			),
			unavailable,
			unavailable,
			func() time.Time { return now },
		),
		store,
		func() time.Time { return now },
	)
	authorization, err := grantapp.NewTrustedRuntimeAuthorization(
		invocation.AccountID,
		"assistant-service",
	)
	if err != nil {
		t.Fatal(err)
	}
	resolved, err := session.AuthorizeFinalInput(
		context.Background(),
		authorization,
		grantapp.FinalAuthorizationInput{
			ResolutionID: invocation.ResolutionID, CapabilityKey: invocation.Capability,
			SurfaceKind: invocation.SurfaceKind, ConnectionRefs: []string{invocation.ConnectionID},
			BindingKind: grantmodel.BindingUserConnector, InputDigest: invocation.InputDigest,
			ConfirmationRef: invocation.ConfirmationRef, PermitRef: invocation.PermitRef,
			IdempotencyKey: invocation.IdempotencyKey,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	bindingDigest, err := grantmodel.BindingDigest(resolved)
	if err != nil {
		t.Fatal(err)
	}
	invocation.BindingDigest = bindingDigest
	invocation.ConfirmationDigest = grantmodel.OpaqueDigest(invocation.ConfirmationRef)
	invocation.PermitDigest = grantmodel.OpaqueDigest(invocation.PermitRef)
	invocation.IdempotencyDigest = grantmodel.OpaqueDigest(invocation.IdempotencyKey)
	return session, client
}

func TestInvocationWorkerRejectsSessionAuthorizedByForeignService(t *testing.T) {
	now := time.Date(2026, time.August, 2, 14, 15, 0, 0, time.UTC)
	store := &workerStore{found: true, claim: invocationmodel.ExecutionClaim{
		Invocation: invocationmodel.Invocation{
			InvocationID: "invocation-foreign", AccountID: "account-1",
			ResolutionID: "resolution-foreign", ConnectionID: "connection-1",
			Capability: "calendar.event.create", SurfaceKind: "personal",
			InputDigest: digestValue("input-foreign"), ConfirmationRef: "confirmation-foreign",
			PermitRef: "permit-foreign", IdempotencyKey: "invoke-foreign",
			Status: invocationmodel.StatusExecuting, Revision: 2,
		},
		PayloadRef: "protected://payload-foreign",
	}}
	connections := &connectionReader{connection: connectionmodel.Connection{
		ConnectionID: "connection-1", AccountID: "account-1",
		ConnectorID: "system_calendar", Status: connectionmodel.StatusActive,
		GrantedCapabilities: []string{"calendar.event.create"}, Revision: 1,
	}}
	definition := definitionmodel.Definition{
		ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
		Capabilities:          []string{"calendar.event.create"},
		SupportedSurfaceKinds: []string{"personal"},
		ReleaseDigest:         digestValue("calendar-contract"),
	}
	session, client := authorizeWorkerInvocation(
		t, now, connections, definition, &store.claim.Invocation,
	)
	key := "integration:capability-grant:resolution-foreign"
	raw, err := client.GetBytes(context.Background(), key)
	if err != nil {
		t.Fatal(err)
	}
	var persisted map[string]any
	if err := json.Unmarshal(raw, &persisted); err != nil {
		t.Fatal(err)
	}
	persisted["serviceActorDigest"] = grantmodel.OpaqueDigest("other-service")
	encoded, err := json.Marshal(persisted)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.Set(
		context.Background(), key, string(encoded), grantmodel.GrantTTL,
	); err != nil {
		t.Fatal(err)
	}
	authority := &recordingExecutionAuthority{}
	executor := &recordingExecutor{}
	worker := invocationapp.NewInvocationWorker(
		store, session, connections, definitionReader{definition: definition},
		authority, executor, "worker-1", time.Minute, func() time.Time { return now },
	)
	processed, err := worker.RunOnce(context.Background())
	if err != nil || !processed {
		t.Fatalf("run worker: processed=%v err=%v", processed, err)
	}
	if authority.called || executor.called {
		t.Fatal("foreign-service session reached execution authority or provider")
	}
	if store.completed.Status != invocationmodel.StatusFailed ||
		store.completed.NormalizedFailureCode != "authorization_invalid" {
		t.Fatalf("unexpected fail-closed terminal: %#v", store.completed)
	}
}

func TestInvocationCompleteRejectsSecretResultOnFailure(t *testing.T) {
	_, err := invocationmodel.NewCompleteInput(invocationmodel.CompleteInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		LeaseOwner: "worker-1", ExpectedRevision: 2,
		Status:                invocationmodel.StatusFailed,
		ResultRef:             "protected://must-not-survive",
		NormalizedFailureCode: "provider_unavailable", RecoveryAction: "retry",
		OccurredAt: time.Now().UTC(),
	})
	if !errors.Is(err, invocationmodel.ErrInvalidArgument) {
		t.Fatalf("failure resultRef must be rejected, got %v", err)
	}
}
