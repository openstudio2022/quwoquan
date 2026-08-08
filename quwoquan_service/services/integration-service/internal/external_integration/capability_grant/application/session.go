package application

import (
	"context"
	"errors"
	"strings"
	"time"

	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
)

var ErrCapabilityGrantSessionUnavailable = errors.New(
	"capability grant session is unavailable",
)

var (
	ErrCapabilityGrantSessionExpired = errors.New("capability grant session expired")
	ErrFinalAuthorizationMismatch    = errors.New("capability grant final authorization mismatch")
)

// CapabilityGrantSessionFacade is the sole typed runtime entrypoint for the
// short-lived CapabilityGrant session. Candidate collection stays behind the
// ResolverPort, so callers cannot inject a universal connector candidate map.
type CapabilityGrantSessionFacade struct {
	resolver ResolverPort
	store    SessionStore
	now      func() time.Time
}

// FinalAuthorizationInput is the complete execution boundary. Protected
// references are used only to recompute their digests; SessionStore never
// persists their raw values.
type FinalAuthorizationInput struct {
	ResolutionID    string
	CapabilityKey   string
	SurfaceKind     string
	ConnectionRefs  []string
	BindingKind     grantmodel.BindingKind
	InputDigest     string
	ConfirmationRef string
	PermitRef       string
	IdempotencyKey  string
}

type ValidatedFinalAuthorization struct {
	Session StoredSession
	Grant   grantmodel.ResolvedCapabilityGrant
}

func (facade *CapabilityGrantSessionFacade) ResolveConnectorGrant(
	ctx context.Context,
	authorization TrustedRuntimeAuthorization,
	request ConnectorResolutionRequest,
) (ConnectorGrantDecision, error) {
	if strings.TrimSpace(authorization.AccountID) == "" ||
		strings.TrimSpace(authorization.ServiceActorID) == "" {
		return ConnectorGrantDecision{}, ErrRuntimeAuthorizationInvalid
	}
	decision := ConnectorGrantDecision{
		CapabilityKey: strings.TrimSpace(request.CapabilityKey),
		SurfaceKind:   strings.TrimSpace(request.SurfaceKind),
		Reason:        "no_connection",
	}
	resolved, err := facade.Resolve(ctx, grantmodel.Requirement{
		ResolutionID:    strings.TrimSpace(request.ResolutionID),
		AccountID:       strings.TrimSpace(authorization.AccountID),
		CapabilityKey:   decision.CapabilityKey,
		SurfaceKind:     decision.SurfaceKind,
		ConnectionRefs:  append([]string(nil), request.ConnectionRefs...),
		BindingPriority: []grantmodel.BindingKind{grantmodel.BindingUserConnector},
	})
	if err != nil {
		switch {
		case errors.Is(err, grantmodel.ErrCapabilityGrantRequired):
			return decision, nil
		case errors.Is(err, grantmodel.ErrConnectorRevoked),
			errors.Is(err, grantmodel.ErrConnectorExpired):
			decision.Reason = "connection_inactive"
			return decision, nil
		case errors.Is(err, grantmodel.ErrConnectorCapability):
			decision.Reason = "capability_denied"
			return decision, nil
		case errors.Is(err, grantmodel.ErrConnectorSurfaceDenied):
			decision.Reason = "surface_denied"
			return decision, nil
		default:
			return ConnectorGrantDecision{}, err
		}
	}
	if resolved.UserConnector == nil ||
		resolved.BindingKind != grantmodel.BindingUserConnector ||
		resolved.ExpiresAt == nil {
		return ConnectorGrantDecision{}, grantmodel.ErrInvalidResolvedGrant
	}
	decision.Allowed = true
	decision.ConnectionID = resolved.UserConnector.ConnectionID
	decision.ConnectorID = resolved.UserConnector.ConnectorID
	freshnessAt := resolved.UserConnector.FreshnessAt.UTC()
	expiresAt := resolved.ExpiresAt.UTC()
	decision.FreshnessAt = &freshnessAt
	decision.ExpiresAt = &expiresAt
	decision.Reason = "allowed"
	return decision, nil
}

var _ ConnectorGrantResolver = (*CapabilityGrantSessionFacade)(nil)

func NewCapabilityGrantSessionFacade(
	resolver ResolverPort,
	store SessionStore,
	nowFunctions ...func() time.Time,
) *CapabilityGrantSessionFacade {
	now := func() time.Time { return time.Now().UTC() }
	if len(nowFunctions) == 1 && nowFunctions[0] != nil {
		now = nowFunctions[0]
	}
	return &CapabilityGrantSessionFacade{resolver: resolver, store: store, now: now}
}

func (facade *CapabilityGrantSessionFacade) Resolve(
	ctx context.Context,
	requirement grantmodel.Requirement,
) (grantmodel.ResolvedCapabilityGrant, error) {
	if facade == nil || facade.resolver == nil || facade.store == nil || ctx == nil {
		return grantmodel.ResolvedCapabilityGrant{}, ErrCapabilityGrantSessionUnavailable
	}
	if err := ctx.Err(); err != nil {
		return grantmodel.ResolvedCapabilityGrant{}, err
	}
	resolved, err := facade.resolver.ResolveCapabilityGrant(ctx, requirement)
	if err != nil {
		return grantmodel.ResolvedCapabilityGrant{}, err
	}
	if err := facade.store.Save(ctx, resolved); err != nil {
		return grantmodel.ResolvedCapabilityGrant{}, ErrCapabilityGrantSessionUnavailable
	}
	return resolved, nil
}

// AuthorizeFinalInput resolves and persists the execution-specific grant. A
// write authorization always binds the final input, confirmation, permit and
// idempotency key before an invocation can be accepted.
func (facade *CapabilityGrantSessionFacade) AuthorizeFinalInput(
	ctx context.Context,
	authorization TrustedRuntimeAuthorization,
	input FinalAuthorizationInput,
) (grantmodel.ResolvedCapabilityGrant, error) {
	if strings.TrimSpace(authorization.AccountID) == "" ||
		strings.TrimSpace(authorization.ServiceActorID) == "" {
		return grantmodel.ResolvedCapabilityGrant{}, ErrRuntimeAuthorizationInvalid
	}
	return facade.Resolve(ctx, finalRequirement(authorization, input))
}

// RevalidateFinalAuthorization loads the immutable session without renewing
// its TTL, checks the exact final-input bindings, and resolves the current
// candidate again. Revocation, expiry, probe failure or contract-digest drift
// therefore blocks execution before the Provider side effect.
func (facade *CapabilityGrantSessionFacade) RevalidateFinalAuthorization(
	ctx context.Context,
	authorization TrustedRuntimeAuthorization,
	input FinalAuthorizationInput,
) (ValidatedFinalAuthorization, error) {
	if strings.TrimSpace(authorization.AccountID) == "" ||
		strings.TrimSpace(authorization.ServiceActorID) == "" {
		return ValidatedFinalAuthorization{}, ErrRuntimeAuthorizationInvalid
	}
	return facade.revalidateFinalAuthorization(
		ctx,
		strings.TrimSpace(authorization.AccountID),
		grantmodel.OpaqueDigest(authorization.ServiceActorID),
		input,
	)
}

// RevalidateFinalAuthorizationForWorker is the only internal-worker bridge.
// It does not accept an arbitrary service principal: the worker identity is a
// closed constant, and the loaded session must have been created from the
// independently verified Assistant service actor plus a real account subject.
func (facade *CapabilityGrantSessionFacade) RevalidateFinalAuthorizationForWorker(
	ctx context.Context,
	authorization TrustedRuntimeWorkerAuthorization,
	input FinalAuthorizationInput,
) (ValidatedFinalAuthorization, error) {
	if strings.TrimSpace(authorization.AccountID) == "" ||
		authorization.WorkerActorID != IntegrationServiceWorkerActorID {
		return ValidatedFinalAuthorization{}, ErrRuntimeAuthorizationInvalid
	}
	return facade.revalidateFinalAuthorization(
		ctx,
		strings.TrimSpace(authorization.AccountID),
		grantmodel.OpaqueDigest(AssistantServiceActorID),
		input,
	)
}

func (facade *CapabilityGrantSessionFacade) revalidateFinalAuthorization(
	ctx context.Context,
	accountID string,
	expectedServiceActorDigest string,
	input FinalAuthorizationInput,
) (ValidatedFinalAuthorization, error) {
	if facade == nil || facade.resolver == nil || facade.store == nil ||
		facade.now == nil || ctx == nil ||
		!grantmodel.IsValidDigest(expectedServiceActorDigest) {
		return ValidatedFinalAuthorization{}, ErrCapabilityGrantSessionUnavailable
	}
	stored, err := facade.store.Load(ctx, strings.TrimSpace(input.ResolutionID))
	if err != nil {
		return ValidatedFinalAuthorization{}, err
	}
	now := facade.now().UTC()
	if !stored.ExpiresAt.After(now) {
		return ValidatedFinalAuthorization{}, ErrCapabilityGrantSessionExpired
	}
	if stored.AccountDigest != grantmodel.OpaqueDigest(accountID) ||
		stored.ServiceActorDigest != expectedServiceActorDigest ||
		stored.CapabilityKey != strings.TrimSpace(input.CapabilityKey) ||
		stored.SurfaceKind != strings.TrimSpace(input.SurfaceKind) ||
		stored.BindingKind != input.BindingKind ||
		stored.InputDigest != strings.TrimSpace(input.InputDigest) ||
		stored.ConfirmationDigest != grantmodel.OpaqueDigest(input.ConfirmationRef) ||
		stored.PermitDigest != grantmodel.OpaqueDigest(input.PermitRef) ||
		stored.IdempotencyDigest != grantmodel.OpaqueDigest(input.IdempotencyKey) {
		return ValidatedFinalAuthorization{}, ErrFinalAuthorizationMismatch
	}
	resolved, err := facade.resolver.ResolveCapabilityGrant(
		ctx,
		finalRequirement(TrustedRuntimeAuthorization{
			AccountID: accountID, ServiceActorID: AssistantServiceActorID,
		}, input),
	)
	if err != nil {
		return ValidatedFinalAuthorization{}, err
	}
	bindingDigest, err := grantmodel.BindingDigest(resolved)
	if err != nil || bindingDigest != stored.BindingDigest {
		return ValidatedFinalAuthorization{}, ErrFinalAuthorizationMismatch
	}
	return ValidatedFinalAuthorization{Session: stored, Grant: resolved}, nil
}

func finalRequirement(
	authorization TrustedRuntimeAuthorization,
	input FinalAuthorizationInput,
) grantmodel.Requirement {
	return grantmodel.Requirement{
		ResolutionID:       strings.TrimSpace(input.ResolutionID),
		AccountID:          strings.TrimSpace(authorization.AccountID),
		ServiceActorDigest: grantmodel.OpaqueDigest(authorization.ServiceActorID),
		CapabilityKey:      strings.TrimSpace(input.CapabilityKey),
		SurfaceKind:        strings.TrimSpace(input.SurfaceKind),
		ConnectionRefs:     append([]string(nil), input.ConnectionRefs...),
		BindingPriority:    []grantmodel.BindingKind{input.BindingKind},
		Write:              true,
		ConfirmationRef:    strings.TrimSpace(input.ConfirmationRef),
		PermitRef:          strings.TrimSpace(input.PermitRef),
		IdempotencyKey:     strings.TrimSpace(input.IdempotencyKey),
		InputDigest:        strings.TrimSpace(input.InputDigest),
	}
}
