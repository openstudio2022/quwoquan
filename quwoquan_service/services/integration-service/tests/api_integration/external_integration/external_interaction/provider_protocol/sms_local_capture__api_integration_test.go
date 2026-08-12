//go:build provider_conformance

// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
package provider_protocol

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
)

const (
	localCaptureProviderName = "local_capture_sms"
	localCaptureTemplateID   = "sms_otp_login_acceptance"
)

type memoryReferenceStore struct {
	mu    sync.Mutex
	items map[string]otpseal.StoredReference
}

func (s *memoryReferenceStore) Put(_ context.Context, reference otpseal.StoredReference) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.items == nil {
		s.items = map[string]otpseal.StoredReference{}
	}
	s.items[reference.RequestID+":"+reference.ChallengeID] = reference
	return nil
}

func (s *memoryReferenceStore) Get(
	_ context.Context,
	requestID string,
	challengeID string,
) (otpseal.StoredReference, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	reference, ok := s.items[requestID+":"+challengeID]
	if !ok {
		return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
	}
	return reference, nil
}

func (s *memoryReferenceStore) Delete(
	_ context.Context,
	requestID string,
	challengeID string,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.items, requestID+":"+challengeID)
	return nil
}

type scenarioTransport struct {
	base     http.RoundTripper
	scenario string
}

func (t scenarioTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	clone := request.Clone(request.Context())
	clone.Header = request.Header.Clone()
	clone.Header.Set("X-QWQ-Debug-Scenario", t.scenario)
	return t.base.RoundTrip(clone)
}

type protocolHarness struct {
	environment   string
	endpoint      string
	providerToken string
	operatorToken string
	configDigest  string
	providerPath  string
	readPath      string
	transport     *http.Transport
	sealer        *otpseal.Sealer
	references    *memoryReferenceStore
	secretValues  []string
}

func TestSMSLocalCaptureAdapterAgainstManagedProtocol(t *testing.T) {
	harness := newProtocolHarness(t)
	harness.assertReadiness(t)
	harness.assertSuccessAndOneTimeRead(t)
	harness.assertIdempotencyAndConflict(t)
	harness.assertAuthenticationAndValidation(t)
	harness.assertThrottleRetryFailureAndTimeout(t)
	harness.assertNetworkFailure(t)
	harness.assertExpiredRequestRejected(t)
	harness.assertRedactedMetrics(t)
}

func newProtocolHarness(t *testing.T) *protocolHarness {
	t.Helper()
	environment := requiredEnvironment(t, "QWQ_SMS_LOCAL_CAPTURE_ENVIRONMENT")
	if environment != "alpha" && environment != "beta" && environment != "gamma" {
		t.Fatal("local-capture protocol environment is not non-production")
	}
	endpoint := requiredEnvironment(t, "QWQ_SMS_LOCAL_CAPTURE_ENDPOINT")
	providerPath := requiredProtocolPath(t, "QWQ_SMS_LOCAL_CAPTURE_PROVIDER_PATH")
	readPath := requiredProtocolPath(
		t,
		"QWQ_SMS_LOCAL_CAPTURE_PROTECTED_READ_PATH",
	)
	parsed, err := url.Parse(endpoint)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() != "localhost" ||
		parsed.Path != providerPath {
		t.Fatal("local-capture protocol endpoint identity is invalid")
	}
	caPath := requiredEnvironment(t, "QWQ_SMS_LOCAL_CAPTURE_CA_FILE")
	caPEM, err := os.ReadFile(filepath.Clean(caPath))
	if err != nil {
		t.Fatal("local-capture protocol CA is unreadable")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caPEM) {
		t.Fatal("local-capture protocol CA is invalid")
	}
	transport := &http.Transport{
		TLSClientConfig: &tls.Config{
			MinVersion: tls.VersionTLS13,
			RootCAs:    roots,
			ServerName: "localhost",
		},
	}
	t.Cleanup(transport.CloseIdleConnections)
	sealingKey := make([]byte, 32)
	if _, err := rand.Read(sealingKey); err != nil {
		t.Fatal("generate test-only OTP sealing key")
	}
	sealer, err := otpseal.NewFromBase64("test-k1", map[string]string{
		"test-k1": base64.StdEncoding.EncodeToString(sealingKey),
	})
	if err != nil {
		t.Fatal("construct test-only OTP sealer")
	}
	return &protocolHarness{
		environment:   environment,
		endpoint:      endpoint,
		providerToken: requiredEnvironment(t, "QWQ_SMS_LOCAL_CAPTURE_PROVIDER_TOKEN"),
		operatorToken: requiredEnvironment(t, "QWQ_SMS_LOCAL_CAPTURE_OPERATOR_TOKEN"),
		configDigest:  requiredEnvironment(t, "QWQ_SMS_LOCAL_CAPTURE_CONFIG_DIGEST"),
		providerPath:  providerPath,
		readPath:      readPath,
		transport:     transport,
		sealer:        sealer,
		references:    &memoryReferenceStore{},
	}
}

func requiredEnvironment(t *testing.T, name string) string {
	t.Helper()
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		t.Fatalf("required conformance input %s is missing", name)
	}
	return value
}

func requiredProtocolPath(t *testing.T, name string) string {
	t.Helper()
	value := requiredEnvironment(t, name)
	if !strings.HasPrefix(value, "/") || strings.Contains(value, "//") ||
		strings.Contains(value, "..") || strings.ContainsAny(value, "?#") {
		t.Fatalf("required conformance protocol path %s is invalid", name)
	}
	return value
}

func (h *protocolHarness) assertReadiness(t *testing.T) {
	t.Helper()
	response := h.perform(t, http.MethodGet, "/healthz", "", nil, nil)
	defer response.Body.Close()
	var payload struct {
		Status              string `json:"status"`
		AdapterID           string `json:"adapterId"`
		Environment         string `json:"environment"`
		ConfigurationDigest string `json:"configurationDigest"`
		NonPromotable       bool   `json:"nonPromotable"`
	}
	if response.StatusCode != http.StatusOK || json.NewDecoder(response.Body).Decode(&payload) != nil {
		t.Fatal("local-capture readiness response is invalid")
	}
	if payload.Status != "ready" || payload.AdapterID != "ext.sms.local_capture" ||
		payload.Environment != h.environment || payload.ConfigurationDigest != h.configDigest ||
		!payload.NonPromotable {
		t.Fatal("local-capture readiness identity mismatch")
	}
}

func (h *protocolHarness) assertSuccessAndOneTimeRead(t *testing.T) {
	t.Helper()
	requestID := "sms-conformance-success"
	challengeID := "challenge-conformance-success"
	recipient := "+8610000000001"
	code := randomOTP(t)
	expiresAt := time.Now().UTC().Add(2 * time.Minute).Truncate(time.Second)
	h.putReference(t, requestID, challengeID, recipient, code, expiresAt)
	result, err := h.provider(t, h.providerToken, "", 2*time.Second).Send(
		context.Background(),
		h.request(requestID, challengeID, expiresAt),
		reliabletask.ReliableAsyncTask{TaskID: "task-conformance-success"},
	)
	if err != nil || result.Status != reliabletask.ExternalInteractionStatusSentUnconfirmed ||
		result.Provider != localCaptureProviderName || result.ProviderRequestID == "" {
		t.Fatal("local-capture Adapter success result is invalid")
	}

	unauthorized := h.readOTP(t, recipient, h.environment, "wrong-operator-token")
	unauthorized.Body.Close()
	if unauthorized.StatusCode != http.StatusUnauthorized {
		t.Fatal("local-capture protected read accepted the wrong principal")
	}
	wrongEnvironment := "alpha"
	if wrongEnvironment == h.environment {
		wrongEnvironment = "beta"
	}
	wrong := h.readOTP(t, recipient, wrongEnvironment, h.operatorToken)
	wrong.Body.Close()
	if wrong.StatusCode != http.StatusBadRequest {
		t.Fatal("local-capture cross-environment read was not rejected")
	}
	read := h.readOTP(t, recipient, h.environment, h.operatorToken)
	defer read.Body.Close()
	var payload struct {
		RequestID string `json:"requestId"`
		Code      string `json:"code"`
		ExpiresAt string `json:"expiresAt"`
	}
	if read.StatusCode != http.StatusOK || json.NewDecoder(read.Body).Decode(&payload) != nil ||
		payload.RequestID != requestID || payload.Code != code || payload.ExpiresAt == "" {
		t.Fatal("protected local-capture readback mismatch")
	}
	second := h.readOTP(t, recipient, h.environment, h.operatorToken)
	second.Body.Close()
	if second.StatusCode != http.StatusNotFound {
		t.Fatal("protected local-capture OTP was not one-time")
	}
}

func (h *protocolHarness) assertIdempotencyAndConflict(t *testing.T) {
	t.Helper()
	requestID := "sms-conformance-idempotency"
	challengeID := "challenge-conformance-idempotency"
	recipient := "+8610000000002"
	code := randomOTP(t)
	expiresAt := time.Now().UTC().Add(2 * time.Minute).Truncate(time.Second)
	request := h.request(requestID, challengeID, expiresAt)
	providerClient := h.provider(t, h.providerToken, "", 2*time.Second)
	h.putReference(t, requestID, challengeID, recipient, code, expiresAt)
	first, err := providerClient.Send(
		context.Background(), request,
		reliabletask.ReliableAsyncTask{TaskID: "task-idempotency-first"},
	)
	if err != nil {
		t.Fatal("local-capture idempotency first send failed")
	}
	h.putReference(t, requestID, challengeID, recipient, code, expiresAt)
	second, err := providerClient.Send(
		context.Background(), request,
		reliabletask.ReliableAsyncTask{TaskID: "task-idempotency-second"},
	)
	if err != nil || first.ProviderRequestID == "" ||
		second.ProviderRequestID != first.ProviderRequestID {
		t.Fatal("local-capture idempotent replay changed its receipt")
	}
	h.putReference(t, requestID, challengeID, recipient, randomOTP(t), expiresAt)
	result, err := providerClient.Send(
		context.Background(), request,
		reliabletask.ReliableAsyncTask{TaskID: "task-idempotency-conflict"},
	)
	assertProviderFailure(
		t,
		result,
		err,
		"INTEGRATION.MIDDLEWARE.sms_provider_rejected",
		http.StatusConflict,
		false,
	)
}

func (h *protocolHarness) assertAuthenticationAndValidation(t *testing.T) {
	t.Helper()
	expiresAt := time.Now().UTC().Add(2 * time.Minute).Truncate(time.Second)
	requestID := "sms-conformance-auth"
	challengeID := "challenge-conformance-auth"
	h.putReference(t, requestID, challengeID, "+8610000000003", randomOTP(t), expiresAt)
	result, err := h.provider(t, "wrong-provider-token", "", time.Second).Send(
		context.Background(),
		h.request(requestID, challengeID, expiresAt),
		reliabletask.ReliableAsyncTask{TaskID: "task-auth"},
	)
	assertProviderFailure(
		t,
		result,
		err,
		"INTEGRATION.MIDDLEWARE.sms_provider_rejected",
		http.StatusUnauthorized,
		false,
	)

	requestID = "sms-conformance-validation"
	challengeID = "challenge-conformance-validation"
	h.putReference(t, requestID, challengeID, "18000000000", randomOTP(t), expiresAt)
	result, err = h.provider(t, h.providerToken, "", time.Second).Send(
		context.Background(),
		h.request(requestID, challengeID, expiresAt),
		reliabletask.ReliableAsyncTask{TaskID: "task-validation"},
	)
	assertProviderFailure(
		t,
		result,
		err,
		"INTEGRATION.MIDDLEWARE.sms_provider_rejected",
		http.StatusBadRequest,
		false,
	)
}

func (h *protocolHarness) assertThrottleRetryFailureAndTimeout(t *testing.T) {
	t.Helper()
	expiresAt := time.Now().UTC().Add(2 * time.Minute).Truncate(time.Second)
	requestID := "sms-conformance-throttle"
	challengeID := "challenge-conformance-throttle"
	recipient := "+8610000000004"
	h.putReference(t, requestID, challengeID, recipient, randomOTP(t), expiresAt)
	request := h.request(requestID, challengeID, expiresAt)
	result, err := h.provider(t, h.providerToken, "rate_limit", time.Second).Send(
		context.Background(), request,
		reliabletask.ReliableAsyncTask{TaskID: "task-throttle"},
	)
	assertProviderFailure(
		t,
		result,
		err,
		"INTEGRATION.MIDDLEWARE.sms_provider_rejected",
		http.StatusTooManyRequests,
		true,
	)
	// The Adapter only deletes the sealed reference after an accepted receipt;
	// the same typed request can therefore recover after a retryable throttle.
	result, err = h.provider(t, h.providerToken, "", time.Second).Send(
		context.Background(), request,
		reliabletask.ReliableAsyncTask{TaskID: "task-throttle-retry"},
	)
	if err != nil || result.Status != reliabletask.ExternalInteractionStatusSentUnconfirmed {
		t.Fatal("local-capture retry did not recover after throttle")
	}

	requestID = "sms-conformance-failure"
	challengeID = "challenge-conformance-failure"
	h.putReference(t, requestID, challengeID, "+8610000000005", randomOTP(t), expiresAt)
	result, err = h.provider(t, h.providerToken, "failure", time.Second).Send(
		context.Background(),
		h.request(requestID, challengeID, expiresAt),
		reliabletask.ReliableAsyncTask{TaskID: "task-failure"},
	)
	assertProviderFailure(
		t,
		result,
		err,
		"INTEGRATION.MIDDLEWARE.sms_provider_rejected",
		http.StatusBadGateway,
		false,
	)

	requestID = "sms-conformance-timeout"
	challengeID = "challenge-conformance-timeout"
	h.putReference(t, requestID, challengeID, "+8610000000006", randomOTP(t), expiresAt)
	result, err = h.provider(t, h.providerToken, "timeout", 40*time.Millisecond).Send(
		context.Background(),
		h.request(requestID, challengeID, expiresAt),
		reliabletask.ReliableAsyncTask{TaskID: "task-timeout"},
	)
	assertProviderFailure(
		t,
		result,
		err,
		"INTEGRATION.MIDDLEWARE.sms_provider_timeout",
		0,
		true,
	)
}

func (h *protocolHarness) assertNetworkFailure(t *testing.T) {
	t.Helper()
	expiresAt := time.Now().UTC().Add(2 * time.Minute).Truncate(time.Second)
	requestID := "sms-conformance-network"
	challengeID := "challenge-conformance-network"
	h.putReference(t, requestID, challengeID, "+8610000000007", randomOTP(t), expiresAt)
	providerClient, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:              localCaptureProviderName,
			Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:          "https://127.0.0.1:1" + h.providerPath,
			BearerToken:       h.providerToken,
			Timeout:           100 * time.Millisecond,
			OTPCodeSealer:     h.sealer,
			OTPCodeReferences: h.references,
		},
		&http.Client{Transport: h.transport},
	)
	if err != nil {
		t.Fatal("construct local-capture network failure Adapter")
	}
	result, err := providerClient.Send(
		context.Background(),
		h.request(requestID, challengeID, expiresAt),
		reliabletask.ReliableAsyncTask{TaskID: "task-network"},
	)
	assertProviderFailure(
		t,
		result,
		err,
		"INTEGRATION.MIDDLEWARE.sms_provider_rejected",
		0,
		true,
	)
}

func (h *protocolHarness) assertExpiredRequestRejected(t *testing.T) {
	t.Helper()
	requestID := "sms-conformance-expired"
	code := randomOTP(t)
	payload := map[string]any{
		"requestId":      requestID,
		"operation":      reliabletask.ExternalInteractionOperationSmsOTP,
		"tenant":         "quwoquan",
		"env":            h.environment,
		"idempotencyKey": requestID,
		"sensitivity":    "secret",
		"expiresAt":      time.Now().UTC().Add(-time.Second).Format(time.RFC3339),
		"payload": map[string]string{
			"recipient":  "+8610000000008",
			"code":       code,
			"templateId": localCaptureTemplateID,
			"platform":   "acceptance",
			"requestRef": requestID,
		},
	}
	response := h.perform(
		t,
		http.MethodPost,
		h.providerPath,
		h.providerToken,
		payload,
		map[string]string{
			"Idempotency-Key":  requestID,
			"X-QWQ-Request-ID": requestID,
		},
	)
	defer response.Body.Close()
	raw, _ := io.ReadAll(response.Body)
	if response.StatusCode != http.StatusBadRequest || bytes.Contains(raw, []byte(code)) {
		t.Fatal("expired local-capture request was accepted or leaked OTP")
	}
}

func (h *protocolHarness) assertRedactedMetrics(t *testing.T) {
	t.Helper()
	response := h.perform(t, http.MethodGet, "/metrics", "", nil, nil)
	defer response.Body.Close()
	raw, err := io.ReadAll(response.Body)
	if err != nil || response.StatusCode != http.StatusOK ||
		!bytes.Contains(raw, []byte(`adapter="ext.sms.local_capture"`)) {
		t.Fatal("local-capture metrics are unavailable")
	}
	for _, secretValue := range h.secretValues {
		if secretValue != "" && bytes.Contains(raw, []byte(secretValue)) {
			t.Fatal("local-capture metrics leaked protected input")
		}
	}
	if bytes.Contains(raw, []byte(h.providerToken)) ||
		bytes.Contains(raw, []byte(h.operatorToken)) {
		t.Fatal("local-capture metrics leaked credentials")
	}
}

func (h *protocolHarness) provider(
	t *testing.T,
	token string,
	scenario string,
	timeout time.Duration,
) *provider.HTTPExternalProvider {
	t.Helper()
	transport := http.RoundTripper(h.transport)
	if scenario != "" {
		transport = scenarioTransport{base: transport, scenario: scenario}
	}
	value, err := provider.NewHTTPExternalProvider(
		provider.HTTPExternalProviderConfig{
			Name:              localCaptureProviderName,
			Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
			Endpoint:          h.endpoint,
			BearerToken:       token,
			Timeout:           timeout,
			OTPCodeSealer:     h.sealer,
			OTPCodeReferences: h.references,
		},
		&http.Client{Transport: transport},
	)
	if err != nil {
		t.Fatal("construct local-capture HTTP Adapter")
	}
	return value
}

func (h *protocolHarness) request(
	requestID string,
	challengeID string,
	expiresAt time.Time,
) reliabletask.ExternalInteractionRequest {
	return reliabletask.ExternalInteractionRequest{
		RequestID:      requestID,
		Operation:      reliabletask.ExternalInteractionOperationSmsOTP,
		Tenant:         "quwoquan",
		Env:            h.environment,
		IdempotencyKey: requestID,
		Sensitivity:    "secret",
		ExpiresAt:      expiresAt,
		Payload: map[string]string{
			"challengeId": challengeID,
			"templateId":  localCaptureTemplateID,
			"platform":    "acceptance",
			"requestRef":  requestID,
		},
	}
}

func (h *protocolHarness) putReference(
	t *testing.T,
	requestID string,
	challengeID string,
	recipient string,
	code string,
	expiresAt time.Time,
) {
	t.Helper()
	codeRef, err := h.sealer.Seal(
		otpseal.Secret{Phone: recipient, Code: code},
		otpseal.Binding{
			RequestID:   requestID,
			ChallengeID: challengeID,
			ExpiresAt:   expiresAt,
		},
	)
	if err != nil {
		t.Fatal("seal conformance OTP reference")
	}
	if err := h.references.Put(context.Background(), otpseal.StoredReference{
		RequestID:   requestID,
		ChallengeID: challengeID,
		CodeRef:     codeRef,
		ExpiresAt:   expiresAt,
	}); err != nil {
		t.Fatal("store conformance OTP reference")
	}
	h.secretValues = append(h.secretValues, recipient, code)
}

func (h *protocolHarness) readOTP(
	t *testing.T,
	recipient string,
	environment string,
	token string,
) *http.Response {
	t.Helper()
	digest := sha256.Sum256([]byte(recipient))
	return h.perform(
		t,
		http.MethodPost,
		h.readPath,
		token,
		map[string]string{
			"environment":     environment,
			"recipientDigest": "sha256:" + hex.EncodeToString(digest[:]),
		},
		nil,
	)
}

func (h *protocolHarness) perform(
	t *testing.T,
	method string,
	path string,
	token string,
	payload any,
	headers map[string]string,
) *http.Response {
	t.Helper()
	var body io.Reader
	if payload != nil {
		raw, err := json.Marshal(payload)
		if err != nil {
			t.Fatal("encode local-capture protocol request")
		}
		body = bytes.NewReader(raw)
	}
	base, err := url.Parse(h.endpoint)
	if err != nil {
		t.Fatal("parse local-capture protocol endpoint")
	}
	base.Path = path
	request, err := http.NewRequestWithContext(
		context.Background(),
		method,
		base.String(),
		body,
	)
	if err != nil {
		t.Fatal("construct local-capture protocol request")
	}
	if token != "" {
		request.Header.Set("Authorization", "Bearer "+token)
	}
	if payload != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	for key, value := range headers {
		request.Header.Set(key, value)
	}
	response, err := (&http.Client{
		Transport: h.transport,
		Timeout:   2 * time.Second,
	}).Do(request)
	if err != nil {
		t.Fatal("call local-capture protocol endpoint")
	}
	return response
}

func randomOTP(t *testing.T) string {
	t.Helper()
	raw := make([]byte, 3)
	if _, err := rand.Read(raw); err != nil {
		t.Fatal("generate random conformance OTP")
	}
	value := int(raw[0])<<16 | int(raw[1])<<8 | int(raw[2])
	return fmt.Sprintf("%06d", value%1_000_000)
}

func assertProviderFailure(
	t *testing.T,
	result reliabletask.ExternalInteractionResult,
	err error,
	expectedCode string,
	expectedStatus int,
	expectedRetryable bool,
) {
	t.Helper()
	if err == nil {
		t.Fatal("local-capture Provider failure was reported as success")
	}
	var providerError *provider.ExternalProviderError
	if !errors.As(err, &providerError) {
		t.Fatal("local-capture Provider failure is not structured")
	}
	if providerError.Code != expectedCode ||
		providerError.StatusCode != expectedStatus ||
		providerError.Retryable != expectedRetryable ||
		result.Status != reliabletask.ExternalInteractionStatusFailed ||
		result.NormalizedError != expectedCode ||
		result.Retryable != expectedRetryable {
		t.Fatal("local-capture Provider failure normalization mismatch")
	}
}
