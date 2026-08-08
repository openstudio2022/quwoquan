package searchclient

import "sort"

// app_search used to call the canonical SearchIndexView with no objectTypes at
// all, so it returned every type the unified index holds. That made it a way
// around object-level assistant policy: an object could declare itself closed to
// 小趣 and still reach the model as a search hit, because the only filtering
// happened inside the search surface, which knows nothing about assistant policy.
//
// These two sets are that policy, projected onto the search registry. They are
// derived from `search_objects.yaml` plus the `object.yaml` of the object that
// owns each registered type, under these rules:
//
//   - a type registered `filter_only` is skipped. It is a taxonomy projection with
//     no landing page and never appears as a hit, so leaving it out narrows
//     nothing.
//   - a first-party type is readable only when its owner declares
//     `assistant_access.read.mode: public`. `owner_scoped` is deliberately
//     excluded rather than treated as a weaker yes: this client queries the
//     shared index without an end-user identity, so it has nothing to scope an
//     owner-scoped object against. Those objects reach 小趣 through the
//     owner-scoped context Readers instead, which do carry the caller.
//   - a first-party type is citable only when its owner also declares a non-`none`
//     `cite.mode`. Reading a hit into the model's context and reproducing it in a
//     user-visible answer are separate disclosures, so chat and profile objects
//     can inform an answer without becoming quotable.
//   - an `external` type has no first-party object to consult, so its exposure is
//     governed by the owning object's `search_policy.exposed: remote_provider`
//     and its provider egress declaration. Reading the run object's own
//     `read.mode` would be answering a different question — whether 小趣 may read
//     someone's assistant run — and would wrongly close off web results.
//
// `verify_object_assistant_access_closure.py` recomputes both sets from the
// contracts on every gate run and blocks on any difference, so widening a grant
// here without changing the owning object's declaration fails.
var (
	assistantReadableObjectTypes = map[string]bool{
		"circle.circle":            true,
		"circle.group":             true,
		"content.post":             true,
		"entity.homepage":          true,
		"integration.location_poi": true,
		"location.place":           true,
		"web.document":             true,
	}

	assistantCitableObjectTypes = map[string]bool{
		"circle.circle":            true,
		"circle.group":             true,
		"content.post":             true,
		"entity.homepage":          true,
		"integration.location_poi": true,
		"location.place":           true,
		"web.document":             true,
	}
)

// AssistantReadableObjectTypes is the object types app_search may ask for and
// may hand back. Callers must not extend the returned slice; widening the reach
// of 小趣 is an object contract change.
func AssistantReadableObjectTypes() []string {
	return sortedKeys(assistantReadableObjectTypes)
}

// AssistantCitableObjectTypes is the subset that may additionally be reproduced
// as a citation in a user-visible answer.
func AssistantCitableObjectTypes() []string {
	return sortedKeys(assistantCitableObjectTypes)
}

func sortedKeys(set map[string]bool) []string {
	result := make([]string, 0, len(set))
	for key := range set {
		result = append(result, key)
	}
	sort.Strings(result)
	return result
}
