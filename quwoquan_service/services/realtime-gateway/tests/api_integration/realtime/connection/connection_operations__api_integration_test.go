// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// readiness_case: issue-connection-ticket-api
// readiness_case: websocket-upgrade-api
// readiness_case: long-poll-api
// readiness_case: get-realtime-config-api
// readiness_case: health-check-api
// readiness_case: readiness-check-api
// readiness_case: metrics-api
// readiness_case: recover-account-closure-dead-letter-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/coder/websocket"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtmetrics "quwoquan_service/runtime/metrics"
	"quwoquan_service/runtime/operation"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/http"
	streamadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/stream"
	wsadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/ws"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/infrastructure/redisstore"
)

func TestConnectionOperationsUseProductionAdaptersAndRealRedis(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	realRedis, err := testinfra.StartRealRedis(ctx)
	if err != nil {
		t.Fatalf("connection api_integration requires real Redis: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cleanupCancel()
		_ = realRedis.Close(cleanupCtx)
	})
	if err := realRedis.FlushDBs(ctx, 0); err != nil {
		t.Fatalf("flush Redis: %v", err)
	}
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"realtime": {
				Mode: "standalone", Addr: realRedis.Addr,
				Password: realRedis.Password, DB: 0, TLS: realRedis.TLS,
			},
		},
		DefaultScene: "realtime",
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = router.Close() })
	client := router.Scene("realtime")
	transport, err := runtimemessaging.NewRedisMessageTransport(client, client)
	if err != nil {
		t.Fatal(err)
	}
	authority := newIntegrationAccountSecurityAuthority()
	presenceProjection := newIntegrationPresenceProjection(t, client)
	stateStore := redisstore.NewAccountSecurityStateStore(client, presenceProjection)
	relay := redisstore.NewAccountSecurityRelay(client)
	tickets, err := application.NewTicketService(
		redisstore.NewTicketStore(client),
		authority,
		stateStore,
	)
	if err != nil {
		t.Fatal(err)
	}
	hub, err := application.NewHub(
		redisstore.NewLeaseStore(client),
		presenceProjection,
		redisstore.NewEventSource(transport),
		authority,
		stateStore,
		relay,
		"connection-operations-api",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := hub.StartAccountSecurityRelay(ctx); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(hub.CloseAccountSecurityRelay)
	resumeReader, err := redisstore.NewResumableEventReader(transport)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := httpadapter.NewHandler(
		tickets,
		hub,
		resumeReader,
		httpadapter.DefaultTransportConfig(),
	)
	if err != nil {
		t.Fatal(err)
	}
	operationDescriptors := connectionOperationDescriptorsForTest()
	upgrade, err := wsadapter.NewHandler(
		tickets,
		hub,
		nil,
		operationDescriptors,
	)
	if err != nil {
		t.Fatal(err)
	}
	failures := redisstore.NewAccountSecurityEventFailureStore(client)
	consumer, err := streamadapter.NewUserAccountSecurityConsumer(
		transport,
		stateStore,
		relay,
		hub,
		failures,
		"connection-operations-recovery-api",
		nil,
		streamadapter.DefaultUserAccountSecurityConsumerConfig(),
	)
	if err != nil {
		t.Fatal(err)
	}
	guarded := http.NewServeMux()
	handler.Routes(guarded)
	guardedWithRecovery, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		guarded,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/realtime/account-closure/dead-letters:recover",
			Module:   rterr.ModuleRealtime,
			Releaser: consumer,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	root := http.NewServeMux()
	checker := rthealth.NewChecker()
	checker.Register("realtime_redis", client.Ping)
	if err := httpadapter.RegisterRuntimeProbeRoutes(root, checker, rtmetrics.Handler()); err != nil {
		t.Fatal(err)
	}
	root.HandleFunc("GET /realtime/ws", upgrade.HandleUpgrade)
	root.Handle(
		"/",
		rtauth.EnforceRuntimeOperationContract(operationDescriptors)(guardedWithRecovery),
	)
	server := httptest.NewServer(withConnectionOperationPrincipal(root))
	t.Cleanup(server.Close)

	const (
		accountID = "account-connection-operations"
		personaID = "persona-connection-operations"
		deviceID  = "device-connection-operations"
	)
	ticket := issueConnectionOperationTicket(
		t,
		server,
		accountID,
		personaID,
		deviceID,
	)
	webSocketURL := strings.Replace(server.URL, "http://", "ws://", 1) +
		"/realtime/ws?ticket=" + ticket
	webSocketContext, webSocketCancel := context.WithTimeout(ctx, 5*time.Second)
	connection, _, err := websocket.Dial(webSocketContext, webSocketURL, nil)
	webSocketCancel()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = connection.Close(websocket.StatusNormalClosure, "test done") })
	readContext, readCancel := context.WithTimeout(ctx, 5*time.Second)
	_, payload, err := connection.Read(readContext)
	readCancel()
	if err != nil || !strings.Contains(string(payload), `"type":"auth_ack"`) {
		t.Fatalf("websocket auth ack payload=%s err=%v", payload, err)
	}

	stream := runtimemessaging.RealtimeChatResumeStream(accountID)
	firstCursor, err := client.XAdd(ctx, stream, map[string]string{
		"payload": `{"eventId":"event-1","type":"MessageSent"}`,
	})
	if err != nil {
		t.Fatal(err)
	}
	secondCursor, err := client.XAdd(ctx, stream, map[string]string{
		"payload": `{"eventId":"event-2","type":"MessageSent"}`,
	})
	if err != nil {
		t.Fatal(err)
	}
	pollRequest, _ := http.NewRequest(
		http.MethodGet,
		server.URL+"/realtime/poll?timeout=1&cursor="+firstCursor,
		nil,
	)
	setConnectionOperationIdentity(pollRequest, accountID, personaID, deviceID)
	pollResponse, err := server.Client().Do(pollRequest)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = pollResponse.Body.Close() }()
	var pollBody struct {
		Events           []map[string]any `json:"events"`
		NextCursor       string           `json:"nextCursor"`
		TransportResumed bool             `json:"transportResumed"`
	}
	if err := json.NewDecoder(pollResponse.Body).Decode(&pollBody); err != nil {
		t.Fatal(err)
	}
	if pollResponse.StatusCode != http.StatusOK || len(pollBody.Events) != 1 ||
		pollBody.Events[0]["eventId"] != "event-2" ||
		pollBody.NextCursor != secondCursor || !pollBody.TransportResumed {
		t.Fatalf("long poll status=%d body=%+v", pollResponse.StatusCode, pollBody)
	}

	configResponse, err := server.Client().Get(server.URL + "/config/realtime")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = configResponse.Body.Close() }()
	var config httpadapter.RealtimeTransportConfig
	if err := json.NewDecoder(configResponse.Body).Decode(&config); err != nil {
		t.Fatal(err)
	}
	if configResponse.StatusCode != http.StatusOK || config != httpadapter.DefaultTransportConfig() {
		t.Fatalf("config status=%d body=%+v", configResponse.StatusCode, config)
	}

	for path, contains := range map[string]string{
		"/healthz": `"status":"ok"`,
		"/readyz":  `"status":"ready"`,
		"/metrics": "go_gc_duration_seconds",
	} {
		response, err := server.Client().Get(server.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		var body bytes.Buffer
		_, copyErr := body.ReadFrom(response.Body)
		_ = response.Body.Close()
		if copyErr != nil || response.StatusCode != http.StatusOK ||
			!strings.Contains(body.String(), contains) {
			t.Fatalf("GET %s status=%d body=%s err=%v", path, response.StatusCode, body.String(), copyErr)
		}
	}

	const sourceStreamID = "1710000000000-88"
	if _, err := failures.RecordAccountSecurityFailure(
		ctx,
		"events.user.account",
		sourceStreamID,
		"event-recovery-api",
		"dependency",
		errors.New("controlled dependency failure"),
	); err != nil {
		t.Fatal(err)
	}
	if err := failures.MarkAccountSecurityDeadLettered(
		ctx,
		"events.user.account",
		sourceStreamID,
	); err != nil {
		t.Fatal(err)
	}
	recoveryRequest, _ := http.NewRequest(
		http.MethodPost,
		server.URL+"/internal/realtime/account-closure/dead-letters:recover",
		bytes.NewBufferString(`{"sourceStreamId":"`+sourceStreamID+`"}`),
	)
	recoveryRequest.Header.Set("Idempotency-Key", "recover-realtime-api-88")
	recoveryRequest.Header.Set("X-Test-Operator", "true")
	recoveryResponse, err := server.Client().Do(recoveryRequest)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = recoveryResponse.Body.Close() }()
	deadLettered, stateErr := failures.IsAccountSecurityDeadLettered(
		ctx,
		"events.user.account",
		sourceStreamID,
	)
	if recoveryResponse.StatusCode != http.StatusAccepted || stateErr != nil || deadLettered {
		t.Fatalf(
			"recovery status=%d deadLettered=%t stateErr=%v",
			recoveryResponse.StatusCode,
			deadLettered,
			stateErr,
		)
	}
}

func connectionOperationDescriptorsForTest() []rtauth.OperationSecurityDescriptor {
	descriptors := operationsecurity.ForDomain("realtime")
	for index := range descriptors {
		descriptor := &descriptors[index]
		if descriptor.CanonicalOperationID != "realtime.connection.WebSocketUpgrade" {
			continue
		}
		budget := rtauth.OperationStreamBudget{
			HandshakeMilliseconds:   5000,
			IdleMilliseconds:        90000,
			MaxDurationMilliseconds: 1800000,
		}
		descriptor.StreamBudget = &budget
		descriptor.TimeoutMilliseconds = budget.MaxDurationMilliseconds
	}
	return descriptors
}

func withConnectionOperationPrincipal(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Header.Get("X-Test-Operator") == "true" {
			request = request.WithContext(rtauth.WithPrincipal(
				request.Context(),
				rtauth.Principal{
					Claims: rtauth.Claims{
						Scope:       "ops.account_closure.write",
						Permissions: []string{"realtime.account_closure.recover"},
						Roles:       []string{"operator"},
					},
				},
			))
			next.ServeHTTP(writer, request)
			return
		}
		accountID := strings.TrimSpace(request.Header.Get("X-Test-Account"))
		personaID := strings.TrimSpace(request.Header.Get("X-Test-Persona"))
		deviceID := strings.TrimSpace(request.Header.Get("X-Test-Device"))
		if accountID != "" || personaID != "" || deviceID != "" {
			request = request.WithContext(rtauth.WithPrincipal(
				request.Context(),
				rtauth.Principal{
					Claims: rtauth.Claims{AuthEpoch: 1},
					Actor: operation.ActorContext{
						AccountID: accountID, PersonaID: personaID, DeviceActorID: deviceID,
					},
				},
			))
		}
		next.ServeHTTP(writer, request)
	})
}

func issueConnectionOperationTicket(
	t *testing.T,
	server *httptest.Server,
	accountID string,
	personaID string,
	deviceID string,
) string {
	t.Helper()
	request, _ := http.NewRequest(http.MethodPost, server.URL+"/realtime/tickets", nil)
	setConnectionOperationIdentity(request, accountID, personaID, deviceID)
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	var body struct {
		Ticket string `json:"ticket"`
	}
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK || strings.TrimSpace(body.Ticket) == "" {
		t.Fatalf("ticket status=%d body=%+v", response.StatusCode, body)
	}
	return body.Ticket
}

func setConnectionOperationIdentity(
	request *http.Request,
	accountID string,
	personaID string,
	deviceID string,
) {
	request.Header.Set("X-Test-Account", accountID)
	request.Header.Set("X-Test-Persona", personaID)
	request.Header.Set("X-Test-Device", deviceID)
}
