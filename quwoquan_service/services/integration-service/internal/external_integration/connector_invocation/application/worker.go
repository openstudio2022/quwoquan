package application

import (
	"context"
	"errors"
	"strings"
	"time"

	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	connectionports "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/ports"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionports "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/ports"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/ports"
)

type CapabilityExecution struct {
	InvocationID    string
	ConnectionID    string
	ConnectorID     string
	Capability      string
	CredentialRef   string
	PayloadRef      string
	ContinuationRef string
}

type CapabilityOutcome struct {
	ResultRef    string
	ResultDigest string
}

type CapabilityExecutor interface {
	Execute(context.Context, CapabilityExecution) (CapabilityOutcome, error)
}

type InvocationWorker struct {
	store       ports.WorkerStore
	connections connectionports.Reader
	definitions definitionports.Reader
	executor    CapabilityExecutor
	workerID    string
	leaseTTL    time.Duration
	now         func() time.Time
}

func NewInvocationWorker(
	store ports.WorkerStore,
	connections connectionports.Reader,
	definitions definitionports.Reader,
	executor CapabilityExecutor,
	workerID string,
	leaseTTL time.Duration,
	now func() time.Time,
) *InvocationWorker {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &InvocationWorker{
		store: store, connections: connections, definitions: definitions,
		executor: executor, workerID: strings.TrimSpace(workerID),
		leaseTTL: leaseTTL, now: now,
	}
}

func (worker *InvocationWorker) RunOnce(ctx context.Context) (bool, error) {
	if worker == nil || worker.store == nil || worker.connections == nil ||
		worker.definitions == nil || worker.executor == nil ||
		worker.workerID == "" || worker.leaseTTL <= 0 {
		return false, model.ErrStorageUnavailable
	}
	claim, found, err := worker.store.ClaimNext(
		ctx,
		worker.workerID,
		worker.now().UTC(),
		worker.leaseTTL,
	)
	if err != nil || !found {
		return found, err
	}

	connection, err := worker.connections.Get(
		ctx,
		claim.Invocation.AccountID,
		claim.Invocation.ConnectionID,
	)
	if errors.Is(err, connectionmodel.ErrNotFound) ||
		(err == nil && !connection.IsActive(worker.now())) {
		return true, worker.fail(ctx, claim, "connection_inactive", "reconnect")
	}
	if err != nil {
		return true, err
	}
	if !connection.Grants(claim.Invocation.Capability) {
		return true, worker.fail(ctx, claim, "capability_denied", "review_permissions")
	}
	definition, err := worker.definitions.Get(ctx, connection.ConnectorID)
	if errors.Is(err, definitionmodel.ErrNotFound) ||
		(err == nil && !definition.Grants(claim.Invocation.Capability)) {
		return true, worker.fail(ctx, claim, "capability_denied", "review_permissions")
	}
	if err != nil {
		return true, err
	}

	outcome, err := worker.executor.Execute(ctx, CapabilityExecution{
		InvocationID:    claim.Invocation.InvocationID,
		ConnectionID:    claim.Invocation.ConnectionID,
		ConnectorID:     connection.ConnectorID,
		Capability:      claim.Invocation.Capability,
		CredentialRef:   connection.CredentialRef,
		PayloadRef:      claim.PayloadRef,
		ContinuationRef: claim.Invocation.ContinuationRef,
	})
	if err != nil {
		return true, worker.fail(ctx, claim, "provider_unavailable", "retry")
	}
	completed, err := model.NewCompleteInput(model.CompleteInput{
		InvocationID:     claim.Invocation.InvocationID,
		AccountID:        claim.Invocation.AccountID,
		LeaseOwner:       worker.workerID,
		ExpectedRevision: claim.Invocation.Revision,
		Status:           model.StatusCompleted,
		ResultRef:        outcome.ResultRef,
		ResultDigest:     outcome.ResultDigest,
		RecoveryAction:   "none",
		OccurredAt:       worker.now(),
	})
	if err != nil {
		return true, worker.fail(ctx, claim, "provider_protocol_invalid", "retry")
	}
	_, err = worker.store.Complete(ctx, completed)
	return true, err
}

func (worker *InvocationWorker) fail(
	ctx context.Context,
	claim model.ExecutionClaim,
	failureCode string,
	recoveryAction string,
) error {
	input, err := model.NewCompleteInput(model.CompleteInput{
		InvocationID:          claim.Invocation.InvocationID,
		AccountID:             claim.Invocation.AccountID,
		LeaseOwner:            worker.workerID,
		ExpectedRevision:      claim.Invocation.Revision,
		Status:                model.StatusFailed,
		NormalizedFailureCode: failureCode,
		RecoveryAction:        recoveryAction,
		OccurredAt:            worker.now(),
	})
	if err != nil {
		return err
	}
	_, err = worker.store.Complete(ctx, input)
	return err
}
