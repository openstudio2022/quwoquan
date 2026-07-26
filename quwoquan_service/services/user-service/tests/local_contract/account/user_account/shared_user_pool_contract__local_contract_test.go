package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
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
		SubAccountRefs      []string `json:"subAccountRefs"`
	} `json:"users"`
}

func TestSharedUserPoolContractMatchesUserServiceIdentityRequirements(t *testing.T) {
	fixturePath := filepath.Clean("../../../support/contract_fixtures/user_pool.json")
	raw, err := os.ReadFile(fixturePath)
	if err != nil {
		t.Fatalf("read shared user pool: %v", err)
	}
	var payload sharedUserPoolContract
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("decode shared user pool: %v", err)
	}
	if len(payload.Users) == 0 || len(payload.Users) != payload.Statistics.UserCount {
		t.Fatalf("user count mismatch: users=%d statistics=%d", len(payload.Users), payload.Statistics.UserCount)
	}
	seenUsers := make(map[string]struct{}, len(payload.Users))
	seenSubAccounts := map[string]struct{}{}
	for index, user := range payload.Users {
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
		for _, subAccountID := range user.SubAccountRefs {
			if subAccountID == "" {
				t.Fatalf("users[%d] contains an empty subAccountRef", index)
			}
			if _, exists := seenSubAccounts[subAccountID]; exists {
				t.Fatalf("duplicate subAccountRef %q", subAccountID)
			}
			seenSubAccounts[subAccountID] = struct{}{}
		}
	}
}
