// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
package local_contract

import (
	"strings"
	"testing"

	"quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/application/importmanifest"
)

func TestImmutableReleaseManifestImportsFlatObjectTagIndex(t *testing.T) {
	t.Parallel()

	raw := []byte(`{
		"object_tag_index": [{
			"objectId": "user-1",
			"objectType": "user",
			"tagRefs": ["Topic/旅行", "Topic/摄影", "Topic/摄影"]
		}]
	}`)

	entries, err := importmanifest.Decode(raw)
	if err != nil {
		t.Fatalf("decode immutable release manifest: %v", err)
	}
	if len(entries) != 1 || entries[0].ObjectID != "user-1" {
		t.Fatalf("unexpected selected entries: %+v", entries)
	}
	if len(entries[0].TagRefs) != 2 ||
		entries[0].TagRefs[0] != "Topic/摄影" ||
		entries[0].TagRefs[1] != "Topic/旅行" {
		t.Fatalf(
			"tag refs must be canonical, sorted, and deduplicated: %+v",
			entries[0].TagRefs,
		)
	}
}

func TestEnvironmentSeedManifestIsRejected(t *testing.T) {
	t.Parallel()

	raw := []byte(`{
		"seedSets": {
			"declared": {
				"object_tag_index": [{
					"objectId": "user-1",
					"objectType": "user",
					"tagRefs": ["Topic/摄影"]
				}]
			}
		}
	}`)

	if _, err := importmanifest.Decode(raw); err == nil ||
		!strings.Contains(err.Error(), "no importable entries") {
		t.Fatalf("environment seed manifest must fail closed, got %v", err)
	}
}

func TestObjectTagManifestRejectsInvalidOrDuplicateIdentity(t *testing.T) {
	t.Parallel()

	duplicate := []byte(`[
		{"objectId":"same","objectType":"user","tagRefs":["Topic/摄影"]},
		{"objectId":"same","objectType":"user","tagRefs":["Topic/旅行"]}
	]`)
	if _, err := importmanifest.Decode(duplicate); err == nil ||
		!strings.Contains(err.Error(), "is duplicated") {
		t.Fatalf("duplicate identity must fail, got %v", err)
	}

	unsupported := []byte(`[
		{"objectId":"same","objectType":"unknown","tagRefs":["Topic/摄影"]}
	]`)
	if _, err := importmanifest.Decode(unsupported); err == nil ||
		!strings.Contains(err.Error(), "unsupported objectType") {
		t.Fatalf("unsupported object type must fail, got %v", err)
	}

	invalidTag := []byte(`[
		{"objectId":"same","objectType":"user","tagRefs":["retired-interest"]}
	]`)
	if _, err := importmanifest.Decode(invalidTag); err == nil ||
		!strings.Contains(err.Error(), "outside the canonical taxonomy") {
		t.Fatalf("invalid tag ref must fail, got %v", err)
	}
}
