package application

import (
	"context"
	"errors"
	"strings"
	"time"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	connectionports "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/ports"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionports "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/ports"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/ports"
)

type CapabilityExecution struct {
	InvocationID       string
	ResolutionID       string
	ConnectionID       string
	ConnectorID        string
	Capability         string
	CredentialRef      string
	PayloadRef         string
	ContinuationRef    string
	InputDigest        string
	BindingDigest      string
	ConfirmationDigest string
	PermitDigest       string
	IdempotencyDigest  string
	ExecutionPermit    ExecutionPermit
}

type CapabilityOutcome struct {
	ResultRef       string
	ResultDigest    string
	ContinuationRef string
}

type CapabilityExecutor interface {
	Execute(context.Context, CapabilityExecution) (CapabilityOutcome, error)
}

type ExecutionAuthorityInput struct {
	Invocation    model.Invocation
	Connection    connectionmodel.Connection
	Definition    definitionmodel.Definition
	PayloadRef    string
	Authorization grantapp.ValidatedFinalAuthorization
}

type ExecutionPermit struct {
	PermitRef string
	Digest    string
	ExpiresAt time.Time
}

type ExecutionAuthority interface {
	AuthorizeExecution(context.Context, ExecutionAuthorityInput) (ExecutionPermit, error)
}

type InvocationWorker struct {
	store          ports.WorkerStore
	authorizations *grantapp.CapabilityGrantSessionFacade
	connections    connectionports.Reader
	definitions    definitionports.Reader
	authority      ExecutionAuthority
	executor       CapabilityExecutor
	workerID       string
	leaseTTL       time.Duration
	now            func() time.Time
}

func NewInvocationWorker(
	store ports.WorkerStore,
	authorizations *grantapp.CapabilityGrantSessionFacade,
	connections connectionports.Reader,
	definitions definitionports.Reader,
	authority ExecutionAuthority,
	executor CapabilityExecutor,
	workerID string,
	leaseTTL time.Duration,
	now func() time.Time,
) *InvocationWorker {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &InvocationWorker{
		store: store, authorizations: authorizations,
		connections: connections, definitions: definitions, authority: authority,
		executor: executor, workerID: strings.TrimSpace(workerID),
		leaseTTL: leaseTTL, now: now,
	}
}

func (worker *InvocationWorker) RunOnce(ctx context.Context) (bool, error) {
	if worker == nil || worker.store == nil || worker.connections == nil ||
		worker.authorizations == nil || worker.definitions == nil ||
		worker.authority == nil || worker.executor == nil ||
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
	authorization, err := grantapp.NewTrustedRuntimeWorkerAuthorization(
		claim.Invocation.AccountID,
		grantapp.IntegrationServiceWorkerActorID,
	)
	if err != nil {
		return true, worker.fail(ctx, claim, "authorization_invalid", "retry")
	}
	validated, err := worker.authorizations.RevalidateFinalAuthorizationForWorker(
		ctx,
		authorization,
		grantapp.FinalAuthorizationInput{
			ResolutionID:    claim.Invocation.ResolutionID,
			CapabilityKey:   claim.Invocation.Capability,
			SurfaceKind:     claim.Invocation.SurfaceKind,
			ConnectionRefs:  []string{claim.Invocation.ConnectionID},
			BindingKind:     grantmodel.BindingUserConnector,
			InputDigest:     claim.Invocation.InputDigest,
			ConfirmationRef: claim.Invocation.ConfirmationRef,
			PermitRef:       claim.Invocation.PermitRef,
			IdempotencyKey:  claim.Invocation.IdempotencyKey,
		},
	)
	if err != nil {
		if errors.Is(err, grantmodel.ErrConnectorRevoked) ||
			errors.Is(err, grantmodel.ErrConnectorExpired) ||
			errors.Is(err, grantapp.ErrCapabilityGrantSessionExpired) {
			return true, worker.fail(ctx, claim, "connection_inactive", "reconnect")
		}
		return true, worker.fail(ctx, claim, "authorization_invalid", "retry")
	}
	if validated.Grant.UserConnector == nil ||
		validated.Grant.UserConnector.ConnectionID != claim.Invocation.ConnectionID ||
		validated.Session.BindingDigest != claim.Invocation.BindingDigest {
		return true, worker.fail(ctx, claim, "authorization_changed", "review_permissions")
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
	if connection.Revision != validated.Grant.UserConnector.Revision ||
		connection.ConnectorID != validated.Grant.UserConnector.ConnectorID {
		return true, worker.fail(ctx, claim, "authorization_changed", "review_permissions")
	}
	definition, err := worker.definitions.Get(ctx, connection.ConnectorID)
	if errors.Is(err, definitionmodel.ErrNotFound) ||
		(err == nil && !definition.Grants(claim.Invocation.Capability)) {
		return true, worker.fail(ctx, claim, "capability_denied", "review_permissions")
	}
	if err != nil {
		return true, err
	}
	if definition.ReleaseDigest != validated.Grant.UserConnector.ContractDigest {
		return true, worker.fail(ctx, claim, "authorization_changed", "review_permissions")
	}
	permit, err := worker.authority.AuthorizeExecution(ctx, ExecutionAuthorityInput{
		Invocation: claim.Invocation, Connection: connection, Definition: definition,
		PayloadRef: claim.PayloadRef, Authorization: validated,
	})
	if err != nil || strings.TrimSpace(permit.PermitRef) == "" ||
		strings.TrimSpace(permit.Digest) != claim.Invocation.PermitDigest ||
		!permit.ExpiresAt.After(worker.now().UTC()) ||
		grantmodel.OpaqueDigest(permit.PermitRef) != claim.Invocation.PermitDigest {
		return true, worker.fail(ctx, claim, "provider_unavailable", "retry")
	}

	outcome, err := worker.executor.Execute(ctx, CapabilityExecution{
		InvocationID:       claim.Invocation.InvocationID,
		ResolutionID:       claim.Invocation.ResolutionID,
		ConnectionID:       claim.Invocation.ConnectionID,
		ConnectorID:        connection.ConnectorID,
		Capability:         claim.Invocation.Capability,
		CredentialRef:      connection.CredentialRef,
		PayloadRef:         claim.PayloadRef,
		ContinuationRef:    claim.Invocation.ContinuationRef,
		InputDigest:        claim.Invocation.InputDigest,
		BindingDigest:      claim.Invocation.BindingDigest,
		ConfirmationDigest: claim.Invocation.ConfirmationDigest,
		PermitDigest:       claim.Invocation.PermitDigest,
		IdempotencyDigest:  claim.Invocation.IdempotencyDigest,
		ExecutionPermit:    permit,
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
		ContinuationRef:  outcome.ContinuationRef,
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
