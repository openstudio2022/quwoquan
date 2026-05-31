package auth

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestSignAndVerifyRoundTrip(t *testing.T) {
	secret := []byte("test-secret")
	signer := NewHS256Signer(secret, 30*time.Minute)
	verifier := NewHS256Verifier(secret)

	token, err := signer.Sign("owner-1", "sub-1", 3, "user")
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	claims, err := verifier.Verify(token)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if claims.Subject != "owner-1" || claims.Persona != "sub-1" || claims.TokenVersion != 3 {
		t.Fatalf("unexpected claims: %#v", claims)
	}
}

func TestVerifyRejectsTamperedSignature(t *testing.T) {
	signer := NewHS256Signer([]byte("secret-a"), time.Minute)
	other := NewHS256Verifier([]byte("secret-b"))
	token, _ := signer.Sign("owner-1", "", 0, "")
	if _, err := other.Verify(token); !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("expected ErrInvalidToken, got %v", err)
	}
}

func TestVerifyRejectsExpired(t *testing.T) {
	secret := []byte("secret")
	signer := NewHS256Signer(secret, time.Minute)
	signer.now = func() time.Time { return time.Unix(1000, 0) }
	verifier := NewHS256Verifier(secret)
	verifier.now = func() time.Time { return time.Unix(1000+120, 0) } // 2min later

	token, _ := signer.Sign("owner-1", "", 0, "")
	if _, err := verifier.Verify(token); !errors.Is(err, ErrExpiredToken) {
		t.Fatalf("expected ErrExpiredToken, got %v", err)
	}
}

func TestMiddlewareOverridesClientUserHeader(t *testing.T) {
	secret := []byte("secret")
	signer := NewHS256Signer(secret, time.Minute)
	verifier := NewHS256Verifier(secret)
	token, _ := signer.Sign("trusted-owner", "trusted-sub", 1, "user")

	var seenUser, seenSub string
	var principalOK bool
	handler := Middleware(verifier)(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		seenUser = r.Header.Get(clientUserIDHeader)
		seenSub = r.Header.Get(clientSubAccountIDHdr)
		_, principalOK = PrincipalFromContext(r.Context())
	}))

	req := httptest.NewRequest(http.MethodGet, "/v1/me/profile", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set(clientUserIDHeader, "spoofed-owner") // 应被 token 覆盖
	handler.ServeHTTP(httptest.NewRecorder(), req)

	if seenUser != "trusted-owner" {
		t.Fatalf("expected token-derived user, got %q", seenUser)
	}
	if seenSub != "trusted-sub" {
		t.Fatalf("expected token-derived sub, got %q", seenSub)
	}
	if !principalOK {
		t.Fatalf("expected principal in context")
	}
}

func TestMiddlewareDropsHeaderOnInvalidToken(t *testing.T) {
	verifier := NewHS256Verifier([]byte("secret"))
	var seenUser string
	handler := Middleware(verifier)(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		seenUser = r.Header.Get(clientUserIDHeader)
	}))
	req := httptest.NewRequest(http.MethodGet, "/v1/me/profile", nil)
	req.Header.Set("Authorization", "Bearer not-a-valid-jwt")
	req.Header.Set(clientUserIDHeader, "spoofed-owner")
	handler.ServeHTTP(httptest.NewRecorder(), req)
	if seenUser != "" {
		t.Fatalf("expected spoofed header dropped on invalid token, got %q", seenUser)
	}
}
