// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004.t1
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	rtcconfig "quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/runtimeconfig"
)

func TestCallAccountSecurityGateRejectsOldJWTBeforeHTTPAndDirectSignalling(
	t *testing.T,
) {
	t.Parallel()

	tokenConfig := rtcAccessTokenConfig()
	signer, err := rtauth.NewHS256Signer(tokenConfig)
	if err != nil {
		t.Fatalf("NewHS256Signer() error = %v", err)
	}
	verifier, err := rtauth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatalf("NewHS256Verifier() error = %v", err)
	}
	oldJWT, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "account-security-test",
		PersonaID: "persona-security-test",
		AuthEpoch: 1,
	})
	if err != nil {
		t.Fatalf("Sign(old JWT) error = %v", err)
	}

	authority := &testAccountSecurityAuthority{
		snapshot: rtauth.AccountSecuritySnapshot{
			AccountState: "active",
			AuthEpoch:    2,
		},
	}
	reachedHandler := false
	handler := rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      verifier,
		AccountSecurityAuthority: authority,
	})(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		reachedHandler = true
	}))
	request := httptest.NewRequest(http.MethodPost, "/rtc/calls", nil)
	request.Header.Set("Authorization", "Bearer "+oldJWT)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("old JWT status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
	if reachedHandler {
		t.Fatal("old JWT reached RTC handler after auth-epoch revocation")
	}

	gate := application.NewCallAccountSecurityGate(authority)
	directContext := rtauth.WithPrincipal(context.Background(), rtauth.Principal{
		Claims: rtauth.Claims{
			TokenType: rtauth.TokenTypeAccess,
			AuthEpoch: 1,
		},
		Actor: operation.ActorContext{
			AccountID: "account-security-test",
			PersonaID: "persona-security-test",
		},
	})
	if err := gate.AuthorizeCallActor(directContext, "persona-security-test"); !errors.Is(
		err,
		application.ErrCallAccountSecurityDenied,
	) {
		t.Fatalf("direct signalling old JWT error = %v, want account-security denial", err)
	}
}

func TestCallAccountSecurityGateFailsClosedWhenAuthorityUnavailable(
	t *testing.T,
) {
	t.Parallel()

	gate := application.NewCallAccountSecurityGate(&testAccountSecurityAuthority{
		err: errors.New("authority transport failure"),
	})
	ctx := rtauth.WithPrincipal(context.Background(), rtauth.Principal{
		Claims: rtauth.Claims{
			TokenType: rtauth.TokenTypeAccess,
			AuthEpoch: 1,
		},
		Actor: operation.ActorContext{
			AccountID: "account-security-test",
			PersonaID: "persona-security-test",
		},
	})
	if err := gate.AuthorizeCallActor(ctx, "persona-security-test"); !errors.Is(
		err,
		application.ErrCallAccountSecurityUnavailable,
	) {
		t.Fatalf("unavailable authority error = %v, want fail-closed unavailable", err)
	}
}

func TestRTCAccountSecurityAuthorityConfigurationRequiresExplicitBoundedValues(
	t *testing.T,
) {
	t.Parallel()

	tokenConfig := rtcAccessTokenConfig()
	if _, err := rtcconfig.NewAccountSecurityAuthority(
		tokenConfig,
		"",
		500,
	); err == nil {
		t.Fatal("empty user-service authority URL was accepted")
	}
	if _, err := rtcconfig.NewAccountSecurityAuthority(
		tokenConfig,
		"http://user-service:18081",
		49,
	); err == nil {
		t.Fatal("unbounded-low authority timeout was accepted")
	}
	if _, err := rtcconfig.NewAccountSecurityAuthority(
		tokenConfig,
		"http://user-service:18081",
		5001,
	); err == nil {
		t.Fatal("unbounded-high authority timeout was accepted")
	}
	if _, err := rtcconfig.NewAccountSecurityAuthority(
		tokenConfig,
		"http://user-service:18081",
		500,
	); err != nil {
		t.Fatalf("bounded explicit authority config rejected: %v", err)
	}
}

type testAccountSecurityAuthority struct {
	snapshot rtauth.AccountSecuritySnapshot
	err      error
}

func (authority *testAccountSecurityAuthority) ReadAccountSecurity(
	context.Context,
	string,
) (rtauth.AccountSecuritySnapshot, error) {
	if authority.err != nil {
		return rtauth.AccountSecuritySnapshot{}, authority.err
	}
	return authority.snapshot, nil
}

func rtcAccessTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte(strings.Repeat("a", 32)),
		Issuer:       "rtc-service-local-contract",
		Audience:     "rtc-service",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Hour,
	}
}
