package application

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/ports"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionports "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/ports"
)

type GrantReceiptVerifier interface {
	Verify(
		context.Context,
		string,
		definitionmodel.Definition,
		string,
		[]string,
	) (model.VerifiedGrant, error)
}

type CommandFacade struct {
	store       ports.Store
	definitions definitionports.Reader
	verifier    GrantReceiptVerifier
	now         func() time.Time
}

type QueryFacade struct {
	reader      ports.Reader
	definitions definitionports.Reader
	now         func() time.Time
}

func NewCommandFacade(
	store ports.Store,
	definitions definitionports.Reader,
	verifier GrantReceiptVerifier,
	now func() time.Time,
) *CommandFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &CommandFacade{
		store: store, definitions: definitions, verifier: verifier, now: now,
	}
}

func NewQueryFacade(reader ports.Reader) *QueryFacade {
	return &QueryFacade{
		reader: reader,
		now: func() time.Time { return time.Now().UTC() },
	}
}

func NewCapabilityQueryFacade(
	reader ports.Reader,
	definitions definitionports.Reader,
	now func() time.Time,
) *QueryFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &QueryFacade{reader: reader, definitions: definitions, now: now}
}

func (facade *CommandFacade) Create(
	ctx context.Context,
	input model.CreateInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil || facade.definitions == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	commandDigest, err := model.CreateCommandDigest(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	replay, found, err := facade.store.Replay(
		ctx,
		strings.TrimSpace(input.AccountID),
		strings.TrimSpace(input.IdempotencyKey),
		"create",
		commandDigest,
	)
	if found || err != nil {
		return replay, err
	}
	definition, err := facade.definitions.Get(ctx, strings.TrimSpace(input.ConnectorID))
	if errors.Is(err, definitionmodel.ErrNotFound) {
		return model.MutationResult{}, model.ErrDefinitionNotFound
	}
	if err != nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	for _, capability := range input.RequestedCapabilities {
		if !definition.Grants(strings.TrimSpace(capability)) {
			return model.MutationResult{}, model.ErrCapabilityDenied
		}
	}
	if facade.verifier == nil {
		return model.MutationResult{}, model.ErrGrantReceiptInvalid
	}
	grant, err := facade.verifier.Verify(
		ctx,
		strings.TrimSpace(input.AccountID),
		definition,
		strings.TrimSpace(input.GrantReceiptRef),
		input.RequestedCapabilities,
	)
	if err != nil {
		return model.MutationResult{}, model.ErrGrantReceiptInvalid
	}
	command, err := model.NewCreateCommand(input, grant, facade.now())
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Create(ctx, command)
}

func (facade *CommandFacade) Revoke(
	ctx context.Context,
	input model.RevokeInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	input.OccurredAt = facade.now()
	normalized, err := model.NewRevokeInput(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Revoke(ctx, normalized)
}

func (facade *QueryFacade) Get(
	ctx context.Context,
	accountID string,
	connectionID string,
) (model.Connection, error) {
	if facade == nil || facade.reader == nil {
		return model.Connection{}, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	connectionID = strings.TrimSpace(connectionID)
	if accountID == "" || connectionID == "" {
		return model.Connection{}, model.ErrInvalidArgument
	}
	return facade.reader.Get(ctx, accountID, connectionID)
}

func (facade *QueryFacade) List(
	ctx context.Context,
	accountID string,
	limit int,
) ([]model.Connection, error) {
	if facade == nil || facade.reader == nil {
		return nil, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	if accountID == "" || limit <= 0 || limit > 100 {
		return nil, model.ErrInvalidArgument
	}
	return facade.reader.List(ctx, accountID, limit)
}

func (facade *QueryFacade) ResolveCapability(
	ctx context.Context,
	input model.ResolveCapabilityInput,
) (model.CapabilityGrantDecision, error) {
	if facade == nil || facade.reader == nil || facade.definitions == nil || facade.now == nil {
		return model.CapabilityGrantDecision{}, model.ErrStorageUnavailable
	}
	normalized, err := model.NormalizeResolveCapabilityInput(input)
	if err != nil {
		return model.CapabilityGrantDecision{}, err
	}
	decision := model.CapabilityGrantDecision{
		CapabilityKey: normalized.CapabilityKey,
		SurfaceKind: normalized.SurfaceKind,
		Reason: model.CapabilityReasonNoConnection,
	}
	now := facade.now().UTC()
	for _, connectionRef := range normalized.ConnectionRefs {
		connection, readErr := facade.reader.Get(ctx, normalized.AccountID, connectionRef)
		if errors.Is(readErr, model.ErrNotFound) {
			continue
		}
		if readErr != nil {
			return model.CapabilityGrantDecision{}, model.ErrStorageUnavailable
		}
		if !connection.IsActive(now) {
			decision.Reason = model.CapabilityReasonConnectionInactive
			continue
		}
		if !connection.Grants(normalized.CapabilityKey) {
			decision.Reason = model.CapabilityReasonCapabilityDenied
			continue
		}
		definition, definitionErr := facade.definitions.Get(ctx, connection.ConnectorID)
		if errors.Is(definitionErr, definitionmodel.ErrNotFound) {
			decision.Reason = model.CapabilityReasonDefinitionMissing
			continue
		}
		if definitionErr != nil {
			return model.CapabilityGrantDecision{}, model.ErrStorageUnavailable
		}
		if !definition.Grants(normalized.CapabilityKey) {
			decision.Reason = model.CapabilityReasonCapabilityDenied
			continue
		}
		if !definition.SupportsSurface(normalized.SurfaceKind) {
			decision.Reason = model.CapabilityReasonSurfaceDenied
			continue
		}
		freshness := connection.FreshnessAt.UTC()
		decision.Allowed = true
		decision.ConnectionID = connection.ConnectionID
		decision.ConnectorID = connection.ConnectorID
		decision.FreshnessAt = &freshness
		decision.ExpiresAt = normalizeDecisionTime(connection.ExpiresAt)
		decision.Reason = model.CapabilityReasonAllowed
		return decision, nil
	}
	return decision, nil
}

func normalizeDecisionTime(value *time.Time) *time.Time {
	if value == nil || value.IsZero() {
		return nil
	}
	normalized := value.UTC()
	return &normalized
}
