// Package httpadapter owns the HTTP route mapping for RecentSearchState.
package httpadapter

import (
	"fmt"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
)

const (
	listOperation   = "search.recent_search_state.ListRecentSearches"
	upsertOperation = "search.recent_search_state.UpsertRecentSearch"
	deleteOperation = "search.recent_search_state.DeleteRecentSearch"
	clearOperation  = "search.recent_search_state.ClearRecentSearches"
)

type Handlers struct {
	List   http.HandlerFunc
	Upsert http.HandlerFunc
	Delete http.HandlerFunc
	Clear  http.HandlerFunc
}

// Register binds every public RecentSearchState command/query to its object-owned route.
func Register(mux *http.ServeMux, handlers Handlers) {
	mux.HandleFunc(mustPattern(listOperation), handlers.List)
	mux.HandleFunc(mustPattern(upsertOperation), handlers.Upsert)
	mux.HandleFunc(mustPattern(deleteOperation), handlers.Delete)
	mux.HandleFunc(mustPattern(clearOperation), handlers.Clear)
}

func mustPattern(canonicalOperationID string) string {
	for _, descriptor := range operationsecurity.ForDomain("search") {
		if descriptor.CanonicalOperationID != canonicalOperationID {
			continue
		}
		method := strings.TrimSpace(descriptor.Method)
		path := strings.TrimSpace(descriptor.PathTemplate)
		if method != "" && path != "" {
			return method + " " + path
		}
	}
	panic(fmt.Sprintf("generated recent-search operation route missing: %s", canonicalOperationID))
}
