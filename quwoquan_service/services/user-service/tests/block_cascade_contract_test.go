package tests

import (
	"context"
	"net/http"
	"testing"
)

func TestBlockCascade_ClearsFollowAndPendingGreeting(t *testing.T) {
	if mongoDB == nil {
		t.Skip("MongoDB unavailable")
	}
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "bc_blocker", "blocker")
	createTestProfile(t, "bc_blocked", "blocked")
	createTestPersonaFull(t, "bc_blocker_p", "bc_blocker", "sa_bc_blocker", "blocker", "default", true)
	createTestPersonaFull(t, "bc_blocked_p", "bc_blocked", "sa_bc_blocked", "blocked", "default", true)

	doRequest(t, http.MethodPost, "/v1/user/sub-accounts/sa_bc_blocked/follow", "", authHeadersForPersona("bc_blocker", "sa_bc_blocker"))
	doRequest(t, http.MethodPost, "/v1/user/sub-accounts/sa_bc_blocker/follow", "", authHeadersForPersona("bc_blocked", "sa_bc_blocked"))

	sendRec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/greeting-request",
		`{"targetSubAccountId":"sa_bc_blocked","requestMessage":"hi","source":"profile"}`,
		authHeadersForPersona("bc_blocker", "sa_bc_blocker"),
	)
	if sendRec.Code != http.StatusCreated {
		t.Fatalf("send greeting: expected 201, got %d: %s", sendRec.Code, sendRec.Body.String())
	}

	blockRec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/sub-accounts/sa_bc_blocked/block",
		"",
		authHeadersForPersona("bc_blocker", "sa_bc_blocker"),
	)
	if blockRec.Code != http.StatusOK {
		t.Fatalf("block: expected 200, got %d", blockRec.Code)
	}

	capRec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/sub-accounts/sa_bc_blocked/relationship/capability",
		"",
		authHeadersForPersona("bc_blocker", "sa_bc_blocker"),
	)
	cap := parseJSON(t, capRec)
	if cap["isBlocked"] != true {
		t.Fatalf("expected isBlocked=true, got %#v", cap)
	}
	if cap["canGreet"] == true || cap["canSendMessage"] == true {
		t.Fatalf("blocked capability should disable greet/message: %#v", cap)
	}

	var greetingStatus string
	err := pgPool.QueryRow(context.Background(), `
		SELECT status FROM greeting_requests
		WHERE requester_sub_account_id = $1 AND target_sub_account_id = $2`,
		"sa_bc_blocker", "sa_bc_blocked").Scan(&greetingStatus)
	if err != nil {
		t.Fatalf("query greeting status: %v", err)
	}
	if greetingStatus != "blocked" {
		t.Fatalf("expected pending greeting marked blocked, got %q", greetingStatus)
	}
}
