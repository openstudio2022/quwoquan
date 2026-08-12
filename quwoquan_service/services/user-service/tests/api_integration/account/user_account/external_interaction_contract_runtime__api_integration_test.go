package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

type externalInteractionContractRuntime struct {
	server        *httptest.Server
	client        *capturingExternalInteractionClient
	captureBridge *localCaptureBridge
	forceFailNext bool
	mu            sync.Mutex
}

type capturingExternalInteractionClient struct {
	delegate application.ExternalInteractionClient
	runtime  *externalInteractionContractRuntime
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
	if client.runtime == nil || client.runtime.captureBridge == nil {
		return application.ExternalInteractionAccepted{}, fmt.Errorf("local capture bridge unavailable")
	}
	if err := client.runtime.forwardToLocalCapture(request, secret); err != nil {
		return application.ExternalInteractionAccepted{}, err
	}
	return client.delegate.SubmitSMSOTP(ctx, request)
}

func startExternalInteractionContractRuntime() (*externalInteractionContractRuntime, error) {
	captureBridge, err := startLocalCaptureBridge()
	if err != nil {
		return nil, err
	}
	runtime := &externalInteractionContractRuntime{captureBridge: captureBridge}
	mux := http.NewServeMux()
	mux.HandleFunc("/integrations/external-requests", runtime.handleExternalInteractionRequest)
	server := httptest.NewServer(mux)
	serverAddress := server.Listener.Addr().String()
	transport := &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "tcp", serverAddress)
		},
	}
	client, err := integration.NewExternalInteractionClient(
		"http://integration-service:18086",
		"beta",
		&http.Client{Transport: transport},
		testAccessSigner,
	)
	if err != nil {
		server.Close()
		captureBridge.Close()
		return nil, err
	}
	runtime.server = server
	runtime.client = &capturingExternalInteractionClient{
		delegate: client,
		runtime:  runtime,
	}
	return runtime, nil
}

func (runtime *externalInteractionContractRuntime) Close() {
	if runtime != nil && runtime.server != nil {
		runtime.server.Close()
	}
	if runtime != nil && runtime.captureBridge != nil {
		runtime.captureBridge.Close()
	}
}

func (runtime *externalInteractionContractRuntime) ForceNextProviderFailure() {
	runtime.mu.Lock()
	runtime.forceFailNext = true
	runtime.mu.Unlock()
	if runtime.captureBridge != nil {
		runtime.captureBridge.ForceNextProviderFailure()
	}
}

func (runtime *externalInteractionContractRuntime) forwardToLocalCapture(
	request application.SMSOTPDispatchRequest,
	secret otpseal.Secret,
) error {
	runtime.mu.Lock()
	failNext := runtime.forceFailNext
	runtime.forceFailNext = false
	runtime.mu.Unlock()
	if failNext {
		runtime.captureBridge.ForceNextProviderFailure()
	}
	body, err := json.Marshal(map[string]any{
		"requestId":      request.RequestID,
		"operation":      "sms_otp.send",
		"env":            "beta",
		"idempotencyKey": request.IdempotencyKey,
		"expiresAt":      request.ExpiresAt.UTC().Format(time.RFC3339),
		"payload": map[string]string{
			"recipient":  secret.Phone,
			"code":       secret.Code,
			"templateId": "sms_otp_login_acceptance",
			"platform":   request.Platform,
			"requestRef": request.RequestRef,
		},
	})
	if err != nil {
		return err
	}
	httpRequest, err := http.NewRequest(
		http.MethodPost,
		runtime.captureBridge.server.URL+"/v1/provider/sms/send",
		bytes.NewReader(body),
	)
	if err != nil {
		return err
	}
	httpRequest.Header.Set("Authorization", "Bearer "+runtime.captureBridge.providerToken)
	httpRequest.Header.Set("Content-Type", "application/json")
	httpRequest.Header.Set("Idempotency-Key", request.IdempotencyKey)
	httpRequest.Header.Set("X-QWQ-Request-ID", request.RequestID)
	response, err := http.DefaultClient.Do(httpRequest)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	raw, _ := io.ReadAll(response.Body)
	if response.StatusCode != http.StatusAccepted {
		return fmt.Errorf("local capture provider status %d: %s", response.StatusCode, string(raw))
	}
	return nil
}

func (runtime *externalInteractionContractRuntime) handleExternalInteractionRequest(
	writer http.ResponseWriter,
	request *http.Request,
) {
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
		!strings.HasPrefix(payload.PayloadRef, "otp_challenge:") ||
		len(payload.PayloadDigest) != 64 ||
		payload.Sensitivity != "secret" ||
		strings.TrimSpace(payload.ExpiresAt) == "" ||
		strings.TrimSpace(payload.Payload["challengeId"]) == "" ||
		strings.TrimSpace(payload.Payload["codeRef"]) == "" ||
		payload.Payload["phoneHash"] != payload.PayloadDigest ||
		strings.TrimSpace(payload.Payload["maskedRecipient"]) == "" ||
		payload.Payload["templateId"] != "sms_otp_login_acceptance" ||
		payload.Payload["platform"] != "acceptance" ||
		payload.Payload["requestRef"] != payload.RequestID {
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
		Platform:       "acceptance",
		RequestRef:     "otp_req_contract",
		IdempotencyKey: "otp:contract:202607140125",
		ExpiresAt:      expiresAt,
	})
	if err != nil {
		t.Fatalf("submit OTP through production integration client: %v", err)
	}
	if accepted.RequestID != "otp_req_contract" || accepted.Status != "accepted" {
		t.Fatalf("unexpected accepted response: %s", fmt.Sprintf("%+v", accepted))
	}
	code, err := externalInteractionRuntime.captureBridge.readOTP("+8618013813901")
	if err != nil {
		t.Fatalf("protected read after contract submit: %v", err)
	}
	if code != "123456" {
		t.Fatalf("protected read returned unexpected code")
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
