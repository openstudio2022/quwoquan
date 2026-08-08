package application

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/ports"
)

type CommandFacade struct {
	store          ports.Store
	authorizations *grantapp.CapabilityGrantSessionFacade
	now            func() time.Time
	newID          func() string
}

type QueryFacade struct {
	reader ports.Reader
}

func NewCommandFacade(
	store ports.Store,
	authorizations *grantapp.CapabilityGrantSessionFacade,
	now func() time.Time,
	newID func() string,
) *CommandFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	if newID == nil {
		newID = uuid.NewString
	}
	return &CommandFacade{
		store: store, authorizations: authorizations, now: now, newID: newID,
	}
}

func NewQueryFacade(reader ports.Reader) *QueryFacade {
	return &QueryFacade{reader: reader}
}

func (facade *CommandFacade) Accept(
	ctx context.Context,
	authorization grantapp.TrustedRuntimeAuthorization,
	input model.AcceptInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil || facade.authorizations == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	now := facade.now()
	resolved, err := facade.authorizations.AuthorizeFinalInput(
		ctx,
		authorization,
		grantapp.FinalAuthorizationInput{
			ResolutionID:    strings.TrimSpace(input.ResolutionID),
			CapabilityKey:   strings.TrimSpace(input.Capability),
			SurfaceKind:     strings.TrimSpace(input.SurfaceKind),
			ConnectionRefs:  []string{strings.TrimSpace(input.ConnectionID)},
			BindingKind:     grantmodel.BindingUserConnector,
			InputDigest:     strings.TrimSpace(input.InputDigest),
			ConfirmationRef: strings.TrimSpace(input.ConfirmationRef),
			PermitRef:       strings.TrimSpace(input.PermitRef),
			IdempotencyKey:  strings.TrimSpace(input.IdempotencyKey),
		},
	)
	if err != nil {
		return model.MutationResult{}, mapGrantError(err)
	}
	if resolved.UserConnector == nil ||
		resolved.BindingKind != grantmodel.BindingUserConnector ||
		resolved.UserConnector.ConnectionID != strings.TrimSpace(input.ConnectionID) {
		return model.MutationResult{}, model.ErrCapabilityDenied
	}
	bindingDigest, err := grantmodel.BindingDigest(resolved)
	if err != nil {
		return model.MutationResult{}, model.ErrCapabilityDenied
	}
	input.InvocationID = facade.newID()
	input.AccountID = authorization.AccountID
	input.BindingDigest = bindingDigest
	input.OccurredAt = now
	command, err := model.NewAcceptCommand(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Accept(ctx, command)
}

func (facade *CommandFacade) Continue(
	ctx context.Context,
	authorization grantapp.TrustedRuntimeAuthorization,
	input model.ContinueInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil || facade.authorizations == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	input.AccountID = authorization.AccountID
	current, err := facade.store.Get(
		ctx,
		strings.TrimSpace(input.AccountID),
		strings.TrimSpace(input.InvocationID),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	if strings.TrimSpace(input.ConfirmationRef) != current.ConfirmationRef {
		return model.MutationResult{}, model.ErrInvalidArgument
	}
	if _, err := facade.authorizations.RevalidateFinalAuthorization(
		ctx,
		authorization,
		grantapp.FinalAuthorizationInput{
			ResolutionID:    current.ResolutionID,
			CapabilityKey:   current.Capability,
			SurfaceKind:     current.SurfaceKind,
			ConnectionRefs:  []string{current.ConnectionID},
			BindingKind:     grantmodel.BindingUserConnector,
			InputDigest:     current.InputDigest,
			ConfirmationRef: current.ConfirmationRef,
			PermitRef:       current.PermitRef,
			IdempotencyKey:  current.IdempotencyKey,
		},
	); err != nil {
		return model.MutationResult{}, mapGrantError(err)
	}
	input.OccurredAt = facade.now()
	normalized, err := model.NewContinueInput(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Continue(ctx, normalized)
}

func mapGrantError(err error) error {
	switch {
	case errors.Is(err, grantmodel.ErrInvalidRequirement),
		errors.Is(err, grantmodel.ErrConfirmationRequired),
		errors.Is(err, grantmodel.ErrPermitRequired),
		errors.Is(err, grantmodel.ErrIdempotencyRequired),
		errors.Is(err, grantapp.ErrRuntimeAuthorizationInvalid),
		errors.Is(err, grantapp.ErrFinalAuthorizationMismatch):
		return model.ErrInvalidArgument
	case errors.Is(err, grantmodel.ErrConnectorRevoked),
		errors.Is(err, grantmodel.ErrConnectorExpired),
		errors.Is(err, grantapp.ErrCapabilityGrantSessionExpired):
		return model.ErrConnectionInactive
	case errors.Is(err, grantmodel.ErrConnectorCapability),
		errors.Is(err, grantmodel.ErrConnectorSurfaceDenied),
		errors.Is(err, grantmodel.ErrCapabilityGrantRequired),
		errors.Is(err, grantapp.ErrCapabilityGrantSessionNotFound):
		return model.ErrCapabilityDenied
	default:
		return model.ErrStorageUnavailable
	}
}

func (facade *QueryFacade) Get(
	ctx context.Context,
	accountID string,
	invocationID string,
) (model.Invocation, error) {
	if facade == nil || facade.reader == nil {
		return model.Invocation{}, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	invocationID = strings.TrimSpace(invocationID)
	if accountID == "" || invocationID == "" {
		return model.Invocation{}, model.ErrInvalidArgument
	}
	return facade.reader.Get(ctx, accountID, invocationID)
}

func (facade *QueryFacade) List(
	ctx context.Context,
	accountID string,
	connectionID string,
	limit int,
) ([]model.Invocation, error) {
	if facade == nil || facade.reader == nil {
		return nil, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	if accountID == "" || limit <= 0 || limit > 100 {
		return nil, model.ErrInvalidArgument
	}
	return facade.reader.List(ctx, accountID, strings.TrimSpace(connectionID), limit)
}
