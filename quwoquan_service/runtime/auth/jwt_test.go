package auth

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func testTokenConfig(tokenType TokenType) TokenConfig {
	return TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "https://auth.quwoquan.test",
		Audience:     "quwoquan-api",
		Type:         tokenType,
		TokenVersion: 3,
		TTL:          time.Minute,
		ClockSkew:    5 * time.Second,
	}
}

func mustSigner(t *testing.T, config TokenConfig) *Signer {
	t.Helper()
	signer, err := NewHS256Signer(config)
	if err != nil {
		t.Fatalf("new signer: %v", err)
	}
	return signer
}

func mustVerifier(t *testing.T, config TokenConfig) *Verifier {
	t.Helper()
	verifier, err := NewHS256Verifier(config)
	if err != nil {
		t.Fatalf("new verifier: %v", err)
	}
	return verifier
}

func TestSignAndVerifyAccessTokenContract(t *testing.T) {
	config := testTokenConfig(TokenTypeAccess)
	signer := mustSigner(t, config)
	verifier := mustVerifier(t, config)

	token, err := signer.Sign(TokenSubject{
		AccountID:   "account-1",
		PersonaID:   "persona-1",
		Scopes:      []string{"user.read", "content.report.write"},
		Permissions: []string{"report.create"},
		Roles:       []string{"user"},
	})
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	claims, err := verifier.Verify(token)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if claims.Subject != "account-1" ||
		claims.Persona != "persona-1" ||
		claims.TokenVersion != config.TokenVersion ||
		claims.Issuer != config.Issuer ||
		claims.Audience != config.Audience ||
		claims.TokenType != TokenTypeAccess ||
		claims.JWTID == "" {
		t.Fatalf("unexpected claims: %#v", claims)
	}
	if claims.Scope != "user.read content.report.write" {
		t.Fatalf("scope=%q", claims.Scope)
	}
}

func TestSignAndVerifyDeviceTicketBuildsOnlyDeviceActor(t *testing.T) {
	config := testTokenConfig(TokenTypeDevice)
	signer := mustSigner(t, config)
	verifier := mustVerifier(t, config)
	token, err := signer.Sign(TokenSubject{
		DeviceActorID: "device-1",
		Scopes:        []string{"location.nearby"},
	})
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	claims, err := verifier.Verify(token)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	principal := principalFromClaims(*claims)
	if principal.Actor.DeviceActorID != "device-1" ||
		principal.Actor.AccountID != "" ||
		principal.Actor.PersonaID != "" {
		t.Fatalf("unexpected device actor: %+v", principal.Actor)
	}
}

func TestTokenConfigAndSubjectFailClosed(t *testing.T) {
	for _, mutate := range []func(*TokenConfig){
		func(config *TokenConfig) { config.Secret = []byte("short") },
		func(config *TokenConfig) { config.Issuer = "" },
		func(config *TokenConfig) { config.Audience = "" },
		func(config *TokenConfig) { config.TokenVersion = 0 },
		func(config *TokenConfig) { config.TTL = 0 },
	} {
		config := testTokenConfig(TokenTypeAccess)
		mutate(&config)
		if _, err := NewHS256Signer(config); err == nil {
			t.Fatal("invalid signer config must fail")
		}
		if _, err := NewHS256Verifier(config); err == nil {
			t.Fatal("invalid verifier config must fail")
		}
	}

	accessSigner := mustSigner(t, testTokenConfig(TokenTypeAccess))
	if _, err := accessSigner.Sign(TokenSubject{DeviceActorID: "device-1"}); err == nil {
		t.Fatal("access token must reject device-only subject")
	}
	deviceSigner := mustSigner(t, testTokenConfig(TokenTypeDevice))
	if _, err := deviceSigner.Sign(TokenSubject{
		AccountID:     "account-1",
		DeviceActorID: "device-1",
	}); err == nil {
		t.Fatal("device ticket must reject mixed identity")
	}
}

func TestVerifyRejectsSignatureIssuerAudienceTypeAndVersionDrift(t *testing.T) {
	config := testTokenConfig(TokenTypeAccess)
	token, err := mustSigner(t, config).Sign(TokenSubject{AccountID: "account-1"})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name   string
		mutate func(*TokenConfig)
		target error
	}{
		{
			name: "signature",
			mutate: func(config *TokenConfig) {
				config.Secret = []byte("abcdef0123456789abcdef0123456789")
			},
			target: ErrInvalidToken,
		},
		{
			name:   "issuer",
			mutate: func(config *TokenConfig) { config.Issuer = "other" },
			target: ErrInvalidToken,
		},
		{
			name:   "audience",
			mutate: func(config *TokenConfig) { config.Audience = "other" },
			target: ErrInvalidToken,
		},
		{
			name:   "type",
			mutate: func(config *TokenConfig) { config.Type = TokenTypeDevice },
			target: ErrInvalidToken,
		},
		{
			name: "version",
			mutate: func(config *TokenConfig) {
				config.TokenVersion += 1
			},
			target: ErrTokenVersion,
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			verifyConfig := config
			testCase.mutate(&verifyConfig)
			_, err := mustVerifier(t, verifyConfig).Verify(token)
			if !errors.Is(err, testCase.target) {
				t.Fatalf("err=%v, want %v", err, testCase.target)
			}
		})
	}
}

func TestVerifyRejectsExpiredAndFutureToken(t *testing.T) {
	config := testTokenConfig(TokenTypeAccess)
	signer := mustSigner(t, config)
	signer.now = func() time.Time { return time.Unix(1000, 0) }
	token, err := signer.Sign(TokenSubject{AccountID: "account-1"})
	if err != nil {
		t.Fatal(err)
	}

	expiredVerifier := mustVerifier(t, config)
	expiredVerifier.now = func() time.Time { return time.Unix(1120, 0) }
	if _, err := expiredVerifier.Verify(token); !errors.Is(err, ErrExpiredToken) {
		t.Fatalf("expected ErrExpiredToken, got %v", err)
	}

	futureSigner := mustSigner(t, config)
	futureSigner.now = func() time.Time { return time.Unix(1200, 0) }
	futureToken, err := futureSigner.Sign(TokenSubject{AccountID: "account-1"})
	if err != nil {
		t.Fatal(err)
	}
	futureVerifier := mustVerifier(t, config)
	futureVerifier.now = func() time.Time { return time.Unix(1000, 0) }
	if _, err := futureVerifier.Verify(futureToken); !errors.Is(err, ErrTokenNotYetValid) {
		t.Fatalf("expected ErrTokenNotYetValid, got %v", err)
	}
}

func TestVerifyRejectsNonHS256HeaderEvenWithValidSignature(t *testing.T) {
	config := testTokenConfig(TokenTypeAccess)
	token, err := mustSigner(t, config).Sign(TokenSubject{AccountID: "account-1"})
	if err != nil {
		t.Fatal(err)
	}
	parts := strings.Split(token, ".")
	header, err := encodeSegment(jwtHeader{Alg: "none", Typ: "JWT"})
	if err != nil {
		t.Fatal(err)
	}
	input := header + "." + parts[1]
	forged := input + "." + sign(input, config.Secret)
	if _, err := mustVerifier(t, config).Verify(forged); !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("expected ErrInvalidToken, got %v", err)
	}
}

func TestMiddlewareUsesVerifiedPrincipalAndRejectsInvalidCredential(t *testing.T) {
	config := testTokenConfig(TokenTypeAccess)
	token, err := mustSigner(t, config).Sign(TokenSubject{
		AccountID: "trusted-account",
		PersonaID: "trusted-persona",
	})
	if err != nil {
		t.Fatal(err)
	}
	verifier := mustVerifier(t, config)

	var seen Principal
	handler := Middleware(MiddlewareConfig{AccessTokenVerifier: verifier})(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			seen, _ = PrincipalFromContext(r.Context())
			if r.Header.Get("Authorization") != "" {
				t.Fatal("verified credential must be removed before downstream logging")
			}
			w.WriteHeader(http.StatusNoContent)
		}),
	)
	req := httptest.NewRequest(http.MethodGet, "/me/profile", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set(clientUserIDHeader, "forged-account")
	req.Header.Set(clientPersonaIDHeader, "forged-persona")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, req)
	if response.Code != http.StatusNoContent ||
		seen.Actor.AccountID != "trusted-account" ||
		seen.Actor.PersonaID != "trusted-persona" {
		t.Fatalf("status=%d principal=%+v", response.Code, seen)
	}

	nextCalled := false
	invalidHandler := Middleware(MiddlewareConfig{AccessTokenVerifier: verifier})(
		http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
			nextCalled = true
		}),
	)
	invalidRequest := httptest.NewRequest(http.MethodGet, "/me/profile", nil)
	invalidRequest.Header.Set("Authorization", "Bearer invalid")
	invalidResponse := httptest.NewRecorder()
	invalidHandler.ServeHTTP(invalidResponse, invalidRequest)
	if invalidResponse.Code != http.StatusUnauthorized || nextCalled {
		t.Fatalf("invalid credential status=%d next=%v", invalidResponse.Code, nextCalled)
	}
}

func TestMiddlewareRejectsAccessAndDeviceCredentialConflict(t *testing.T) {
	accessConfig := testTokenConfig(TokenTypeAccess)
	deviceConfig := testTokenConfig(TokenTypeDevice)
	accessToken, _ := mustSigner(t, accessConfig).Sign(
		TokenSubject{AccountID: "account-1"},
	)
	deviceTicket, _ := mustSigner(t, deviceConfig).Sign(
		TokenSubject{DeviceActorID: "device-1"},
	)
	handler := Middleware(MiddlewareConfig{
		AccessTokenVerifier:  mustVerifier(t, accessConfig),
		DeviceTicketVerifier: mustVerifier(t, deviceConfig),
	})(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("credential conflict reached downstream")
	}))
	request := httptest.NewRequest(http.MethodGet, "/", nil)
	request.Header.Set("Authorization", "Bearer "+accessToken)
	request.Header.Set(DeviceTicketHeader, deviceTicket)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status=%d", response.Code)
	}
}
