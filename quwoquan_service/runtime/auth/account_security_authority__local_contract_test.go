package auth

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

type staticAccountSecurityAuthority struct {
	mu       sync.Mutex
	snapshot AccountSecuritySnapshot
	err      error
	calls    int
	account  string
}

func (authority *staticAccountSecurityAuthority) ReadAccountSecurity(
	_ context.Context,
	accountID string,
) (AccountSecuritySnapshot, error) {
	authority.mu.Lock()
	defer authority.mu.Unlock()
	authority.calls++
	authority.account = accountID
	return authority.snapshot, authority.err
}

type staticServiceCredentials struct {
	header string
	err    error
}

func (credentials staticServiceCredentials) AuthorizationHeader(
	context.Context,
) (string, error) {
	return credentials.header, credentials.err
}

func TestHTTPAccountSecurityAuthorityUsesStrictScopedRequest(t *testing.T) {
	var (
		receivedMethod string
		receivedPath   string
		receivedAuth   string
		receivedCache  string
	)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedMethod = r.Method
		receivedPath = r.URL.EscapedPath()
		receivedAuth = r.Header.Get("Authorization")
		receivedCache = r.Header.Get("Cache-Control")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"accountState":"active","authEpoch":7}`))
	}))
	defer server.Close()

	authority, err := NewHTTPAccountSecurityAuthority(
		HTTPAccountSecurityAuthorityConfig{
			BaseURL:     server.URL,
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: staticServiceCredentials{header: "Bearer service-token"},
			Timeout:     250 * time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	snapshot, err := authority.ReadAccountSecurity(context.Background(), "account / opaque")
	if err != nil {
		t.Fatal(err)
	}
	if snapshot.AccountState != "active" || snapshot.AuthEpoch != 7 {
		t.Fatalf("snapshot=%+v", snapshot)
	}
	if receivedMethod != http.MethodGet ||
		receivedPath != "/internal/user/accounts/account%20%2F%20opaque/security" ||
		receivedAuth != "Bearer service-token" ||
		receivedCache != "no-store" {
		t.Fatalf(
			"request method=%q path=%q auth=%q cache=%q",
			receivedMethod,
			receivedPath,
			receivedAuth,
			receivedCache,
		)
	}
}

func TestHTTPAccountSecurityAuthorityFailsClosedForInvalidResponses(t *testing.T) {
	for name, response := range map[string]struct {
		status int
		body   string
	}{
		"unknown field":  {status: http.StatusOK, body: `{"accountState":"active","authEpoch":1,"userId":"leak"}`},
		"invalid state":  {status: http.StatusOK, body: `{"accountState":"","authEpoch":1}`},
		"invalid epoch":  {status: http.StatusOK, body: `{"accountState":"active","authEpoch":0}`},
		"upstream error": {status: http.StatusInternalServerError, body: `{"error":"do not propagate"}`},
	} {
		t.Run(name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(response.status)
				_, _ = w.Write([]byte(response.body))
			}))
			defer server.Close()
			authority, err := NewHTTPAccountSecurityAuthority(
				HTTPAccountSecurityAuthorityConfig{
					BaseURL:     server.URL,
					HTTPClient:  &http.Client{Timeout: time.Second},
					Credentials: staticServiceCredentials{header: "Bearer service-token"},
					Timeout:     time.Second,
				},
			)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := authority.ReadAccountSecurity(context.Background(), "account-1"); !errors.Is(err, ErrAccountSecurityUnavailable) {
				t.Fatalf("err=%v, want unavailable", err)
			}
		})
	}
}

func TestHTTPAccountSecurityAuthorityDoesNotFollowRedirects(t *testing.T) {
	redirectTargetReached := false
	redirectTarget := httptest.NewServer(http.HandlerFunc(func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		redirectTargetReached = true
		if got := r.Header.Get("Authorization"); got != "" {
			t.Errorf("redirect target received scoped authorization %q", got)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer redirectTarget.Close()

	origin := httptest.NewServer(http.HandlerFunc(func(
		w http.ResponseWriter,
		_ *http.Request,
	) {
		w.Header().Set("Location", redirectTarget.URL+"/authority-redirect")
		w.WriteHeader(http.StatusTemporaryRedirect)
	}))
	defer origin.Close()

	authority, err := NewHTTPAccountSecurityAuthority(
		HTTPAccountSecurityAuthorityConfig{
			BaseURL:     origin.URL,
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: staticServiceCredentials{header: "Bearer service-token"},
			Timeout:     time.Second,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := authority.ReadAccountSecurity(
		context.Background(),
		"account-1",
	); !errors.Is(err, ErrAccountSecurityUnavailable) {
		t.Fatalf("redirect err=%v, want unavailable", err)
	}
	if redirectTargetReached {
		t.Fatal("authority client must not follow redirects")
	}
}

func TestHTTPAccountSecurityAuthorityMapsOnlyNotFoundAsTerminalSubject(t *testing.T) {
	server := httptest.NewServer(http.NotFoundHandler())
	defer server.Close()
	authority, err := NewHTTPAccountSecurityAuthority(
		HTTPAccountSecurityAuthorityConfig{
			BaseURL:     server.URL,
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: staticServiceCredentials{header: "Bearer service-token"},
			Timeout:     time.Second,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := authority.ReadAccountSecurity(context.Background(), "account-1"); !errors.Is(err, ErrAccountSecurityNotFound) {
		t.Fatalf("err=%v, want not found", err)
	}
}

func TestHTTPAccountSecurityAuthorityReadinessUsesScopedHealthRoute(t *testing.T) {
	var (
		receivedPath string
		receivedAuth string
	)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedPath = r.URL.EscapedPath()
		receivedAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer server.Close()
	authority, err := NewHTTPAccountSecurityAuthority(
		HTTPAccountSecurityAuthorityConfig{
			BaseURL:     server.URL,
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: staticServiceCredentials{header: "Bearer service-token"},
			Timeout:     time.Second,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := authority.CheckAccountSecurityAuthority(context.Background()); err != nil {
		t.Fatal(err)
	}
	if receivedPath != accountSecurityAuthorityHealthPath ||
		receivedAuth != "Bearer service-token" {
		t.Fatalf("path=%q auth=%q", receivedPath, receivedAuth)
	}
}

func TestHTTPAccountSecurityAuthorityPropagatesOnlyCorrelationHeaders(t *testing.T) {
	var received http.Header
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		received = r.Header.Clone()
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"accountState":"active","authEpoch":1}`))
	}))
	defer server.Close()
	authority, err := NewHTTPAccountSecurityAuthority(
		HTTPAccountSecurityAuthorityConfig{
			BaseURL:     server.URL,
			HTTPClient:  &http.Client{Timeout: time.Second},
			Credentials: staticServiceCredentials{header: "Bearer service-token"},
			Timeout:     time.Second,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	headers := http.Header{
		"X-Request-Id": []string{"request-123"},
		"X-Trace-Id":   []string{"trace-123"},
	}
	ctx := withAccountSecurityAuthorityCorrelation(context.Background(), headers)
	if _, err := authority.ReadAccountSecurity(ctx, "account-1"); err != nil {
		t.Fatal(err)
	}
	if received.Get("X-Request-Id") != "request-123" ||
		received.Get("X-Trace-Id") != "trace-123" {
		t.Fatalf("correlation headers=%v", received)
	}
	if received.Get("X-Client-User-Id") != "" ||
		received.Get("X-Client-Persona-Id") != "" {
		t.Fatalf("identity headers must not cross authority boundary: %v", received)
	}
}

func TestHTTPAccountSecurityAuthorityRejectsNonOriginConfiguration(t *testing.T) {
	for _, raw := range []string{
		"",
		"user-service:18082",
		"https://user-service.internal/path",
		"https://user-service.internal?mode=compat",
		"https://user:secret@user-service.internal",
	} {
		if _, err := NewHTTPAccountSecurityAuthority(
			HTTPAccountSecurityAuthorityConfig{
				BaseURL:     raw,
				HTTPClient:  &http.Client{Timeout: time.Second},
				Credentials: staticServiceCredentials{header: "Bearer service-token"},
				Timeout:     time.Second,
			},
		); err == nil {
			t.Fatalf("base URL %q must be rejected", raw)
		}
	}
}

func TestMiddlewareAppliesAccountSecurityAuthorityBeforePrincipalInjection(t *testing.T) {
	type testCase struct {
		name       string
		snapshot   AccountSecuritySnapshot
		err        error
		authEpoch  int64
		wantStatus int
		wantCode   string
	}
	cases := []testCase{
		{
			name:       "closed account",
			snapshot:   AccountSecuritySnapshot{AccountState: "closed", AuthEpoch: 2},
			authEpoch:  2,
			wantStatus: http.StatusGone,
			wantCode:   "USER.AUTH.account_deleted",
		},
		{
			name:       "suspended account",
			snapshot:   AccountSecuritySnapshot{AccountState: "suspended", AuthEpoch: 2},
			authEpoch:  2,
			wantStatus: http.StatusForbidden,
			wantCode:   "USER.AUTH.account_suspended",
		},
		{
			name:       "stale epoch",
			snapshot:   AccountSecuritySnapshot{AccountState: "active", AuthEpoch: 3},
			authEpoch:  2,
			wantStatus: http.StatusUnauthorized,
			wantCode:   "USER.AUTH.token_stale",
		},
		{
			name:       "missing account",
			err:        ErrAccountSecurityNotFound,
			authEpoch:  2,
			wantStatus: http.StatusGone,
			wantCode:   "USER.AUTH.account_deleted",
		},
		{
			name:       "authority unavailable",
			err:        ErrAccountSecurityUnavailable,
			authEpoch:  2,
			wantStatus: http.StatusServiceUnavailable,
			wantCode:   "USER.AUTH.account_security_unavailable",
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			config := testTokenConfig(TokenTypeAccess)
			token, err := mustSigner(t, config).Sign(TokenSubject{
				AccountID: "account-security-subject",
				AuthEpoch: testCase.authEpoch,
			})
			if err != nil {
				t.Fatal(err)
			}
			authority := &staticAccountSecurityAuthority{
				snapshot: testCase.snapshot,
				err:      testCase.err,
			}
			nextCalled := false
			handler := Middleware(MiddlewareConfig{
				AccessTokenVerifier:      mustVerifier(t, config),
				AccountSecurityAuthority: authority,
			})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				nextCalled = true
				if _, exists := PrincipalFromContext(r.Context()); !exists {
					t.Error("principal must be injected only after a successful authority check")
				}
				w.WriteHeader(http.StatusNoContent)
			}))
			request := httptest.NewRequest(http.MethodGet, "/protected", nil)
			request.Header.Set("Authorization", "Bearer "+token)
			response := httptest.NewRecorder()

			handler.ServeHTTP(response, request)

			if response.Code != testCase.wantStatus || nextCalled {
				t.Fatalf("status=%d next=%v", response.Code, nextCalled)
			}
			if authority.calls != 1 || authority.account != "account-security-subject" {
				t.Fatalf("authority calls=%d account=%q", authority.calls, authority.account)
			}
			var body struct {
				Code string `json:"code"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
				t.Fatal(err)
			}
			if body.Code != testCase.wantCode {
				t.Fatalf("code=%q want=%q", body.Code, testCase.wantCode)
			}
			if strings.Contains(response.Body.String(), "account-security-subject") {
				t.Fatal("authority denial response must not expose account identity")
			}
		})
	}
}

func TestMiddlewareAllowsActiveMatchingAccountSecuritySnapshot(t *testing.T) {
	config := testTokenConfig(TokenTypeAccess)
	token, err := mustSigner(t, config).Sign(TokenSubject{
		AccountID: "account-1",
		AuthEpoch: 9,
	})
	if err != nil {
		t.Fatal(err)
	}
	authority := &staticAccountSecurityAuthority{
		snapshot: AccountSecuritySnapshot{AccountState: "active", AuthEpoch: 9},
	}
	handler := Middleware(MiddlewareConfig{
		AccessTokenVerifier:      mustVerifier(t, config),
		AccountSecurityAuthority: authority,
	})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		principal, exists := PrincipalFromContext(r.Context())
		if !exists || principal.Actor.AccountID != "account-1" {
			t.Fatalf("principal=%+v exists=%v", principal, exists)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	request := httptest.NewRequest(http.MethodGet, "/protected", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)

	if response.Code != http.StatusNoContent || authority.calls != 1 {
		t.Fatalf("status=%d authorityCalls=%d", response.Code, authority.calls)
	}
}

func TestMiddlewareSkipsAccountSecurityAuthorityForServiceAndDevicePrincipals(t *testing.T) {
	accessConfig := testTokenConfig(TokenTypeAccess)
	deviceConfig := testTokenConfig(TokenTypeDevice)
	serviceToken, err := mustSigner(t, accessConfig).Sign(TokenSubject{
		AccountID: "service:caller",
		Roles:     []string{"service"},
	})
	if err != nil {
		t.Fatal(err)
	}
	deviceTicket, err := mustSigner(t, deviceConfig).Sign(TokenSubject{
		DeviceActorID: "device-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	for name, request := range map[string]*http.Request{
		"service": func() *http.Request {
			request := httptest.NewRequest(http.MethodGet, "/internal", nil)
			request.Header.Set("Authorization", "Bearer "+serviceToken)
			return request
		}(),
		"device": func() *http.Request {
			request := httptest.NewRequest(http.MethodGet, "/device", nil)
			request.Header.Set(DeviceTicketHeader, deviceTicket)
			return request
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			authority := &staticAccountSecurityAuthority{
				err: ErrAccountSecurityUnavailable,
			}
			handler := Middleware(MiddlewareConfig{
				AccessTokenVerifier:      mustVerifier(t, accessConfig),
				DeviceTicketVerifier:     mustVerifier(t, deviceConfig),
				AccountSecurityAuthority: authority,
			})(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusNoContent)
			}))
			response := httptest.NewRecorder()

			handler.ServeHTTP(response, request)

			if response.Code != http.StatusNoContent || authority.calls != 0 {
				t.Fatalf("status=%d authorityCalls=%d", response.Code, authority.calls)
			}
		})
	}
}
