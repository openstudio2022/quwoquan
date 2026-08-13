// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002
// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002.t3
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/spec.md#sit-003
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	streamadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/stream"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/infrastructure/redisstore"
)

type integrationAccountSecurityAuthority struct {
	mu        sync.RWMutex
	snapshots map[string]rtauth.AccountSecuritySnapshot
	err       error
}

func newIntegrationAccountSecurityAuthority() *integrationAccountSecurityAuthority {
	return &integrationAccountSecurityAuthority{
		snapshots: map[string]rtauth.AccountSecuritySnapshot{},
	}
}

func (authority *integrationAccountSecurityAuthority) ReadAccountSecurity(
	_ context.Context,
	accountID string,
) (rtauth.AccountSecuritySnapshot, error) {
	authority.mu.RLock()
	defer authority.mu.RUnlock()
	if authority.err != nil {
		return rtauth.AccountSecuritySnapshot{}, authority.err
	}
	if snapshot, ok := authority.snapshots[accountID]; ok {
		return snapshot, nil
	}
	return rtauth.AccountSecuritySnapshot{AccountState: "active", AuthEpoch: 1}, nil
}

func (authority *integrationAccountSecurityAuthority) set(
	accountID string,
	state string,
	epoch int64,
) {
	authority.mu.Lock()
	defer authority.mu.Unlock()
	authority.snapshots[accountID] = rtauth.AccountSecuritySnapshot{
		AccountState: state,
		AuthEpoch:    epoch,
	}
}

func (authority *integrationAccountSecurityAuthority) setError(err error) {
	authority.mu.Lock()
	defer authority.mu.Unlock()
	authority.err = err
}

type integrationConnectionSink struct {
	mu        sync.Mutex
	kickCount int
	kicked    chan struct{}
}

func newIntegrationConnectionSink() *integrationConnectionSink {
	return &integrationConnectionSink{kicked: make(chan struct{}, 1)}
}

func (sink *integrationConnectionSink) Deliver(_ string) bool {
	return true
}

func (sink *integrationConnectionSink) Kick(_ string) {
	sink.mu.Lock()
	sink.kickCount++
	sink.mu.Unlock()
	select {
	case sink.kicked <- struct{}{}:
	default:
	}
}

func (sink *integrationConnectionSink) Kicks() int {
	sink.mu.Lock()
	defer sink.mu.Unlock()
	return sink.kickCount
}

// GWT-SECURITY-001: real Redis Streams plus Redis Pub/Sub must prevent a
// UserSuspended replay from leaving a pending ticket, cross-node socket, lease,
// or presence record. A later restore admits only a fresh epoch.
func TestUserAccountSecurityTerminalStateClosesRealRedisAcrossNodes(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	realRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("account security api_integration requires real Redis: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cancelCleanup := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancelCleanup()
		_ = realRedis.Close(cleanupCtx)
	})
	if err := realRedis.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush Redis: %v", err)
	}
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"realtime": {
				Mode:     "standalone",
				Addr:     realRedis.Addr,
				Password: realRedis.Password,
				DB:       0,
				TLS:      realRedis.TLS,
			},
		},
		DefaultScene: "realtime",
	})
	if err != nil {
		t.Fatalf("new Redis router: %v", err)
	}
	t.Cleanup(func() { _ = router.Close() })
	client := router.Scene("realtime")
	transport, err := runtimemessaging.NewRedisMessageTransport(
		client,
		client,
	)
	if err != nil {
		t.Fatalf("new Redis message transport: %v", err)
	}

	authority := newIntegrationAccountSecurityAuthority()
	presenceProjection := newIntegrationPresenceProjection(t, client)
	stateStore := redisstore.NewAccountSecurityStateStore(
		client,
		presenceProjection,
	)
	relay := redisstore.NewAccountSecurityRelay(client)
	eventSource := redisstore.NewEventSource(transport)
	newHub := func(nodeID string) *application.Hub {
		hub, hubErr := application.NewHub(
			redisstore.NewLeaseStore(client),
			presenceProjection,
			eventSource,
			authority,
			stateStore,
			relay,
			nodeID,
			nil,
		)
		if hubErr != nil {
			t.Fatalf("new %s hub: %v", nodeID, hubErr)
		}
		if hubErr := hub.StartAccountSecurityRelay(ctx); hubErr != nil {
			t.Fatalf("start %s relay: %v", nodeID, hubErr)
		}
		t.Cleanup(hub.CloseAccountSecurityRelay)
		return hub
	}
	consumerHub := newHub("node-consumer")
	remoteHub := newHub("node-remote")
	tickets, err := application.NewTicketService(
		redisstore.NewTicketStore(client),
		authority,
		stateStore,
	)
	if err != nil {
		t.Fatalf("new ticket service: %v", err)
	}

	identity := application.TrustedIdentity{
		AccountID: "account-security-api",
		PersonaID: "persona-security-api",
		DeviceID:  "device-security-api",
	}
	pending, err := tickets.Issue(ctx, identity, 1)
	if err != nil {
		t.Fatalf("issue pending ticket: %v", err)
	}
	sink := newIntegrationConnectionSink()
	detach, err := remoteHub.Attach(
		ctx,
		identity,
		1,
		"connection-security-api",
		"websocket",
		sink,
	)
	if err != nil {
		t.Fatalf("attach remote connection: %v", err)
	}
	t.Cleanup(detach)

	consumerConfig := streamadapter.DefaultUserAccountSecurityConsumerConfig()
	consumerConfig.MinIdle = 0
	consumer, err := streamadapter.NewUserAccountSecurityConsumer(
		transport,
		stateStore,
		relay,
		consumerHub,
		redisstore.NewAccountSecurityEventFailureStore(client),
		"api-integration-consumer",
		nil,
		consumerConfig,
	)
	if err != nil {
		t.Fatalf("new account security consumer: %v", err)
	}
	appendSuspendedUserAccountEvent(t, ctx, transport, identity, "event-api-terminal")
	appendSuspendedUserAccountEvent(t, ctx, transport, identity, "event-api-terminal")
	if processed, processErr := consumer.ProcessOnce(ctx); processErr != nil || processed != 2 {
		t.Fatalf("process terminal replays=%d err=%v", processed, processErr)
	}
	select {
	case <-sink.kicked:
	case <-time.After(5 * time.Second):
		t.Fatal("remote node did not receive terminal security relay")
	}
	if sink.Kicks() != 1 {
		t.Fatalf("duplicate terminal event kicked remote socket %d times, want 1", sink.Kicks())
	}
	if _, consumeErr := tickets.Consume(ctx, pending.Ticket); !errors.Is(
		consumeErr,
		application.ErrTicketInvalid,
	) {
		t.Fatalf("terminal event must reject pending ticket, got %v", consumeErr)
	}
	presence, presenceErr := client.HGetAll(
		ctx,
		"presence:persona:"+identity.PersonaID,
	)
	if presenceErr != nil {
		t.Fatalf("read presence after terminal event: %v", presenceErr)
	}
	if len(presence) != 0 {
		t.Fatalf("residual presence after terminal event: %v", presence)
	}
	if _, leaseErr := client.Get(
		ctx,
		"rt:conn:lease:"+identity.PersonaID+":"+identity.DeviceID+
			":connection-security-api",
	); !errors.Is(leaseErr, rtredis.ErrKeyNotFound) {
		t.Fatalf("residual lease after terminal event: %v", leaseErr)
	}
	if err := stateStore.Admit(ctx, identity, 1); !errors.Is(
		err,
		application.ErrAccountSecurityDenied,
	) {
		t.Fatalf("terminal state admission = %v, want denial", err)
	}

	authority.set(identity.AccountID, "active", 3)
	appendRestoredUserAccountEvent(t, ctx, transport, identity, "event-api-restored", 3)
	if processed, processErr := consumer.ProcessOnce(ctx); processErr != nil || processed != 1 {
		t.Fatalf("process restore=%d err=%v", processed, processErr)
	}
	if err := stateStore.Admit(ctx, identity, 1); !errors.Is(
		err,
		application.ErrAccountSecurityDenied,
	) {
		t.Fatalf("restore revived old auth epoch: %v", err)
	}
	if _, consumeErr := tickets.Consume(ctx, pending.Ticket); !errors.Is(
		consumeErr,
		application.ErrTicketInvalid,
	) {
		t.Fatalf("restore revived old ticket: %v", consumeErr)
	}
	if _, issueErr := tickets.Issue(ctx, identity, 3); issueErr != nil {
		t.Fatalf("restore did not admit a fresh auth epoch: %v", issueErr)
	}

	authority.setError(rtauth.ErrAccountSecurityUnavailable)
	if _, issueErr := tickets.Issue(ctx, identity, 3); !errors.Is(
		issueErr,
		application.ErrAccountSecurityUnavailable,
	) {
		t.Fatalf("unavailable authority must fail closed, got %v", issueErr)
	}
}

func appendSuspendedUserAccountEvent(
	t *testing.T,
	ctx context.Context,
	transport runtimemessaging.MessageTransport,
	identity application.TrustedIdentity,
	eventID string,
) {
	t.Helper()
	now := time.Now().UTC()
	payload, err := json.Marshal(map[string]any{
		"userId":       identity.AccountID,
		"personaIds":   []string{identity.PersonaID},
		"accountState": "suspended",
		"authEpoch":    2,
		"decisionRef":  "decision-reference",
		"occurredAt":   now.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("marshal suspension payload: %v", err)
	}
	appendUserAccountSecurityStreamRecord(
		t,
		ctx,
		transport,
		"UserSuspended",
		eventID,
		identity.AccountID,
		string(payload),
		now,
	)
}

func appendRestoredUserAccountEvent(
	t *testing.T,
	ctx context.Context,
	transport runtimemessaging.MessageTransport,
	identity application.TrustedIdentity,
	eventID string,
	authEpoch int64,
) {
	t.Helper()
	now := time.Now().UTC()
	payload, err := json.Marshal(map[string]any{
		"userId":       identity.AccountID,
		"personaIds":   []string{identity.PersonaID},
		"accountState": "active",
		"authEpoch":    authEpoch,
		"decisionRef":  "decision-reference",
		"occurredAt":   now.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("marshal restore payload: %v", err)
	}
	appendUserAccountSecurityStreamRecord(
		t,
		ctx,
		transport,
		"UserRestored",
		eventID,
		identity.AccountID,
		string(payload),
		now,
	)
}

func appendUserAccountSecurityStreamRecord(
	t *testing.T,
	ctx context.Context,
	transport runtimemessaging.MessageTransport,
	eventName string,
	eventID string,
	accountID string,
	payload string,
	occurredAt time.Time,
) {
	t.Helper()
	if _, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: "events.user.account",
		Fields: []runtimemessaging.DurableField{
			{Name: "eventName", Value: eventName},
			{Name: "eventId", Value: eventID},
			{Name: "accountId", Value: accountID},
			{Name: "accountVersion", Value: "1"},
			{Name: "occurredAt", Value: occurredAt.Format(time.RFC3339Nano)},
			{Name: "payload", Value: payload},
		},
	}); err != nil {
		t.Fatalf("append UserAccount security stream record: %v", err)
	}
}
