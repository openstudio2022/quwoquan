package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestGreeting_SendIdempotentReplay 验证 SendGreetingRequest 的命令回执语义：
// 同一 Idempotency-Key 的重试重放首次结果（同一 greeting id），而不是撞
// duplicate_pending 409；receipt 与 state、outbox 同事务提交。
func TestGreeting_SendIdempotentReplay(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "gri_req", "reqi")
	createTestProfile(t, "gri_tgt", "tgti")
	createTestPersonaFull(t, "", "gri_req", "sa_gri_req", "reqi", "default", true)
	createTestPersonaFull(t, "", "gri_tgt", "sa_gri_tgt", "tgti", "default", true)

	headers := authHeadersForPersona("gri_req", "sa_gri_req")
	body := `{"targetSubAccountId":"sa_gri_tgt","requestMessage":"hello","source":"profile"}`

	first := doGreetingRequestWithKey(t, body, headers, "greeting-retry-key-1")
	if first.Code != http.StatusCreated {
		t.Fatalf("first send: expected 201, got %d: %s", first.Code, first.Body.String())
	}
	firstBody := parseJSON(t, first)
	firstID, _ := firstBody["id"].(string)
	if firstID == "" {
		t.Fatalf("expected greeting id, got %#v", firstBody)
	}

	replay := doGreetingRequestWithKey(t, body, headers, "greeting-retry-key-1")
	if replay.Code != http.StatusCreated {
		t.Fatalf("replayed send: expected 201, got %d: %s", replay.Code, replay.Body.String())
	}
	replayBody := parseJSON(t, replay)
	if replayBody["id"] != firstID {
		t.Fatalf("replay must return the original greeting: first=%s replay=%#v", firstID, replayBody)
	}

	var pendingCount int
	if err := pgPool.QueryRow(context.Background(), `
		SELECT COUNT(*) FROM greeting_requests
		WHERE requester_sub_account_id = 'sa_gri_req' AND status = 'pending'`,
	).Scan(&pendingCount); err != nil {
		t.Fatalf("count pending: %v", err)
	}
	if pendingCount != 1 {
		t.Fatalf("replay must not create a second pending greeting, got %d", pendingCount)
	}
	var outboxCount int
	if err := pgPool.QueryRow(context.Background(), `
		SELECT COUNT(*) FROM greeting_request_outbox WHERE aggregate_id = $1`, firstID,
	).Scan(&outboxCount); err != nil {
		t.Fatalf("count outbox: %v", err)
	}
	if outboxCount != 1 {
		t.Fatalf("replay must not append outbox events, got %d", outboxCount)
	}
}

// doGreetingRequestWithKey 与 doRequest 相同，但固定 Idempotency-Key
// （doRequest 每次自动生成新 key，无法表达重试语义）。
func doGreetingRequestWithKey(
	t *testing.T,
	body string,
	headers map[string]string,
	idempotencyKey string,
) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/user/greeting-request", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", idempotencyKey)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	return rec
}
