package application

import (
	"context"
	"errors"

	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
)

var (
	ErrResolverUnavailable        = errors.New("capability grant resolver is unavailable")
	ErrCandidateSourceUnavailable = errors.New("capability grant candidate source is unavailable")
	ErrCandidateDomainMismatch    = errors.New("capability grant candidate source returned a different capability")
)

// PublicProviderCandidateSource returns only environment-owned bindings for the
// requested capability. It must not expose endpoint or credential material.
type PublicProviderCandidateSource interface {
	PublicProviderCandidates(
		context.Context,
		grantmodel.Requirement,
	) ([]grantmodel.PublicProviderBinding, error)
}

// UserConnectorCandidateSource returns redacted, Integration-owned connection
// authority. Credential references never cross this port.
type UserConnectorCandidateSource interface {
	UserConnectorCandidates(
		context.Context,
		grantmodel.Requirement,
	) ([]grantmodel.UserConnectorConnection, error)
}

// DeviceCapabilityCandidateSource returns attested state for the current
// installation only.
type DeviceCapabilityCandidateSource interface {
	DeviceCapabilityCandidates(
		context.Context,
		grantmodel.Requirement,
	) ([]grantmodel.DeviceCapabilityBinding, error)
}

// DomainOperationCandidate preserves the capability key outside the canonical
// owner binding. The adapter can therefore reject a source-domain mismatch
// without copying owner payload or invariants into the grant.
type DomainOperationCandidate struct {
	CapabilityKey string
	Binding       grantmodel.DomainOperationBinding
}

// DomainOperationCandidateSource returns owner-operation references for the
// requested capability; owner payload is revalidated at its execution boundary.
type DomainOperationCandidateSource interface {
	DomainOperationCandidates(
		context.Context,
		grantmodel.Requirement,
	) ([]DomainOperationCandidate, error)
}

// ResolverPort is the application boundary implemented by the object-local
// infrastructure adapter.
type ResolverPort interface {
	ResolveCapabilityGrant(
		context.Context,
		grantmodel.Requirement,
	) (grantmodel.ResolvedCapabilityGrant, error)
}
