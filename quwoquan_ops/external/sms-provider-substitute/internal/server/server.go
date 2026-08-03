package server

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	AdapterID       = "ext.sms.local_capture"
	OperationSMSOTP = "sms_otp.send"
	maxRequestBytes = 64 << 10
)

var (
	recipientPattern = regexp.MustCompile(`^\+[1-9][0-9]{7,14}$`)
	codePattern      = regexp.MustCompile(`^[0-9]{6}$`)
	digestPattern    = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
)

type Config struct {
	Environment         string
	ConfigurationDigest string
	ProviderToken       string
	OperatorToken       string
	CaptureKey          []byte
	DefaultScene        string
	TimeoutDelay        time.Duration
	Now                 func() time.Time
}

type Server struct {
	environment         string
	configurationDigest string
	providerToken       string
	operatorToken       string
	aead                cipher.AEAD
	defaultScene        string
	timeoutDelay        time.Duration
	now                 func() time.Time

	mu           sync.Mutex
	captures     map[string]capture
	idempotency  map[string]idempotencyRecord
	attempts     atomic.Uint64
	accepted     atomic.Uint64
	rejected     atomic.Uint64
	latencyNanos atomic.Uint64
	latencyCount atomic.Uint64
}

type capture struct {
	RequestID  string
	Ciphertext []byte
	ExpiresAt  time.Time
}

type idempotencyRecord struct {
	Digest            [32]byte
	ProviderRequestID string
	ExpiresAt         time.Time
}

type providerRequest struct {
	RequestID      string            `json:"requestId"`
	Operation      string            `json:"operation"`
	Environment    string            `json:"env"`
	IdempotencyKey string            `json:"idempotencyKey"`
	ExpiresAt      string            `json:"expiresAt"`
	Payload        map[string]string `json:"payload"`
}

type otpReadRequest struct {
	Environment     string `json:"environment"`
	RecipientDigest string `json:"recipientDigest"`
}

func New(cfg Config) (*Server, error) {
	environment := strings.TrimSpace(cfg.Environment)
	if environment != "alpha" && environment != "beta" && environment != "gamma" {
		return nil, fmt.Errorf("debug SMS substitute requires alpha|beta|gamma, got %q", environment)
	}
	configurationDigest := strings.TrimSpace(cfg.ConfigurationDigest)
	if !digestPattern.MatchString(configurationDigest) {
		return nil, errors.New("canonical runtime configuration digest is required")
	}
	if strings.TrimSpace(cfg.ProviderToken) == "" || strings.TrimSpace(cfg.OperatorToken) == "" {
		return nil, errors.New("provider and operator tokens are required")
	}
	if subtle.ConstantTimeCompare([]byte(cfg.ProviderToken), []byte(cfg.OperatorToken)) == 1 {
		return nil, errors.New("provider and operator tokens must be distinct")
	}
	block, err := aes.NewCipher(cfg.CaptureKey)
	if err != nil {
		return nil, fmt.Errorf("capture key: %w", err)
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("capture cipher: %w", err)
	}
	scene := strings.TrimSpace(cfg.DefaultScene)
	if scene == "" {
		scene = "success"
	}
	if !validScene(scene) {
		return nil, fmt.Errorf("unsupported default scene %q", scene)
	}
	delay := cfg.TimeoutDelay
	if delay <= 0 {
		delay = 15 * time.Second
	}
	now := cfg.Now
	if now == nil {
		now = time.Now
	}
	return &Server{
		environment:         environment,
		configurationDigest: configurationDigest,
		providerToken:       cfg.ProviderToken,
		operatorToken:       cfg.OperatorToken,
		aead:                aead,
		defaultScene:        scene,
		timeoutDelay:        delay,
		now:                 now,
		captures:            map[string]capture{},
		idempotency:         map[string]idempotencyRecord{},
	}, nil
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.health)
	mux.HandleFunc("GET /metrics", s.metrics)
	mux.HandleFunc("POST /v1/provider/sms/send", s.send)
	mux.HandleFunc("POST /v1/debug/sms/otp/latest", s.readOTP)
	return securityHeaders(mux)
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status":              "ready",
		"adapterId":           AdapterID,
		"environment":         s.environment,
		"configurationDigest": s.configurationDigest,
		"profile":             s.defaultScene,
		"nonPromotable":       true,
	})
}

func (s *Server) metrics(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	labels := fmt.Sprintf("environment=%q,adapter=%q", s.environment, AdapterID)
	fmt.Fprintf(w, "qwq_sms_substitute_attempt_total{%s} %d\n", labels, s.attempts.Load())
	fmt.Fprintf(w, "qwq_sms_substitute_receipt_total{%s,status=%q} %d\n", labels, "accepted", s.accepted.Load())
	fmt.Fprintf(w, "qwq_sms_substitute_receipt_total{%s,status=%q} %d\n", labels, "rejected", s.rejected.Load())
	fmt.Fprintf(w, "qwq_sms_substitute_latency_seconds_sum{%s} %.9f\n", labels, float64(s.latencyNanos.Load())/float64(time.Second))
	fmt.Fprintf(w, "qwq_sms_substitute_latency_seconds_count{%s} %d\n", labels, s.latencyCount.Load())
}

func (s *Server) send(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	defer func() {
		s.latencyNanos.Add(uint64(time.Since(started)))
		s.latencyCount.Add(1)
	}()
	s.attempts.Add(1)
	if !authorized(r, s.providerToken) {
		s.rejected.Add(1)
		writeError(w, http.StatusUnauthorized, false, "unauthorized")
		return
	}
	var request providerRequest
	raw, err := decodeJSON(r, &request)
	if err != nil {
		s.rejected.Add(1)
		writeError(w, http.StatusBadRequest, false, "invalid_request")
		return
	}
	if err := s.validateProviderRequest(r, request); err != nil {
		s.rejected.Add(1)
		writeError(w, http.StatusBadRequest, false, "invalid_request")
		return
	}
	scene := strings.TrimSpace(r.Header.Get("X-QWQ-Debug-Scenario"))
	if scene == "" {
		scene = s.defaultScene
	}
	if !validScene(scene) {
		s.rejected.Add(1)
		writeError(w, http.StatusBadRequest, false, "invalid_scenario")
		return
	}
	switch scene {
	case "rate_limit":
		s.rejected.Add(1)
		writeError(w, http.StatusTooManyRequests, true, "rate_limited")
		return
	case "failure":
		s.rejected.Add(1)
		writeError(w, http.StatusBadGateway, false, "provider_failed")
		return
	case "timeout":
		timer := time.NewTimer(s.timeoutDelay)
		defer timer.Stop()
		select {
		case <-r.Context().Done():
			return
		case <-timer.C:
			s.rejected.Add(1)
			writeError(w, http.StatusGatewayTimeout, true, "provider_timeout")
			return
		}
	}

	digest := sha256.Sum256(raw)
	providerRequestID := "smsdbg_" + hex.EncodeToString(digest[:8])
	s.mu.Lock()
	s.purgeExpiredLocked()
	if existing, ok := s.idempotency[request.IdempotencyKey]; ok {
		if existing.Digest != digest {
			s.mu.Unlock()
			s.rejected.Add(1)
			writeError(w, http.StatusConflict, false, "idempotency_conflict")
			return
		}
		providerRequestID = existing.ProviderRequestID
		s.mu.Unlock()
		s.accepted.Add(1)
		writeReceipt(w, request.RequestID, providerRequestID)
		return
	}
	expiresAt, _ := time.Parse(time.RFC3339, request.ExpiresAt)
	recipientDigest := RecipientDigest(request.Payload["recipient"])
	ciphertext, err := s.seal(request.RequestID, recipientDigest, request.Payload["code"])
	if err != nil {
		s.mu.Unlock()
		s.rejected.Add(1)
		writeError(w, http.StatusInternalServerError, true, "capture_failed")
		return
	}
	s.captures[recipientDigest] = capture{
		RequestID: request.RequestID, Ciphertext: ciphertext, ExpiresAt: expiresAt,
	}
	s.idempotency[request.IdempotencyKey] = idempotencyRecord{
		Digest: digest, ProviderRequestID: providerRequestID, ExpiresAt: expiresAt,
	}
	s.mu.Unlock()
	s.accepted.Add(1)
	writeReceipt(w, request.RequestID, providerRequestID)
}

func (s *Server) readOTP(w http.ResponseWriter, r *http.Request) {
	if !authorized(r, s.operatorToken) {
		writeError(w, http.StatusUnauthorized, false, "unauthorized")
		return
	}
	var request otpReadRequest
	if _, err := decodeJSON(r, &request); err != nil ||
		request.Environment != s.environment || !digestPattern.MatchString(request.RecipientDigest) {
		writeError(w, http.StatusBadRequest, false, "invalid_request")
		return
	}
	s.mu.Lock()
	s.purgeExpiredLocked()
	captured, ok := s.captures[request.RecipientDigest]
	if ok {
		delete(s.captures, request.RecipientDigest)
	}
	s.mu.Unlock()
	if !ok {
		writeError(w, http.StatusNotFound, false, "otp_not_found")
		return
	}
	code, err := s.open(captured.RequestID, request.RecipientDigest, captured.Ciphertext)
	if err != nil {
		writeError(w, http.StatusGone, false, "otp_unavailable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"requestId": captured.RequestID,
		"code":      code,
		"expiresAt": captured.ExpiresAt.UTC().Format(time.RFC3339),
	})
}

func (s *Server) validateProviderRequest(r *http.Request, request providerRequest) error {
	if strings.TrimSpace(request.RequestID) == "" || request.Operation != OperationSMSOTP ||
		request.Environment != s.environment || strings.TrimSpace(request.IdempotencyKey) == "" ||
		request.IdempotencyKey != strings.TrimSpace(r.Header.Get("Idempotency-Key")) ||
		request.RequestID != strings.TrimSpace(r.Header.Get("X-QWQ-Request-ID")) {
		return errors.New("request identity mismatch")
	}
	expiresAt, err := time.Parse(time.RFC3339, request.ExpiresAt)
	if err != nil || !expiresAt.After(s.now().UTC()) {
		return errors.New("challenge is expired")
	}
	if !recipientPattern.MatchString(strings.TrimSpace(request.Payload["recipient"])) ||
		!codePattern.MatchString(strings.TrimSpace(request.Payload["code"])) ||
		strings.TrimSpace(request.Payload["templateId"]) == "" {
		return errors.New("invalid SMS payload")
	}
	return nil
}

func (s *Server) seal(requestID, digest, code string) ([]byte, error) {
	nonce := make([]byte, s.aead.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}
	sealed := s.aead.Seal(nil, nonce, []byte(code), []byte(requestID+"\x00"+digest))
	return append(nonce, sealed...), nil
}

func (s *Server) open(requestID, digest string, ciphertext []byte) (string, error) {
	if len(ciphertext) <= s.aead.NonceSize() {
		return "", errors.New("invalid ciphertext")
	}
	nonce, sealed := ciphertext[:s.aead.NonceSize()], ciphertext[s.aead.NonceSize():]
	plain, err := s.aead.Open(nil, nonce, sealed, []byte(requestID+"\x00"+digest))
	if err != nil {
		return "", err
	}
	return string(plain), nil
}

func (s *Server) purgeExpiredLocked() {
	now := s.now().UTC()
	for digest, captured := range s.captures {
		if !captured.ExpiresAt.After(now) {
			delete(s.captures, digest)
		}
	}
	for key, record := range s.idempotency {
		if !record.ExpiresAt.After(now) {
			delete(s.idempotency, key)
		}
	}
}

func RecipientDigest(recipient string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(recipient)))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func authorized(r *http.Request, expected string) bool {
	provided := strings.TrimPrefix(strings.TrimSpace(r.Header.Get("Authorization")), "Bearer ")
	return len(provided) == len(expected) && subtle.ConstantTimeCompare([]byte(provided), []byte(expected)) == 1
}

func decodeJSON(r *http.Request, target any) ([]byte, error) {
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxRequestBytes+1))
	if err != nil {
		return nil, err
	}
	if len(raw) > maxRequestBytes {
		return nil, errors.New("request body exceeds limit")
	}
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return nil, err
	}
	if decoder.Decode(&struct{}{}) != io.EOF {
		return nil, errors.New("multiple JSON values")
	}
	return raw, nil
}

func validScene(scene string) bool {
	return scene == "success" || scene == "rate_limit" || scene == "failure" || scene == "timeout"
}

func writeReceipt(w http.ResponseWriter, requestID, providerRequestID string) {
	writeJSON(w, http.StatusAccepted, map[string]string{
		"requestId": requestID, "providerRequestId": providerRequestID, "status": "queued",
	})
}

func writeError(w http.ResponseWriter, status int, retryable bool, code string) {
	writeJSON(w, status, map[string]any{"status": "failed", "retryable": retryable, "error": code})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		next.ServeHTTP(w, r)
	})
}
