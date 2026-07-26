// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-snapshot-versioning/spec.md#gwt-002
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

type fakeProfileSearchOutboxStore struct {
	event       userports.UserProfileSearchOutboxEvent
	found       bool
	published   bool
	failed      bool
	failure     userports.UserProfileSearchOutboxFailure
	nextAttempt time.Time
	pending     int
}

func (store *fakeProfileSearchOutboxStore) ClaimReady(
	context.Context,
	string,
	time.Time,
	time.Duration,
) (userports.UserProfileSearchOutboxEvent, bool, error) {
	if !store.found {
		return userports.UserProfileSearchOutboxEvent{}, false, nil
	}
	store.found = false
	return store.event, true, nil
}

func (store *fakeProfileSearchOutboxStore) MarkPublished(
	context.Context,
	string,
	string,
	time.Time,
) error {
	store.published = true
	store.pending = 0
	return nil
}

func (store *fakeProfileSearchOutboxStore) MarkFailed(
	_ context.Context,
	_ string,
	_ string,
	_ time.Time,
	nextAttemptAt time.Time,
	failure userports.UserProfileSearchOutboxFailure,
) error {
	store.failed = true
	store.failure = failure
	store.nextAttempt = nextAttemptAt
	return nil
}

func (store *fakeProfileSearchOutboxStore) PendingCount(context.Context) (int, error) {
	return store.pending, nil
}

type fakeProfileSearchProjectionPublisher struct {
	err       error
	projected []string
}

func (publisher *fakeProfileSearchProjectionPublisher) ProjectUserProfileSearch(
	_ context.Context,
	eventType string,
	userID string,
) error {
	publisher.projected = append(publisher.projected, eventType+":"+userID)
	return publisher.err
}

func TestUserProfileSearchOutboxRelayRetriesWithoutAdvancingCheckpoint(
	t *testing.T,
) {
	store := &fakeProfileSearchOutboxStore{
		found:   true,
		pending: 1,
		event: userports.UserProfileSearchOutboxEvent{
			EventID:         "profile-search-event-1",
			UserID:          "profile-owner-1",
			ProfileVersion:  4,
			EventType:       "UserAvatarUpdated",
			OccurredAt:      time.Now().UTC(),
			DeliveryAttempt: 1,
		},
	}
	publisher := &fakeProfileSearchProjectionPublisher{
		err: errors.New("elasticsearch unavailable for profile-owner-1"),
	}
	relay, err := useraccountapp.NewUserProfileSearchOutboxRelay(
		store,
		publisher,
		"relay-test",
	)
	if err != nil {
		t.Fatal(err)
	}

	didWork, err := relay.RelayOnce(context.Background())
	if !didWork || err == nil {
		t.Fatalf("expected visible retryable failure, didWork=%v err=%v", didWork, err)
	}
	if !store.failed || store.published || !store.nextAttempt.After(time.Now().Add(-time.Second)) {
		t.Fatalf("failed ES projection must retain the checkpoint: %+v", store)
	}
	if store.failure.Code != userports.UserProfileSearchOutboxFailureProject ||
		len(store.failure.Digest) != 64 ||
		strings.Contains(store.failure.Digest, "profile-owner-1") ||
		strings.Contains(err.Error(), "profile-owner-1") {
		t.Fatalf("retry failure must remain sanitized: failure=%+v err=%v", store.failure, err)
	}

	store.found = true
	store.event.DeliveryAttempt = 2
	publisher.err = nil
	didWork, err = relay.RelayOnce(context.Background())
	if err != nil || !didWork || !store.published {
		t.Fatalf("successful replay must advance the checkpoint: didWork=%v err=%v store=%+v", didWork, err, store)
	}
	if got, want := publisher.projected, []string{
		"UserAvatarUpdated:profile-owner-1",
		"UserAvatarUpdated:profile-owner-1",
	}; len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("same event must be safely replayed, got %#v", got)
	}
	if err := relay.Healthy(context.Background(), time.Second); err != nil {
		t.Fatalf("replayed checkpoint must restore relay readiness: %v", err)
	}
}
