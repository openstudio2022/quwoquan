package api_integration

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	authchallengegenerated "quwoquan_service/services/user-service/generated/account/authentication_challenge"
	useraccountgenerated "quwoquan_service/services/user-service/generated/account/user_account"
)

// localCaptureBridge mirrors the sms-provider-substitute capture/readback
// contract inside user-service api_integration so SendOtp → capture →
// protected read → LoginWithPhone can be proven without a live gamma stack.
type localCaptureBridge struct {
	server        *httptest.Server
	providerToken string
	operatorToken string
	environment   string
	aead          cipher.AEAD
	mu            sync.Mutex
	captures      map[string]bridgeCapture
	failNext      bool
}

type bridgeCapture struct {
	requestID  string
	ciphertext []byte
	expiresAt  time.Time
}

var (
	bridgeRecipientPattern = regexp.MustCompile(`^\+[1-9][0-9]{7,14}$`)
	bridgeCodePattern      = regexp.MustCompile(`^[0-9]{6}$`)
)

func startLocalCaptureBridge() (*localCaptureBridge, error) {
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	bridge := &localCaptureBridge{
		providerToken: "test-sms-provider-token",
		operatorToken: "test-sms-operator-token",
		environment:   "beta",
		aead:          aead,
		captures:      map[string]bridgeCapture{},
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/provider/sms/send", bridge.handleProviderSend)
	mux.HandleFunc("/v1/debug/sms/otp/latest", bridge.handleProtectedRead)
	bridge.server = httptest.NewServer(mux)
	return bridge, nil
}

func (bridge *localCaptureBridge) Close() {
	if bridge != nil && bridge.server != nil {
		bridge.server.Close()
	}
}

func (bridge *localCaptureBridge) ForceNextProviderFailure() {
	bridge.mu.Lock()
	defer bridge.mu.Unlock()
	bridge.failNext = true
}

func (bridge *localCaptureBridge) recipientDigest(recipient string) string {
	sum := sha256.Sum256([]byte(recipient))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func (bridge *localCaptureBridge) handleProviderSend(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost ||
		!bridge.authorized(request, bridge.providerToken) {
		writeCaptureBridgeError(
			writer,
			request,
			useraccountgenerated.AppErrorFromUnauthorized("capture bridge provider authorization rejected"),
		)
		return
	}
	var payload struct {
		RequestID      string            `json:"requestId"`
		Operation      string            `json:"operation"`
		Environment    string            `json:"env"`
		IdempotencyKey string            `json:"idempotencyKey"`
		ExpiresAt      string            `json:"expiresAt"`
		Payload        map[string]string `json:"payload"`
	}
	if err := json.NewDecoder(request.Body).Decode(&payload); err != nil ||
		payload.Operation != "sms_otp.send" ||
		payload.Environment != bridge.environment ||
		strings.TrimSpace(payload.RequestID) == "" ||
		strings.TrimSpace(payload.IdempotencyKey) == "" ||
		!bridgeRecipientPattern.MatchString(strings.TrimSpace(payload.Payload["recipient"])) ||
		!bridgeCodePattern.MatchString(strings.TrimSpace(payload.Payload["code"])) ||
		strings.TrimSpace(payload.Payload["templateId"]) == "" {
		writeCaptureBridgeError(
			writer,
			request,
			useraccountgenerated.AppErrorFromInvalidArgument("capture bridge provider payload is invalid"),
		)
		return
	}
	expiresAt, err := time.Parse(time.RFC3339, payload.ExpiresAt)
	if err != nil || !expiresAt.After(time.Now().UTC()) {
		writeCaptureBridgeError(
			writer,
			request,
			authchallengegenerated.AppErrorFromOtpExpired("capture bridge challenge is expired"),
		)
		return
	}
	bridge.mu.Lock()
	failNext := bridge.failNext
	bridge.failNext = false
	bridge.mu.Unlock()
	if failNext {
		writeCaptureBridgeError(
			writer,
			request,
			authchallengegenerated.AppErrorFromOtpProviderFailed("capture bridge provider failure was injected"),
		)
		return
	}
	digest := bridge.recipientDigest(payload.Payload["recipient"])
	ciphertext, err := bridge.seal(payload.RequestID, digest, payload.Payload["code"])
	if err != nil {
		writeCaptureBridgeError(
			writer,
			request,
			useraccountgenerated.AppErrorFromInternalError("capture bridge failed to seal otp"),
		)
		return
	}
	bridge.mu.Lock()
	bridge.captures[digest] = bridgeCapture{
		requestID:  payload.RequestID,
		ciphertext: ciphertext,
		expiresAt:  expiresAt,
	}
	bridge.mu.Unlock()
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(writer).Encode(map[string]string{
		"requestId":         payload.RequestID,
		"providerRequestID": "smsdbg_" + payload.RequestID,
		"status":            "accepted",
	})
}

func (bridge *localCaptureBridge) handleProtectedRead(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost ||
		!bridge.authorized(request, bridge.operatorToken) {
		writeCaptureBridgeError(
			writer,
			request,
			useraccountgenerated.AppErrorFromUnauthorized("capture bridge operator authorization rejected"),
		)
		return
	}
	var payload struct {
		Environment     string `json:"environment"`
		RecipientDigest string `json:"recipientDigest"`
	}
	if err := json.NewDecoder(request.Body).Decode(&payload); err != nil ||
		payload.Environment != bridge.environment ||
		!strings.HasPrefix(payload.RecipientDigest, "sha256:") {
		writeCaptureBridgeError(
			writer,
			request,
			useraccountgenerated.AppErrorFromInvalidArgument("capture bridge read request is invalid"),
		)
		return
	}
	bridge.mu.Lock()
	captured, ok := bridge.captures[payload.RecipientDigest]
	if ok {
		delete(bridge.captures, payload.RecipientDigest)
	}
	bridge.mu.Unlock()
	if !ok || !captured.expiresAt.After(time.Now().UTC()) {
		writeCaptureBridgeError(
			writer,
			request,
			useraccountgenerated.AppErrorFromUserNotFound("capture bridge otp was not found"),
		)
		return
	}
	code, err := bridge.open(captured.requestID, payload.RecipientDigest, captured.ciphertext)
	if err != nil {
		writeCaptureBridgeError(
			writer,
			request,
			authchallengegenerated.AppErrorFromOtpExpired("capture bridge otp is unavailable"),
		)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(map[string]string{
		"requestId": captured.requestID,
		"code":      code,
		"expiresAt": captured.expiresAt.UTC().Format(time.RFC3339),
	})
}

func writeCaptureBridgeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

func (bridge *localCaptureBridge) readOTP(recipient string) (string, error) {
	body, err := json.Marshal(map[string]string{
		"environment":     bridge.environment,
		"recipientDigest": bridge.recipientDigest(recipient),
	})
	if err != nil {
		return "", err
	}
	request, err := http.NewRequest(
		http.MethodPost,
		bridge.server.URL+"/v1/debug/sms/otp/latest",
		strings.NewReader(string(body)),
	)
	if err != nil {
		return "", err
	}
	request.Header.Set("Authorization", "Bearer "+bridge.operatorToken)
	request.Header.Set("Content-Type", "application/json")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(response.Body)
	if err != nil {
		return "", err
	}
	if response.StatusCode != http.StatusOK {
		return "", errHTTPStatus{status: response.StatusCode, body: string(raw)}
	}
	var payload struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return "", err
	}
	if !bridgeCodePattern.MatchString(payload.Code) {
		return "", errHTTPStatus{status: response.StatusCode, body: "invalid otp payload"}
	}
	return payload.Code, nil
}

func (bridge *localCaptureBridge) authorized(request *http.Request, token string) bool {
	got := strings.TrimPrefix(request.Header.Get("Authorization"), "Bearer ")
	return subtle.ConstantTimeCompare([]byte(got), []byte(token)) == 1
}

func (bridge *localCaptureBridge) seal(requestID, digest, code string) ([]byte, error) {
	nonce := make([]byte, bridge.aead.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}
	sealed := bridge.aead.Seal(nil, nonce, []byte(code), []byte(requestID+"\x00"+digest))
	return append(nonce, sealed...), nil
}

func (bridge *localCaptureBridge) open(requestID, digest string, ciphertext []byte) (string, error) {
	if len(ciphertext) <= bridge.aead.NonceSize() {
		return "", errHTTPStatus{status: http.StatusGone, body: "invalid ciphertext"}
	}
	nonce := ciphertext[:bridge.aead.NonceSize()]
	plain, err := bridge.aead.Open(
		nil,
		nonce,
		ciphertext[bridge.aead.NonceSize():],
		[]byte(requestID+"\x00"+digest),
	)
	if err != nil {
		return "", err
	}
	return string(plain), nil
}

type errHTTPStatus struct {
	status int
	body   string
}

func (err errHTTPStatus) Error() string {
	return err.body
}
