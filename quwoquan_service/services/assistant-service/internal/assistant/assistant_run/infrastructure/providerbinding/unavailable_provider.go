package providerbinding

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

// UnavailableSearchProvider is an explicit fail-closed boundary for an
// unconfigured optional external capability. It never returns synthesized data.
type UnavailableSearchProvider struct {
	Capability string
}

func (p UnavailableSearchProvider) Search(
	_ context.Context,
	_ ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	return ports.ExternalSearchResult{}, p.failure()
}

func (p UnavailableSearchProvider) Lookup(
	_ context.Context,
	_ ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	return ports.ExternalSearchResult{}, p.failure()
}

func (p UnavailableSearchProvider) failure() ports.ProviderFailure {
	return ports.ProviderFailure{
		Capability: p.Capability,
		Reason:     ports.ProviderFailureUnavailable,
	}
}
