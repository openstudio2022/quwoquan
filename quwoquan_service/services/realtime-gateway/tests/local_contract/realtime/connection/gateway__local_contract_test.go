package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"

	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/http"
	wsadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/ws"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/infrastructure/redisstore"
)

type gatewayHarness struct {
	client    rtredis.Client
	authority *testAccountSecurityAuthority
	tickets   *application.TicketService
	hub       *application.Hub
	server    *httptest.Server
}

func newGatewayHarness(t *testing.T) *gatewayHarness {
	t.Helper()
	client := rtredis.NewMemoryClient()
	authority := newTestAccountSecurityAuthority()
	securityStore := redisstore.NewAccountSecurityStateStore(client)
	relay := redisstore.NewAccountSecurityRelay(client)
	tickets, err := application.NewTicketService(
		redisstore.NewTicketStore(client),
		authority,
		securityStore,
	)
	if err != nil {
		t.Fatalf("new ticket service: %v", err)
	}
	eventSource := newTestEventSource(t, client)
	hub, err := application.NewHub(
		redisstore.NewLeaseStore(client),
		redisstore.NewPresenceStore(client),
		eventSource,
		authority,
		securityStore,
		relay,
		"node-test",
		slog.Default(),
	)
	if err != nil {
		t.Fatalf("new hub: %v", err)
	}
	if err := hub.StartAccountSecurityRelay(context.Background()); err != nil {
		t.Fatalf("start account security relay: %v", err)
	}
	t.Cleanup(hub.CloseAccountSecurityRelay)
	handler, err := httpadapter.NewHandler(
		tickets,
		hub,
		mustTestResumableEventReader(t, client),
		redisstore.NewPresenceStore(client),
		httpadapter.DefaultTransportConfig(),
	)
	if err != nil {
		t.Fatalf("new http handler: %v", err)
	}
	upgrade, err := wsadapter.NewHandler(tickets, hub, slog.Default())
	if err != nil {
		t.Fatalf("new ws handler: %v", err)
	}
	mux := http.NewServeMux()
	handler.Routes(mux)
	mux.HandleFunc("GET /realtime/ws", upgrade.HandleUpgrade)
	server := httptest.NewServer(withTestPrincipal(mux))
	t.Cleanup(server.Close)
	return &gatewayHarness{
		client:    client,
		authority: authority,
		tickets:   tickets,
		hub:       hub,
		server:    server,
	}
}

func mustTestResumableEventReader(
	t *testing.T,
	client rtredis.Client,
) *redisstore.ResumableEventReader {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"realtime-gateway-resume-test",
		runtimemessaging.RedisMessageTransportFixture,
		client,
		client,
	)
	if err != nil {
		t.Fatalf("new resume message transport: %v", err)
	}
	reader, err := redisstore.NewResumableEventReader(transport)
	if err != nil {
		t.Fatalf("new resumable event reader: %v", err)
	}
	return reader
}

type testAccountSecurityAuthority struct {
	mu        sync.RWMutex
	snapshots map[string]rtauth.AccountSecuritySnapshot
	err       error
}

func newTestAccountSecurityAuthority() *testAccountSecurityAuthority {
	return &testAccountSecurityAuthority{
		snapshots: map[string]rtauth.AccountSecuritySnapshot{},
	}
}

func (authority *testAccountSecurityAuthority) ReadAccountSecurity(
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
	return rtauth.AccountSecuritySnapshot{
		AccountState: "active",
		AuthEpoch:    1,
	}, nil
}

func (authority *testAccountSecurityAuthority) set(
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

func (authority *testAccountSecurityAuthority) setError(err error) {
	authority.mu.Lock()
	defer authority.mu.Unlock()
	authority.err = err
}

func newTestEventSource(t *testing.T, client rtredis.Client) *redisstore.EventSource {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"realtime-gateway-test",
		runtimemessaging.RedisMessageTransportFixture,
		client,
		client,
	)
	if err != nil {
		t.Fatalf("new message transport: %v", err)
	}
	return redisstore.NewEventSource(transport)
}

// withTestPrincipal 模拟 auth middleware：只有完整三元组才注入可信 principal。
func withTestPrincipal(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		account := strings.TrimSpace(r.Header.Get("X-Test-Account"))
		persona := strings.TrimSpace(r.Header.Get("X-Test-Persona"))
		device := strings.TrimSpace(r.Header.Get("X-Test-Device"))
		if account != "" || persona != "" || device != "" {
			principal := rtauth.Principal{
				Claims: rtauth.Claims{
					AuthEpoch: 1,
				},
				Actor: operation.ActorContext{
					AccountID:     account,
					PersonaID:     persona,
					DeviceActorID: device,
				},
			}
			r = r.WithContext(rtauth.WithPrincipal(r.Context(), principal))
		}
		next.ServeHTTP(w, r)
	})
}

func issueTicket(
	t *testing.T,
	harness *gatewayHarness,
	account string,
	persona string,
	device string,
) string {
	t.Helper()
	request, err := http.NewRequest(
		http.MethodPost,
		harness.server.URL+"/realtime/tickets",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("X-Test-Account", account)
	request.Header.Set("X-Test-Persona", persona)
	request.Header.Set("X-Test-Device", device)
	response, err := harness.server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("issue ticket status = %d", response.StatusCode)
	}
	var body struct {
		Ticket string `json:"ticket"`
	}
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if strings.TrimSpace(body.Ticket) == "" {
		t.Fatal("issued ticket must not be empty")
	}
	return body.Ticket
}

func dialWebSocket(
	t *testing.T,
	harness *gatewayHarness,
	ticket string,
) *websocket.Conn {
	t.Helper()
	url := strings.Replace(harness.server.URL, "http://", "ws://", 1) +
		"/realtime/ws?ticket=" + ticket
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	conn, _, err := websocket.Dial(ctx, url, nil)
	if err != nil {
		t.Fatalf("dial websocket: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close(websocket.StatusNormalClosure, "test done") })
	return conn
}

func readFrame(t *testing.T, conn *websocket.Conn) map[string]any {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_, payload, err := conn.Read(ctx)
	if err != nil {
		t.Fatalf("read websocket frame: %v", err)
	}
	var frame map[string]any
	if err := json.Unmarshal(payload, &frame); err != nil {
		t.Fatalf("decode frame %s: %v", payload, err)
	}
	return frame
}

func TestTicketIsSingleUseWithStructuredNegatives(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)
	ctx := context.Background()

	issued, err := harness.tickets.Issue(ctx, application.TrustedIdentity{
		AccountID: "acct-1",
		PersonaID: "persona-1",
		DeviceID:  "device-1",
	}, 1)
	if err != nil {
		t.Fatalf("issue: %v", err)
	}
	claims, err := harness.tickets.Consume(ctx, issued.Ticket)
	if err != nil ||
		claims.AccountID != "acct-1" ||
		claims.PersonaID != "persona-1" ||
		claims.DeviceID != "device-1" {
		t.Fatalf("consume claims = %+v err = %v", claims, err)
	}
	if _, err := harness.tickets.Consume(ctx, issued.Ticket); !errors.Is(
		err,
		application.ErrTicketReplayed,
	) {
		t.Fatalf("second consume must be replayed, got %v", err)
	}
	if _, err := harness.tickets.Consume(ctx, "forged-ticket"); !errors.Is(
		err,
		application.ErrTicketInvalid,
	) {
		t.Fatalf("forged ticket must be invalid, got %v", err)
	}
}

func TestIssueTicketRequiresTrustedPrincipal(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)
	response, err := harness.server.Client().Post(
		harness.server.URL+"/realtime/tickets",
		"application/json",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("anonymous ticket status = %d, want 401", response.StatusCode)
	}
	var body struct {
		Code string `json:"code"`
	}
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.Code != "REALTIME.USER.unauthorized" {
		t.Fatalf("anonymous ticket code = %q", body.Code)
	}
}

func TestWebSocketUpgradeConsumesTicketAndAcks(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)
	ticket := issueTicket(
		t,
		harness,
		"acct-ws",
		"persona-ws",
		"device-ws",
	)

	conn := dialWebSocket(t, harness, ticket)
	ack := readFrame(t, conn)
	if ack["type"] != "auth_ack" || ack["authenticated"] != true {
		t.Fatalf("first frame must be auth_ack, got %v", ack)
	}

	// 同一 ticket 重放升级必须失败。
	url := strings.Replace(harness.server.URL, "http://", "ws://", 1) +
		"/realtime/ws?ticket=" + ticket
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if _, _, err := websocket.Dial(ctx, url, nil); err == nil {
		t.Fatal("replayed ticket upgrade must fail")
	}

	// ping/pong 心跳协议。
	writeCtx, cancelWrite := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancelWrite()
	if err := conn.Write(
		writeCtx,
		websocket.MessageText,
		[]byte(`{"type":"ping"}`),
	); err != nil {
		t.Fatalf("write ping: %v", err)
	}
	pong := readFrame(t, conn)
	if pong["type"] != "pong" {
		t.Fatalf("expected pong, got %v", pong)
	}
}

func TestEventsAreRoutedByTrustedIdentityOnly(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)
	connA := dialWebSocket(t, harness, issueTicket(
		t,
		harness,
		"acct-a",
		"persona-a",
		"device-a",
	))
	connB := dialWebSocket(t, harness, issueTicket(
		t,
		harness,
		"acct-b",
		"persona-b",
		"device-b",
	))
	if frame := readFrame(t, connA); frame["type"] != "auth_ack" {
		t.Fatalf("connA auth_ack missing: %v", frame)
	}
	if frame := readFrame(t, connB); frame["type"] != "auth_ack" {
		t.Fatalf("connB auth_ack missing: %v", frame)
	}

	ctx := context.Background()
	publish := func(channel string, eventType string) {
		payload, _ := json.Marshal(map[string]any{"type": eventType})
		if err := harness.client.Publish(ctx, channel, string(payload)); err != nil {
			t.Fatalf("publish %s: %v", channel, err)
		}
	}
	publish("rt:rtc:user:persona-a", "call.forbidden_alias")
	publish("rt:user:acct-a", "chat.test_event")
	publish("rt:rtc:persona:persona-a", "call.ringing")

	first := readFrame(t, connA)
	second := readFrame(t, connA)
	types := map[string]bool{
		first["type"].(string):  true,
		second["type"].(string): true,
	}
	if !types["chat.test_event"] || !types["call.ringing"] {
		t.Fatalf("connA must receive its chat and rtc events, got %v", types)
	}

	// 用户 B 不得收到用户 A 的事件：先给 B 发一条自己的事件，再断言下一帧
	// 只能是它自己的（若 A 的事件泄漏，会先于该帧到达）。
	publish("rt:user:acct-b", "chat.own_event")
	frame := readFrame(t, connB)
	if frame["type"] != "chat.own_event" {
		t.Fatalf("connB must only receive its own events, got %v", frame)
	}
}

func TestRTCPersonaChannelFiltersDeviceTargetedFrames(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)
	connA := dialWebSocket(t, harness, issueTicket(
		t,
		harness,
		"acct-shared",
		"persona-shared",
		"device-a",
	))
	connB := dialWebSocket(t, harness, issueTicket(
		t,
		harness,
		"acct-shared",
		"persona-shared",
		"device-b",
	))
	if frame := readFrame(t, connA); frame["type"] != "auth_ack" {
		t.Fatalf("connA auth_ack missing: %v", frame)
	}
	if frame := readFrame(t, connB); frame["type"] != "auth_ack" {
		t.Fatalf("connB auth_ack missing: %v", frame)
	}

	ctx := context.Background()
	publish := func(payload map[string]any) {
		encoded, _ := json.Marshal(payload)
		if err := harness.client.Publish(
			ctx,
			"rt:rtc:persona:persona-shared",
			string(encoded),
		); err != nil {
			t.Fatalf("publish persona RTC frame: %v", err)
		}
	}
	publish(map[string]any{
		"type":            "call.ringing",
		"targetPersonaId": "persona-shared",
		"deviceId":        "device-a",
		"deliveryKey":     "sha256:device-a",
	})
	publish(map[string]any{
		"type":    "call.presentation_cancelled",
		"callId":  "call-shared",
		"eventId": "event-cancel",
	})

	if frame := readFrame(t, connA); frame["deviceId"] != "device-a" {
		t.Fatalf("device A must receive its targeted frame, got %v", frame)
	}
	if frame := readFrame(t, connA); frame["type"] != "call.presentation_cancelled" {
		t.Fatalf("device A cancellation missing: %v", frame)
	}
	if frame := readFrame(t, connB); frame["type"] != "call.presentation_cancelled" {
		t.Fatalf("device B received another device's targeted frame: %v", frame)
	}
}

func TestLeaseFencingTokensAreMonotonic(t *testing.T) {
	t.Parallel()
	client := rtredis.NewMemoryClient()
	leases := redisstore.NewLeaseStore(client)
	ctx := context.Background()

	identity := application.TrustedIdentity{
		AccountID: "acct-lease",
		PersonaID: "persona-lease",
		DeviceID:  "device-lease",
	}
	first, err := leases.Acquire(ctx, identity, "conn-1", time.Minute)
	if err != nil {
		t.Fatalf("acquire first: %v", err)
	}
	second, err := leases.Acquire(ctx, identity, "conn-2", time.Minute)
	if err != nil {
		t.Fatalf("acquire second: %v", err)
	}
	if second <= first {
		t.Fatalf("fencing token must be monotonic: first=%d second=%d", first, second)
	}
	current, err := leases.CurrentFence(ctx, identity)
	if err != nil || current != second {
		t.Fatalf("current fence = %d err = %v, want %d", current, err, second)
	}
	if err := leases.Release(ctx, identity, "conn-1"); err != nil {
		t.Fatalf("release: %v", err)
	}
}

func TestLongPollReturnsCursorEnvelopeForEmptyAndEphemeralDelivery(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)

	// 无事件：短 hold 仍返回可持久化 cursor envelope，避免相邻 poll 窗口丢事件。
	request, _ := http.NewRequest(
		http.MethodGet,
		harness.server.URL+"/realtime/poll?timeout=1",
		nil,
	)
	request.Header.Set("X-Test-Account", "acct-poll")
	request.Header.Set("X-Test-Persona", "persona-poll")
	request.Header.Set("X-Test-Device", "device-poll")
	response, err := harness.server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("empty poll status = %d, want 200", response.StatusCode)
	}
	var emptyBody struct {
		Events           []map[string]any `json:"events"`
		NextCursor       string           `json:"nextCursor"`
		TransportResumed bool             `json:"transportResumed"`
	}
	if err := json.NewDecoder(response.Body).Decode(&emptyBody); err != nil {
		t.Fatal(err)
	}
	if len(emptyBody.Events) != 0 || emptyBody.NextCursor != "0-0" || emptyBody.TransportResumed {
		t.Fatalf("empty poll body = %#v", emptyBody)
	}

	// 有事件：hold 期间发布，返回 200 + events。
	go func() {
		time.Sleep(300 * time.Millisecond)
		payload, _ := json.Marshal(map[string]any{"type": "chat.poll_event"})
		_ = harness.client.Publish(
			context.Background(),
			"rt:user:acct-poll",
			string(payload),
		)
	}()
	request2, _ := http.NewRequest(
		http.MethodGet,
		harness.server.URL+"/realtime/poll?timeout=5",
		nil,
	)
	request2.Header.Set("X-Test-Account", "acct-poll")
	request2.Header.Set("X-Test-Persona", "persona-poll")
	request2.Header.Set("X-Test-Device", "device-poll")
	response2, err := harness.server.Client().Do(request2)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response2.Body.Close() }()
	if response2.StatusCode != http.StatusOK {
		t.Fatalf("poll with event status = %d, want 200", response2.StatusCode)
	}
	var body struct {
		Events     []map[string]any `json:"events"`
		NextCursor string           `json:"nextCursor"`
	}
	if err := json.NewDecoder(response2.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if len(body.Events) != 1 || body.Events[0]["type"] != "chat.poll_event" {
		t.Fatalf("poll events = %v", body.Events)
	}
	if body.NextCursor != "0-0" {
		t.Fatalf("ephemeral delivery must not advance durable cursor: %q", body.NextCursor)
	}

	// 匿名 poll 返回 401。
	anonymous, _ := http.NewRequest(
		http.MethodGet,
		harness.server.URL+"/realtime/poll?timeout=1",
		nil,
	)
	anonymousResponse, err := harness.server.Client().Do(anonymous)
	if err != nil {
		t.Fatal(err)
	}
	_ = anonymousResponse.Body.Close()
	if anonymousResponse.StatusCode != http.StatusUnauthorized {
		t.Fatalf("anonymous poll status = %d, want 401", anonymousResponse.StatusCode)
	}
}

func TestLongPollResumesDurableEventsStrictlyAfterCursor(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)
	ctx := context.Background()
	stream := runtimemessaging.RealtimeChatResumeStream("acct-resume")
	firstPayload, _ := json.Marshal(map[string]any{
		"eventId": "event-1", "type": "MessageSent", "conversationId": "conv-1",
	})
	firstCursor, err := harness.client.XAdd(ctx, stream, map[string]string{
		"payload": string(firstPayload),
	})
	if err != nil {
		t.Fatal(err)
	}
	secondPayload, _ := json.Marshal(map[string]any{
		"eventId": "event-2", "type": "MessageSent", "conversationId": "conv-1",
	})
	secondCursor, err := harness.client.XAdd(ctx, stream, map[string]string{
		"payload": string(secondPayload),
	})
	if err != nil {
		t.Fatal(err)
	}

	request, _ := http.NewRequest(
		http.MethodGet,
		harness.server.URL+"/realtime/poll?timeout=1&cursor="+firstCursor,
		nil,
	)
	request.Header.Set("X-Test-Account", "acct-resume")
	request.Header.Set("X-Test-Persona", "persona-resume")
	request.Header.Set("X-Test-Device", "device-resume")
	response, err := harness.server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	var body struct {
		Events           []map[string]any `json:"events"`
		NextCursor       string           `json:"nextCursor"`
		TransportResumed bool             `json:"transportResumed"`
	}
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK || len(body.Events) != 1 {
		t.Fatalf("resume status=%d body=%#v", response.StatusCode, body)
	}
	if body.Events[0]["eventId"] != "event-2" || body.NextCursor != secondCursor || !body.TransportResumed {
		t.Fatalf("resume body=%#v", body)
	}

	invalid, _ := http.NewRequest(
		http.MethodGet,
		harness.server.URL+"/realtime/poll?cursor=%24",
		nil,
	)
	invalid.Header.Set("X-Test-Account", "acct-resume")
	invalid.Header.Set("X-Test-Persona", "persona-resume")
	invalid.Header.Set("X-Test-Device", "device-resume")
	invalidResponse, err := harness.server.Client().Do(invalid)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = invalidResponse.Body.Close() }()
	if invalidResponse.StatusCode != http.StatusBadRequest {
		t.Fatalf("invalid cursor status=%d, want 400", invalidResponse.StatusCode)
	}
}

func TestPresenceViewRemovesStaleDeviceFieldsIndependently(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	store := redisstore.NewPresenceStore(client)
	now := time.Date(2026, 7, 20, 15, 0, 0, 0, time.UTC)
	key := "presence:persona:persona-presence"
	active := map[string]any{
		"accountId":       "account-presence",
		"personaId":       "persona-presence",
		"deviceId":        "device-active",
		"connId":          "conn-active",
		"nodeId":          "node-a",
		"transport":       "websocket",
		"lastHeartbeatAt": now.Add(-10 * time.Second).Format(time.RFC3339Nano),
	}
	stale := map[string]any{
		"accountId":       "account-presence",
		"personaId":       "persona-presence",
		"deviceId":        "device-stale",
		"connId":          "conn-stale",
		"nodeId":          "node-b",
		"transport":       "websocket",
		"lastHeartbeatAt": now.Add(-61 * time.Second).Format(time.RFC3339Nano),
	}
	for deviceID, entry := range map[string]map[string]any{
		"device-active": active,
		"device-stale":  stale,
	} {
		encoded, _ := json.Marshal(entry)
		if err := client.HSet(ctx, key, deviceID, string(encoded)); err != nil {
			t.Fatal(err)
		}
	}
	view, err := store.ReadPresence(ctx, "persona-presence", now)
	if err != nil {
		t.Fatalf("read presence: %v", err)
	}
	if len(view.Devices) != 1 ||
		view.Devices[0].DeviceID != "device-active" ||
		view.Devices[0].AccountID != "account-presence" {
		t.Fatalf("presence view=%+v", view)
	}
	if _, err := client.HGet(ctx, key, "device-stale"); !errors.Is(
		err,
		rtredis.ErrKeyNotFound,
	) {
		t.Fatalf("stale field must be removed, err=%v", err)
	}
	if _, err := client.HGet(ctx, key, "device-active"); err != nil {
		t.Fatalf("active field must remain despite stale sibling: %v", err)
	}
}
