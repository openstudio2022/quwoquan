package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/services/user-service/internal/application"
	"quwoquan_service/services/user-service/internal/infrastructure/integration"
)

type externalInteractionContractRuntime struct {
	server *httptest.Server
	client *capturingExternalInteractionClient
}

type capturingExternalInteractionClient struct {
	delegate application.ExternalInteractionClient
	mu       sync.RWMutex
	codes    map[string]string
}

func (client *capturingExternalInteractionClient) SubmitSMSOTP(
	ctx context.Context,
	request application.SMSOTPDispatchRequest,
) (application.ExternalInteractionAccepted, error) {
	secret, err := testOTPCodeSealer.Open(request.CodeRef, otpseal.Binding{
		RequestID:   request.RequestID,
		ChallengeID: request.ChallengeID,
		ExpiresAt:   request.ExpiresAt,
	})
	if err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	client.mu.Lock()
	client.codes[secret.Phone] = secret.Code
	client.mu.Unlock()
	return client.delegate.SubmitSMSOTP(ctx, request)
}

func (client *capturingExternalInteractionClient) OTPCode(phone string) string {
	client.mu.RLock()
	defer client.mu.RUnlock()
	return client.codes[phone]
}

func startExternalInteractionContractRuntime() (*externalInteractionContractRuntime, error) {
	mux := http.NewServeMux()
	mux.HandleFunc("/integrations/external-requests", handleExternalInteractionRequest)
	server := httptest.NewTLSServer(mux)
	client, err := integration.NewExternalInteractionClient(server.URL, "beta", server.Client(), testAccessSigner)
	if err != nil {
		server.Close()
		return nil, err
	}
	return &externalInteractionContractRuntime{
		server: server,
		client: &capturingExternalInteractionClient{
			delegate: client,
			codes:    map[string]string{},
		},
	}, nil
}

func (runtime *externalInteractionContractRuntime) Close() {
	if runtime != nil && runtime.server != nil {
		runtime.server.Close()
	}
}

func handleExternalInteractionRequest(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost || request.Header.Get("Content-Type") != "application/json" {
		http.Error(writer, "invalid external interaction request", http.StatusBadRequest)
		return
	}
	token := strings.TrimPrefix(request.Header.Get("Authorization"), "Bearer ")
	claims, authErr := testAccessVerifier.Verify(token)
	if authErr != nil || !containsString(claims.Roles, "service") ||
		!strings.Contains(claims.Scope, "integration.external_interaction.submit") {
		http.Error(writer, "invalid service principal", http.StatusUnauthorized)
		return
	}
	var payload struct {
		RequestID      string            `json:"requestId"`
		Operation      string            `json:"operation"`
		Tenant         string            `json:"tenant"`
		Environment    string            `json:"env"`
		IdempotencyKey string            `json:"idempotencyKey"`
		CallbackEvent  string            `json:"callbackEvent"`
		PayloadRef     string            `json:"payloadRef"`
		PayloadDigest  string            `json:"payloadDigest"`
		Sensitivity    string            `json:"sensitivity"`
		ExpiresAt      string            `json:"expiresAt"`
		Payload        map[string]string `json:"payload"`
	}
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil ||
		strings.TrimSpace(payload.RequestID) == "" ||
		payload.Operation != "sms_otp.send" ||
		payload.Tenant != "quwoquan" ||
		payload.Environment != "beta" ||
		strings.TrimSpace(payload.IdempotencyKey) == "" ||
		payload.CallbackEvent != "SmsOtpDeliverySucceeded" ||
		!strings.HasPrefix(payload.PayloadRef, "otp_challenge:") ||
		len(payload.PayloadDigest) != 64 ||
		payload.Sensitivity != "secret" ||
		strings.TrimSpace(payload.ExpiresAt) == "" ||
		strings.TrimSpace(payload.Payload["challengeId"]) == "" ||
		strings.TrimSpace(payload.Payload["codeRef"]) == "" ||
		payload.Payload["phoneHash"] != payload.PayloadDigest ||
		strings.TrimSpace(payload.Payload["maskedRecipient"]) == "" ||
		payload.Payload["templateId"] != "sms_otp_login" {
		http.Error(writer, "external interaction contract rejected", http.StatusBadRequest)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(writer).Encode(application.ExternalInteractionAccepted{
		RequestID: payload.RequestID,
		Status:    "accepted",
	})
}

func TestExternalInteractionContractRuntime_ProductionClientSubmitsSecretReference(t *testing.T) {
	if externalInteractionRuntime == nil || externalInteractionRuntime.client == nil {
		t.Fatal("external interaction contract runtime is not initialized")
	}
	expiresAt := time.Now().UTC().Add(5 * time.Minute)
	codeRef, err := testOTPCodeSealer.Seal(
		otpseal.Secret{Phone: "+8618013813901", Code: "123456"},
		otpseal.Binding{
			RequestID:   "otp_req_contract",
			ChallengeID: "otp_ch_contract",
			ExpiresAt:   expiresAt,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	accepted, err := externalInteractionRuntime.client.SubmitSMSOTP(context.Background(), application.SMSOTPDispatchRequest{
		RequestID:      "otp_req_contract",
		ChallengeID:    "otp_ch_contract",
		CodeRef:        codeRef,
		PhoneHash:      strings.Repeat("a", 64),
		MaskedPhone:    "+86****3901",
		IdempotencyKey: "otp:contract:202607140125",
		ExpiresAt:      expiresAt,
	})
	if err != nil {
		t.Fatalf("submit OTP through production integration client: %v", err)
	}
	if accepted.RequestID != "otp_req_contract" || accepted.Status != "accepted" {
		t.Fatalf("unexpected accepted response: %s", fmt.Sprintf("%+v", accepted))
	}
}

func containsString(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}
