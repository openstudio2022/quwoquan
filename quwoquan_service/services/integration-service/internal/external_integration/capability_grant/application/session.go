package application

import (
	"context"
	"errors"

	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
)

var ErrCapabilityGrantSessionUnavailable = errors.New(
	"capability grant session is unavailable",
)

// CapabilityGrantSessionFacade is the sole typed runtime entrypoint for the
// short-lived CapabilityGrant session. Candidate collection stays behind the
// ResolverPort, so callers cannot inject a universal connector candidate map.
type CapabilityGrantSessionFacade struct {
	resolver ResolverPort
}

func NewCapabilityGrantSessionFacade(
	resolver ResolverPort,
) *CapabilityGrantSessionFacade {
	return &CapabilityGrantSessionFacade{resolver: resolver}
}

func (facade *CapabilityGrantSessionFacade) Resolve(
	ctx context.Context,
	requirement grantmodel.Requirement,
) (grantmodel.ResolvedCapabilityGrant, error) {
	if facade == nil || facade.resolver == nil || ctx == nil {
		return grantmodel.ResolvedCapabilityGrant{}, ErrCapabilityGrantSessionUnavailable
	}
	if err := ctx.Err(); err != nil {
		return grantmodel.ResolvedCapabilityGrant{}, err
	}
	return facade.resolver.ResolveCapabilityGrant(ctx, requirement)
}
