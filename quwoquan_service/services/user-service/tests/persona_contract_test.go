package tests

import (
	"context"
	"net/http"
	"testing"

	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
)

func seedPersonaInviteHistory(t *testing.T, recordID, subAccountID, ownerID string) {
	t.Helper()
	_, err := pgPool.Exec(
		context.Background(),
		`INSERT INTO invite_records (
			id, inviter_sub_account_id, inviter_owner_account_id, channel, link_code,
			invitee_phone_hash, status, expire_at, generated_at
		) VALUES ($1, $2, $3, 'link', $4, $5, 'generated', NOW() + INTERVAL '1 day', NOW())`,
		recordID,
		subAccountID,
		ownerID,
		recordID+"_code",
		recordID+"_phone",
	)
	if err != nil {
		t.Fatalf("seed invite history: %v", err)
	}
}

func TestGetPersonaLifecycleGuard_HistoryCoverageBySource(t *testing.T) {
	cases := []struct {
		name string
		seed func(t *testing.T, profileSubjectID string)
	}{
		{
			name: "content_post",
			seed: seedPersonaPostHistory,
		},
		{
			name: "content_comment",
			seed: seedPersonaCommentHistory,
		},
		{
			name: "chat_message",
			seed: seedPersonaChatHistory,
		},
		{
			name: "notification",
			seed: seedPersonaNotificationHistory,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Cleanup(func() { cleanAll(t) })
			createTestProfile(t, "persona_history_"+tc.name, "persona_history_"+tc.name)
			createTestPersonaFull(t, "pa_primary_"+tc.name, "persona_history_"+tc.name, "pa_primary_sa_"+tc.name, "Primary", "open", true)
			createTestPersonaFull(t, "pa_shadow_"+tc.name, "persona_history_"+tc.name, "pa_shadow_sa_"+tc.name, "Shadow", "open", false)
			tc.seed(t, "pa_shadow_sa_"+tc.name)

			rec := doRequest(
				t,
				http.MethodGet,
				"/v1/user/personas/pa_shadow_sa_"+tc.name+"/lifecycle-guard",
				"",
				authHeaders("persona_history_"+tc.name),
			)
			if rec.Code != http.StatusOK {
				t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
			}
			result := parseJSON(t, rec)
			if result["hasAttributedHistory"] != true {
				t.Fatalf("expected hasAttributedHistory=true for %s, got %v", tc.name, result["hasAttributedHistory"])
			}
			if result["reasonCode"] != "retire_instead_of_delete" {
				t.Fatalf("expected retire_instead_of_delete for %s, got %v", tc.name, result["reasonCode"])
			}
		})
	}
}

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
		`{"displayName":"After","userHandle":"after_handle","phone":"13800138000","email":"after@example.com","avatarUrl":"https://example.com/avatar-after.png","isolationLevel":"semi"}`,
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
	if result["avatarUrl"] != "https://example.com/avatar-after.png" {
		t.Fatalf("expected avatarUrl reflected, got %v", result["avatarUrl"])
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
	usertelemetry.Reset()
	t.Cleanup(usertelemetry.Reset)
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
	snapshot := usertelemetry.Collector().Snapshot()
	if snapshot[usertelemetry.MetricProfileSubjectSyncScopeSubmitCount] != 1 {
		t.Fatalf("expected sync scope submit count = 1, got %v", snapshot)
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
	if result["reasonCode"] != "blocked_primary_persona" {
		t.Fatalf("expected blocked_primary_persona, got %v", result["reasonCode"])
	}
	if result["requiresSuccessor"] != false {
		t.Fatalf("expected requiresSuccessor=false when primary guard wins, got %v", result["requiresSuccessor"])
	}
	if result["canRetire"] != false {
		t.Fatalf("expected canRetire=false for active primary persona, got %v", result["canRetire"])
	}
}

func TestGetPersonaLifecycleGuard_HistoryRequiresRetire(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	usertelemetry.Reset()
	t.Cleanup(usertelemetry.Reset)
	createTestProfile(t, "persona_user_8", "persona_user8")
	createTestPersonaFull(t, "pa_primary", "persona_user_8", "pa_primary_sa", "Primary", "open", true, true)
	createTestPersonaFull(t, "pa_shadow", "persona_user_8", "pa_shadow_sa", "Shadow", "open", false, false)
	seedPersonaInviteHistory(t, "invite_hist_8", "pa_shadow_sa", "persona_user_8")

	rec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/personas/pa_shadow_sa/lifecycle-guard",
		"",
		authHeaders("persona_user_8"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["reasonCode"] != "retire_instead_of_delete" {
		t.Fatalf("expected retire_instead_of_delete, got %v", result["reasonCode"])
	}
	if result["hasAttributedHistory"] != true {
		t.Fatalf("expected hasAttributedHistory=true, got %v", result["hasAttributedHistory"])
	}
	if result["canDelete"] != false || result["canRetire"] != true {
		t.Fatalf("expected delete blocked and retire allowed, got delete=%v retire=%v", result["canDelete"], result["canRetire"])
	}
	if result["requiredAction"] != "retire" {
		t.Fatalf("expected requiredAction=retire, got %v", result["requiredAction"])
	}
	snapshot := usertelemetry.Collector().Snapshot()
	if snapshot[usertelemetry.MetricRetiredSubjectAttributionFallbackCount] != 0 {
		t.Fatalf("expected no mongo fallback metric for pg-backed history, got %v", snapshot)
	}
}

func TestGetPersonaLifecycleGuard_RecordsMongoHistoryFallbackMetric(t *testing.T) {
	if mongoDB == nil {
		t.Skip("mongo unavailable")
	}
	t.Cleanup(func() { cleanAll(t) })
	usertelemetry.Reset()
	t.Cleanup(usertelemetry.Reset)
	createTestProfile(t, "persona_user_mongo_metric", "persona_user_mongo_metric")
	createTestPersonaFull(t, "pa_primary_metric", "persona_user_mongo_metric", "pa_primary_metric_sa", "Primary", "open", true)
	createTestPersonaFull(t, "pa_shadow_metric", "persona_user_mongo_metric", "pa_shadow_metric_sa", "Shadow", "open", false)
	seedPersonaPostHistory(t, "pa_shadow_metric_sa")

	rec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/personas/pa_shadow_metric_sa/lifecycle-guard",
		"",
		authHeaders("persona_user_mongo_metric"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	snapshot := usertelemetry.Collector().Snapshot()
	if snapshot[usertelemetry.MetricRetiredSubjectAttributionFallbackCount] != 1 {
		t.Fatalf("expected mongo fallback metric = 1, got %v", snapshot)
	}
}

func TestRetirePersona_PersistsRetiredStatus(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_9", "persona_user9")
	createTestPersonaFull(t, "pa_primary", "persona_user_9", "pa_primary_sa", "Primary", "open", true)
	createTestPersonaFull(t, "pa_shadow", "persona_user_9", "pa_shadow_sa", "Shadow", "open", false)
	seedPersonaInviteHistory(t, "invite_hist_9", "pa_shadow_sa", "persona_user_9")

	rec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/personas/pa_shadow_sa/retire",
		"",
		authHeaders("persona_user_9"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["requestedAction"] != "retire" {
		t.Fatalf("expected requestedAction=retire, got %v", result["requestedAction"])
	}
	if result["allowed"] != true {
		t.Fatalf("expected allowed=true after successful retire, got %v", result["allowed"])
	}

	var status string
	var isActive bool
	var retiredAt *string
	err := pgPool.QueryRow(
		context.Background(),
		`SELECT status, is_active, retired_at::text
		 FROM personas
		 WHERE sub_account_id = $1`,
		"pa_shadow_sa",
	).Scan(&status, &isActive, &retiredAt)
	if err != nil {
		t.Fatalf("query retired persona: %v", err)
	}
	if status != "retired" {
		t.Fatalf("expected status=retired, got %s", status)
	}
	if isActive {
		t.Fatal("expected retired persona to be inactive")
	}
	if retiredAt == nil || *retiredAt == "" {
		t.Fatal("expected retired_at to be populated")
	}
}

func TestDeleteEmptyPersona_HistoryRequiresRetireConflict(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_10", "persona_user10")
	createTestPersonaFull(t, "pa_primary", "persona_user_10", "pa_primary_sa", "Primary", "open", true)
	createTestPersonaFull(t, "pa_shadow", "persona_user_10", "pa_shadow_sa", "Shadow", "open", false)
	seedPersonaInviteHistory(t, "invite_hist_10", "pa_shadow_sa", "persona_user_10")

	rec := doRequest(
		t,
		http.MethodDelete,
		"/v1/user/personas/pa_shadow_sa/delete-empty",
		"",
		authHeaders("persona_user_10"),
	)
	if rec.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestRetiredPersona_CannotBeActivatedOrUpdated(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "persona_user_11", "persona_user11")
	createTestPersonaFull(t, "pa_primary", "persona_user_11", "pa_primary_sa", "Primary", "open", true)
	createTestPersonaFull(t, "pa_shadow", "persona_user_11", "pa_shadow_sa", "Shadow", "open", false)
	seedPersonaInviteHistory(t, "invite_hist_11", "pa_shadow_sa", "persona_user_11")

	retireRec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/personas/pa_shadow_sa/retire",
		"",
		authHeaders("persona_user_11"),
	)
	if retireRec.Code != http.StatusOK {
		t.Fatalf("expected retire 200, got %d: %s", retireRec.Code, retireRec.Body.String())
	}

	activateRec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/personas/pa_shadow_sa/activate",
		"",
		authHeaders("persona_user_11"),
	)
	if activateRec.Code != http.StatusBadRequest {
		t.Fatalf("expected activate retired persona 400, got %d: %s", activateRec.Code, activateRec.Body.String())
	}

	updateRec := doRequest(
		t,
		http.MethodPatch,
		"/v1/user/personas/pa_shadow_sa",
		`{"displayName":"AfterRetire"}`,
		authHeaders("persona_user_11"),
	)
	if updateRec.Code != http.StatusBadRequest {
		t.Fatalf("expected update retired persona 400, got %d: %s", updateRec.Code, updateRec.Body.String())
	}

	summaryRec := doRequest(t, http.MethodGet, "/v1/user/personas/summary", "", authHeaders("persona_user_11"))
	if summaryRec.Code != http.StatusOK {
		t.Fatalf("expected summary 200, got %d: %s", summaryRec.Code, summaryRec.Body.String())
	}
	summary := parseJSON(t, summaryRec)
	items, ok := summary["items"].([]any)
	if !ok {
		t.Fatalf("expected items array, got %v", summary["items"])
	}
	foundRetired := false
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok || item["subAccountId"] != "pa_shadow_sa" {
			continue
		}
		foundRetired = true
		if item["status"] != "retired" {
			t.Fatalf("expected summary status=retired, got %v", item["status"])
		}
		if item["hasAttributedHistory"] != true {
			t.Fatalf("expected summary hasAttributedHistory=true, got %v", item["hasAttributedHistory"])
		}
	}
	if !foundRetired {
		t.Fatal("expected retired persona to remain visible in summary")
	}
}
