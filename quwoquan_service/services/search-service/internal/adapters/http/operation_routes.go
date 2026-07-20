package http

import (
	"fmt"
	"strings"

	"quwoquan_service/generated/operationsecurity"
)

const (
	searchQueryOperation    = "search.query.SearchQuery"
	listHotQueriesOperation = "search.query.ListHotQueries"
	reportFeedbackOperation = "search.query.ReportSearchFeedback"
	listRecentOperation     = "search.recent_search_state.ListRecentSearches"
	upsertRecentOperation   = "search.recent_search_state.UpsertRecentSearch"
	deleteRecentOperation   = "search.recent_search_state.DeleteRecentSearch"
	clearRecentOperation    = "search.recent_search_state.ClearRecentSearches"
)

func mustOperationPattern(canonicalOperationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("search") {
		if descriptor.CanonicalOperationID != canonicalOperationID {
			continue
		}
		method := strings.TrimSpace(descriptor.Method)
		path := strings.TrimSpace(descriptor.PathTemplate)
		if method == "" || path == "" {
			break
		}
		return method + " " + path
	}
	panic(fmt.Sprintf(
		"generated search operation route missing: %s",
		canonicalOperationID,
	))
}
