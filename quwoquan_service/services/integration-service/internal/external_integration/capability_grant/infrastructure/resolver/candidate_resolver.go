package resolver

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
)

// CandidateResolver implements the application resolver port by consulting only
// the typed source selected by BindingPriority. A source failure or authoritative
// denied candidate stops resolution; lower-priority sources are never a fallback.
type CandidateResolver struct {
	publicProviders  grantapp.PublicProviderCandidateSource
	userConnectors   grantapp.UserConnectorCandidateSource
	deviceBindings   grantapp.DeviceCapabilityCandidateSource
	domainOperations grantapp.DomainOperationCandidateSource
	now              func() time.Time
}

func NewCandidateResolver(
	publicProviders grantapp.PublicProviderCandidateSource,
	userConnectors grantapp.UserConnectorCandidateSource,
	deviceBindings grantapp.DeviceCapabilityCandidateSource,
	domainOperations grantapp.DomainOperationCandidateSource,
	now func() time.Time,
) *CandidateResolver {
	return &CandidateResolver{
		publicProviders:  publicProviders,
		userConnectors:   userConnectors,
		deviceBindings:   deviceBindings,
		domainOperations: domainOperations,
		now:              now,
	}
}

func (resolver *CandidateResolver) ResolveCapabilityGrant(
	ctx context.Context,
	requirement grantmodel.Requirement,
) (grantmodel.ResolvedCapabilityGrant, error) {
	if resolver == nil || resolver.now == nil {
		return grantmodel.ResolvedCapabilityGrant{}, grantapp.ErrResolverUnavailable
	}
	now := resolver.now().UTC()
	normalized, err := grantmodel.NormalizeRequirement(requirement, now)
	if err != nil {
		return grantmodel.ResolvedCapabilityGrant{}, err
	}
	for _, kind := range normalized.BindingPriority {
		candidates, sourceErr := resolver.collectCandidates(ctx, normalized, kind)
		if sourceErr != nil {
			return grantmodel.ResolvedCapabilityGrant{}, sourceErr
		}
		resolved, resolveErr := grantmodel.ResolveCapabilityGrant(
			normalized,
			candidates,
			now,
		)
		if errors.Is(resolveErr, grantmodel.ErrCapabilityGrantRequired) {
			continue
		}
		if resolveErr != nil {
			return grantmodel.ResolvedCapabilityGrant{}, resolveErr
		}
		return resolved, nil
	}
	return grantmodel.ResolvedCapabilityGrant{}, grantmodel.ErrCapabilityGrantRequired
}

func (resolver *CandidateResolver) collectCandidates(
	ctx context.Context,
	requirement grantmodel.Requirement,
	kind grantmodel.BindingKind,
) (grantmodel.Candidates, error) {
	switch kind {
	case grantmodel.BindingPublicProvider:
		if resolver.publicProviders == nil {
			return grantmodel.Candidates{}, unavailableSource(kind, nil)
		}
		values, err := resolver.publicProviders.PublicProviderCandidates(ctx, requirement)
		if err != nil {
			return grantmodel.Candidates{}, unavailableSource(kind, err)
		}
		normalized, err := normalizePublicProviders(requirement.CapabilityKey, values)
		return grantmodel.Candidates{PublicProviders: normalized}, err
	case grantmodel.BindingUserConnector:
		if resolver.userConnectors == nil {
			return grantmodel.Candidates{}, unavailableSource(kind, nil)
		}
		values, err := resolver.userConnectors.UserConnectorCandidates(ctx, requirement)
		if err != nil {
			return grantmodel.Candidates{}, unavailableSource(kind, err)
		}
		normalized, err := normalizeUserConnectors(requirement.CapabilityKey, values)
		return grantmodel.Candidates{UserConnectors: normalized}, err
	case grantmodel.BindingDevice:
		if resolver.deviceBindings == nil {
			return grantmodel.Candidates{}, unavailableSource(kind, nil)
		}
		values, err := resolver.deviceBindings.DeviceCapabilityCandidates(ctx, requirement)
		if err != nil {
			return grantmodel.Candidates{}, unavailableSource(kind, err)
		}
		normalized, err := normalizeDeviceBindings(requirement.CapabilityKey, values)
		return grantmodel.Candidates{DeviceBindings: normalized}, err
	case grantmodel.BindingDomainOperation:
		if resolver.domainOperations == nil {
			return grantmodel.Candidates{}, unavailableSource(kind, nil)
		}
		values, err := resolver.domainOperations.DomainOperationCandidates(ctx, requirement)
		if err != nil {
			return grantmodel.Candidates{}, unavailableSource(kind, err)
		}
		normalized, err := normalizeDomainOperations(requirement.CapabilityKey, values)
		return grantmodel.Candidates{DomainOperations: normalized}, err
	default:
		return grantmodel.Candidates{}, grantmodel.ErrInvalidRequirement
	}
}

func unavailableSource(kind grantmodel.BindingKind, cause error) error {
	if cause == nil {
		return fmt.Errorf(
			"%w: %s source is not configured",
			grantapp.ErrCandidateSourceUnavailable,
			kind,
		)
	}
	return fmt.Errorf(
		"%w: %s source: %v",
		grantapp.ErrCandidateSourceUnavailable,
		kind,
		cause,
	)
}

func normalizePublicProviders(
	capabilityKey string,
	values []grantmodel.PublicProviderBinding,
) ([]grantmodel.PublicProviderBinding, error) {
	result := make([]grantmodel.PublicProviderBinding, 0, len(values))
	for _, value := range values {
		value.CapabilityKey = strings.TrimSpace(value.CapabilityKey)
		if value.CapabilityKey != capabilityKey {
			return nil, candidateDomainMismatch(grantmodel.BindingPublicProvider)
		}
		value.AdapterID = strings.TrimSpace(value.AdapterID)
		value.ContractDigest = strings.TrimSpace(value.ContractDigest)
		value.ConfigRef = strings.TrimSpace(value.ConfigRef)
		value.RatePolicyRef = strings.TrimSpace(value.RatePolicyRef)
		value.State = grantmodel.ProviderBindingState(strings.TrimSpace(string(value.State)))
		value.ProbeState = grantmodel.ProviderProbeState(
			strings.TrimSpace(string(value.ProbeState)),
		)
		result = append(result, value)
	}
	return result, nil
}

func normalizeUserConnectors(
	capabilityKey string,
	values []grantmodel.UserConnectorConnection,
) ([]grantmodel.UserConnectorConnection, error) {
	result := make([]grantmodel.UserConnectorConnection, 0, len(values))
	for _, value := range values {
		value.CapabilityKey = strings.TrimSpace(value.CapabilityKey)
		if value.CapabilityKey != capabilityKey {
			return nil, candidateDomainMismatch(grantmodel.BindingUserConnector)
		}
		value.AccountID = strings.TrimSpace(value.AccountID)
		value.ConnectionID = strings.TrimSpace(value.ConnectionID)
		value.ConnectorID = strings.TrimSpace(value.ConnectorID)
		value.ProviderAccountSubjectDigest = strings.TrimSpace(
			value.ProviderAccountSubjectDigest,
		)
		value.GrantedCapabilities = normalizeCapabilities(value.GrantedCapabilities)
		value.GrantState = grantmodel.ConnectorGrantState(
			strings.TrimSpace(string(value.GrantState)),
		)
		value.FreshnessAt = value.FreshnessAt.UTC()
		value.ExpiresAt = normalizeTimePointer(value.ExpiresAt)
		result = append(result, value)
	}
	return result, nil
}

func normalizeDeviceBindings(
	capabilityKey string,
	values []grantmodel.DeviceCapabilityBinding,
) ([]grantmodel.DeviceCapabilityBinding, error) {
	result := make([]grantmodel.DeviceCapabilityBinding, 0, len(values))
	for _, value := range values {
		value.CapabilityKey = strings.TrimSpace(value.CapabilityKey)
		if value.CapabilityKey != capabilityKey {
			return nil, candidateDomainMismatch(grantmodel.BindingDevice)
		}
		value.BridgeCapability = strings.TrimSpace(value.BridgeCapability)
		value.AttestationDigest = strings.TrimSpace(value.AttestationDigest)
		value.Availability = grantmodel.DeviceAvailability(
			strings.TrimSpace(string(value.Availability)),
		)
		value.Permission = grantmodel.DevicePermission(
			strings.TrimSpace(string(value.Permission)),
		)
		result = append(result, value)
	}
	return result, nil
}

func normalizeDomainOperations(
	capabilityKey string,
	values []grantapp.DomainOperationCandidate,
) ([]grantmodel.DomainOperationBinding, error) {
	result := make([]grantmodel.DomainOperationBinding, 0, len(values))
	for _, value := range values {
		if strings.TrimSpace(value.CapabilityKey) != capabilityKey {
			return nil, candidateDomainMismatch(grantmodel.BindingDomainOperation)
		}
		value.Binding.OwnerOperationID = strings.TrimSpace(value.Binding.OwnerOperationID)
		value.Binding.ContractDigest = strings.TrimSpace(value.Binding.ContractDigest)
		result = append(result, value.Binding)
	}
	return result, nil
}

func candidateDomainMismatch(kind grantmodel.BindingKind) error {
	return fmt.Errorf("%w: source=%s", grantapp.ErrCandidateDomainMismatch, kind)
}

func normalizeCapabilities(values []string) []string {
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		normalized := strings.TrimSpace(value)
		if normalized == "" {
			continue
		}
		if _, duplicate := seen[normalized]; duplicate {
			continue
		}
		seen[normalized] = struct{}{}
		result = append(result, normalized)
	}
	return result
}

func normalizeTimePointer(value *time.Time) *time.Time {
	if value == nil || value.IsZero() {
		return nil
	}
	normalized := value.UTC()
	return &normalized
}
