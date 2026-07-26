// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	streamadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/stream"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/infrastructure/redisstore"
)

type testConnectionSink struct {
	mu        sync.Mutex
	kickCount int
	kicked    chan string
}

type failOnceAccountSecurityGate struct {
	application.AccountSecurityGate
	mu       sync.Mutex
	failNext bool
}

func (gate *failOnceAccountSecurityGate) ApplyAccountSecurityEvent(
	ctx context.Context,
	event application.AccountSecurityEvent,
) (application.AccountSecurityApplyResult, error) {
	gate.mu.Lock()
	shouldFail := gate.failNext
	gate.failNext = false
	gate.mu.Unlock()
	if shouldFail {
		return application.AccountSecurityApplyResult{},
			application.ErrAccountSecurityUnavailable
	}
	return gate.AccountSecurityGate.ApplyAccountSecurityEvent(ctx, event)
}

func newTestConnectionSink() *testConnectionSink {
	return &testConnectionSink{kicked: make(chan string, 1)}
}

func (sink *testConnectionSink) Deliver(_ string) bool {
	return true
}

func (sink *testConnectionSink) Kick(reason string) {
	sink.mu.Lock()
	sink.kickCount++
	sink.mu.Unlock()
	select {
	case sink.kicked <- reason:
	default:
	}
}

func (sink *testConnectionSink) Kicks() int {
	sink.mu.Lock()
	defer sink.mu.Unlock()
	return sink.kickCount
}

func newAccountSecurityConsumer(
	t *testing.T,
	harness *gatewayHarness,
	maxAttempts int64,
) (*streamadapter.UserAccountSecurityConsumer, runtimemessaging.MessageTransport) {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"realtime-gateway-security-local-contract",
		runtimemessaging.RedisMessageTransportFixture,
		harness.client,
		harness.client,
	)
	if err != nil {
		t.Fatalf("new durable transport: %v", err)
	}
	config := streamadapter.DefaultUserAccountSecurityConsumerConfig()
	config.MaxAttempts = maxAttempts
	config.MinIdle = 0
	consumer, err := streamadapter.NewUserAccountSecurityConsumer(
		transport,
		redisstore.NewAccountSecurityStateStore(harness.client),
		redisstore.NewAccountSecurityRelay(harness.client),
		harness.hub,
		redisstore.NewAccountSecurityEventFailureStore(harness.client),
		"local-contract-consumer",
		nil,
		config,
	)
	if err != nil {
		t.Fatalf("new account security consumer: %v", err)
	}
	return consumer, transport
}

func appendUserAccountSecurityEvent(
	t *testing.T,
	transport runtimemessaging.MessageTransport,
	eventName string,
	eventID string,
	accountID string,
	personaID string,
	authEpoch int64,
) string {
	t.Helper()
	now := time.Now().UTC()
	payload := map[string]any{
		"userId":       accountID,
		"personaIds":   []string{personaID},
		"accountState": "closed",
		"updatedAt":    now.Format(time.RFC3339Nano),
	}
	switch eventName {
	case "UserSuspended":
		payload = map[string]any{
			"userId":       accountID,
			"personaIds":   []string{personaID},
			"accountState": "suspended",
			"authEpoch":    authEpoch,
			"decisionRef":  "decision-reference",
			"occurredAt":   now.Format(time.RFC3339Nano),
		}
	case "UserRestored":
		payload = map[string]any{
			"userId":       accountID,
			"personaIds":   []string{personaID},
			"accountState": "active",
			"authEpoch":    authEpoch,
			"decisionRef":  "decision-reference",
			"occurredAt":   now.Format(time.RFC3339Nano),
		}
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal UserAccount security payload: %v", err)
	}
	messageID, err := transport.AppendDurable(
		context.Background(),
		runtimemessaging.DurableMessage{
			Stream: "events.user.account",
			Fields: []runtimemessaging.DurableField{
				{Name: "eventName", Value: eventName},
				{Name: "eventId", Value: eventID},
				{Name: "accountId", Value: accountID},
				{Name: "accountVersion", Value: "1"},
				{Name: "occurredAt", Value: now.Format(time.RFC3339Nano)},
				{Name: "payload", Value: string(encoded)},
			},
		},
	)
	if err != nil {
		t.Fatalf("append UserAccount security event: %v", err)
	}
	return messageID
}

func TestUserAccountSuspensionRejectsPendingTicketEvictsAndClearsPresence(
	t *testing.T,
) {
	harness := newGatewayHarness(t)
	consumer, transport := newAccountSecurityConsumer(t, harness, 5)
	const accountID = "account-security-local"
	const personaID = "persona-security-local"
	const deviceID = "device-security-local"

	pendingTicket := issueTicket(t, harness, accountID, personaID, deviceID)
	activeTicket := issueTicket(t, harness, accountID, personaID, "device-active")
	connection := dialWebSocket(t, harness, activeTicket)
	if frame := readFrame(t, connection); frame["type"] != "auth_ack" {
		t.Fatalf("websocket acknowledgement = %v", frame)
	}

	appendUserAccountSecurityEvent(
		t,
		transport,
		"UserSuspended",
		"event-suspended-local",
		accountID,
		personaID,
		2,
	)
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("suspension consume processed=%d err=%v", processed, err)
	}

	readContext, cancelRead := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancelRead()
	if _, _, err := connection.Read(readContext); err == nil {
		t.Fatal("suspended account websocket must be evicted")
	}
	if _, err := harness.tickets.Consume(context.Background(), pendingTicket); !errors.Is(
		err,
		application.ErrTicketInvalid,
	) {
		t.Fatalf("terminal event must revoke pending ticket, got %v", err)
	}
	presence, err := harness.client.HGetAll(
		context.Background(),
		"presence:persona:"+personaID,
	)
	if err != nil {
		t.Fatalf("read residual presence: %v", err)
	}
	if len(presence) != 0 {
		t.Fatalf("terminal event left residual presence: %v", presence)
	}
}

func TestUserAccountSuspensionEvictsActiveLongPoll(t *testing.T) {
	harness := newGatewayHarness(t)
	consumer, transport := newAccountSecurityConsumer(t, harness, 5)
	const accountID = "account-security-long-poll"
	const personaID = "persona-security-long-poll"
	const deviceID = "device-security-long-poll"
	requestContext, cancelRequest := context.WithTimeout(
		context.Background(),
		5*time.Second,
	)
	defer cancelRequest()
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodGet,
		harness.server.URL+"/realtime/poll?timeout=30",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("X-Test-Account", accountID)
	request.Header.Set("X-Test-Persona", personaID)
	request.Header.Set("X-Test-Device", deviceID)
	responseCh := make(chan *http.Response, 1)
	errorCh := make(chan error, 1)
	go func() {
		response, requestErr := harness.server.Client().Do(request)
		if requestErr != nil {
			errorCh <- requestErr
			return
		}
		responseCh <- response
	}()
	waitForLongPollPresence(t, harness, personaID)

	appendUserAccountSecurityEvent(
		t,
		transport,
		"UserSuspended",
		"event-long-poll-local",
		accountID,
		personaID,
		2,
	)
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("long-poll suspension consume processed=%d err=%v", processed, err)
	}
	select {
	case err := <-errorCh:
		t.Fatalf("long-poll request failed: %v", err)
	case response := <-responseCh:
		defer func() { _ = response.Body.Close() }()
		if response.StatusCode != http.StatusUnauthorized {
			t.Fatalf("suspended long-poll status = %d, want 401", response.StatusCode)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("suspended long-poll did not return promptly")
	}
}

func waitForLongPollPresence(
	t *testing.T,
	harness *gatewayHarness,
	personaID string,
) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for {
		entries, err := harness.client.HGetAll(
			context.Background(),
			"presence:persona:"+personaID,
		)
		if err == nil && len(entries) > 0 {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("long-poll did not register presence: %v", err)
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func TestAccountSecurityStateIsIdempotentAndRestoreDoesNotReviveOldTicket(
	t *testing.T,
) {
	harness := newGatewayHarness(t)
	identity := application.TrustedIdentity{
		AccountID: "account-security-idempotent",
		PersonaID: "persona-security-idempotent",
		DeviceID:  "device-security-idempotent",
	}
	issued, err := harness.tickets.Issue(context.Background(), identity, 1)
	if err != nil {
		t.Fatalf("issue pre-terminal ticket: %v", err)
	}
	store := redisstore.NewAccountSecurityStateStore(harness.client)
	suspended := application.AccountSecurityEvent{
		EventID:      "event-idempotent",
		AccountID:    identity.AccountID,
		PersonaIDs:   []string{identity.PersonaID},
		AccountState: "suspended",
		AuthEpoch:    2,
		OccurredAt:   time.Now().UTC(),
	}
	first, err := store.ApplyAccountSecurityEvent(context.Background(), suspended)
	if err != nil || !first.Evict || first.Replayed {
		t.Fatalf("first terminal apply = %+v err=%v", first, err)
	}
	replayed, err := store.ApplyAccountSecurityEvent(context.Background(), suspended)
	if err != nil || !replayed.Evict || !replayed.Replayed {
		t.Fatalf("replayed terminal apply = %+v err=%v", replayed, err)
	}
	restored := suspended
	restored.EventID = "event-restored"
	restored.AccountState = "active"
	restored.AuthEpoch = 3
	restored.OccurredAt = time.Now().UTC()
	if result, err := store.ApplyAccountSecurityEvent(context.Background(), restored); err != nil || result.Evict {
		t.Fatalf("restore apply = %+v err=%v", result, err)
	}
	if _, err := harness.tickets.Consume(context.Background(), issued.Ticket); !errors.Is(
		err,
		application.ErrTicketInvalid,
	) {
		t.Fatalf("restore must not revive pre-terminal ticket, got %v", err)
	}
	if err := store.Admit(context.Background(), identity, 1); !errors.Is(
		err,
		application.ErrAccountSecurityDenied,
	) {
		t.Fatalf("old auth epoch must remain rejected after restore, got %v", err)
	}
}

func TestUserAccountClosedIsIrreversibleAfterRestoreEvent(t *testing.T) {
	harness := newGatewayHarness(t)
	consumer, transport := newAccountSecurityConsumer(t, harness, 5)
	identity := application.TrustedIdentity{
		AccountID: "account-security-closed",
		PersonaID: "persona-security-closed",
		DeviceID:  "device-security-closed",
	}
	issued, err := harness.tickets.Issue(context.Background(), identity, 1)
	if err != nil {
		t.Fatalf("issue closed-account ticket: %v", err)
	}
	appendUserAccountSecurityEvent(
		t,
		transport,
		"UserAccountClosed",
		"event-closed-local",
		identity.AccountID,
		identity.PersonaID,
		0,
	)
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("consume close processed=%d err=%v", processed, err)
	}
	harness.authority.set(identity.AccountID, "active", 3)
	appendUserAccountSecurityEvent(
		t,
		transport,
		"UserRestored",
		"event-closed-restore-local",
		identity.AccountID,
		identity.PersonaID,
		3,
	)
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("consume closed-account restore processed=%d err=%v", processed, err)
	}
	store := redisstore.NewAccountSecurityStateStore(harness.client)
	if err := store.Admit(context.Background(), identity, 3); !errors.Is(
		err,
		application.ErrAccountSecurityDenied,
	) {
		t.Fatalf("closed account must remain terminal after restore event, got %v", err)
	}
	if _, err := harness.tickets.Consume(context.Background(), issued.Ticket); !errors.Is(
		err,
		application.ErrTicketInvalid,
	) {
		t.Fatalf("closed account restore revived old ticket: %v", err)
	}
}

func TestAccountSecurityRelayEvictsRemoteNodeExactlyOnce(t *testing.T) {
	harness := newGatewayHarness(t)
	store := redisstore.NewAccountSecurityStateStore(harness.client)
	relay := redisstore.NewAccountSecurityRelay(harness.client)
	remoteHub, err := application.NewHub(
		redisstore.NewLeaseStore(harness.client),
		redisstore.NewPresenceStore(harness.client),
		newTestEventSource(t, harness.client),
		harness.authority,
		store,
		relay,
		"node-remote",
		nil,
	)
	if err != nil {
		t.Fatalf("new remote hub: %v", err)
	}
	if err := remoteHub.StartAccountSecurityRelay(context.Background()); err != nil {
		t.Fatalf("start remote relay: %v", err)
	}
	t.Cleanup(remoteHub.CloseAccountSecurityRelay)

	identity := application.TrustedIdentity{
		AccountID: "account-security-remote",
		PersonaID: "persona-security-remote",
		DeviceID:  "device-security-remote",
	}
	sink := newTestConnectionSink()
	detach, err := remoteHub.Attach(
		context.Background(),
		identity,
		1,
		"remote-connection",
		"websocket",
		sink,
	)
	if err != nil {
		t.Fatalf("attach remote connection: %v", err)
	}
	t.Cleanup(detach)
	event := application.AccountSecurityEvent{
		EventID:      "event-remote",
		AccountID:    identity.AccountID,
		PersonaIDs:   []string{identity.PersonaID},
		AccountState: "suspended",
		AuthEpoch:    2,
		OccurredAt:   time.Now().UTC(),
	}
	if result, err := store.ApplyAccountSecurityEvent(context.Background(), event); err != nil || !result.Evict {
		t.Fatalf("apply remote terminal state = %+v err=%v", result, err)
	}
	if err := relay.PublishAccountSecurity(context.Background(), event); err != nil {
		t.Fatalf("publish remote relay: %v", err)
	}
	select {
	case <-sink.kicked:
	case <-time.After(2 * time.Second):
		t.Fatal("remote node did not receive account-security eviction relay")
	}
	if sink.Kicks() != 1 {
		t.Fatalf("remote connection kick count = %d, want 1", sink.Kicks())
	}
}

func TestAccountSecurityAuthorityUnavailableDeniesTicketIssue(t *testing.T) {
	harness := newGatewayHarness(t)
	harness.authority.setError(rtauth.ErrAccountSecurityUnavailable)
	_, err := harness.tickets.Issue(
		context.Background(),
		application.TrustedIdentity{
			AccountID: "account-security-unavailable",
			PersonaID: "persona-security-unavailable",
			DeviceID:  "device-security-unavailable",
		},
		1,
	)
	if !errors.Is(err, application.ErrAccountSecurityUnavailable) {
		t.Fatalf("unavailable authority must deny ticket issuance, got %v", err)
	}
	request, err := http.NewRequest(
		http.MethodPost,
		harness.server.URL+"/realtime/tickets",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("X-Test-Account", "account-security-unavailable")
	request.Header.Set("X-Test-Persona", "persona-security-unavailable")
	request.Header.Set("X-Test-Device", "device-security-unavailable")
	response, err := harness.server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("unavailable authority ticket status = %d, want 503", response.StatusCode)
	}
	var body struct {
		Code string `json:"code"`
	}
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.Code != "REALTIME.SYSTEM.account_security_authority_unavailable" {
		t.Fatalf("unavailable authority error code = %q", body.Code)
	}
}

func TestWebSocketAttachRechecksAuthorityAfterTicketConsumption(t *testing.T) {
	harness := newGatewayHarness(t)
	identity := application.TrustedIdentity{
		AccountID: "account-security-stale-upgrade",
		PersonaID: "persona-security-stale-upgrade",
		DeviceID:  "device-security-stale-upgrade",
	}
	issued, err := harness.tickets.Issue(context.Background(), identity, 1)
	if err != nil {
		t.Fatalf("issue ticket: %v", err)
	}
	claims, err := harness.tickets.Consume(context.Background(), issued.Ticket)
	if err != nil {
		t.Fatalf("consume ticket before epoch advance: %v", err)
	}
	harness.authority.set(identity.AccountID, "active", 2)
	if _, err := harness.hub.Attach(
		context.Background(),
		claims.TrustedIdentity,
		claims.AuthEpoch,
		"connection-stale-upgrade",
		"websocket",
		newTestConnectionSink(),
	); !errors.Is(err, application.ErrAccountSecurityDenied) {
		t.Fatalf("websocket attach must recheck and reject stale auth epoch, got %v", err)
	}
	presence, err := harness.client.HGetAll(
		context.Background(),
		"presence:persona:"+identity.PersonaID,
	)
	if err != nil {
		t.Fatalf("read stale-upgrade presence: %v", err)
	}
	if len(presence) != 0 {
		t.Fatalf("stale websocket upgrade registered presence: %v", presence)
	}
}

func TestTicketConsumptionRejectsAuthorityStaleEpoch(t *testing.T) {
	harness := newGatewayHarness(t)
	identity := application.TrustedIdentity{
		AccountID: "account-security-stale-ticket",
		PersonaID: "persona-security-stale-ticket",
		DeviceID:  "device-security-stale-ticket",
	}
	issued, err := harness.tickets.Issue(context.Background(), identity, 1)
	if err != nil {
		t.Fatalf("issue stale ticket: %v", err)
	}
	harness.authority.set(identity.AccountID, "active", 2)
	if _, err := harness.tickets.Consume(context.Background(), issued.Ticket); !errors.Is(
		err,
		application.ErrAccountSecurityDenied,
	) {
		t.Fatalf("stale ticket consumption must be rejected, got %v", err)
	}
}

func TestAccountSecurityDLQOnlyRetainsDigests(t *testing.T) {
	harness := newGatewayHarness(t)
	consumer, transport := newAccountSecurityConsumer(t, harness, 1)
	const accountID = "account-sensitive-value"
	const personaID = "persona-sensitive-value"
	const payloadSecret = "payload-sensitive-value"
	now := time.Now().UTC()
	if _, err := transport.AppendDurable(
		context.Background(),
		runtimemessaging.DurableMessage{
			Stream: "events.user.account",
			Fields: []runtimemessaging.DurableField{
				{Name: "eventName", Value: "UserSuspended"},
				{Name: "eventId", Value: "event-sensitive-value"},
				{Name: "accountId", Value: accountID},
				{Name: "accountVersion", Value: "1"},
				{Name: "occurredAt", Value: now.Format(time.RFC3339Nano)},
				{Name: "payload", Value: `{"userId":"account-sensitive-value","personaIds":["persona-sensitive-value"],"accountState":"suspended","authEpoch":2,"decisionRef":"payload-sensitive-value","occurredAt":"` + now.Format(time.RFC3339Nano) + `","unexpected":"payload-sensitive-value"}`},
			},
		},
	); err != nil {
		t.Fatalf("append invalid UserAccount event: %v", err)
	}
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("process invalid event processed=%d err=%v", processed, err)
	}
	durable, ok := transport.(runtimemessaging.DurableDeliveryTransport)
	if !ok {
		t.Fatal("test message transport must expose durable reader")
	}
	const dlqGroup = "realtime-gateway-security-dlq-local-contract"
	if err := durable.EnsureDurableConsumerGroup(
		context.Background(),
		"events.user.account.realtime-gateway.dlq",
		dlqGroup,
		"0",
	); err != nil {
		t.Fatalf("create DLQ consumer group: %v", err)
	}
	records, err := durable.ReadDurable(
		context.Background(),
		runtimemessaging.StreamReadRequest{
			Stream:   "events.user.account.realtime-gateway.dlq",
			Group:    dlqGroup,
			Consumer: "local-contract-reader",
			Count:    1,
			Block:    100 * time.Millisecond,
		},
	)
	if err != nil || len(records) != 1 {
		t.Fatalf("read DLQ records=%d err=%v", len(records), err)
	}
	for _, field := range records[0].Fields {
		for _, prohibited := range []string{accountID, personaID, payloadSecret} {
			if strings.Contains(field.Value, prohibited) {
				t.Fatalf("DLQ field %q leaked protected source value", field.Name)
			}
		}
	}
}

func TestAccountSecurityDeadLetterRecoveryReplaysOriginalPEL(t *testing.T) {
	harness := newGatewayHarness(t)
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"realtime-gateway-security-recovery-local-contract",
		runtimemessaging.RedisMessageTransportFixture,
		harness.client,
		harness.client,
	)
	if err != nil {
		t.Fatalf("new recovery transport: %v", err)
	}
	stateStore := redisstore.NewAccountSecurityStateStore(harness.client)
	failureStore := redisstore.NewAccountSecurityEventFailureStore(harness.client)
	consumerConfig := streamadapter.DefaultUserAccountSecurityConsumerConfig()
	consumerConfig.MaxAttempts = 1
	consumerConfig.MinIdle = 0
	consumer, err := streamadapter.NewUserAccountSecurityConsumer(
		transport,
		&failOnceAccountSecurityGate{
			AccountSecurityGate: stateStore,
			failNext:            true,
		},
		redisstore.NewAccountSecurityRelay(harness.client),
		harness.hub,
		failureStore,
		"local-contract-recovery-consumer",
		nil,
		consumerConfig,
	)
	if err != nil {
		t.Fatalf("new recovery consumer: %v", err)
	}
	const transientMessageID = "1710000000000-1"
	if attempts, err := failureStore.RecordAccountSecurityFailure(
		t.Context(),
		"events.user.account",
		transientMessageID,
		"event-transient-recovery-guard",
		"dependency",
		errors.New("temporary dependency failure"),
	); err != nil || attempts != 1 {
		t.Fatalf("record transient recovery guard: attempts=%d err=%v", attempts, err)
	}
	if err := consumer.RecoverDeadLetter(t.Context(), transientMessageID); err != nil {
		t.Fatalf("non-terminal recovery must be an idempotent no-op: %v", err)
	}
	if attempts, err := failureStore.RecordAccountSecurityFailure(
		t.Context(),
		"events.user.account",
		transientMessageID,
		"event-transient-recovery-guard",
		"dependency",
		errors.New("temporary dependency failure"),
	); err != nil || attempts != 2 {
		t.Fatalf(
			"non-terminal recovery cleared retry receipt: attempts=%d err=%v",
			attempts,
			err,
		)
	}
	identity := application.TrustedIdentity{
		AccountID: "account-security-recovery",
		PersonaID: "persona-security-recovery",
		DeviceID:  "device-security-recovery",
	}
	pending, err := harness.tickets.Issue(context.Background(), identity, 1)
	if err != nil {
		t.Fatalf("issue recovery ticket: %v", err)
	}
	messageID := appendUserAccountSecurityEvent(
		t,
		transport,
		"UserSuspended",
		"event-recovery-local",
		identity.AccountID,
		identity.PersonaID,
		2,
	)
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("first process (DLQ) processed=%d err=%v", processed, err)
	}
	if err := consumer.RecoverDeadLetter(context.Background(), messageID); err != nil {
		t.Fatalf("clear dead-letter recovery state: %v", err)
	}
	if processed, err := consumer.ProcessOnce(context.Background()); err != nil || processed != 1 {
		t.Fatalf("recovered PEL process=%d err=%v", processed, err)
	}
	if _, err := harness.tickets.Consume(context.Background(), pending.Ticket); !errors.Is(
		err,
		application.ErrTicketInvalid,
	) {
		t.Fatalf("recovered terminal event did not revoke ticket: %v", err)
	}
}

func TestAccountSecurityFailureStoreRejectsTerminalMarkerWithoutSourceReference(
	t *testing.T,
) {
	harness := newGatewayHarness(t)
	store := redisstore.NewAccountSecurityEventFailureStore(harness.client)
	const (
		stream    = "events.user.account"
		messageID = "1710000000000-99"
	)
	if err := store.MarkAccountSecurityDeadLettered(
		t.Context(),
		stream,
		messageID,
	); err == nil || !strings.Contains(err.Error(), "source PEL reference") {
		t.Fatalf("terminal marker without source reference was accepted: %v", err)
	}
	if attempts, err := store.RecordAccountSecurityFailure(
		t.Context(),
		stream,
		messageID,
		"event-99",
		"dependency",
		errors.New("relay unavailable"),
	); err != nil || attempts != 1 {
		t.Fatalf("record source failure: attempts=%d err=%v", attempts, err)
	}
	if err := store.MarkAccountSecurityDeadLettered(
		t.Context(),
		stream,
		messageID,
	); err != nil {
		t.Fatalf("mark source PEL held: %v", err)
	}
}
