// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package local_contract

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/infrastructure/redisstore"
)

type cyclingAccountSecurityRelay struct {
	mu                    sync.Mutex
	subscriptions         []*cyclingAccountSecuritySubscription
	subscribeCalls        int
	reconnectFailuresLeft int
}

func newCyclingAccountSecurityRelay(
	subscriptionCount int,
	reconnectFailures int,
) *cyclingAccountSecurityRelay {
	subscriptions := make([]*cyclingAccountSecuritySubscription, 0, subscriptionCount)
	for range subscriptionCount {
		subscriptions = append(subscriptions, &cyclingAccountSecuritySubscription{
			events: make(chan application.AccountSecurityEvent, 1),
		})
	}
	return &cyclingAccountSecurityRelay{
		subscriptions:         subscriptions,
		reconnectFailuresLeft: reconnectFailures,
	}
}

func (relay *cyclingAccountSecurityRelay) PublishAccountSecurity(
	context.Context,
	application.AccountSecurityEvent,
) error {
	return nil
}

func (relay *cyclingAccountSecurityRelay) SubscribeAccountSecurity(
	context.Context,
) (application.AccountSecurityRelaySubscription, error) {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	if relay.subscribeCalls > 0 && relay.reconnectFailuresLeft > 0 {
		relay.reconnectFailuresLeft--
		return nil, errors.New("scripted account security relay reconnect failure")
	}
	if relay.subscribeCalls >= len(relay.subscriptions) {
		return nil, errors.New("no scripted account security relay subscription")
	}
	subscription := relay.subscriptions[relay.subscribeCalls]
	relay.subscribeCalls++
	return subscription, nil
}

func (relay *cyclingAccountSecurityRelay) subscription(
	index int,
) *cyclingAccountSecuritySubscription {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	return relay.subscriptions[index]
}

func (relay *cyclingAccountSecurityRelay) subscriptionsStarted() int {
	relay.mu.Lock()
	defer relay.mu.Unlock()
	return relay.subscribeCalls
}

type cyclingAccountSecuritySubscription struct {
	events    chan application.AccountSecurityEvent
	closeOnce sync.Once
}

func (subscription *cyclingAccountSecuritySubscription) Events() <-chan application.AccountSecurityEvent {
	return subscription.events
}

func (subscription *cyclingAccountSecuritySubscription) Close() error {
	subscription.closeOnce.Do(func() {
		close(subscription.events)
	})
	return nil
}

// spec_ref: GWT-002
func TestAccountSecurityRelayReconnectsBeforeReadinessRecovers(t *testing.T) {
	client := rtredis.NewMemoryClient()
	authority := newTestAccountSecurityAuthority()
	presenceProjection := newTestPresenceProjection(t, client)
	securityStore := redisstore.NewAccountSecurityStateStore(
		client,
		presenceProjection,
	)
	relay := newCyclingAccountSecurityRelay(2, 1)
	hub, err := application.NewHub(
		redisstore.NewLeaseStore(client),
		presenceProjection,
		newTestEventSource(t, client),
		authority,
		securityStore,
		relay,
		"node-relay-recovery",
		slog.Default(),
	)
	if err != nil {
		t.Fatalf("new hub: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	t.Cleanup(hub.CloseAccountSecurityRelay)
	if err := hub.StartAccountSecurityRelay(ctx); err != nil {
		t.Fatalf("start account security relay: %v", err)
	}
	if err := hub.AccountSecurityRelayHealthy(); err != nil {
		t.Fatalf("initial account security relay health: %v", err)
	}

	identity := application.TrustedIdentity{
		AccountID: "account-relay-recovery",
		PersonaID: "persona-relay-recovery",
		DeviceID:  "device-relay-recovery",
	}
	sink := newTestConnectionSink()
	detach, err := hub.Attach(
		ctx,
		identity,
		1,
		"connection-relay-recovery",
		"websocket",
		sink,
	)
	if err != nil {
		t.Fatalf("attach connection: %v", err)
	}
	t.Cleanup(detach)

	if err := relay.subscription(0).Close(); err != nil {
		t.Fatalf("close first relay subscription: %v", err)
	}
	waitForAccountSecurityRelayCondition(t, 2*time.Second, func() bool {
		return hub.AccountSecurityRelayHealthy() != nil
	}, "relay readiness did not fail after subscription closure")
	waitForAccountSecurityRelayCondition(t, 2*time.Second, func() bool {
		return relay.subscriptionsStarted() == 2 &&
			hub.AccountSecurityRelayHealthy() == nil
	}, "relay did not reconnect and recover readiness")

	event := application.AccountSecurityEvent{
		EventID:      "event-relay-recovery",
		AccountID:    identity.AccountID,
		PersonaIDs:   []string{identity.PersonaID},
		AccountState: "suspended",
		AuthEpoch:    2,
		OccurredAt:   time.Now().UTC(),
	}
	if result, err := securityStore.ApplyAccountSecurityEvent(ctx, event); err != nil || !result.Evict {
		t.Fatalf("apply terminal account state: result=%+v err=%v", result, err)
	}
	relay.subscription(1).events <- event
	select {
	case <-sink.kicked:
	case <-time.After(2 * time.Second):
		t.Fatal("reconnected relay did not evict active connection")
	}
	if sink.Kicks() != 1 {
		t.Fatalf("reconnected relay kick count=%d, want 1", sink.Kicks())
	}
}

func waitForAccountSecurityRelayCondition(
	t *testing.T,
	timeout time.Duration,
	condition func() bool,
	failure string,
) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if condition() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal(failure)
}
