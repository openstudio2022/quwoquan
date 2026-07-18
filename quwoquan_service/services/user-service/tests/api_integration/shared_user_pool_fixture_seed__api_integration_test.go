package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"testing"
)

type sharedPoolUser struct {
	UserID          string   `json:"userId"`
	DisplayName     string   `json:"displayName"`
	AvatarObjectKey string   `json:"avatarObjectKey"`
	Bio             string   `json:"bio"`
	SubAccountRefs  []string `json:"subAccountRefs"`
}

type sharedPoolPersona struct {
	UserID          string
	SubAccountID    string
	DisplayName     string
	AvatarObjectKey string
	Bio             string
}

func loadSharedPoolPersonas(t *testing.T) []sharedPoolPersona {
	t.Helper()
	fixturePath := filepath.Join(
		locateWorkspaceRoot(t),
		"quwoquan_service",
		"contracts",
		"metadata",
		"_shared",
		"test_fixtures",
		"user_pool.json",
	)
	raw, err := os.ReadFile(fixturePath)
	if err != nil {
		t.Fatalf("read shared user pool: %v", err)
	}
	var payload struct {
		Users []sharedPoolUser `json:"users"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("decode shared user pool: %v", err)
	}
	personas := make([]sharedPoolPersona, 0, len(payload.Users))
	for _, user := range payload.Users {
		for _, subAccountID := range user.SubAccountRefs {
			personas = append(personas, sharedPoolPersona{
				UserID:          user.UserID,
				SubAccountID:    subAccountID,
				DisplayName:     user.DisplayName,
				AvatarObjectKey: user.AvatarObjectKey,
				Bio:             user.Bio,
			})
		}
	}
	if len(personas) == 0 {
		t.Fatal("shared user pool must contain at least one persona")
	}
	return personas
}

func locateWorkspaceRoot(t *testing.T) string {
	t.Helper()
	current, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if info, statErr := os.Stat(filepath.Join(current, "quwoquan_service", "contracts", "metadata")); statErr == nil && info.IsDir() {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			t.Fatal("workspace root not found")
		}
		current = parent
	}
}

func seedSharedPoolPersonas(t *testing.T, personas []sharedPoolPersona) {
	t.Helper()
	seededProfiles := map[string]struct{}{}
	for _, persona := range personas {
		_, profileExists := seededProfiles[persona.UserID]
		if !profileExists {
			createTestProfile(t, persona.UserID, persona.DisplayName)
			seededProfiles[persona.UserID] = struct{}{}
		}
		createTestPersonaFull(
			t,
			"persona_"+persona.SubAccountID,
			persona.UserID,
			persona.SubAccountID,
			persona.DisplayName,
			"open",
			!profileExists,
			!profileExists,
		)
		if _, err := pgPool.Exec(
			context.Background(),
			`UPDATE personas SET user_handle = $1, avatar_url = $2 WHERE sub_account_id = $3`,
			persona.SubAccountID,
			persona.AvatarObjectKey,
			persona.SubAccountID,
		); err != nil {
			t.Fatalf("seed shared persona handle/avatar: %v", err)
		}
		if _, err := pgPool.Exec(
			context.Background(),
			`UPDATE user_profiles SET bio = $1 WHERE user_id = $2`,
			persona.Bio,
			persona.UserID,
		); err != nil {
			t.Fatalf("seed shared profile bio: %v", err)
		}
	}
}

func TestContractFixtureSeedSharedUserPoolReadsViaHandler(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personas := loadSharedPoolPersonas(t)
	seedSharedPoolPersonas(t, personas)
	viewer := personas[0]
	verifiedProfiles := map[string]struct{}{}
	for _, target := range personas {
		if _, exists := verifiedProfiles[target.UserID]; !exists {
			profileRec := doRequest(t, http.MethodGet, "/user/profile/"+target.UserID, "", nil)
			if profileRec.Code != http.StatusOK {
				t.Fatalf("profile %s expected 200, got %d: %s", target.UserID, profileRec.Code, profileRec.Body.String())
			}
			verifiedProfiles[target.UserID] = struct{}{}
		}

		bundleRec := doRequest(
			t,
			http.MethodGet,
			"/user/sub-accounts/"+target.SubAccountID+"/homepage-bundle",
			"",
			authHeadersForPersona(viewer.UserID, viewer.SubAccountID),
		)
		if bundleRec.Code != http.StatusOK {
			t.Fatalf("homepage-bundle %s expected 200, got %d: %s", target.SubAccountID, bundleRec.Code, bundleRec.Body.String())
		}
	}
}
