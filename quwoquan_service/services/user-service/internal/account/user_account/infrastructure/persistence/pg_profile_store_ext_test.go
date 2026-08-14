package persistence

import (
	"testing"
	"time"
)

func TestUserProfileSearchBackfillEventIDIsReplaySpecific(t *testing.T) {
	firstAt := time.Date(2026, 8, 14, 0, 0, 0, 0, time.UTC)
	secondAt := firstAt.Add(time.Nanosecond)

	first := userProfileSearchBackfillEventID("user-1", 7, firstAt)
	second := userProfileSearchBackfillEventID("user-1", 7, secondAt)
	writePath := userProfileSearchProjectionEventID(
		"user-1",
		7,
		"user.user_account.UserProfileUpdated",
	)

	if first == second {
		t.Fatal("separate backfill attempts must have distinct event identities")
	}
	if first == writePath {
		t.Fatal("backfill event must not collide with the write-path event")
	}
}
