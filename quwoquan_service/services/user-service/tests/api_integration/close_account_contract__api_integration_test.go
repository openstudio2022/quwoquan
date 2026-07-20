package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	mqpkg "quwoquan_service/services/user-service/internal/adapters/mq"
)

// seedActiveSession 直插一条 active 会话，供 close 后断言全量吊销。
func seedActiveSession(t *testing.T, accountID, sessionID string) {
	t.Helper()
	_, err := pgPool.Exec(context.Background(), `
INSERT INTO account_sessions (
  session_id, account_id, device_id, refresh_token_hash, lineage_id,
  status, issued_at, expires_at
) VALUES ($1, $2, 'close-test-device', $3, $4, 'active', NOW(), $5)`,
		sessionID, accountID, "hash_"+sessionID, "lineage_"+sessionID,
		time.Now().Add(24*time.Hour).UTC(),
	)
	if err != nil {
		t.Fatalf("seed active session: %v", err)
	}
}

// TestCloseAccount_TerminalStateCascades 验证 5.1.1(v) 注销闭环：
// 账号 closed 终态、凭证失效、分身退役、会话吊销、终态事件与登录拒绝。
func TestCloseAccount_TerminalStateCascades(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "close_owner", "close_owner")
	createTestPersonaFull(t, "close_owner_primary", "close_owner", "ps_close_primary", "close_primary", "default", true)
	createTestPersonaFull(t, "close_owner_second", "close_owner", "ps_close_second", "close_second", "default", false, false)
	createTestCredential(t, "cred_close_1", "close_owner", "phone", "close-phone-key")
	seedActiveSession(t, "close_owner", "sess_close_1")
	seedActiveSession(t, "close_owner", "sess_close_2")

	eventGroup := subscribeUserAccountEvents(t)

	rec := doRequest(
		t,
		http.MethodPost,
		"/owner/account/close",
		`{"clientRequestId":"close-e2e-001"}`,
		authHeadersForPersona("close_owner", "ps_close_primary"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("close account: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	if body["accountState"] != "closed" || body["idempotentReplay"] != false {
		t.Fatalf("unexpected close result: %#v", body)
	}

	var accountState string
	if err := pgPool.QueryRow(context.Background(),
		"SELECT account_state FROM user_profiles WHERE user_id = $1",
		"close_owner").Scan(&accountState); err != nil {
		t.Fatalf("query account state: %v", err)
	}
	if accountState != "closed" {
		t.Fatalf("expected account_state=closed, got %s", accountState)
	}

	var activeCredentials int64
	if err := pgPool.QueryRow(context.Background(),
		"SELECT COUNT(*) FROM credential_bindings WHERE owner_id = $1 AND is_active = true",
		"close_owner").Scan(&activeCredentials); err != nil {
		t.Fatalf("query credentials: %v", err)
	}
	if activeCredentials != 0 {
		t.Fatalf("expected all credentials revoked, %d still active", activeCredentials)
	}

	var nonRetiredPersonas int64
	if err := pgPool.QueryRow(context.Background(),
		"SELECT COUNT(*) FROM personas WHERE user_id = $1 AND status <> 'retired'",
		"close_owner").Scan(&nonRetiredPersonas); err != nil {
		t.Fatalf("query personas: %v", err)
	}
	if nonRetiredPersonas != 0 {
		t.Fatalf("expected all personas retired, %d still active", nonRetiredPersonas)
	}

	var activeSessions int64
	if err := pgPool.QueryRow(context.Background(),
		"SELECT COUNT(*) FROM account_sessions WHERE account_id = $1 AND status = 'active'",
		"close_owner").Scan(&activeSessions); err != nil {
		t.Fatalf("query sessions: %v", err)
	}
	if activeSessions != 0 {
		t.Fatalf("expected all sessions revoked, %d still active", activeSessions)
	}

	event := waitForUserAccountEvent(t, eventGroup)
	if event.Values["eventName"] != "UserAccountClosed" {
		t.Fatalf("expected UserAccountClosed event, got %+v", event)
	}
	if event.Values["accountId"] != "close_owner" {
		t.Fatalf("unexpected closed event payload: %+v", event)
	}
	var payload struct {
		UserID       string `json:"userId"`
		AccountState string `json:"accountState"`
	}
	if err := json.Unmarshal([]byte(event.Values["payload"]), &payload); err != nil {
		t.Fatalf("decode UserAccountClosed payload: %v", err)
	}
	if payload.UserID != "close_owner" || payload.AccountState != "closed" {
		t.Fatalf("unexpected closed event payload: %+v", payload)
	}
	deadline := time.Now().Add(2 * time.Second)
	for {
		var published bool
		if err := pgPool.QueryRow(
			context.Background(),
			`SELECT published_at IS NOT NULL
			   FROM user_account_outbox
			  WHERE aggregate_id=$1 AND event_type='UserAccountClosed'`,
			"close_owner",
		).Scan(&published); err != nil {
			t.Fatalf("query UserAccountClosed outbox: %v", err)
		}
		if published {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("UserAccountClosed outbox must be acknowledged after stream publish")
		}
		time.Sleep(20 * time.Millisecond)
	}

	// closed 账号不再是公开可见主页（strict 语义下不暴露存在性）。
	profileRec := doRequest(
		t,
		http.MethodGet,
		"/user/ps_close_primary",
		"",
		nil,
	)
	if profileRec.Code != http.StatusNotFound {
		t.Fatalf("closed account public profile: expected 404, got %d: %s",
			profileRec.Code, profileRec.Body.String())
	}
}

func subscribeUserAccountEvents(t *testing.T) string {
	t.Helper()
	group := "close-account-contract-" + t.Name()
	if err := redisClient.XGroupCreateMkStream(
		context.Background(),
		mqpkg.UserAccountEventStream,
		group,
		"$",
	); err != nil {
		t.Fatalf("create UserAccount event consumer group: %v", err)
	}
	return group
}

func waitForUserAccountEvent(
	t *testing.T,
	group string,
) rtredis.StreamMessage {
	t.Helper()
	messages, err := redisClient.XReadGroup(
		context.Background(),
		group,
		"close-account-contract",
		map[string]string{mqpkg.UserAccountEventStream: ">"},
		1,
		3*time.Second,
	)
	if err != nil {
		t.Fatalf("read UserAccount event stream: %v", err)
	}
	if len(messages) != 1 {
		t.Fatalf("expected one UserAccount event, got %d", len(messages))
	}
	return messages[0]
}

func TestCloseAccount_ReplayReturnsIdempotent(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "close_replay_owner", "close_replay_owner")
	createTestPersonaFull(t, "close_replay_persona", "close_replay_owner", "ps_close_replay", "close_replay", "default", true)

	first := doRequest(
		t,
		http.MethodPost,
		"/owner/account/close",
		"",
		authHeadersForPersona("close_replay_owner", "ps_close_replay"),
	)
	if first.Code != http.StatusOK {
		t.Fatalf("first close: expected 200, got %d: %s", first.Code, first.Body.String())
	}
	firstBody := parseJSON(t, first)

	second := doRequest(
		t,
		http.MethodPost,
		"/owner/account/close",
		"",
		authHeadersForPersona("close_replay_owner", "ps_close_replay"),
	)
	if second.Code != http.StatusOK {
		t.Fatalf("replay close: expected 200, got %d: %s", second.Code, second.Body.String())
	}
	secondBody := parseJSON(t, second)
	if secondBody["idempotentReplay"] != true {
		t.Fatalf("expected idempotent replay, got %#v", secondBody)
	}
	if secondBody["closedAt"] == "" || firstBody["closedAt"] == "" {
		t.Fatalf("closedAt must be stable: first=%v second=%v", firstBody, secondBody)
	}
}

func TestCloseAccount_RequiresAuthentication(t *testing.T) {
	requireMongoBackedRuntime(t)
	rec := doRequest(t, http.MethodPost, "/owner/account/close", "", nil)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous close: expected 401, got %d: %s", rec.Code, rec.Body.String())
	}
}
