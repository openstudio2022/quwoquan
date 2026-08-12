package local_contract

import (
	"testing"

	"quwoquan_service/services/user-service/tests/support/testobject"
)

type sharedUserPoolContract struct {
	Statistics struct {
		UserCount int `json:"userCount"`
	} `json:"statistics"`
	Users []struct {
		UserID              string   `json:"userId"`
		DisplayName         string   `json:"displayName"`
		AvatarObjectKey     string   `json:"avatarObjectKey"`
		BackgroundObjectKey string   `json:"backgroundObjectKey"`
		PersonaRefs         []string `json:"personaRefs"`
	} `json:"users"`
}

func TestSharedUserPoolContractMatchesUserServiceIdentityRequirements(t *testing.T) {
	users := testobject.BuildUserPool(32)
	if len(users) != 32 {
		t.Fatalf("user builder count mismatch: users=%d", len(users))
	}
	seenUsers := make(map[string]struct{}, len(users))
	seenPersonas := map[string]struct{}{}
	for index, user := range users {
		if user.UserID == "" || user.DisplayName == "" {
			t.Fatalf("users[%d] requires userId and displayName", index)
		}
		if user.AvatarObjectKey == "" || user.BackgroundObjectKey == "" {
			t.Fatalf("users[%d] requires avatar and background object keys", index)
		}
		if _, exists := seenUsers[user.UserID]; exists {
			t.Fatalf("duplicate userId %q", user.UserID)
		}
		seenUsers[user.UserID] = struct{}{}
		for _, personaID := range user.PersonaRefs {
			if personaID == "" {
				t.Fatalf("users[%d] contains an empty personaRef", index)
			}
			if _, exists := seenPersonas[personaID]; exists {
				t.Fatalf("duplicate personaRef %q", personaID)
			}
			seenPersonas[personaID] = struct{}{}
		}
	}
}
