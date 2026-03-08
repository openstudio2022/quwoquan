package tests

import (
	"context"
	"net/http"
	"testing"
)

func TestCreatePersona_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_1", "persona_user1")

	rec := doRequest(t, http.MethodPost, "/v1/user/personas",
		`{"displayName":"Shadow","isPrivate":true}`,
		authHeaders("persona_user_1"))
	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["displayName"] != "Shadow" {
		t.Errorf("expected displayName=Shadow, got %v", result["displayName"])
	}
}

func TestActivatePersona_Transaction(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_2", "persona_user2")
	createTestPersona(t, "pa_1", "persona_user_2", "PersonaA", true, true)
	createTestPersona(t, "pa_2", "persona_user_2", "PersonaB", false, false)

	rec := doRequest(t, http.MethodPost, "/v1/user/personas/pa_2/activate", "", authHeaders("persona_user_2"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var activeCount int
	err := pgPool.QueryRow(context.Background(),
		"SELECT COUNT(*) FROM personas WHERE user_id = $1 AND is_active = true",
		"persona_user_2").Scan(&activeCount)
	if err != nil {
		t.Fatalf("query active count: %v", err)
	}
	if activeCount != 1 {
		t.Errorf("expected exactly 1 active persona, got %d", activeCount)
	}

	var activeID string
	_ = pgPool.QueryRow(context.Background(),
		"SELECT id FROM personas WHERE user_id = $1 AND is_active = true",
		"persona_user_2").Scan(&activeID)
	if activeID != "pa_2" {
		t.Errorf("expected active persona pa_2, got %s", activeID)
	}
}

func TestDeletePersona_PrimaryForbidden(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_3", "persona_user3")
	createTestPersona(t, "pa_primary", "persona_user_3", "Primary", true, true)

	rec := doRequest(t, http.MethodDelete, "/v1/user/personas/pa_primary", "", authHeaders("persona_user_3"))
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for deleting primary persona, got %d: %s", rec.Code, rec.Body.String())
	}
}
