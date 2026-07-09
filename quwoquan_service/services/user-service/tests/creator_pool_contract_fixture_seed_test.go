package tests

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

type creatorPoolSeedUser struct {
	CreatorProfileID string `json:"creatorProfileId"`
	SubAccountID     string `json:"subAccountId"`
	DisplayName      string `json:"displayName"`
	UserHandle       string `json:"userHandle"`
	AvatarPresetID   string `json:"avatarPresetId"`
	Bio              string `json:"bio"`
}

func loadCreatorPoolSeedUsers(t *testing.T, limit int) []creatorPoolSeedUser {
	t.Helper()
	repoRoot := filepath.Clean("../../../../")
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
	var payload struct {
		Users []creatorPoolSeedUser `json:"users"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("decode seed fixture: %v", err)
	}
	if len(payload.Users) == 0 {
		t.Fatalf("expected non-empty creator pool seed users")
	}
	if limit > 0 && len(payload.Users) > limit {
		return payload.Users[:limit]
	}
	return payload.Users
}

func seedCreatorPoolUsers(t *testing.T, users []creatorPoolSeedUser) {
	t.Helper()
	for _, user := range users {
		createTestProfile(t, user.CreatorProfileID, user.DisplayName)
		createTestPersonaFull(
			t,
			"persona_"+user.SubAccountID,
			user.CreatorProfileID,
			user.SubAccountID,
			user.DisplayName,
			"open",
			true,
			true,
		)
		_, err := pgPool.Exec(
			context.Background(),
			`UPDATE personas SET user_handle = $1, avatar_url = $2 WHERE sub_account_id = $3`,
			user.UserHandle,
			"https://cdn.example.com/preset/avatar/"+user.AvatarPresetID+".png",
			user.SubAccountID,
		)
		if err != nil {
			t.Fatalf("seed creator persona handle/avatar: %v", err)
		}
		_, err = pgPool.Exec(
			context.Background(),
			`UPDATE user_profiles SET bio = $1 WHERE user_id = $2`,
			user.Bio,
			user.CreatorProfileID,
		)
		if err != nil {
			t.Fatalf("seed creator profile bio: %v", err)
		}
	}
}

func assertCreatorPoolReadsViaHandler(t *testing.T, users []creatorPoolSeedUser) {
	t.Helper()
	viewer := users[0]
	for _, target := range users {
		profileReq := httptest.NewRequest(http.MethodGet, "/v1/user/"+target.SubAccountID, nil)
		profileRec := httptest.NewRecorder()
		testHandler.ServeHTTP(profileRec, profileReq)
		if profileRec.Code != http.StatusOK {
			t.Fatalf("profile %s expected 200, got %d: %s", target.SubAccountID, profileRec.Code, profileRec.Body.String())
		}
		var profile map[string]any
		if err := json.Unmarshal(profileRec.Body.Bytes(), &profile); err != nil {
			t.Fatalf("decode profile: %v", err)
		}
		if profile["subAccountId"] != target.SubAccountID {
			t.Fatalf("profile subAccountId mismatch: got %v want %s", profile["subAccountId"], target.SubAccountID)
		}

		bundleReq := httptest.NewRequest(
			http.MethodGet,
			"/v1/user/sub-accounts/"+target.UserHandle+"/homepage-bundle",
			nil,
		)
		for key, value := range authHeadersForPersona(viewer.CreatorProfileID, viewer.SubAccountID) {
			bundleReq.Header.Set(key, value)
		}
		bundleRec := httptest.NewRecorder()
		testHandler.ServeHTTP(bundleRec, bundleReq)
		if bundleRec.Code != http.StatusOK {
			t.Fatalf("homepage-bundle %s expected 200, got %d: %s", target.UserHandle, bundleRec.Code, bundleRec.Body.String())
		}
	}
}

// TestContractFixtureSeed_CreatorPoolBetaReadsViaHandler validates the 100-user
// curated 1k subset reads back via the user-service handler.
func TestContractFixtureSeed_CreatorPoolBetaReadsViaHandler(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	users := loadCreatorPoolSeedUsers(t, 100)
	seedCreatorPoolUsers(t, users)
	assertCreatorPoolReadsViaHandler(t, users)
}

// TestContractFixtureSeed_CreatorPoolFullBatchReadsViaHandler scales validation
// to the full commercial batch (1000 creators), not just the pilot subset.
func TestContractFixtureSeed_CreatorPoolFullBatchReadsViaHandler(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	users := loadCreatorPoolSeedUsers(t, 0)
	if len(users) != 1000 {
		t.Fatalf("expected full batch of 1000 creators, got %d", len(users))
	}
	seedCreatorPoolUsers(t, users)
	assertCreatorPoolReadsViaHandler(t, users)
}
