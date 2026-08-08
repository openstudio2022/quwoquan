package application

import (
	"context"
	"errors"
	"strings"
	"time"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
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
	reader ports.Reader
	grants grantapp.ConnectorGrantResolver
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
	return &QueryFacade{reader: reader}
}

func NewCapabilityQueryFacade(
	reader ports.Reader,
	grants grantapp.ConnectorGrantResolver,
) *QueryFacade {
	return &QueryFacade{reader: reader, grants: grants}
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
	if definition.AuthorizationMode == definitionmodel.AuthorizationOAuth2 &&
		!model.ValidProviderAccountSubjectDigest(grant.ProviderAccountSubjectDigest) {
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
	authorization grantapp.TrustedRuntimeAuthorization,
	input model.ResolveCapabilityInput,
) (model.CapabilityGrantDecision, error) {
	if facade == nil || facade.grants == nil {
		return model.CapabilityGrantDecision{}, model.ErrStorageUnavailable
	}
	normalized, err := model.NormalizeResolveCapabilityInput(input)
	if err != nil {
		return model.CapabilityGrantDecision{}, err
	}
	decision, err := facade.grants.ResolveConnectorGrant(
		ctx,
		authorization,
		grantapp.ConnectorResolutionRequest{
			ResolutionID:   normalized.ResolutionID,
			CapabilityKey:  normalized.CapabilityKey,
			SurfaceKind:    normalized.SurfaceKind,
			ConnectionRefs: normalized.ConnectionRefs,
		},
	)
	if err != nil {
		return model.CapabilityGrantDecision{}, err
	}
	return model.CapabilityGrantDecision{
		Allowed:       decision.Allowed,
		CapabilityKey: decision.CapabilityKey,
		SurfaceKind:   decision.SurfaceKind,
		ConnectionID:  decision.ConnectionID,
		ConnectorID:   decision.ConnectorID,
		FreshnessAt:   decision.FreshnessAt,
		ExpiresAt:     decision.ExpiresAt,
		Reason:        decision.Reason,
	}, nil
}
