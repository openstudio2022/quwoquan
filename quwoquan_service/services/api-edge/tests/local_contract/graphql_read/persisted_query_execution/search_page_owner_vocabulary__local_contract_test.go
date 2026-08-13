// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t3
package local_contract

import (
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	ownerinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
)

// TestSearchPageBindingsMatchTheRealOwnerVocabulary pins the edge translation
// table against the exact canonical vocabulary the real search-service accepts
// (rtsearch.TargetsForCanonicalFilter). The historic P0 break was an edge that
// sent vocabulary the owner rejected while the owner test stub accepted it;
// this contract makes that split structurally impossible without touching a
// real network.
func TestSearchPageBindingsMatchTheRealOwnerVocabulary(t *testing.T) {
	objectBindings := ownerinfra.SearchObjectTypeBindings()
	contentBindings := ownerinfra.SearchContentTypeBindings()

	searchable := map[string]bool{}
	for _, objectType := range rtsearch.CloudSearchableObjectTypes {
		searchable[objectType] = true
	}

	// 1) Every edge binding value must be accepted by the real owner validator.
	for enumValue, canonical := range objectBindings {
		if !searchable[canonical] {
			t.Fatalf("edge binding %s=%q is not cloud-searchable in the real owner", enumValue, canonical)
		}
		if _, err := rtsearch.TargetsForCanonicalFilter([]string{canonical}, nil, nil); err != nil {
			t.Fatalf("real owner rejects edge objectType %q: %v", canonical, err)
		}
	}
	for enumValue, canonical := range contentBindings {
		if _, err := rtsearch.TargetsForCanonicalFilter(
			[]string{rtsearch.CanonicalObjectContentPost}, []string{canonical}, nil,
		); err != nil {
			t.Fatalf("real owner rejects edge contentType %s=%q: %v", enumValue, canonical, err)
		}
	}

	// 2) Every cloud-searchable object type must be reachable through the edge
	// (no silently unsearchable object class).
	reachable := map[string]bool{}
	for _, canonical := range objectBindings {
		reachable[canonical] = true
	}
	for _, objectType := range rtsearch.CloudSearchableObjectTypes {
		if !reachable[objectType] {
			t.Fatalf("cloud-searchable object type %q has no GraphQL binding", objectType)
		}
	}

	// 3) Internal recall-target vocabulary must never appear as a binding value.
	for _, canonical := range objectBindings {
		if _, err := rtsearch.TargetsForCanonicalFilter(nil, []string{canonical}, nil); err == nil {
			t.Fatalf("object binding %q doubles as a content vocabulary value; vocabularies must stay disjoint", canonical)
		}
	}
	if _, err := rtsearch.TargetsForCanonicalFilter([]string{"photo"}, nil, nil); err == nil {
		t.Fatal("internal target vocabulary (photo) must be rejected by the owner validator")
	}
}
