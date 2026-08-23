// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-002
//
// Connection fail-closed 负例断言：application guard 保证非法输入不触达
// Redis/安全依赖；真实 gateway harness（内存 Redis + httptest server + 真实
// handler 组合）以字面 wire code 锁定端云错误契约。
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
	wsadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/ws"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
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

type errSemCountingTicketStore struct {
	issueCalls   int
	consumeCalls int
	revokeCalls  int
}

func (store *errSemCountingTicketStore) Issue(
	context.Context,
	application.TicketClaims,
	time.Duration,
) (string, error) {
	store.issueCalls++
	return "unexpected-ticket", nil
}

func (store *errSemCountingTicketStore) Consume(
	context.Context,
	string,
) (application.TicketClaims, error) {
	store.consumeCalls++
	return application.TicketClaims{}, nil
}

func (store *errSemCountingTicketStore) Revoke(
	context.Context,
	string,
	string,
) error {
	store.revokeCalls++
	return nil
}

type errSemCountingAccountSecurityAuthority struct {
	readCalls int
}

func (authority *errSemCountingAccountSecurityAuthority) ReadAccountSecurity(
	context.Context,
	string,
) (rtauth.AccountSecuritySnapshot, error) {
	authority.readCalls++
	return rtauth.AccountSecuritySnapshot{
		AccountState: "active",
		AuthEpoch:    1,
	}, nil
}

type errSemCountingAccountSecurityGate struct {
	application.AccountSecurityGate
	admitCalls int
}

func (gate *errSemCountingAccountSecurityGate) Admit(
	context.Context,
	application.TrustedIdentity,
	int64,
) error {
	gate.admitCalls++
	return nil
}

func TestTicketServiceRequiresEveryCollaborator(t *testing.T) {
	store := &errSemCountingTicketStore{}
	authority := &errSemCountingAccountSecurityAuthority{}
	security := &errSemCountingAccountSecurityGate{}

	for _, testCase := range []struct {
		name      string
		store     application.TicketStore
		authority rtauth.AccountSecurityAuthority
		security  application.AccountSecurityGate
	}{
		{name: "store", authority: authority, security: security},
		{name: "authority", store: store, security: security},
		{name: "security gate", store: store, authority: authority},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			service, err := application.NewTicketService(
				testCase.store,
				testCase.authority,
				testCase.security,
			)
			if service != nil {
				t.Fatalf("service=%#v want nil", service)
			}
			const want = "realtime ticket service requires store, account security authority and gate"
			if err == nil || err.Error() != want {
				t.Fatalf("error=%v want=%q", err, want)
			}
		})
	}
}

func TestTicketServiceRejectsInvalidInputBeforeDependencies(t *testing.T) {
	store := &errSemCountingTicketStore{}
	authority := &errSemCountingAccountSecurityAuthority{}
	security := &errSemCountingAccountSecurityGate{}
	service, err := application.NewTicketService(store, authority, security)
	if err != nil {
		t.Fatalf("new ticket service: %v", err)
	}
	ctx := context.Background()

	issued, err := service.Issue(ctx, application.TrustedIdentity{
		AccountID: " ",
		PersonaID: "persona-errsem",
		DeviceID:  "device-errsem",
	}, 1)
	if issued != (application.IssuedTicket{}) {
		t.Fatalf("issued=%#v want zero value", issued)
	}
	const wantIdentityError = "realtime ticket requires trusted account, persona and device identities"
	if err == nil || err.Error() != wantIdentityError {
		t.Fatalf("identity error=%v want=%q", err, wantIdentityError)
	}

	issued, err = service.Issue(ctx, application.TrustedIdentity{
		AccountID: "acct-errsem",
		PersonaID: "persona-errsem",
		DeviceID:  "device-errsem",
	}, 0)
	if issued != (application.IssuedTicket{}) {
		t.Fatalf("issued=%#v want zero value", issued)
	}
	if !errors.Is(err, application.ErrAccountSecurityDenied) {
		t.Fatalf("auth epoch error=%v want=%v", err, application.ErrAccountSecurityDenied)
	}

	claims, err := service.Consume(ctx, " ")
	if claims != (application.TicketClaims{}) {
		t.Fatalf("claims=%#v want zero value", claims)
	}
	if !errors.Is(err, application.ErrTicketInvalid) {
		t.Fatalf("ticket error=%v want=%v", err, application.ErrTicketInvalid)
	}

	if store.issueCalls != 0 || store.consumeCalls != 0 || store.revokeCalls != 0 {
		t.Fatalf(
			"ticket store calls issue=%d consume=%d revoke=%d want all zero",
			store.issueCalls,
			store.consumeCalls,
			store.revokeCalls,
		)
	}
	if authority.readCalls != 0 {
		t.Fatalf("account security authority reads=%d want=0", authority.readCalls)
	}
	if security.admitCalls != 0 {
		t.Fatalf("account security gate admits=%d want=0", security.admitCalls)
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

type errSemValidationTicketStore struct {
	issueCalls   int
	consumeCalls int
	revokeCalls  int
}

func (store *errSemValidationTicketStore) Issue(
	context.Context,
	application.TicketClaims,
	time.Duration,
) (string, error) {
	store.issueCalls++
	return "unexpected-ticket", nil
}

func (store *errSemValidationTicketStore) Consume(
	context.Context,
	string,
) (application.TicketClaims, error) {
	store.consumeCalls++
	return application.TicketClaims{}, nil
}

func (store *errSemValidationTicketStore) Revoke(
	context.Context,
	string,
	string,
) error {
	store.revokeCalls++
	return nil
}

type errSemValidationAuthority struct {
	calls int
}

func (authority *errSemValidationAuthority) ReadAccountSecurity(
	context.Context,
	string,
) (rtauth.AccountSecuritySnapshot, error) {
	authority.calls++
	return rtauth.AccountSecuritySnapshot{
		AccountState: "active",
		AuthEpoch:    1,
	}, nil
}

type errSemValidationGate struct {
	admitCalls int
}

func (gate *errSemValidationGate) Admit(
	context.Context,
	application.TrustedIdentity,
	int64,
) error {
	gate.admitCalls++
	return nil
}

func (*errSemValidationGate) RegisterSession(
	context.Context,
	application.TrustedIdentity,
	string,
) error {
	return nil
}

func (*errSemValidationGate) UnregisterSession(
	context.Context,
	application.TrustedIdentity,
	string,
) error {
	return nil
}

func (*errSemValidationGate) ApplyAccountSecurityEvent(
	context.Context,
	application.AccountSecurityEvent,
) (application.AccountSecurityApplyResult, error) {
	return application.AccountSecurityApplyResult{}, nil
}

func TestTicketServiceRequiresEveryCollaborator(t *testing.T) {
	t.Parallel()
	store := &errSemValidationTicketStore{}
	authority := &errSemValidationAuthority{}
	gate := &errSemValidationGate{}

	for _, testCase := range []struct {
		name      string
		store     application.TicketStore
		authority rtauth.AccountSecurityAuthority
		gate      application.AccountSecurityGate
	}{
		{name: "store", authority: authority, gate: gate},
		{name: "authority", store: store, gate: gate},
		{name: "gate", store: store, authority: authority},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			service, err := application.NewTicketService(
				testCase.store,
				testCase.authority,
				testCase.gate,
			)
			if service != nil {
				t.Fatal("invalid ticket service must not be returned")
			}
			if err == nil || err.Error() !=
				"realtime ticket service requires store, account security authority and gate" {
				t.Fatalf("unexpected construction error: %v", err)
			}
		})
	}
}

func TestTicketServiceRejectsInvalidInputBeforeDependencies(t *testing.T) {
	t.Parallel()
	store := &errSemValidationTicketStore{}
	authority := &errSemValidationAuthority{}
	gate := &errSemValidationGate{}
	service, err := application.NewTicketService(store, authority, gate)
	if err != nil {
		t.Fatalf("new ticket service: %v", err)
	}

	_, err = service.Issue(context.Background(), application.TrustedIdentity{
		AccountID: "  ",
		PersonaID: " persona-validation ",
		DeviceID:  " device-validation ",
	}, 1)
	if err == nil || err.Error() !=
		"realtime ticket requires trusted account, persona and device identities" {
		t.Fatalf("unexpected incomplete identity error: %v", err)
	}

	_, err = service.Issue(context.Background(), application.TrustedIdentity{
		AccountID: "account-validation",
		PersonaID: "persona-validation",
		DeviceID:  "device-validation",
	}, 0)
	if !errors.Is(err, application.ErrAccountSecurityDenied) {
		t.Fatalf("non-positive auth epoch error = %v", err)
	}

	if _, err := service.Consume(context.Background(), "  "); !errors.Is(
		err,
		application.ErrTicketInvalid,
	) {
		t.Fatalf("blank ticket error = %v", err)
	}

	if store.issueCalls != 0 || store.consumeCalls != 0 || store.revokeCalls != 0 {
		t.Fatalf(
			"invalid input reached ticket store: issue=%d consume=%d revoke=%d",
			store.issueCalls,
			store.consumeCalls,
			store.revokeCalls,
		)
	}
	if authority.calls != 0 || gate.admitCalls != 0 {
		t.Fatalf(
			"invalid input reached security dependencies: authority=%d gate=%d",
			authority.calls,
			gate.admitCalls,
		)
	}
}
