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

	rec := doRequest(t, http.MethodPost, "/v1/user/personas/pa_2_sa/activate", "", authHeaders("persona_user_2"))
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

	createTestPersonaFull(t, "pa_other", "persona_user_3", "pa_other_sa", "Other", "open", false, false)
	rec := doRequest(t, http.MethodDelete, "/v1/user/personas/pa_primary_sa/delete-empty", "", authHeaders("persona_user_3"))
	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for deleting primary persona, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestGetPersonaManagementSummary_ReturnsQuotaAndActiveContext(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_4", "persona_user4")
	createTestPersonaFull(t, "pa_primary", "persona_user_4", "pa_primary_sa", "Primary", "open", true, true)
	createTestPersonaFull(t, "pa_shadow", "persona_user_4", "pa_shadow_sa", "Shadow", "semi", false, false)

	rec := doRequest(t, http.MethodGet, "/v1/user/personas/summary", "", authHeaders("persona_user_4"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)

	items, ok := result["items"].([]any)
	if !ok || len(items) != 2 {
		t.Fatalf("expected 2 summary items, got %v", result["items"])
	}
	quota, ok := result["quota"].(map[string]any)
	if !ok {
		t.Fatalf("expected quota object, got %v", result["quota"])
	}
	if quota["maxSubAccounts"] != float64(5) {
		t.Fatalf("expected maxSubAccounts=5, got %v", quota["maxSubAccounts"])
	}
	active, ok := result["activeContext"].(map[string]any)
	if !ok {
		t.Fatalf("expected activeContext object, got %v", result["activeContext"])
	}
	if active["subAccountId"] != "pa_primary_sa" {
		t.Fatalf("expected activeContext.subAccountId=pa_primary_sa, got %v", active["subAccountId"])
	}
}

func TestUpdatePersona_ReflectsManagementFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_5", "persona_user5")
	createTestPersonaFull(t, "pa_edit", "persona_user_5", "pa_edit_sa", "Before", "open", true, true)

	rec := doRequest(
		t,
		http.MethodPatch,
		"/v1/user/personas/pa_edit_sa",
		`{"displayName":"After","userHandle":"after_handle","phone":"13800138000","email":"after@example.com","isolationLevel":"semi"}`,
		authHeaders("persona_user_5"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["displayName"] != "After" {
		t.Fatalf("expected displayName=After, got %v", result["displayName"])
	}
	if result["userHandle"] != "after_handle" {
		t.Fatalf("expected userHandle=after_handle, got %v", result["userHandle"])
	}
	if result["phone"] != "13800138000" {
		t.Fatalf("expected phone reflected, got %v", result["phone"])
	}
	if result["email"] != "after@example.com" {
		t.Fatalf("expected email reflected, got %v", result["email"])
	}

	var inherits bool
	err := pgPool.QueryRow(
		context.Background(),
		"SELECT inherits_profile_from_owner FROM personas WHERE sub_account_id = $1",
		"pa_edit_sa",
	).Scan(&inherits)
	if err != nil {
		t.Fatalf("query inherits_profile_from_owner: %v", err)
	}
	if inherits {
		t.Fatal("expected updated persona to stop inheriting owner profile")
	}
}

func TestApplyPersonaProfileSync_ReturnsAppliedCount(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_6", "persona_user6")
	createTestPersonaFull(t, "pa_source", "persona_user_6", "pa_source_sa", "Source", "open", true, true)
	createTestPersonaFull(t, "pa_target", "persona_user_6", "pa_target_sa", "Target", "open", false, false)

	_, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas
		 SET phone = $1, email = $2, user_handle = $3
		 WHERE sub_account_id = $4`,
		"13800138000",
		"source@example.com",
		"source_handle",
		"pa_source_sa",
	)
	if err != nil {
		t.Fatalf("seed source persona profile: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/personas/pa_source_sa/profile-sync",
		`{"applyScope":"selected_subjects","syncTargetIds":["pa_target_sa"],"fieldsMask":["phone","email"]}`,
		authHeaders("persona_user_6"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["appliedCount"] != float64(1) {
		t.Fatalf("expected appliedCount=1, got %v", result["appliedCount"])
	}
}

func TestGetPersonaLifecycleGuard_ActivePersonaRequiresSuccessor(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_7", "persona_user7")
	createTestPersonaFull(t, "pa_primary", "persona_user_7", "pa_primary_sa", "Primary", "open", true, true)
	createTestPersonaFull(t, "pa_backup", "persona_user_7", "pa_backup_sa", "Backup", "open", false, false)

	rec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/personas/pa_primary_sa/lifecycle-guard",
		"",
		authHeaders("persona_user_7"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["reasonCode"] != "blocked_active_persona" {
		t.Fatalf("expected blocked_active_persona, got %v", result["reasonCode"])
	}
	if result["requiresSuccessor"] != true {
		t.Fatalf("expected requiresSuccessor=true, got %v", result["requiresSuccessor"])
	}
	if result["canRetire"] != false {
		t.Fatalf("expected canRetire=false for active primary persona, got %v", result["canRetire"])
	}
}

func TestRetirePersona_ReturnsRetireGuardView(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_8", "persona_user8")
	createTestPersonaFull(t, "pa_primary", "persona_user_8", "pa_primary_sa", "Primary", "open", true, true)
	createTestPersonaFull(t, "pa_shadow", "persona_user_8", "pa_shadow_sa", "Shadow", "open", false, false)

	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/personas/pa_shadow_sa/retire",
		"",
		authHeaders("persona_user_8"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["requestedAction"] != "retire" {
		t.Fatalf("expected requestedAction=retire, got %v", result["requestedAction"])
	}
	if result["subAccountId"] != "pa_shadow_sa" {
		t.Fatalf("expected subAccountId=pa_shadow_sa, got %v", result["subAccountId"])
	}
}
