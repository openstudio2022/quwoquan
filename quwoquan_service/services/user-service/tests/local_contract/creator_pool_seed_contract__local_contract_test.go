package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestCreatorPoolSeedFixture_StructureMatchesUserServiceExpectations(t *testing.T) {
	repoRoot := filepath.Clean("../../../../../")
	seedPath := filepath.Join(
		repoRoot,
		"quwoquan_service",
		"contracts",
		"metadata",
		"_shared",
		"test_fixtures",
		"creator_pool",
		"creator_travel_batch100.seed.json",
	)
	raw, err := os.ReadFile(seedPath)
	if err != nil {
		t.Fatalf("read seed fixture: %v", err)
	}
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("decode seed fixture: %v", err)
	}
	users, ok := payload["users"].([]any)
	if !ok || len(users) == 0 {
		t.Fatalf("expected non-empty users array, got %#v", payload["users"])
	}
	sampleCount := 20
	if len(users) < sampleCount {
		sampleCount = len(users)
	}
	for idx := 0; idx < sampleCount; idx++ {
		user, ok := users[idx].(map[string]any)
		if !ok {
			t.Fatalf("user[%d] not object", idx)
		}
		for _, key := range []string{"subAccountId", "authorId", "displayName", "userHandle", "avatarObjectKey", "bio", "headline"} {
			if v, _ := user[key].(string); v == "" {
				t.Fatalf("user[%d].%s must be non-empty", idx, key)
			}
		}
	}
}
