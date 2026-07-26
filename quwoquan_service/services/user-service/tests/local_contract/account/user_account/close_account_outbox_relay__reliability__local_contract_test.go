// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package local_contract

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"strings"
	"testing"
	"time"

	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
)

type fakeCloseOutboxStore struct {
	event         accountports.UserAccountOutboxEvent
	found         bool
	published     bool
	failed        bool
	terminal      bool
	nextAttemptAt time.Time
	failure       accountports.UserAccountOutboxFailure
	terminalCount int
	claimErr      error
	retryErr      error
	terminalErr   error
}

func (store *fakeCloseOutboxStore) ClaimReady(
	context.Context,
	string,
	time.Time,
	time.Duration,
) (accountports.UserAccountOutboxEvent, bool, error) {
	if store.claimErr != nil {
		return accountports.UserAccountOutboxEvent{}, false, store.claimErr
	}
	if !store.found {
		return accountports.UserAccountOutboxEvent{}, false, nil
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
	_ time.Time,
	nextAttemptAt time.Time,
	failure accountports.UserAccountOutboxFailure,
) error {
	store.failed = true
	store.nextAttemptAt = nextAttemptAt
	store.failure = failure
	return store.retryErr
}

func (store *fakeCloseOutboxStore) MarkTerminalFailure(
	_ context.Context,
	_ string,
	_ string,
	_ time.Time,
	_ time.Time,
	failure accountports.UserAccountOutboxFailure,
) error {
	store.terminal = true
	store.terminalCount = 1
	store.failure = failure
	return store.terminalErr
}

func (store *fakeCloseOutboxStore) ListTerminalFailures(
	context.Context,
	time.Time,
	int,
) ([]accountports.UserAccountOutboxTerminalFailure, error) {
	return nil, nil
}

func (store *fakeCloseOutboxStore) ReplayTerminalFailure(
	context.Context,
	string,
	time.Time,
) error {
	store.terminal = false
	store.terminalCount = 0
	return nil
}

func (store *fakeCloseOutboxStore) PruneExpiredTerminalFailures(
	context.Context,
	time.Time,
) (int64, error) {
	return 0, nil
}

func (store *fakeCloseOutboxStore) TerminalFailureCount(
	context.Context,
) (int, error) {
	return store.terminalCount, nil
}

type fakeClosedStreamPublisher struct {
	err       error
	published int
}

type fakeCloseOutboxObserver struct {
	deliveries       []string
	ready            bool
	terminalFailures int
}

func (observer *fakeCloseOutboxObserver) RecordDelivery(result string) {
	observer.deliveries = append(observer.deliveries, result)
}

func (observer *fakeCloseOutboxObserver) RecordReadiness(
	ready bool,
	terminalFailures int,
) {
	observer.ready = ready
	observer.terminalFailures = terminalFailures
}

type signalingCloseOutboxPublisher struct {
	err    error
	called chan struct{}
}

func (publisher *signalingCloseOutboxPublisher) PublishUserAccountEvent(
	context.Context,
	accountports.UserAccountOutboxEvent,
	map[string]any,
) error {
	close(publisher.called)
	return publisher.err
}

type canceledCloseOutboxStore struct{}

func (canceledCloseOutboxStore) ClaimReady(
	ctx context.Context,
	_ string,
	_ time.Time,
	_ time.Duration,
) (accountports.UserAccountOutboxEvent, bool, error) {
	return accountports.UserAccountOutboxEvent{}, false, ctx.Err()
}

func (canceledCloseOutboxStore) MarkPublished(
	context.Context,
	string,
	string,
	time.Time,
) error {
	return nil
}

func (canceledCloseOutboxStore) MarkFailed(
	context.Context,
	string,
	string,
	time.Time,
	time.Time,
	accountports.UserAccountOutboxFailure,
) error {
	return nil
}

func (canceledCloseOutboxStore) MarkTerminalFailure(
	context.Context,
	string,
	string,
	time.Time,
	time.Time,
	accountports.UserAccountOutboxFailure,
) error {
	return nil
}

func (canceledCloseOutboxStore) ListTerminalFailures(
	context.Context,
	time.Time,
	int,
) ([]accountports.UserAccountOutboxTerminalFailure, error) {
	return nil, nil
}

func (canceledCloseOutboxStore) ReplayTerminalFailure(
	context.Context,
	string,
	time.Time,
) error {
	return nil
}

func (canceledCloseOutboxStore) PruneExpiredTerminalFailures(
	context.Context,
	time.Time,
) (int64, error) {
	return 0, nil
}

func (canceledCloseOutboxStore) TerminalFailureCount(context.Context) (int, error) {
	return 0, nil
}

func (publisher *fakeClosedStreamPublisher) PublishUserAccountEvent(
	context.Context,
	accountports.UserAccountOutboxEvent,
	map[string]any,
) error {
	publisher.published++
	return publisher.err
}

func TestCloseAccountOutboxRelayMarksPublishedAfterDurablePublish(t *testing.T) {
	store := &fakeCloseOutboxStore{
		found: true,
		event: accountports.UserAccountOutboxEvent{
			EventID:        "event-close-1",
			AccountID:      "account-1",
			AccountVersion: 2,
			EventType:      useraccountapp.UserAccountClosedEventName,
			PayloadJSON:    []byte(`{"userId":"account-1","accountState":"closed"}`),
			OccurredAt:     time.Now().UTC(),
		},
	}
	publisher := &fakeClosedStreamPublisher{}
	relay, err := useraccountapp.NewUserAccountOutboxRelay(
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
		event: accountports.UserAccountOutboxEvent{
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
		err: errors.New("stream unavailable for secret@example.com"),
	}
	relay, err := useraccountapp.NewUserAccountOutboxRelay(
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
	if store.failure.Code != "stream_publish" ||
		len(store.failure.Digest) != 64 ||
		strings.Contains(store.failure.Digest, "secret@example.com") {
		t.Fatalf("retry failure must persist only code/digest: %+v", store.failure)
	}
	if strings.Contains(err.Error(), "secret@example.com") {
		t.Fatalf("relay error leaked raw publisher cause: %v", err)
	}
}

func TestCloseAccountOutboxRelayMovesBoundedFailureToPayloadFreeTerminalState(
	t *testing.T,
) {
	store := &fakeCloseOutboxStore{
		found: true,
		event: accountports.UserAccountOutboxEvent{
			EventID:         "event-restore-terminal",
			AccountID:       "account-restore",
			AccountVersion:  9,
			EventType:       useraccountapp.UserRestoredEventName,
			PayloadJSON:     []byte(`{"userId":"account-restore"}`),
			OccurredAt:      time.Now().UTC(),
			DeliveryAttempt: 8,
		},
	}
	observer := &fakeCloseOutboxObserver{}
	relay, err := useraccountapp.NewUserAccountOutboxRelay(
		store,
		&fakeClosedStreamPublisher{
			err: errors.New("stream rejected account=account-restore"),
		},
		"relay-test",
		useraccountapp.WithUserAccountOutboxObserver(observer),
	)
	if err != nil {
		t.Fatal(err)
	}

	didWork, err := relay.RelayOnce(context.Background())
	if err != nil {
		t.Fatalf("terminal transition must complete relay work: %v", err)
	}
	if !didWork || !store.terminal || store.failed || store.published {
		t.Fatalf("bounded failure must become terminal without publish ack: %+v", store)
	}
	if store.failure.Code != "stream_publish" ||
		len(store.failure.Digest) != 64 ||
		strings.Contains(store.failure.Digest, "account-restore") {
		t.Fatalf("terminal failure must remain payload-free: %+v", store.failure)
	}
	if len(observer.deliveries) != 1 || observer.deliveries[0] != "terminal" {
		t.Fatalf("terminal delivery metric drift: %+v", observer.deliveries)
	}
}

func TestCloseAccountOutboxRelayReadinessRequiresNoTerminalFailure(t *testing.T) {
	store := &fakeCloseOutboxStore{}
	observer := &fakeCloseOutboxObserver{}
	relay, err := useraccountapp.NewUserAccountOutboxRelay(
		store,
		&fakeClosedStreamPublisher{},
		"relay-test",
		useraccountapp.WithUserAccountOutboxObserver(observer),
	)
	if err != nil {
		t.Fatal(err)
	}
	if didWork, err := relay.RelayOnce(context.Background()); didWork || err != nil {
		t.Fatalf("empty scan must establish a healthy relay heartbeat: didWork=%v err=%v", didWork, err)
	}
	if err := relay.Healthy(context.Background(), time.Second); err != nil {
		t.Fatalf("relay must be ready after a scan: %v", err)
	}
	if !observer.ready || observer.terminalFailures != 0 {
		t.Fatalf("ready metric drift: %+v", observer)
	}

	store.terminalCount = 1
	if err := relay.Healthy(context.Background(), time.Second); err == nil {
		t.Fatal("terminal failure must make readiness fail")
	}
	if observer.ready || observer.terminalFailures != 1 {
		t.Fatalf("terminal readiness metric drift: %+v", observer)
	}
}

func TestCloseAccountOutboxRelayLogsOnlyFailureCodeAndDigest(t *testing.T) {
	previous := slog.Default()
	var logs bytes.Buffer
	slog.SetDefault(slog.New(slog.NewTextHandler(&logs, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })

	publisher := &signalingCloseOutboxPublisher{
		err:    errors.New("broker rejected email=secret@example.com"),
		called: make(chan struct{}),
	}
	relay, err := useraccountapp.NewUserAccountOutboxRelay(
		&fakeCloseOutboxStore{
			found: true,
			event: accountports.UserAccountOutboxEvent{
				EventID:         "event-log-sanitize",
				AccountID:       "account-log-sanitize",
				AccountVersion:  1,
				EventType:       useraccountapp.UserAccountClosedEventName,
				PayloadJSON:     []byte(`{"userId":"account-log-sanitize"}`),
				OccurredAt:      time.Now().UTC(),
				DeliveryAttempt: 1,
			},
		},
		publisher,
		"relay-test",
	)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		relay.Run(ctx)
		close(done)
	}()
	select {
	case <-publisher.called:
	case <-time.After(time.Second):
		cancel()
		<-done
		t.Fatal("relay did not attempt stream publish")
	}
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("relay did not stop after cancellation")
	}

	logOutput := logs.String()
	if strings.Contains(logOutput, "secret@example.com") ||
		strings.Contains(logOutput, "account-log-sanitize") {
		t.Fatalf("relay log leaked raw failure context: %s", logOutput)
	}
	if !strings.Contains(logOutput, "failure_code=stream_publish") ||
		!strings.Contains(logOutput, "failure_digest=") {
		t.Fatalf("relay log omitted sanitized failure fields: %s", logOutput)
	}
}

func TestCloseAccountOutboxRelayDoesNotLogExpectedContextCancellation(t *testing.T) {
	previous := slog.Default()
	var logs bytes.Buffer
	slog.SetDefault(slog.New(slog.NewTextHandler(&logs, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })

	relay, err := useraccountapp.NewUserAccountOutboxRelay(
		canceledCloseOutboxStore{},
		&fakeClosedStreamPublisher{},
		"relay-test",
	)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	relay.Run(ctx)

	if logs.Len() != 0 {
		t.Fatalf("expected shutdown cancellation to be silent, got logs: %s", logs.String())
	}
}

func TestUserAccountOutboxRelayPublishesReversibleEnforcementEvents(t *testing.T) {
	store := &fakeCloseOutboxStore{
		found: true,
		event: accountports.UserAccountOutboxEvent{
			EventID:        "event-suspend-1",
			AccountID:      "account-3",
			AccountVersion: 4,
			EventType:      useraccountapp.UserSuspendedEventName,
			PayloadJSON: []byte(
				`{"userId":"account-3","personaIds":["persona-3"],"accountState":"suspended","authEpoch":2,"decisionRef":"decision-3","occurredAt":"2026-07-21T00:00:00Z"}`,
			),
			OccurredAt: time.Now().UTC(),
		},
	}
	publisher := &fakeClosedStreamPublisher{}
	relay, err := useraccountapp.NewUserAccountOutboxRelay(
		store,
		publisher,
		"relay-test",
	)
	if err != nil {
		t.Fatal(err)
	}
	didWork, err := relay.RelayOnce(context.Background())
	if err != nil {
		t.Fatalf("relay suspended event: %v", err)
	}
	if !didWork || publisher.published != 1 || !store.published || store.failed {
		t.Fatalf(
			"reversible enforcement event must use the same durable relay: %+v",
			store,
		)
	}
}
