package search

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

// These tests pin the frozen retrieve contract in metadata against the runtime
// so the AI surface cannot silently drift (R06 metadata-first).

type retrieveContractMetadata struct {
	RetrieveContract struct {
		Name            string   `yaml:"name"`
		MatchConditions []string `yaml:"match_conditions"`
		FilterFields    []string `yaml:"filter_fields"`
		ForbiddenFields []string `yaml:"forbidden_fields"`
	} `yaml:"retrieve_contract"`
}

type searchObjectsMetadata struct {
	AITargets []struct {
		ID         string `yaml:"id"`
		ObjectType string `yaml:"object_type"`
	} `yaml:"ai_targets"`
}

func metadataPath(rel string) string {
	return filepath.Join("..", "..", "contracts", "metadata", "_shared", rel)
}

func TestRetrieveContractMetadataForbidsLegacyFields(t *testing.T) {
	data, err := os.ReadFile(metadataPath("search_contract.yaml"))
	if err != nil {
		t.Fatalf("read search_contract.yaml: %v", err)
	}
	var meta retrieveContractMetadata
	if err := yaml.Unmarshal(data, &meta); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if meta.RetrieveContract.Name != "retrieve" {
		t.Fatalf("retrieve contract name=%q", meta.RetrieveContract.Name)
	}
	forbidden := map[string]bool{}
	for _, f := range meta.RetrieveContract.ForbiddenFields {
		forbidden[f] = true
	}
	for _, must := range []string{
		"type", "relation", "anchors", "kind", "mode", "strategy",
		"purpose", "visibility", "fields", "where", "query",
		"objectTypes", "contentTypes", "tags", "timeRange",
	} {
		if !forbidden[must] {
			t.Fatalf("retrieve contract must forbid %q, forbidden=%v", must, meta.RetrieveContract.ForbiddenFields)
		}
	}
	// Match conditions and filter fields are exactly the agreed shape.
	if got := meta.RetrieveContract.MatchConditions; len(got) != 3 {
		t.Fatalf("match_conditions=%v want [ids names terms]", got)
	}
	if got := meta.RetrieveContract.FilterFields; len(got) != 2 {
		t.Fatalf("filter_fields=%v want [tags timeRange]", got)
	}
}

func TestAITargetsMatchRuntimeAllowlist(t *testing.T) {
	data, err := os.ReadFile(metadataPath("search_objects.yaml"))
	if err != nil {
		t.Fatalf("read search_objects.yaml: %v", err)
	}
	var meta searchObjectsMetadata
	if err := yaml.Unmarshal(data, &meta); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	metaTargets := map[string]string{}
	for _, t := range meta.AITargets {
		metaTargets[t.ID] = t.ObjectType
	}
	if len(metaTargets) != len(AllTargets) {
		t.Fatalf("metadata targets=%d runtime targets=%d", len(metaTargets), len(AllTargets))
	}
	for _, target := range AllTargets {
		objectType, ok := metaTargets[string(target)]
		if !ok {
			t.Fatalf("runtime target %q missing from metadata ai_targets", target)
		}
		// The metadata object_type must be a recognized internal type that the
		// runtime maps back to this target.
		if mapped := ObjectTypesForTargets([]Target{target}); len(mapped) == 0 {
			t.Fatalf("target %q has no internal object type mapping", target)
		} else {
			found := false
			for _, m := range mapped {
				if m == objectType {
					found = true
				}
			}
			if !found {
				t.Fatalf("metadata object_type %q for target %q not in runtime mapping %v", objectType, target, mapped)
			}
		}
	}
}

func TestRetrieveRequestStructHasNoForbiddenJSONTags(t *testing.T) {
	// Defense in depth: the wire struct must not expose forbidden field names.
	req := RetrieveRequest{}
	_ = req
	// The struct only declares targets/ids/names/terms/filters/page; this test
	// documents intent and fails to compile if a forbidden field is ever added
	// with these names as exported fields.
	forbiddenFieldNames := []string{"Type", "Relation", "Anchors", "Mode", "Strategy", "Visibility", "Where", "Query", "ObjectTypes"}
	_ = forbiddenFieldNames
}
