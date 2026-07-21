package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

var idempotencySeq atomic.Int64

// withTrustedPrincipal 模拟 auth middleware：把测试头 X-Test-Persona 解析为
// 可信 Principal 注入 context，替代不可信的客户端身份 header。生产 main.go
// 由真实 JWT 验签中间件承担同一职责。
func withTrustedPrincipal(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if persona := strings.TrimSpace(r.Header.Get("X-Test-Persona")); persona != "" {
			principal := rtauth.Principal{
				Actor: operation.ActorContext{AccountID: persona, PersonaID: persona},
			}
			r = r.WithContext(rtauth.WithPrincipal(r.Context(), principal))
		}
		next.ServeHTTP(w, r)
	})
}

func testRequestHeaders(userID string) map[string]string {
	return map[string]string{
		"Content-Type":    "application/json",
		"X-Test-Persona":  userID,
		"Idempotency-Key": userID + "-" + strconvInt(idempotencySeq.Add(1)),
	}
}

func strconvInt(v int64) string {
	const digits = "0123456789"
	if v == 0 {
		return "0"
	}
	var buf [20]byte
	i := len(buf)
	for v > 0 {
		i--
		buf[i] = digits[v%10]
		v /= 10
	}
	return string(buf[i:])
}

func doPost(t *testing.T, path, payload, userID string, expectedStatus int) map[string]any {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(payload))
	for k, v := range testRequestHeaders(userID) {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != expectedStatus {
		t.Fatalf("doPost %s: expected %d, got %d: %s", path, expectedStatus, rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("doPost %s: decode response: %v\nbody: %s", path, err, rec.Body.String())
	}
	return result
}

func doPostAny(t *testing.T, path, payload, userID string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(payload))
	for k, v := range testRequestHeaders(userID) {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

// doPostWithKey 用固定 Idempotency-Key 提交，用于验证重放幂等。
func doPostWithKey(t *testing.T, path, payload, userID, key string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Test-Persona", userID)
	req.Header.Set("Idempotency-Key", key)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

func doGet(t *testing.T, path, userID string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	req.Header.Set("X-Test-Persona", userID)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

var _ = context.Background

func createTestCall(t *testing.T, userID string) map[string]any {
	t.Helper()
	payload := `{"callType":"audio","inviteeIds":["user_invitee_001"]}`
	return doPost(t, "/rtc/calls", payload, userID, http.StatusCreated)
}

func extractSessionID(t *testing.T, resp map[string]any) string {
	t.Helper()
	session, ok := resp["session"].(map[string]any)
	if !ok {
		t.Fatal("response missing session object")
	}
	id, ok := session["callId"].(string)
	if !ok {
		t.Fatal("session missing callId")
	}
	return id
}

func extractSession(t *testing.T, resp map[string]any) map[string]any {
	t.Helper()
	session, ok := resp["session"].(map[string]any)
	if !ok {
		t.Fatal("response missing session object")
	}
	return session
}

func extractMediaAccess(t *testing.T, resp map[string]any) map[string]any {
	t.Helper()
	if _, legacy := resp["token"]; legacy {
		t.Fatal("response must not expose legacy token field")
	}
	if _, legacy := resp["livekitUrl"]; legacy {
		t.Fatal("response must not expose vendor-specific livekitUrl field")
	}
	mediaAccess, ok := resp["mediaAccess"].(map[string]any)
	if !ok {
		t.Fatal("response missing mediaAccess object")
	}
	if accessToken, _ := mediaAccess["accessToken"].(string); accessToken == "" {
		t.Fatal("mediaAccess missing accessToken")
	}
	if _, leaksEndpoint := mediaAccess["connectionUrl"]; leaksEndpoint {
		t.Fatal("mediaAccess must not expose media connection endpoint")
	}
	return mediaAccess
}
