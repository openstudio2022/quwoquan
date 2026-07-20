package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	useraccountapp "quwoquan_service/services/user-service/internal/application/account/user_account"
	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
)

type fakeCloseOutboxStore struct {
	event         accountports.CloseOutboxEvent
	found         bool
	published     bool
	failed        bool
	nextAttemptAt time.Time
}

func (store *fakeCloseOutboxStore) ClaimReady(
	context.Context,
	string,
	time.Time,
	time.Duration,
) (accountports.CloseOutboxEvent, bool, error) {
	if !store.found {
		return accountports.CloseOutboxEvent{}, false, nil
	}
	store.found = false
	return store.event, true, nil
}

func (store *fakeCloseOutboxStore) MarkPublished(
	context.Context,
	string,
	string,
	time.Time,
) error {
	store.published = true
	return nil
}

func (store *fakeCloseOutboxStore) MarkFailed(
	_ context.Context,
	_ string,
	_ string,
	nextAttemptAt time.Time,
	_ string,
) error {
	store.failed = true
	store.nextAttemptAt = nextAttemptAt
	return nil
}

type fakeClosedStreamPublisher struct {
	err       error
	published int
}

func (publisher *fakeClosedStreamPublisher) PublishUserAccountClosed(
	context.Context,
	accountports.CloseOutboxEvent,
	map[string]any,
) error {
	publisher.published++
	return publisher.err
}

func TestCloseAccountOutboxRelayMarksPublishedAfterDurablePublish(t *testing.T) {
	store := &fakeCloseOutboxStore{
		found: true,
		event: accountports.CloseOutboxEvent{
			EventID:        "event-close-1",
			AccountID:      "account-1",
			AccountVersion: 2,
			EventType:      useraccountapp.UserAccountClosedEventName,
			PayloadJSON:    []byte(`{"userId":"account-1","accountState":"closed"}`),
			OccurredAt:     time.Now().UTC(),
		},
	}
	publisher := &fakeClosedStreamPublisher{}
	relay, err := useraccountapp.NewCloseOutboxRelay(
		store,
		publisher,
		"relay-test",
	)
	if err != nil {
		t.Fatal(err)
	}

	didWork, err := relay.RelayOnce(context.Background())
	if err != nil {
		t.Fatalf("relay close event: %v", err)
	}
	if !didWork || publisher.published != 1 || !store.published ||
		store.failed {
		t.Fatalf(
			"expected one publish ack, didWork=%v publisher=%+v store=%+v",
			didWork,
			publisher,
			store,
		)
	}
}

func TestCloseAccountOutboxRelayRetriesPublisherFailure(t *testing.T) {
	now := time.Now().UTC()
	store := &fakeCloseOutboxStore{
		found: true,
		event: accountports.CloseOutboxEvent{
			EventID:         "event-close-2",
			AccountID:       "account-2",
			AccountVersion:  3,
			EventType:       useraccountapp.UserAccountClosedEventName,
			PayloadJSON:     []byte(`{"userId":"account-2"}`),
			OccurredAt:      now,
			DeliveryAttempt: 1,
		},
	}
	publisher := &fakeClosedStreamPublisher{
		err: errors.New("stream unavailable"),
	}
	relay, err := useraccountapp.NewCloseOutboxRelay(
		store,
		publisher,
		"relay-test",
	)
	if err != nil {
		t.Fatal(err)
	}

	didWork, err := relay.RelayOnce(context.Background())
	if !didWork || err == nil {
		t.Fatalf("expected visible publisher failure, didWork=%v err=%v", didWork, err)
	}
	if !store.failed || store.published || !store.nextAttemptAt.After(now) {
		t.Fatalf("failed delivery must schedule retry: %+v", store)
	}
}
