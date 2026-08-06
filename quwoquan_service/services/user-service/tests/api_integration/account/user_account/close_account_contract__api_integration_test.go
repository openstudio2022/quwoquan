// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
// readiness_case: close-account-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	mqpkg "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/mq"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
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
	accessHeaders := authHeadersForPersona("close_owner", "ps_close_primary")

	rec := doRequest(
		t,
		http.MethodPost,
		"/owner/account/close",
		`{"clientRequestId":"close-e2e-001"}`,
		accessHeaders,
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("close account: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	if body["accountState"] != "closed" || body["idempotentReplay"] != false {
		t.Fatalf("unexpected close result: %#v", body)
	}

	var (
		accountState string
		authEpoch    int64
	)
	if err := pgPool.QueryRow(context.Background(),
		"SELECT account_state, auth_epoch FROM user_profiles WHERE user_id = $1",
		"close_owner").Scan(&accountState, &authEpoch); err != nil {
		t.Fatalf("query account state: %v", err)
	}
	if accountState != "closed" {
		t.Fatalf("expected account_state=closed, got %s", accountState)
	}
	if authEpoch != 2 {
		t.Fatalf("close must advance auth_epoch in the terminal transaction, got %d", authEpoch)
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
	if event.Values["accountVersion"] != "2" {
		t.Fatalf("unexpected closed event accountVersion: %+v", event)
	}
	if _, err := time.Parse(time.RFC3339Nano, event.Values["occurredAt"]); err != nil {
		t.Fatalf("invalid closed event occurredAt: %q: %v", event.Values["occurredAt"], err)
	}
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		UpdatedAt    string   `json:"updatedAt"`
	}
	if err := json.Unmarshal([]byte(event.Values["payload"]), &payload); err != nil {
		t.Fatalf("decode UserAccountClosed payload: %v", err)
	}
	if payload.UserID != "close_owner" ||
		len(payload.PersonaIDs) != 2 ||
		payload.PersonaIDs[0] != "ps_close_primary" ||
		payload.PersonaIDs[1] != "ps_close_second" ||
		payload.AccountState != "closed" {
		t.Fatalf("unexpected closed event payload: %+v", payload)
	}
	if _, err := time.Parse(time.RFC3339Nano, payload.UpdatedAt); err != nil {
		t.Fatalf("invalid closed payload updatedAt: %q: %v", payload.UpdatedAt, err)
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

	// CloseAccount 的事务提交必须立即使提交前的 access JWT 失效；不能等待 JWT
	// 自然过期或仅依赖 refresh token 吊销。
	previousAccessRec := doRequest(
		t,
		http.MethodGet,
		"/me",
		"",
		accessHeaders,
	)
	if previousAccessRec.Code != http.StatusGone {
		t.Fatalf(
			"closed account access JWT must be rejected immediately: expected 410, got %d: %s",
			previousAccessRec.Code,
			previousAccessRec.Body.String(),
		)
	}
	if response := parseJSON(t, previousAccessRec); response["code"] != "USER.AUTH.account_deleted" {
		t.Fatalf("closed account access JWT error drift: %#v", response)
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
	var authEpoch int64
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT auth_epoch FROM user_profiles WHERE user_id=$1`,
		"close_replay_owner",
	).Scan(&authEpoch); err != nil {
		t.Fatalf("query replay auth epoch: %v", err)
	}
	if authEpoch != 2 {
		t.Fatalf("idempotent close replay must not advance auth_epoch again, got %d", authEpoch)
	}
}

func TestCloseAccount_ReleasesCredentialForNewAccountWithoutHistoryRecovery(
	t *testing.T,
) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	const phone = "+8618013813988"

	firstCode := requestOtpCode(t, phone)
	firstLogin := doRequest(
		t,
		http.MethodPost,
		"/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+firstCode+`","deviceId":"close-release-first","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if firstLogin.Code != http.StatusOK {
		t.Fatalf(
			"first phone login: expected 200, got %d: %s",
			firstLogin.Code,
			firstLogin.Body.String(),
		)
	}
	firstBody := parseJSON(t, firstLogin)
	firstOwnerID, _ := firstBody["ownerId"].(string)
	firstAccessToken, _ := firstBody["accessToken"].(string)
	if firstOwnerID == "" || firstAccessToken == "" {
		t.Fatalf("first phone login must issue owner and access token: %#v", firstBody)
	}

	closeResponse := doRequest(
		t,
		http.MethodPost,
		"/owner/account/close",
		"",
		map[string]string{"Authorization": "Bearer " + firstAccessToken},
	)
	if closeResponse.Code != http.StatusOK {
		t.Fatalf(
			"close first account: expected 200, got %d: %s",
			closeResponse.Code,
			closeResponse.Body.String(),
		)
	}

	secondCode := requestOtpCode(t, phone)
	secondLogin := doRequest(
		t,
		http.MethodPost,
		"/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+secondCode+`","deviceId":"close-release-second","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if secondLogin.Code != http.StatusOK {
		t.Fatalf(
			"credential must register a new account after close: expected 200, got %d: %s",
			secondLogin.Code,
			secondLogin.Body.String(),
		)
	}
	secondBody := parseJSON(t, secondLogin)
	secondOwnerID, _ := secondBody["ownerId"].(string)
	if secondOwnerID == "" || secondOwnerID == firstOwnerID {
		t.Fatalf(
			"credential reuse must create a new account, first=%q second=%q",
			firstOwnerID,
			secondOwnerID,
		)
	}
	var historicalSessionCount int64
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM account_sessions WHERE account_id=$1`,
		secondOwnerID,
	).Scan(&historicalSessionCount); err != nil {
		t.Fatalf("query new account sessions: %v", err)
	}
	if historicalSessionCount != 1 {
		t.Fatalf(
			"new account must contain only its newly issued session, got %d",
			historicalSessionCount,
		)
	}
}

func TestCloseAccount_OutboxFailureRollsBackEntireTerminalTransition(
	t *testing.T,
) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	const (
		accountID = "close_rollback_owner"
		personaID = "ps_close_rollback"
	)
	createTestProfile(t, accountID, "close_rollback_owner")
	createTestPersonaFull(
		t,
		"close_rollback_persona",
		accountID,
		personaID,
		"close_rollback",
		"default",
		true,
	)
	createTestCredential(
		t,
		"cred_close_rollback",
		accountID,
		"phone",
		"close-rollback-phone",
	)
	seedActiveSession(t, accountID, "sess_close_rollback")

	if _, err := pgPool.Exec(context.Background(), `
CREATE FUNCTION reject_user_account_close_outbox()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'forced UserAccountClosed outbox failure';
END;
$$;
CREATE TRIGGER reject_user_account_close_outbox_trigger
BEFORE INSERT ON user_account_outbox
FOR EACH ROW EXECUTE FUNCTION reject_user_account_close_outbox();`); err != nil {
		t.Fatalf("install forced UserAccountClosed outbox failure: %v", err)
	}
	t.Cleanup(func() {
		if _, err := pgPool.Exec(context.Background(), `
DROP TRIGGER IF EXISTS reject_user_account_close_outbox_trigger ON user_account_outbox;
DROP FUNCTION IF EXISTS reject_user_account_close_outbox();`); err != nil {
			t.Errorf("remove forced UserAccountClosed outbox failure: %v", err)
		}
	})

	accessHeaders := authHeadersForPersona(accountID, personaID)
	response := doRequest(
		t,
		http.MethodPost,
		"/owner/account/close",
		"",
		accessHeaders,
	)
	if response.Code != http.StatusInternalServerError {
		t.Fatalf(
			"outbox failure must reject close atomically: expected 500, got %d: %s",
			response.Code,
			response.Body.String(),
		)
	}

	var (
		accountState      string
		authEpoch         int64
		activeCredentials int64
		activeSessions    int64
		closeOutboxCount  int64
	)
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT account_state, auth_epoch FROM user_profiles WHERE user_id=$1`,
		accountID,
	).Scan(&accountState, &authEpoch); err != nil {
		t.Fatalf("query rollback account state: %v", err)
	}
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM credential_bindings WHERE owner_id=$1 AND is_active=true`,
		accountID,
	).Scan(&activeCredentials); err != nil {
		t.Fatalf("query rollback credential state: %v", err)
	}
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM account_sessions WHERE account_id=$1 AND status='active'`,
		accountID,
	).Scan(&activeSessions); err != nil {
		t.Fatalf("query rollback session state: %v", err)
	}
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM user_account_outbox WHERE aggregate_id=$1`,
		accountID,
	).Scan(&closeOutboxCount); err != nil {
		t.Fatalf("query rollback outbox state: %v", err)
	}
	if accountState != "active" || authEpoch != 1 ||
		activeCredentials != 1 || activeSessions != 1 ||
		closeOutboxCount != 0 {
		t.Fatalf(
			"close transaction left partial state: account=%q authEpoch=%d credentials=%d sessions=%d outbox=%d",
			accountState,
			authEpoch,
			activeCredentials,
			activeSessions,
			closeOutboxCount,
		)
	}
	if stillActive := doRequest(t, http.MethodGet, "/me", "", accessHeaders); stillActive.Code != http.StatusOK {
		t.Fatalf(
			"failed close must keep existing access credential valid: got %d: %s",
			stillActive.Code,
			stillActive.Body.String(),
		)
	}
}

func TestUserAccountOutboxTerminalFailureIsSanitizedOrderedAndReplayable(
	t *testing.T,
) {
	cleanAll(t)
	t.Cleanup(func() { cleanAll(t) })
	ctx := context.Background()
	store, err := useraccountpersistence.NewUserAccountOutboxStore(pgPool)
	if err != nil {
		t.Fatalf("construct UserAccount outbox store: %v", err)
	}

	const accountID = "outbox-terminal-account"
	firstEventID := strings.Repeat("a", 64)
	secondEventID := strings.Repeat("b", 64)
	payload := `{"userId":"outbox-terminal-account","email":"secret@example.com"}`
	// Keep these records beyond the wall clock so the TestMain relay cannot
	// race this store-level lease/order contract.
	firstOccurredAt := time.Now().UTC().Add(24 * time.Hour)
	secondOccurredAt := firstOccurredAt.Add(time.Second)
	if _, err := pgPool.Exec(ctx, `
INSERT INTO user_account_outbox(
  event_id,
  aggregate_id,
  aggregate_version,
  event_type,
  payload_json,
  occurred_at,
  next_attempt_at
) VALUES
  ($1, $2, 1, 'UserSuspended', $3::jsonb, $4, $4),
  ($5, $2, 2, 'UserRestored', $3::jsonb, $6, $6)`,
		firstEventID,
		accountID,
		payload,
		firstOccurredAt,
		secondEventID,
		secondOccurredAt,
	); err != nil {
		t.Fatalf("seed ordered UserAccount outbox: %v", err)
	}

	claimedAt := secondOccurredAt.Add(time.Second)
	claimed, found, err := store.ClaimPendingOutbox(
		ctx,
		"terminal-relay",
		claimedAt,
		30*time.Second,
	)
	if err != nil || !found || claimed.EventID != firstEventID {
		t.Fatalf("claim earliest outbox event: found=%v event=%+v err=%v", found, claimed, err)
	}
	failure := accountports.UserAccountOutboxFailure{
		Code:   "stream_publish",
		Digest: strings.Repeat("c", 64),
	}
	if err := store.MarkTerminalFailure(
		ctx,
		claimed.EventID,
		"terminal-relay",
		claimedAt,
		claimedAt.Add(30*24*time.Hour),
		accountports.UserAccountOutboxFailure{
			Code: accountports.UserAccountOutboxFailureCode(
				"email=secret@example.com",
			),
			Digest: strings.Repeat("c", 64),
		},
	); err == nil {
		t.Fatal("terminal failure must reject a non-canonical failure code")
	}
	if err := store.MarkTerminalFailure(
		ctx,
		claimed.EventID,
		"terminal-relay",
		claimedAt,
		claimedAt.Add(30*24*time.Hour),
		failure,
	); err != nil {
		t.Fatalf("mark terminal failure: %v", err)
	}

	terminalFailures, err := store.ListTerminalFailures(ctx, claimedAt, 10)
	if err != nil {
		t.Fatalf("list terminal failures: %v", err)
	}
	if len(terminalFailures) != 1 {
		t.Fatalf("terminal failures=%d, want 1", len(terminalFailures))
	}
	terminal := terminalFailures[0]
	if terminal.EventID != firstEventID ||
		terminal.EventType != "UserSuspended" ||
		terminal.Failure != failure ||
		terminal.DeliveryAttempt != 1 {
		t.Fatalf("unexpected terminal record: %+v", terminal)
	}
	serializedTerminal, err := json.Marshal(terminal)
	if err != nil {
		t.Fatalf("marshal terminal record: %v", err)
	}
	if strings.Contains(string(serializedTerminal), accountID) ||
		strings.Contains(string(serializedTerminal), "secret@example.com") {
		t.Fatalf("terminal record leaked source payload")
	}

	var forbiddenDLQColumns int
	if err := pgPool.QueryRow(ctx, `
SELECT COUNT(*)
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'user_account_outbox_dead_letters'
  AND column_name IN ('aggregate_id', 'payload_json', 'last_error')`).Scan(&forbiddenDLQColumns); err != nil {
		t.Fatalf("inspect terminal DLQ columns: %v", err)
	}
	if forbiddenDLQColumns != 0 {
		t.Fatalf("terminal DLQ must not persist source identity or payload columns: %d", forbiddenDLQColumns)
	}
	var rawFailureColumns int
	if err := pgPool.QueryRow(ctx, `
SELECT COUNT(*)
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'user_account_outbox'
  AND column_name = 'last_error'`).Scan(&rawFailureColumns); err != nil {
		t.Fatalf("inspect outbox failure columns: %v", err)
	}
	if rawFailureColumns != 0 {
		t.Fatal("raw UserAccount outbox last_error column must be removed")
	}

	if blocked, found, err := store.ClaimPendingOutbox(
		ctx,
		"blocked-relay",
		claimedAt.Add(time.Second),
		30*time.Second,
	); err != nil || found {
		t.Fatalf("terminal event must block later same-account delivery: found=%v event=%+v err=%v", found, blocked, err)
	}
	if err := store.ReplayTerminalFailure(
		ctx,
		firstEventID,
		claimedAt.Add(2*time.Second),
	); err != nil {
		t.Fatalf("replay terminal failure: %v", err)
	}
	replayed, found, err := store.ClaimPendingOutbox(
		ctx,
		"replay-relay",
		claimedAt.Add(2*time.Second),
		30*time.Second,
	)
	if err != nil || !found || replayed.EventID != firstEventID {
		t.Fatalf("replay must restore earliest event first: found=%v event=%+v err=%v", found, replayed, err)
	}
	if err := store.MarkPublished(
		ctx,
		replayed.EventID,
		"replay-relay",
		claimedAt.Add(2*time.Second),
	); err != nil {
		t.Fatalf("ack replayed event after durable publish: %v", err)
	}
	later, found, err := store.ClaimPendingOutbox(
		ctx,
		"replay-relay",
		claimedAt.Add(3*time.Second),
		30*time.Second,
	)
	if err != nil || !found || later.EventID != secondEventID {
		t.Fatalf("later event must follow replayed predecessor: found=%v event=%+v err=%v", found, later, err)
	}
	if err := store.MarkPublished(
		ctx,
		later.EventID,
		"replay-relay",
		claimedAt.Add(3*time.Second),
	); err != nil {
		t.Fatalf("ack later durable event: %v", err)
	}

	expiredEventID := strings.Repeat("d", 64)
	expiredOccurredAt := claimedAt.Add(4 * time.Second)
	if _, err := pgPool.Exec(ctx, `
INSERT INTO user_account_outbox(
  event_id,
  aggregate_id,
  aggregate_version,
  event_type,
  payload_json,
  occurred_at,
  next_attempt_at
) VALUES ($1, 'outbox-terminal-retention', 1, 'UserAccountClosed', $2::jsonb, $3, $3)`,
		expiredEventID,
		payload,
		expiredOccurredAt,
	); err != nil {
		t.Fatalf("seed expiry outbox event: %v", err)
	}
	expired, found, err := store.ClaimPendingOutbox(
		ctx,
		"expiry-relay",
		expiredOccurredAt,
		30*time.Second,
	)
	if err != nil || !found || expired.EventID != expiredEventID {
		t.Fatalf("claim expiry event: found=%v event=%+v err=%v", found, expired, err)
	}
	expiresAt := expiredOccurredAt.Add(time.Second)
	if err := store.MarkTerminalFailure(
		ctx,
		expired.EventID,
		"expiry-relay",
		expiredOccurredAt,
		expiresAt,
		failure,
	); err != nil {
		t.Fatalf("mark expiring terminal failure: %v", err)
	}
	pruned, err := store.PruneExpiredTerminalFailures(
		ctx,
		expiresAt.Add(time.Second),
	)
	if err != nil || pruned != 1 {
		t.Fatalf("prune terminal retention: pruned=%d err=%v", pruned, err)
	}
	if remaining, err := store.ListTerminalFailures(
		ctx,
		expiresAt.Add(time.Second),
		10,
	); err != nil || len(remaining) != 0 {
		t.Fatalf("expired DLQ record must not remain queryable: records=%d err=%v", len(remaining), err)
	}
	if err := store.ReplayTerminalFailure(
		ctx,
		expiredEventID,
		expiresAt.Add(time.Second),
	); err != nil {
		t.Fatalf("terminal source must remain replayable after diagnostic TTL: %v", err)
	}
	replayedExpired, found, err := store.ClaimPendingOutbox(
		ctx,
		"expiry-replay-relay",
		expiresAt.Add(time.Second),
		30*time.Second,
	)
	if err != nil || !found || replayedExpired.EventID != expiredEventID {
		t.Fatalf("claim replayed expiry event: found=%v event=%+v err=%v", found, replayedExpired, err)
	}
	if err := store.MarkPublished(
		ctx,
		replayedExpired.EventID,
		"expiry-replay-relay",
		expiresAt.Add(time.Second),
	); err != nil {
		t.Fatalf("ack replayed expiry event: %v", err)
	}
}

func TestCloseAccount_RequiresAuthentication(t *testing.T) {
	requireMongoBackedRuntime(t)
	rec := doRequest(t, http.MethodPost, "/owner/account/close", "", nil)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous close: expected 401, got %d: %s", rec.Code, rec.Body.String())
	}
}
