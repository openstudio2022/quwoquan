// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// Connection 声明错误码的负例断言：经真实 gateway harness（内存 redis +
// httptest server + 真实 handler 组合）驱动身份不完整、非法游标、票据无效/
// 重放与票据签发存储失败路径，以字面 wire code 锁定端云契约。
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	wsadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/ws"
)

func requireConnectionErrorCode(
	t *testing.T,
	body io.Reader,
	gotStatus, wantStatus int,
	wantCode string,
) {
	t.Helper()
	raw, err := io.ReadAll(body)
	if err != nil {
		t.Fatalf("read error body: %v", err)
	}
	if gotStatus != wantStatus {
		t.Fatalf("status=%d want=%d body=%s", gotStatus, wantStatus, string(raw))
	}
	var envelope struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		t.Fatalf("decode error envelope: %v body=%s", err, string(raw))
	}
	if envelope.Code != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, envelope.Code)
	}
}

func TestIssueTicketWithIncompleteIdentityEmitsRealtimeUnauthorized(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)

	request, err := http.NewRequest(
		http.MethodPost, harness.server.URL+"/realtime/tickets", nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("X-Test-Account", "acct-errsem")
	request.Header.Set("X-Test-Persona", "persona-errsem")
	response, err := harness.server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	requireConnectionErrorCode(
		t, response.Body, response.StatusCode, http.StatusUnauthorized,
		"REALTIME.USER.unauthorized",
	)
}

func TestLongPollWithMalformedCursorEmitsInvalidArgument(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)

	request, err := http.NewRequest(
		http.MethodGet, harness.server.URL+"/realtime/poll?cursor=garbage", nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("X-Test-Account", "acct-errsem")
	request.Header.Set("X-Test-Persona", "persona-errsem")
	request.Header.Set("X-Test-Device", "device-errsem")
	response, err := harness.server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	requireConnectionErrorCode(
		t, response.Body, response.StatusCode, http.StatusBadRequest,
		"REALTIME.USER.invalid_argument",
	)
}

func TestUpgradeWithoutWebSocketHeaderEmitsTicketInvalid(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)

	response, err := harness.server.Client().Get(harness.server.URL + "/realtime/ws")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	requireConnectionErrorCode(
		t, response.Body, response.StatusCode, http.StatusUnauthorized,
		"REALTIME.USER.ticket_invalid",
	)
}

func TestUpgradeWithConsumedTicketEmitsTicketReplayed(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)
	ctx := context.Background()

	issued, err := harness.tickets.Issue(ctx, application.TrustedIdentity{
		AccountID: "acct-errsem",
		PersonaID: "persona-errsem",
		DeviceID:  "device-errsem",
	}, 1)
	if err != nil {
		t.Fatalf("issue: %v", err)
	}
	if _, err := harness.tickets.Consume(ctx, issued.Ticket); err != nil {
		t.Fatalf("first consume: %v", err)
	}

	// Go HTTP client 会剥离 hop-by-hop 的 Upgrade 头，因此直接驱动
	// HandleUpgrade（与 harness 相同的 handler 组合方式）。
	upgrade, err := wsadapter.NewHandler(
		harness.tickets,
		harness.hub,
		slog.Default(),
		realtimeOperationDescriptorsForTest(rtauth.OperationStreamBudget{
			HandshakeMilliseconds:   5000,
			IdleMilliseconds:        90000,
			MaxDurationMilliseconds: 1800000,
		}),
	)
	if err != nil {
		t.Fatalf("new ws handler: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodGet, "/realtime/ws?ticket="+issued.Ticket, nil,
	)
	request.Header.Set("Upgrade", "websocket")
	request.Header.Set("Connection", "Upgrade")
	response := httptest.NewRecorder()
	upgrade.HandleUpgrade(response, request)
	requireConnectionErrorCode(
		t, response.Body, response.Code, http.StatusUnauthorized,
		"REALTIME.USER.ticket_replayed",
	)
}

type errSemFailingTicketStore struct {
	application.TicketStore
}

func (s errSemFailingTicketStore) Issue(
	context.Context, application.TicketClaims, time.Duration,
) (string, error) {
	return "", errors.New("redis SET failed")
}

func TestIssueTicketStoreFailureEmitsRealtimeInternalError(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarnessWithConfig(t, gatewayHarnessConfig{
		streamBudget: rtauth.OperationStreamBudget{
			HandshakeMilliseconds:   5000,
			IdleMilliseconds:        90000,
			MaxDurationMilliseconds: 1800000,
		},
		wrapTicketStore: func(store application.TicketStore) application.TicketStore {
			return errSemFailingTicketStore{TicketStore: store}
		},
	})

	request, err := http.NewRequest(
		http.MethodPost, harness.server.URL+"/realtime/tickets", nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("X-Test-Account", "acct-errsem")
	request.Header.Set("X-Test-Persona", "persona-errsem")
	request.Header.Set("X-Test-Device", "device-errsem")
	response, err := harness.server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = response.Body.Close() }()
	requireConnectionErrorCode(
		t, response.Body, response.StatusCode, http.StatusInternalServerError,
		"REALTIME.SYSTEM.internal_error",
	)
}
