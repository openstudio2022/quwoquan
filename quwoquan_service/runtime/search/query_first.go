package search

import "strings"

// SplitQueryTerms expands a query-first string into Terms: the whole query plus
// its individual whitespace tokens. Shared by every query-first caller (App,
// assistant tool, search-service) so recall term semantics stay single-sourced.
func SplitQueryTerms(query string) []string {
	q := strings.TrimSpace(query)
	if q == "" {
		return nil
	}
	terms := []string{q}
	for _, token := range strings.Fields(q) {
		if token != "" && token != q {
			terms = append(terms, token)
		}
	}
	return terms
}

// NormalizeTargets lowercases/trims object-type strings into the allowed Target
// allowlist, dropping unknowns and duplicates. It falls back to defaults when no
// valid target remains so callers never accidentally search everything.
func NormalizeTargets(objectTypes []string, defaults []Target) []Target {
	out := []Target{}
	seen := map[Target]bool{}
	for _, t := range objectTypes {
		rt := Target(strings.ToLower(strings.TrimSpace(t)))
		if rt == "" || !targetAllowed(rt) || seen[rt] {
			continue
		}
		seen[rt] = true
		out = append(out, rt)
	}
	if len(out) == 0 {
		return defaults
	}
	return out
}

// BuildQueryFirstRequest assembles a RetrieveRequest from the canonical
// query-first inputs that the App and AI agents both send.
func BuildQueryFirstRequest(query string, objectTypes []string, limit int, filters RetrieveFilters, defaults []Target) RetrieveRequest {
	return RetrieveRequest{
		Targets: NormalizeTargets(objectTypes, defaults),
		Terms:   SplitQueryTerms(query),
		Filters: filters,
		Page:    PageRequest{Limit: limit},
	}
}
