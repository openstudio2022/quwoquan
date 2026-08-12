package searchclient

import (
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

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
	assistantReadableObjectTypes = objectTypeSet(generated.AssistantSearchReadableObjectTypes)
	assistantCitableObjectTypes  = objectTypeSet(generated.AssistantSearchCitableObjectTypes)
)

// AssistantReadableObjectTypes is the object types app_search may ask for and
// may hand back. Callers must not extend the returned slice; widening the reach
// of 小趣 is an object contract change.
func AssistantReadableObjectTypes() []string {
	return append([]string(nil), generated.AssistantSearchReadableObjectTypes...)
}

// AssistantCitableObjectTypes is the subset that may additionally be reproduced
// as a citation in a user-visible answer.
func AssistantCitableObjectTypes() []string {
	return append([]string(nil), generated.AssistantSearchCitableObjectTypes...)
}

// AssistantAccessPolicyDigest binds a retrieval plan to the exact generated
// readable/citable projection. A later object-contract change therefore makes
// the old plan unverifiable instead of silently widening its scope.
func AssistantAccessPolicyDigest() string {
	return generated.AssistantSearchAccessPolicyDigest
}

func objectTypeSet(values []string) map[string]bool {
	result := make(map[string]bool, len(values))
	for _, value := range values {
		result[value] = true
	}
	return result
}
