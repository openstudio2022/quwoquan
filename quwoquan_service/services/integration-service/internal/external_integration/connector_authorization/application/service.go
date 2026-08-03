package application

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/ports"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionports "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/ports"
)

const (
	defaultAuthorizationTTL = 10 * time.Minute
	defaultGrantReceiptTTL  = 5 * time.Minute
)

type OpaqueReferenceIssuer interface {
	Issue(string) (string, string, error)
}

type ProofVerifier interface {
	VerifyNative(context.Context, model.Authorization, string) (model.VerifiedProof, error)
	VerifyOAuth(context.Context, model.Authorization, string) (model.VerifiedProof, error)
}

type CommandFacade struct {
	store       ports.Store
	definitions definitionports.Reader
	issuer      OpaqueReferenceIssuer
	verifier    ProofVerifier
	now         func() time.Time
	newID       func() string
}

type QueryFacade struct {
	reader ports.Reader
}

func NewCommandFacade(
	store ports.Store,
	definitions definitionports.Reader,
	issuer OpaqueReferenceIssuer,
	verifier ProofVerifier,
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
		store:       store,
		definitions: definitions,
		issuer:      issuer,
		verifier:    verifier,
		now:         now,
		newID:       newID,
	}
}

func NewQueryFacade(reader ports.Reader) *QueryFacade {
	return &QueryFacade{reader: reader}
}

func (facade *CommandFacade) Start(
	ctx context.Context,
	input model.StartInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil || facade.definitions == nil || facade.issuer == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	definition, err := facade.definitions.Get(ctx, strings.TrimSpace(input.ConnectorID))
	if errors.Is(err, definitionmodel.ErrNotFound) {
		return model.MutationResult{}, model.ErrDefinitionNotFound
	}
	if err != nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	if definition.AuthorizationMode == definitionmodel.AuthorizationPublicLink {
		return model.MutationResult{}, model.ErrModeUnsupported
	}
	capabilities := model.NormalizeCapabilities(input.RequestedCapabilities)
	if len(capabilities) == 0 {
		return model.MutationResult{}, model.ErrInvalidArgument
	}
	for _, capability := range capabilities {
		if !definition.Grants(capability) {
			return model.MutationResult{}, model.ErrCapabilityDenied
		}
	}
	continuationRef, continuationDigest, err := facade.issuer.Issue("connector-continuation")
	if err != nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	now := facade.now().UTC()
	input.RequestedCapabilities = capabilities
	command, err := model.NewStartCommand(
		input,
		facade.newID(),
		definition.AuthorizationMode,
		continuationRef,
		continuationDigest,
		now,
		now.Add(defaultAuthorizationTTL),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Start(ctx, command)
}

func (facade *CommandFacade) CompleteNative(
	ctx context.Context,
	input model.CompleteInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	current, err := facade.store.Get(
		ctx,
		strings.TrimSpace(input.AccountID),
		strings.TrimSpace(input.AuthorizationID),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.complete(ctx, current, input, model.ModeDeviceNative)
}

func (facade *CommandFacade) CompleteOAuth(
	ctx context.Context,
	input model.CompleteInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	current, err := facade.store.GetByID(ctx, strings.TrimSpace(input.AuthorizationID))
	if err != nil {
		return model.MutationResult{}, err
	}
	input.AccountID = current.AccountID
	return facade.complete(ctx, current, input, model.ModeOAuth2)
}

func (facade *CommandFacade) complete(
	ctx context.Context,
	current model.Authorization,
	input model.CompleteInput,
	mode string,
) (model.MutationResult, error) {
	if facade.verifier == nil || facade.issuer == nil {
		return model.MutationResult{}, model.ErrProviderUnavailable
	}
	now := facade.now().UTC()
	commandDigest, err := model.CompletionCommandDigest(input, mode)
	if err != nil {
		return model.MutationResult{}, err
	}
	replay, found, err := facade.store.Replay(
		ctx,
		strings.TrimSpace(input.AccountID),
		strings.TrimSpace(input.IdempotencyKey),
		"verify",
		commandDigest,
	)
	if found || err != nil {
		return replay, err
	}
	if current.AuthorizationMode != mode {
		return model.MutationResult{}, model.ErrModeMismatch
	}
	if current.Revision != input.ExpectedRevision {
		return model.MutationResult{}, model.ErrRevisionConflict
	}
	if !current.IsPending(now) {
		if !current.ExpiresAt.After(now) {
			return model.MutationResult{}, model.ErrExpired
		}
		return model.MutationResult{}, model.ErrRevisionConflict
	}
	var proof model.VerifiedProof
	var proofErr error
	if mode == model.ModeDeviceNative {
		proof, proofErr = facade.verifier.VerifyNative(ctx, current, strings.TrimSpace(input.ProofRef))
	} else {
		proof, proofErr = facade.verifier.VerifyOAuth(ctx, current, strings.TrimSpace(input.ProofRef))
	}
	if proofErr != nil {
		if errors.Is(proofErr, model.ErrProviderUnavailable) {
			return model.MutationResult{}, model.ErrProviderUnavailable
		}
		if mode == model.ModeDeviceNative {
			return model.MutationResult{}, model.ErrNativeProofInvalid
		}
		return model.MutationResult{}, model.ErrOAuthCallbackInvalid
	}
	grantReceiptRef, grantReceiptDigest, err := facade.issuer.Issue("connector-grant")
	if err != nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	command, err := model.NewVerifyCommand(
		current,
		input,
		mode,
		proof,
		grantReceiptRef,
		grantReceiptDigest,
		commandDigest,
		now,
		now.Add(defaultGrantReceiptTTL),
	)
	if err != nil {
		return model.MutationResult{}, err
	}
	return facade.store.Verify(ctx, command)
}

func (facade *QueryFacade) Get(
	ctx context.Context,
	accountID string,
	authorizationID string,
) (model.Authorization, error) {
	if facade == nil || facade.reader == nil {
		return model.Authorization{}, model.ErrStorageUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	authorizationID = strings.TrimSpace(authorizationID)
	if accountID == "" || authorizationID == "" {
		return model.Authorization{}, model.ErrInvalidArgument
	}
	return facade.reader.Get(ctx, accountID, authorizationID)
}
