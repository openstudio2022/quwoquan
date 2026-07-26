package api_integration

import (
	"context"
	"net/http"
	"testing"
)

func TestInvitationGenerateResolveAndAccept(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "invite_owner", "invite_owner")
	createTestPersonaFull(t, "invite_persona", "invite_owner", "sa_invite", "Invite", "open", true, true)
	createTestProfile(t, "invite_acceptor", "invite_acceptor")

	generated := doRequest(
		t,
		http.MethodPost,
		"/user/invites",
		`{"subAccountId":"sa_invite","channel":"direct","inviteePhone":"13800138000"}`,
		authHeadersForPersona("invite_owner", "sa_invite"),
	)
	if generated.Code != http.StatusCreated {
		t.Fatalf("generate invitation: expected 201, got %d: %s", generated.Code, generated.Body.String())
	}
	body := parseJSON(t, generated)
	linkCode, _ := body["linkCode"].(string)
	if linkCode == "" {
		t.Fatalf("generated response missing linkCode: %#v", body)
	}
	if _, leaked := body["inviterOwnerAccountId"]; leaked {
		t.Fatal("private response leaked inviterOwnerAccountId")
	}
	if _, leaked := body["inviteePhoneHash"]; leaked {
		t.Fatal("private response leaked inviteePhoneHash")
	}
	var storedHash string
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT invitee_phone_hash FROM invite_records WHERE link_code=$1`,
		linkCode,
	).Scan(&storedHash); err != nil {
		t.Fatalf("read stored phone digest: %v", err)
	}
	if storedHash == "" || storedHash == "13800138000" {
		t.Fatalf("invitee phone must be stored only as digest, got %q", storedHash)
	}

	resolved := doRequest(t, http.MethodGet, "/invites/"+linkCode, "", nil)
	if resolved.Code != http.StatusOK {
		t.Fatalf("resolve invitation: expected 200, got %d: %s", resolved.Code, resolved.Body.String())
	}
	publicBody := parseJSON(t, resolved)
	if _, leaked := publicBody["linkCode"]; leaked {
		t.Fatal("public response leaked linkCode")
	}
	if publicBody["status"] != "delivered" {
		t.Fatalf("resolve must mark invitation delivered, got %#v", publicBody)
	}

	unauthorized := doRequest(t, http.MethodPost, "/invites/"+linkCode+"/accept", "", nil)
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("unauthorized accept: expected 401, got %d: %s", unauthorized.Code, unauthorized.Body.String())
	}
	accepted := doRequest(
		t,
		http.MethodPost,
		"/invites/"+linkCode+"/accept",
		"",
		authHeaders("invite_acceptor"),
	)
	if accepted.Code != http.StatusOK {
		t.Fatalf("accept invitation: expected 200, got %d: %s", accepted.Code, accepted.Body.String())
	}
	if parseJSON(t, accepted)["status"] != "accepted" {
		t.Fatalf("accepted response status mismatch: %s", accepted.Body.String())
	}
}

func TestInvitationGenerateIsIdempotentAndOwnerScoped(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "invite_idem_owner", "invite_idem_owner")
	createTestProfile(t, "invite_spoof_owner", "invite_spoof_owner")
	createTestPersonaFull(t, "invite_idem_persona", "invite_idem_owner", "sa_invite_idem", "Invite", "open", true, true)

	payload := `{"subAccountId":"sa_invite_idem","channel":"direct","inviteePhone":"13800138001"}`
	first := doRequest(t, http.MethodPost, "/user/invites", payload, authHeadersForPersona("invite_idem_owner", "sa_invite_idem"))
	second := doRequest(t, http.MethodPost, "/user/invites", payload, authHeadersForPersona("invite_idem_owner", "sa_invite_idem"))
	if first.Code != http.StatusCreated || second.Code != http.StatusCreated {
		t.Fatalf("idempotent generate status mismatch: first=%d second=%d", first.Code, second.Code)
	}
	if parseJSON(t, first)["linkCode"] != parseJSON(t, second)["linkCode"] {
		t.Fatal("same idempotency tuple must reuse linkCode")
	}

	spoofed := doRequest(t, http.MethodPost, "/user/invites", payload, authHeadersForPersona("invite_spoof_owner", "sa_invite_idem"))
	if spoofed.Code != http.StatusForbidden {
		t.Fatalf("persona ownership spoof: expected 403, got %d: %s", spoofed.Code, spoofed.Body.String())
	}

	listed := doRequest(
		t,
		http.MethodGet,
		"/user/invites?subAccountId=sa_invite_idem",
		"",
		authHeadersForPersona("invite_idem_owner", "sa_invite_idem"),
	)
	if listed.Code != http.StatusOK {
		t.Fatalf("list invitations: expected 200, got %d: %s", listed.Code, listed.Body.String())
	}
	items, _ := parseJSON(t, listed)["invites"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected exactly one idempotent invitation, got %d", len(items))
	}
}
