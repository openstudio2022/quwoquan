package auth

// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-002

import (
	"crypto"
	crand "crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestOIDCVerifierChecksJWKSIssuerAudienceAndMFA(t *testing.T) {
	key, err := rsa.GenerateKey(crand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate rsa key: %v", err)
	}
	const keyID = "operator-key-1"
	jwksServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(oidcJWKSet{Keys: []oidcJWK{{
			KTY: "RSA",
			Use: "sig",
			Alg: "RS256",
			KID: keyID,
			N:   base64.RawURLEncoding.EncodeToString(key.N.Bytes()),
			E:   base64.RawURLEncoding.EncodeToString([]byte{1, 0, 1}),
		}}})
	}))
	defer jwksServer.Close()

	verifier, err := NewOIDCVerifier(OIDCConfig{
		Issuer:     jwksServer.URL,
		Audience:   "quwoquan-ops",
		JWKSURL:    jwksServer.URL,
		RequireMFA: true,
	})
	if err != nil {
		t.Fatalf("new oidc verifier: %v", err)
	}
	token := signOIDCTestToken(t, key, keyID, map[string]any{
		"iss":         jwksServer.URL,
		"aud":         "quwoquan-ops",
		"sub":         "operator-1",
		"scope":       "ops.read",
		"roles":       []string{"operator"},
		"permissions": []string{"audit.inspect"},
		"amr":         []string{"pwd", "mfa"},
		"iat":         time.Now().Unix(),
		"exp":         time.Now().Add(5 * time.Minute).Unix(),
		"jti":         "oidc-jti-1",
	})
	principal, err := verifier.Verify(token)
	if err != nil {
		t.Fatalf("verify oidc token: %v", err)
	}
	if principal.Actor.AccountID != "operator-1" ||
		!containsAll(principal.Roles, []string{"operator"}) ||
		!containsAll(principal.Permissions, []string{"audit.inspect"}) {
		t.Fatalf("unexpected operator principal: %+v", principal)
	}

	guard := RequireGeneratedOperationAuthorization([]OperationSecurityDescriptor{{
		CanonicalOperationID: "ops.audit.ListAuditEvents",
		ContractGraphSHA256:  "oidc-local-contract",
		Method:               http.MethodGet,
		PathTemplate:         "/control-plane/audit/events",
		OperationKind:        "query",
		AuthMode:             "required",
		ActorRequirement:     "account",
		Principal:            "operator",
		Permissions:          []string{"audit.inspect"},
		CommercialStatus:     "ready",
	}})
	handler := Middleware(MiddlewareConfig{OperatorOIDCVerifier: verifier})(guard(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			verified, ok := PrincipalFromContext(r.Context())
			if !ok || verified.Actor.AccountID != "operator-1" {
				t.Fatalf("verified OIDC principal missing: %+v ok=%v", verified, ok)
			}
			if got := r.Header.Get(untrustedActorHeader); got != "" {
				t.Fatalf("forged actor header survived middleware: %q", got)
			}
			if got := r.Header.Get(untrustedUserIDHeader); got != "" {
				t.Fatalf("forged user header survived middleware: %q", got)
			}
			if got := r.Header.Get(clientAccountIDHeader); got != "operator-1" {
				t.Fatalf("trusted account header=%q", got)
			}
			w.WriteHeader(http.StatusNoContent)
		}),
	))
	request := httptest.NewRequest(http.MethodGet, "/control-plane/audit/events", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set(untrustedActorHeader, "forged-operator")
	request.Header.Set(untrustedUserIDHeader, "forged-user")
	request.Header.Set(clientAccountIDHeader, "forged-account")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("OIDC protected operation status=%d body=%s", response.Code, response.Body.String())
	}
}

func TestOIDCVerifierRejectsTokenWithoutMFA(t *testing.T) {
	key, err := rsa.GenerateKey(crand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate rsa key: %v", err)
	}
	const keyID = "operator-key-2"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(oidcJWKSet{Keys: []oidcJWK{{
			KTY: "RSA", Alg: "RS256", KID: keyID,
			N: base64.RawURLEncoding.EncodeToString(key.N.Bytes()),
			E: base64.RawURLEncoding.EncodeToString([]byte{1, 0, 1}),
		}}})
	}))
	defer server.Close()
	verifier, err := NewOIDCVerifier(OIDCConfig{
		Issuer: server.URL, Audience: "ops", JWKSURL: server.URL, RequireMFA: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	token := signOIDCTestToken(t, key, keyID, map[string]any{
		"iss": server.URL, "aud": "ops", "sub": "operator-2",
		"iat": time.Now().Unix(), "exp": time.Now().Add(time.Minute).Unix(),
	})
	if _, err := verifier.Verify(token); err != ErrOIDCNotMFA {
		t.Fatalf("verify error = %v, want ErrOIDCNotMFA", err)
	}
}

func signOIDCTestToken(t *testing.T, key *rsa.PrivateKey, kid string, claims map[string]any) string {
	t.Helper()
	header, err := encodeSegment(oidcHeader{Alg: "RS256", Typ: "JWT", KID: kid})
	if err != nil {
		t.Fatal(err)
	}
	payload, err := encodeSegment(claims)
	if err != nil {
		t.Fatal(err)
	}
	input := header + "." + payload
	digest := sha256.Sum256([]byte(input))
	signature, err := rsa.SignPKCS1v15(crand.Reader, key, crypto.SHA256, digest[:])
	if err != nil {
		t.Fatal(err)
	}
	return input + "." + base64.RawURLEncoding.EncodeToString(signature)
}

func TestLooksLikeRS256JWTRejectsHS256(t *testing.T) {
	if looksLikeRS256JWT(strings.Join([]string{"eyJhbGciOiJIUzI1NiJ9", "e30", "sig"}, ".")) {
		t.Fatal("HS256 token must not be routed to OIDC verifier")
	}
}
