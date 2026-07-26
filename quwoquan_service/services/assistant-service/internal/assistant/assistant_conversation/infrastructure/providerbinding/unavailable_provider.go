package providerbinding

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
)

// UnavailableSearchProvider is an explicit fail-closed boundary for an
// unconfigured optional external capability. It never returns synthesized data.
type UnavailableSearchProvider struct {
	Capability string
}

func (p UnavailableSearchProvider) Search(
	_ context.Context,
	_ application.ExternalSearchRequest,
) (application.ExternalSearchResult, error) {
	return application.ExternalSearchResult{}, p.failure()
}

func (p UnavailableSearchProvider) Lookup(
	_ context.Context,
	_ application.ExternalSearchRequest,
) (application.ExternalSearchResult, error) {
	return application.ExternalSearchResult{}, p.failure()
}

func (p UnavailableSearchProvider) failure() application.ProviderFailure {
	return application.ProviderFailure{
		Capability: p.Capability,
		Reason:     application.ProviderFailureUnavailable,
	}
}
