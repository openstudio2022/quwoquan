package local_contract

import (
	"testing"

	usermodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
)

func TestGreetingRequestStatusCanonicalClosedSet(t *testing.T) {
	t.Parallel()

	valid := []string{
		usermodel.GreetingStatusPending,
		usermodel.GreetingStatusReplied,
		usermodel.GreetingStatusIgnored,
		usermodel.GreetingStatusBlocked,
		usermodel.GreetingStatusCancelled,
		usermodel.GreetingStatusExpired,
	}
	for _, value := range valid {
		if !usermodel.IsGreetingRequestStatus(value) {
			t.Fatalf("expected canonical greeting status %q to be accepted", value)
		}
	}
	for _, value := range []string{"", "accepted", "deleted", "friend"} {
		if usermodel.IsGreetingRequestStatus(value) {
			t.Fatalf("expected non-canonical greeting status %q to be rejected", value)
		}
	}
}
