package http

import (
	"fmt"
	"strings"

	"quwoquan_service/generated/operationsecurity"
)

const (
	searchQueryOperation = "search.search_index_view.Search"
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
