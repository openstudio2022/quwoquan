// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_invocation_test

import (
	"context"
	"errors"
	"testing"
	"time"

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
			Status: invocationmodel.StatusExecuting, Revision: 2,
		},
		PayloadRef: "protected://payload-1",
	}}
	connections := &connectionReader{connection: connectionmodel.Connection{
		ConnectionID: "connection-1", AccountID: "account-1",
		ConnectorID: "system_calendar", Status: connectionmodel.StatusRevoked,
		GrantedCapabilities: []string{"calendar.event.create"},
	}}
	executor := &recordingExecutor{}
	worker := invocationapp.NewInvocationWorker(
		store,
		connections,
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
			Capabilities: []string{"calendar.event.create"},
		}},
		executor,
		"worker-1",
		time.Minute,
		func() time.Time { return now },
	)
	processed, err := worker.RunOnce(context.Background())
	if err != nil || !processed {
		t.Fatalf("run worker: processed=%v err=%v", processed, err)
	}
	if executor.called {
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
	}}
	executor := &recordingExecutor{outcome: invocationapp.CapabilityOutcome{
		ResultRef:    "protected://result-2",
		ResultDigest: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
	}}
	worker := invocationapp.NewInvocationWorker(
		store,
		connections,
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
			Capabilities: []string{"calendar.event.create"},
		}},
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
		store.completed.RecoveryAction != "none" {
		t.Fatalf("unexpected completion: %#v", store.completed)
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
