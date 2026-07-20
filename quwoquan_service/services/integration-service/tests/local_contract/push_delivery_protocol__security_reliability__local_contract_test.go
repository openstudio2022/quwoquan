package local_contract

import (
	"context"
	"crypto"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/infrastructure/provider"
)

const protocolDeliveryKey = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"

func TestAPNsVoIPAndFCMProtocols(t *testing.T) {
	t.Run("APNs_HTTP2_ES256_VoIP_headers", testAPNsVoIPProtocol)
	t.Run("FCM_HTTP2_RS256_OAuth_cache_and_data", testFCMProtocol)
}

func testAPNsVoIPProtocol(t *testing.T) {
	now := time.Date(2026, 7, 20, 6, 0, 0, 0, time.UTC)
	key, keyFile := writeTemporaryECKey(t)
	var calls atomic.Int32
	server := newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		calls.Add(1)
		if request.ProtoMajor != 2 {
			t.Errorf("APNs request must use HTTP/2, got %s", request.Proto)
		}
		if request.URL.Path != "/3/device/device-token-apns" {
			t.Errorf("unexpected APNs path: %s", request.URL.Path)
		}
		assertAPNsJWT(t, strings.TrimPrefix(request.Header.Get("Authorization"), "bearer "), &key.PublicKey, now)
		for header, want := range map[string]string{
			"apns-push-type":   "voip",
			"apns-topic":       "com.quwoquan.app.voip",
			"apns-priority":    "10",
			"apns-expiration":  fmt.Sprintf("%d", now.Add(2*time.Minute).Unix()),
			"apns-collapse-id": expectedProviderCollapseKey(protocolDeliveryKey),
		} {
			if got := request.Header.Get(header); got != want {
				t.Errorf("%s=%q want %q", header, got, want)
			}
		}
		var payload struct {
			APS struct {
				ContentAvailable int `json:"content-available"`
			} `json:"aps"`
			Action          string `json:"action"`
			DeliveryKey     string `json:"deliveryKey"`
			CallID          string `json:"callId"`
			TargetPersonaID string `json:"targetPersonaId"`
			CallType        string `json:"callType"`
			CallerName      string `json:"callerName"`
			SourceLabel     string `json:"sourceLabel"`
			TrustRelation   string `json:"trustRelation"`
			ExpiresAt       string `json:"expiresAt"`
			OccurredAt      string `json:"occurredAt"`
		}
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			t.Errorf("decode APNs payload: %v", err)
		}
		expectedAction := application.PushDeliveryActionRing
		if calls.Load() == 2 {
			expectedAction = application.PushDeliveryActionCancel
		}
		if payload.APS.ContentAvailable != 1 ||
			payload.Action != expectedAction ||
			payload.DeliveryKey != protocolDeliveryKey ||
			payload.CallID != "call-001" ||
			payload.TargetPersonaID != "persona-target-001" ||
			payload.CallType != "audio" ||
			payload.CallerName != "来电用户" ||
			payload.SourceLabel != "契约会话" ||
			payload.TrustRelation != "known" ||
			payload.ExpiresAt != now.Add(2*time.Minute).Format(time.RFC3339) ||
			payload.OccurredAt != now.Format(time.RFC3339) {
			t.Errorf("unexpected APNs payload: %+v", payload)
		}
		w.Header().Set("apns-id", "apns-request-001")
		w.WriteHeader(http.StatusOK)
	}))
	apns, err := provider.NewAPNsVoIPProvider(provider.APNsVoIPConfig{
		Environment: provider.APNsEnvironmentSandbox,
		KeyFile:     keyFile,
		KeyID:       "APNSKEY01",
		TeamID:      "TEAM000001",
		Topic:       "com.quwoquan.app.voip",
		Timeout:     time.Second,
		BaseURL:     server.URL,
		Now:         func() time.Time { return now },
	}, server.Client())
	if err != nil {
		t.Fatalf("construct APNs provider: %v", err)
	}
	receipt, err := apns.SendPush(context.Background(), "device-token-apns", protocolPushMessage(now))
	if err != nil {
		t.Fatalf("send APNs VoIP: %v", err)
	}
	if receipt.ProviderRequestID != "apns-request-001" || calls.Load() != 1 {
		t.Fatalf("unexpected APNs receipt=%+v calls=%d", receipt, calls.Load())
	}
	cancelMessage := protocolPushMessage(now)
	cancelMessage.Action = application.PushDeliveryActionCancel
	if _, err := apns.SendPush(
		context.Background(),
		"device-token-apns",
		cancelMessage,
	); err != nil {
		t.Fatalf("send APNs cancellation: %v", err)
	}
	if calls.Load() != 2 {
		t.Fatalf("APNs cancellation calls=%d", calls.Load())
	}
}

func testFCMProtocol(t *testing.T) {
	now := time.Date(2026, 7, 20, 6, 0, 0, 0, time.UTC)
	key := writeTemporaryRSAKey(t)
	var tokenCalls atomic.Int32
	var sendCalls atomic.Int32
	var server *httptest.Server
	server = newHTTP2TLSServer(t, http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		if request.ProtoMajor != 2 {
			t.Errorf("FCM request must use HTTP/2, got %s", request.Proto)
		}
		switch request.URL.Path {
		case "/token":
			tokenCalls.Add(1)
			if err := request.ParseForm(); err != nil {
				t.Errorf("parse OAuth form: %v", err)
			}
			if request.Form.Get("grant_type") != "urn:ietf:params:oauth:grant-type:jwt-bearer" {
				t.Errorf("unexpected OAuth grant_type: %q", request.Form.Get("grant_type"))
			}
			assertFCMAssertion(t, request.Form.Get("assertion"), &key.PublicKey, server.URL+"/token", now)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"access_token": "oauth-access-token",
				"token_type":   "Bearer",
				"expires_in":   3600,
			})
		case "/v1/projects/qwq-test/messages:send":
			sendCalls.Add(1)
			if request.Header.Get("Authorization") != "Bearer oauth-access-token" {
				t.Errorf("unexpected FCM authorization")
			}
			var payload struct {
				Message struct {
					Token   string            `json:"token"`
					Data    map[string]string `json:"data"`
					Android struct {
						Priority    string `json:"priority"`
						TTL         string `json:"ttl"`
						CollapseKey string `json:"collapse_key"`
					} `json:"android"`
				} `json:"message"`
			}
			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Errorf("decode FCM request: %v", err)
			}
			if payload.Message.Token != "device-token-fcm" ||
				payload.Message.Android.Priority != "high" ||
				payload.Message.Android.TTL != "120s" ||
				payload.Message.Android.CollapseKey != expectedProviderCollapseKey(protocolDeliveryKey) ||
				payload.Message.Data["action"] != application.PushDeliveryActionRing &&
					payload.Message.Data["action"] != application.PushDeliveryActionCancel ||
				payload.Message.Data["callId"] != "call-001" ||
				payload.Message.Data["targetPersonaId"] != "persona-target-001" ||
				payload.Message.Data["trustRelation"] != "known" ||
				payload.Message.Data["occurredAt"] != now.Format(time.RFC3339) {
				t.Errorf("unexpected FCM payload: %+v", payload)
			}
			_ = json.NewEncoder(w).Encode(map[string]string{
				"name": fmt.Sprintf("projects/qwq-test/messages/%d", sendCalls.Load()),
			})
		default:
			http.NotFound(w, request)
		}
	}))
	serviceAccountFile := writeServiceAccountFile(t, key, server.URL+"/token")
	fcm, err := provider.NewFCMProvider(provider.FCMConfig{
		ServiceAccountFile: serviceAccountFile,
		ProjectID:          "qwq-test",
		Timeout:            time.Second,
		APIBaseURL:         server.URL,
		Now:                func() time.Time { return now },
	}, server.Client())
	if err != nil {
		t.Fatalf("construct FCM provider: %v", err)
	}
	const concurrentSends = 8
	var wait sync.WaitGroup
	sendErrors := make(chan error, concurrentSends)
	for index := 0; index < concurrentSends; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			receipt, sendErr := fcm.SendPush(
				context.Background(),
				"device-token-fcm",
				protocolPushMessage(now),
			)
			if sendErr != nil {
				sendErrors <- sendErr
				return
			}
			if !strings.HasPrefix(receipt.ProviderRequestID, "projects/qwq-test/messages/") {
				sendErrors <- fmt.Errorf("unexpected FCM receipt: %+v", receipt)
			}
		}()
	}
	wait.Wait()
	close(sendErrors)
	for sendErr := range sendErrors {
		t.Fatal(sendErr)
	}
	if tokenCalls.Load() != 1 {
		t.Fatalf("OAuth token must be cached, token calls=%d", tokenCalls.Load())
	}
	if sendCalls.Load() != concurrentSends {
		t.Fatalf("expected %d FCM sends, got %d", concurrentSends, sendCalls.Load())
	}
	cancelMessage := protocolPushMessage(now)
	cancelMessage.Action = application.PushDeliveryActionCancel
	if _, err := fcm.SendPush(
		context.Background(),
		"device-token-fcm",
		cancelMessage,
	); err != nil {
		t.Fatalf("send FCM cancellation: %v", err)
	}
	if sendCalls.Load() != concurrentSends+1 || tokenCalls.Load() != 1 {
		t.Fatalf(
			"FCM cancellation sends=%d tokenCalls=%d",
			sendCalls.Load(),
			tokenCalls.Load(),
		)
	}
}

func protocolPushMessage(now time.Time) application.PushDeliveryMessage {
	return application.PushDeliveryMessage{
		Action:          application.PushDeliveryActionRing,
		EndpointRef:     "endpoint-001",
		DeliveryKey:     protocolDeliveryKey,
		CallID:          "call-001",
		TargetPersonaID: "persona-target-001",
		CallType:        "audio",
		CallerName:      "来电用户",
		SourceLabel:     "契约会话",
		TrustRelation:   "known",
		ExpiresAt:       now.Add(2 * time.Minute),
		OccurredAt:      now,
	}
}

func expectedProviderCollapseKey(deliveryKey string) string {
	if len(deliveryKey) <= 64 {
		return deliveryKey
	}
	sum := sha256.Sum256([]byte(deliveryKey))
	return hex.EncodeToString(sum[:])
}

func newHTTP2TLSServer(t *testing.T, handler http.Handler) *httptest.Server {
	t.Helper()
	server := httptest.NewUnstartedServer(handler)
	server.EnableHTTP2 = true
	server.StartTLS()
	t.Cleanup(server.Close)
	return server
}

func writeTemporaryECKey(t *testing.T) (*ecdsa.PrivateKey, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	path := t.TempDir() + "/AuthKey_APNSKEY01.p8"
	if err := os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der}), 0o600); err != nil {
		t.Fatal(err)
	}
	return key, path
}

func writeTemporaryRSAKey(t *testing.T) *rsa.PrivateKey {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	return key
}

func writeServiceAccountFile(t *testing.T, key *rsa.PrivateKey, tokenURI string) string {
	t.Helper()
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	privatePEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
	raw, err := json.Marshal(map[string]string{
		"type":           "service_account",
		"project_id":     "qwq-test",
		"private_key_id": "rsa-key-001",
		"private_key":    string(privatePEM),
		"client_email":   "push-test@qwq-test.iam.gserviceaccount.com",
		"token_uri":      tokenURI,
	})
	if err != nil {
		t.Fatal(err)
	}
	path := t.TempDir() + "/fcm-service-account.json"
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func assertAPNsJWT(
	t *testing.T,
	token string,
	publicKey *ecdsa.PublicKey,
	now time.Time,
) {
	t.Helper()
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		t.Fatalf("invalid APNs JWT")
	}
	var header struct {
		Algorithm string `json:"alg"`
		KeyID     string `json:"kid"`
	}
	var claims struct {
		Issuer   string `json:"iss"`
		IssuedAt int64  `json:"iat"`
	}
	decodeJWTPart(t, parts[0], &header)
	decodeJWTPart(t, parts[1], &claims)
	if header.Algorithm != "ES256" || header.KeyID != "APNSKEY01" ||
		claims.Issuer != "TEAM000001" || claims.IssuedAt != now.Unix() {
		t.Fatalf("unexpected APNs JWT header=%+v claims=%+v", header, claims)
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || len(signature) != 64 {
		t.Fatalf("invalid APNs JWT signature")
	}
	digest := sha256.Sum256([]byte(parts[0] + "." + parts[1]))
	r := new(big.Int).SetBytes(signature[:32])
	s := new(big.Int).SetBytes(signature[32:])
	if !ecdsa.Verify(publicKey, digest[:], r, s) {
		t.Fatal("APNs JWT signature verification failed")
	}
}

func assertFCMAssertion(
	t *testing.T,
	assertion string,
	publicKey *rsa.PublicKey,
	audience string,
	now time.Time,
) {
	t.Helper()
	parts := strings.Split(assertion, ".")
	if len(parts) != 3 {
		t.Fatalf("invalid FCM assertion")
	}
	var header struct {
		Algorithm string `json:"alg"`
		Type      string `json:"typ"`
		KeyID     string `json:"kid"`
	}
	var claims struct {
		Issuer   string `json:"iss"`
		Scope    string `json:"scope"`
		Audience string `json:"aud"`
		IssuedAt int64  `json:"iat"`
		Expires  int64  `json:"exp"`
	}
	decodeJWTPart(t, parts[0], &header)
	decodeJWTPart(t, parts[1], &claims)
	if header.Algorithm != "RS256" || header.Type != "JWT" ||
		header.KeyID != "rsa-key-001" ||
		claims.Issuer != "push-test@qwq-test.iam.gserviceaccount.com" ||
		claims.Scope != "https://www.googleapis.com/auth/firebase.messaging" ||
		claims.Audience != audience ||
		claims.IssuedAt != now.Unix() ||
		claims.Expires != now.Add(time.Hour).Unix() {
		t.Fatalf("unexpected FCM assertion header=%+v claims=%+v", header, claims)
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		t.Fatalf("decode FCM assertion signature: %v", err)
	}
	digest := sha256.Sum256([]byte(parts[0] + "." + parts[1]))
	if err := rsa.VerifyPKCS1v15(publicKey, crypto.SHA256, digest[:], signature); err != nil {
		t.Fatalf("FCM assertion signature verification failed: %v", err)
	}
}

func decodeJWTPart(t *testing.T, encoded string, target any) {
	t.Helper()
	raw, err := base64.RawURLEncoding.DecodeString(encoded)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, target); err != nil {
		t.Fatal(err)
	}
}
