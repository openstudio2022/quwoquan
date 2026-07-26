package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
)

func TestAccountSessionPacketHashRotationReplayAndOutbox(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const phone = "+8618013813991"
	code := requestOtpCode(t, phone)
	login := doRequest(
		t,
		http.MethodPost,
		"/auth/login/phone",
		`{"phone":"`+phone+`","otpCode":"`+code+`","deviceId":"session-device","platform":"ios","appVersion":"1.0.0","agreementVersion":"2026-06","privacyVersion":"2026-06"}`,
		nil,
	)
	if login.Code != http.StatusOK {
		t.Fatalf("login: status=%d body=%s", login.Code, login.Body.String())
	}
	loginBody := parseJSON(t, login)
	ownerID, _ := loginBody["ownerId"].(string)
	firstToken, _ := loginBody["refreshToken"].(string)
	if ownerID == "" || firstToken == "" {
		t.Fatalf("login result missing session identity: %#v", loginBody)
	}

	ctx := context.Background()
	var (
		lineageID string
		deviceID  string
		hash      string
	)
	if err := pgPool.QueryRow(ctx, `
SELECT lineage_id, device_id, refresh_token_hash
FROM account_sessions
WHERE account_id=$1 AND status='active'`, ownerID).Scan(
		&lineageID, &deviceID, &hash,
	); err != nil {
		t.Fatalf("read issued session: %v", err)
	}
	if deviceID != "session-device" || hash == "" || hash == firstToken {
		t.Fatalf(
			"session must bind device and persist only hash: device=%q hash=%q",
			deviceID,
			hash,
		)
	}
	var authenticatedPayload []byte
	if err := pgPool.QueryRow(ctx, `
SELECT payload_json
FROM account_sessions_outbox
WHERE event_type='AccountSessionAuthenticated' AND aggregate_id IN (
  SELECT session_id FROM account_sessions WHERE account_id=$1
)`, ownerID).Scan(&authenticatedPayload); err != nil {
		t.Fatalf("read authenticated outbox: %v", err)
	}
	var event map[string]any
	if err := json.Unmarshal(authenticatedPayload, &event); err != nil {
		t.Fatalf("decode authenticated payload: %v", err)
	}
	for _, key := range []string{
		"authenticationSubject",
		"identityOrigin",
		"deviceId",
		"issuedAt",
	} {
		if event[key] == nil || event[key] == "" {
			t.Fatalf("authenticated event missing %s: %#v", key, event)
		}
	}

	refresh := doRequest(
		t,
		http.MethodPost,
		"/auth/token/refresh",
		`{"refreshToken":"`+firstToken+`"}`,
		nil,
	)
	if refresh.Code != http.StatusOK {
		t.Fatalf("refresh: status=%d body=%s", refresh.Code, refresh.Body.String())
	}
	secondToken, _ := parseJSON(t, refresh)["refreshToken"].(string)
	if secondToken == "" || secondToken == firstToken {
		t.Fatal("refresh must rotate token")
	}

	replay := doRequest(
		t,
		http.MethodPost,
		"/auth/token/refresh",
		`{"refreshToken":"`+firstToken+`"}`,
		nil,
	)
	if replay.Code == http.StatusOK {
		t.Fatalf("rotated token replay must revoke lineage: %s", replay.Body.String())
	}
	var activeCount int
	if err := pgPool.QueryRow(ctx, `
SELECT COUNT(*) FROM account_sessions
WHERE lineage_id=$1 AND status='active'`, lineageID).Scan(&activeCount); err != nil {
		t.Fatalf("count active lineage sessions: %v", err)
	}
	if activeCount != 0 {
		t.Fatalf("replay must revoke entire lineage, active=%d", activeCount)
	}
	var revokedCount int
	if err := pgPool.QueryRow(ctx, `
SELECT COUNT(*) FROM account_sessions_outbox
WHERE event_type='AccountSessionRevoked'
  AND aggregate_id=$1`, lineageID).Scan(&revokedCount); err != nil {
		t.Fatalf("count revoked outbox: %v", err)
	}
	if revokedCount != 1 {
		t.Fatalf("lineage replay must append one revoke fact, got %d", revokedCount)
	}

	// 已吊销 token 的 logout 是幂等 no-op。
	headers := authHeaders(ownerID)
	for attempt := 0; attempt < 2; attempt++ {
		logout := doRequest(
			t,
			http.MethodPost,
			"/auth/logout",
			`{"refreshToken":"`+secondToken+`","deviceId":"session-device"}`,
			headers,
		)
		if logout.Code != http.StatusOK {
			t.Fatalf(
				"logout attempt %d: status=%d body=%s",
				attempt+1,
				logout.Code,
				logout.Body.String(),
			)
		}
	}
}
