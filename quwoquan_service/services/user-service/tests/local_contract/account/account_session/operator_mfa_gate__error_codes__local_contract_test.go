package local_contract

import (
	"crypto"
	crand "crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

func signOperatorMfaTestToken(
	t *testing.T,
	key *rsa.PrivateKey,
	keyID string,
	claims map[string]any,
) string {
	t.Helper()
	headerJSON, err := json.Marshal(map[string]string{
		"alg": "RS256", "typ": "JWT", "kid": keyID,
	})
	if err != nil {
		t.Fatalf("marshal jwt header: %v", err)
	}
	payloadJSON, err := json.Marshal(claims)
	if err != nil {
		t.Fatalf("marshal jwt claims: %v", err)
	}
	input := base64.RawURLEncoding.EncodeToString(headerJSON) +
		"." + base64.RawURLEncoding.EncodeToString(payloadJSON)
	digest := sha256.Sum256([]byte(input))
	signature, err := rsa.SignPKCS1v15(crand.Reader, key, crypto.SHA256, digest[:])
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return input + "." + base64.RawURLEncoding.EncodeToString(signature)
}

// USER.AUTH.mfa_required 由 runtime/auth 在 control-plane credential 边界发射:
// 运营 OIDC 凭据签名与受众均合法,但缺少 MFA 声明时,必须拒绝并升级提示。
func TestOperatorOIDCCredentialWithoutMFAReturnsMfaRequired(t *testing.T) {
	t.Parallel()

	key, err := rsa.GenerateKey(crand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate rsa key: %v", err)
	}
	const keyID = "operator-mfa-gate-key"
	jwksServer := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			_ = json.NewEncoder(w).Encode(map[string]any{
				"keys": []map[string]string{{
					"kty": "RSA",
					"use": "sig",
					"alg": "RS256",
					"kid": keyID,
					"n":   base64.RawURLEncoding.EncodeToString(key.N.Bytes()),
					"e":   base64.RawURLEncoding.EncodeToString([]byte{1, 0, 1}),
				}},
			})
		},
	))
	t.Cleanup(jwksServer.Close)

	verifier, err := rtauth.NewOIDCVerifier(rtauth.OIDCConfig{
		Issuer:     jwksServer.URL,
		Audience:   "quwoquan-ops",
		JWKSURL:    jwksServer.URL,
		RequireMFA: true,
	})
	if err != nil {
		t.Fatalf("construct oidc verifier: %v", err)
	}

	tokenWithoutMFA := signOperatorMfaTestToken(t, key, keyID, map[string]any{
		"iss": jwksServer.URL,
		"aud": "quwoquan-ops",
		"sub": "operator-no-mfa",
		"iat": time.Now().Unix(),
		"exp": time.Now().Add(time.Minute).Unix(),
	})

	handler := rtauth.Middleware(rtauth.MiddlewareConfig{
		OperatorOIDCVerifier: verifier,
	})(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("credential without MFA must not reach the protected handler")
	}))

	request := httptest.NewRequest(http.MethodGet, "/control-plane/audit/events", nil)
	request.Header.Set("Authorization", "Bearer "+tokenWithoutMFA)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)

	var wire struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &wire); err != nil {
		t.Fatalf("decode error response %q: %v", recorder.Body.String(), err)
	}
	if recorder.Code != http.StatusUnauthorized ||
		wire.Code != "USER.AUTH.mfa_required" {
		t.Fatalf(
			"expected 401 USER.AUTH.mfa_required, got status=%d code=%s body=%s",
			recorder.Code, wire.Code, recorder.Body.String(),
		)
	}
}
