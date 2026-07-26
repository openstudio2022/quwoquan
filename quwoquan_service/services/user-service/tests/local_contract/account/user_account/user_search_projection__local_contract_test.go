package local_contract

import (
	"testing"
	"time"

	searches "quwoquan_service/runtime/search/es"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

func TestUserSearchProjectionCarriesSelfContainedPublicPayload(t *testing.T) {
	profile := model.UserProfile{
		UserID:        "user-search-payload",
		AccountState:  "active",
		Status:        "active",
		Nickname:      "林摄影",
		Bio:           "旅行摄影",
		AvatarURL:     "https://cdn.example/avatar.webp",
		FollowerCount: 128,
		PostCount:     17,
		UpdatedAt:     time.Date(2026, time.July, 26, 8, 0, 0, 0, time.UTC),
	}
	document := application.ProjectUserProfileToSearchDocument(profile)
	indexed := searches.DocumentToIndex(document)
	payload, ok := indexed["payload"].(map[string]any)
	if !ok {
		t.Fatalf("search payload missing: %#v", indexed)
	}
	for key, want := range map[string]string{
		"avatarUrl":     profile.AvatarURL,
		"followerCount": "128",
		"postCount":     "17",
	} {
		if payload[key] != want {
			t.Fatalf("payload[%s]=%v want=%s", key, payload[key], want)
		}
	}
	roundTrip := searches.IndexToDocument(indexed)
	if roundTrip.Fields["avatarUrl"] != profile.AvatarURL ||
		roundTrip.Fields["followerCount"] != "128" {
		t.Fatalf("presentation payload did not round-trip: %#v", roundTrip.Fields)
	}
}
