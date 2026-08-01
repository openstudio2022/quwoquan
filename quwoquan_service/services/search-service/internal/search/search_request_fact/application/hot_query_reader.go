package application

import (
	"context"

	"quwoquan_service/services/search-service/internal/search/search_request_fact/application/queryheat"
)

// TermHeatReader exposes the SearchTermHeatView projection owned by
// SearchRequestFact. SearchIndexView may consume the same port for ranking, but
// the read model lifecycle remains in this object.
type TermHeatReader interface {
	RelatedTerms(context.Context, string, int) ([]queryheat.TermHeat, error)
}
