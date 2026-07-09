package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
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
		"creator_travel_photo_1k_v1.seed.json",
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
	userID := regexp.MustCompile(`^sys_(travel|photo|travelphoto)_[0-9]{4}$`)
	for idx := 0; idx < sampleCount; idx++ {
		user, ok := users[idx].(map[string]any)
		if !ok {
			t.Fatalf("user[%d] not object", idx)
		}
		for _, key := range []string{"creatorProfileId", "subAccountId", "displayName", "userHandle", "avatarPresetId", "coverPresetId", "bio", "headline", "slogan"} {
			if v, _ := user[key].(string); v == "" {
				t.Fatalf("user[%d].%s must be non-empty", idx, key)
			}
		}
		creatorID, _ := user["creatorProfileId"].(string)
		subAccountID, _ := user["subAccountId"].(string)
		if !userID.MatchString(creatorID) {
			t.Fatalf("user[%d].creatorProfileId = %q", idx, creatorID)
		}
		if subAccountID != creatorID+"_sub_01" {
			t.Fatalf("user[%d].subAccountId = %q", idx, subAccountID)
		}
		if _, ok := user["ipLocation"]; ok {
			t.Fatalf("user[%d].ipLocation must not be published", idx)
		}
		for _, key := range []string{"authorId", "avatarObjectKey", "backgroundObjectKey", "coverObjectKey", "archiveAliases"} {
			if _, ok := user[key]; ok {
				t.Fatalf("user[%d].%s must not be published", idx, key)
			}
		}
		avatar, _ := user["avatarPresetId"].(string)
		cover, _ := user["coverPresetId"].(string)
		if !regexp.MustCompile(`^avatar_`).MatchString(avatar) {
			t.Fatalf("user[%d].avatarPresetId = %q", idx, avatar)
		}
		if !regexp.MustCompile(`^cover_`).MatchString(cover) {
			t.Fatalf("user[%d].coverPresetId = %q", idx, cover)
		}
	}
}
