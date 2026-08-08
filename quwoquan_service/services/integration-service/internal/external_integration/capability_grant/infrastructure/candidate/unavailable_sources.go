package candidate

import (
	"context"
	"fmt"
	"strings"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
)

// UnavailableSources is the production fail-closed binding for candidate kinds
// whose canonical owner has not supplied a trusted adapter in this process.
// Supplying this object is deliberate: nil must never be mistaken for an empty
// but authoritative candidate set that permits fallback.
type UnavailableSources struct {
	reason string
}

func NewUnavailableSources(reason string) *UnavailableSources {
	return &UnavailableSources{reason: strings.TrimSpace(reason)}
}

func (source *UnavailableSources) sourceError(
	kind grantmodel.BindingKind,
) error {
	reason := "canonical owner adapter is not configured"
	if source != nil && source.reason != "" {
		reason = source.reason
	}
	return fmt.Errorf(
		"%w: %s source: %s",
		grantapp.ErrCandidateSourceUnavailable,
		kind,
		reason,
	)
}

func (source *UnavailableSources) PublicProviderCandidates(
	context.Context,
	grantmodel.Requirement,
) ([]grantmodel.PublicProviderBinding, error) {
	return nil, source.sourceError(grantmodel.BindingPublicProvider)
}

func (source *UnavailableSources) DeviceCapabilityCandidates(
	context.Context,
	grantmodel.Requirement,
) ([]grantmodel.DeviceCapabilityBinding, error) {
	return nil, source.sourceError(grantmodel.BindingDevice)
}

func (source *UnavailableSources) DomainOperationCandidates(
	context.Context,
	grantmodel.Requirement,
) ([]grantapp.DomainOperationCandidate, error) {
	return nil, source.sourceError(grantmodel.BindingDomainOperation)
}

var (
	_ grantapp.PublicProviderCandidateSource   = (*UnavailableSources)(nil)
	_ grantapp.DeviceCapabilityCandidateSource = (*UnavailableSources)(nil)
	_ grantapp.DomainOperationCandidateSource  = (*UnavailableSources)(nil)
)
