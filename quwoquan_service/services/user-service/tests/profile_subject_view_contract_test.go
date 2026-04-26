package tests

import (
	"context"
	"net/http"
	"testing"

	followtelemetry "quwoquan_service/services/user-service/internal/domain/follow/telemetry"
	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
)

func TestProfileSubjectView_GetMeProfileUsesActiveSubAccount(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_me_profile", "owner_me")
	createTestPersonaFull(t, "persona_active_me", "owner_me_profile", "sa_me_profile", "摄影分身", "open", true, true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE sub_account_id = $2`, "photo_me", "sa_me_profile"); err != nil {
		t.Fatalf("seed user_handle: %v", err)
	}

	rec := doRequest(t, http.MethodGet, "/v1/me", "", authHeaders("owner_me_profile"))
	if rec.Code != http.StatusOK {
		t.Fatalf("get me profile: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := parseJSON(t, rec)
	if body["profileSubjectId"] != "sa_me_profile" {
		t.Fatalf("expected active subAccount profileSubjectId, got %v", body["profileSubjectId"])
	}
	if body["ownerUserId"] != "owner_me_profile" {
		t.Fatalf("expected ownerUserId=owner_me_profile, got %v", body["ownerUserId"])
	}
	if body["subjectType"] != "persona" {
		t.Fatalf("expected subjectType=persona, got %v", body["subjectType"])
	}
	if body["displayName"] != "摄影分身" {
		t.Fatalf("expected displayName=摄影分身, got %v", body["displayName"])
	}
	if body["userHandle"] != "photo_me" || body["username"] != "photo_me" {
		t.Fatalf("expected userHandle/username=photo_me, got %#v", body)
	}
	if body["isolationLevel"] != "open" || body["profileVisibility"] != "public" {
		t.Fatalf("expected open/public visibility fields, got %#v", body)
	}
}

func TestProfileSubjectView_GetSubAccountProfile(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_public_profile", "owner_public")
	createTestPersonaFull(t, "persona_public", "owner_public_profile", "sa_public_profile", "公开分身", "open", true, true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE sub_account_id = $2`, "public_view", "sa_public_profile"); err != nil {
		t.Fatalf("seed user_handle: %v", err)
	}

	rec := doRequest(t, http.MethodGet, "/v1/user/public_view", "", authHeaders("viewer_subject"))
	if rec.Code != http.StatusOK {
		t.Fatalf("get sub-account profile: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := parseJSON(t, rec)
	if body["profileSubjectId"] != "sa_public_profile" {
		t.Fatalf("expected profileSubjectId=sa_public_profile, got %v", body["profileSubjectId"])
	}
	if body["subAccountId"] != "sa_public_profile" {
		t.Fatalf("expected subAccountId=sa_public_profile, got %v", body["subAccountId"])
	}
	if body["userHandle"] != "public_view" || body["username"] != "public_view" {
		t.Fatalf("expected userHandle=username=public_view, got %#v", body)
	}
	if body["displayName"] != "公开分身" {
		t.Fatalf("expected displayName=公开分身, got %v", body["displayName"])
	}
	if _, ok := body["ownerUserId"]; ok {
		t.Fatalf("public profile should not expose ownerUserId, got %#v", body)
	}
}

func TestProfileSubjectView_StrictPersonaReturnsNotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_strict_profile", "owner_strict")
	createTestPersonaFull(t, "persona_strict", "owner_strict_profile", "sa_strict_profile", "严格分身", "strict", true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE sub_account_id = $2`, "strict_hidden", "sa_strict_profile"); err != nil {
		t.Fatalf("seed user_handle: %v", err)
	}

	rec := doRequest(t, http.MethodGet, "/v1/user/strict_hidden", "", authHeaders("viewer_subject"))
	if rec.Code != http.StatusNotFound {
		t.Fatalf("strict persona should be hidden with 404, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestProfileSubjectView_RetiredPersonaReturnsNotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_retired_profile", "owner_retired")
	createTestPersonaFull(t, "persona_retired", "owner_retired_profile", "sa_retired_profile", "退役分身", "open", true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1, status = 'retired', retired_at = NOW(), is_active = false WHERE sub_account_id = $2`, "retired_hidden", "sa_retired_profile"); err != nil {
		t.Fatalf("seed retired persona: %v", err)
	}
	seedPersonaPostHistory(t, "sa_retired_profile")

	rec := doRequest(t, http.MethodGet, "/v1/user/retired_hidden", "", authHeaders("viewer_subject"))
	if rec.Code != http.StatusNotFound {
		t.Fatalf("retired persona should be hidden with 404, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestProfileSubjectView_FeatureFlagOffFallsBackToPersonaID(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	t.Setenv("OPS_USER_PROFILE_SUBJECT_V1", "false")
	createTestProfile(t, "owner_flag_profile", "owner_flag")
	createTestPersonaFull(t, "persona_flag", "owner_flag_profile", "sa_flag_profile", "回滚分身", "open", true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE sub_account_id = $2`, "flag_handle", "sa_flag_profile"); err != nil {
		t.Fatalf("seed user_handle: %v", err)
	}

	handleRec := doRequest(t, http.MethodGet, "/v1/user/flag_handle", "", authHeaders("viewer_subject"))
	if handleRec.Code != http.StatusNotFound {
		t.Fatalf("flag-off should hide handle route fallback, got %d: %s", handleRec.Code, handleRec.Body.String())
	}

	personaRec := doRequest(t, http.MethodGet, "/v1/user/sa_flag_profile", "", authHeaders("viewer_subject"))
	if personaRec.Code != http.StatusOK {
		t.Fatalf("flag-off personaId fallback should stay available, got %d: %s", personaRec.Code, personaRec.Body.String())
	}
}

func TestProfileSubjectMetrics_PublicReadAndVisibilityMiss(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	usertelemetry.Reset()
	t.Cleanup(usertelemetry.Reset)
	createTestProfile(t, "owner_metrics_profile", "owner_metrics")
	createTestPersonaFull(t, "persona_metrics_visible", "owner_metrics_profile", "sa_metrics_visible", "可见分身", "open", true)
	createTestPersonaFull(t, "persona_metrics_hidden", "owner_metrics_profile", "sa_metrics_hidden", "隐藏分身", "strict", false)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE sub_account_id = $2`, "metrics_visible", "sa_metrics_visible"); err != nil {
		t.Fatalf("seed visible handle: %v", err)
	}
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE sub_account_id = $2`, "metrics_hidden", "sa_metrics_hidden"); err != nil {
		t.Fatalf("seed hidden handle: %v", err)
	}

	visibleRec := doRequest(t, http.MethodGet, "/v1/user/metrics_visible", "", authHeaders("viewer_subject"))
	if visibleRec.Code != http.StatusOK {
		t.Fatalf("expected visible persona 200, got %d: %s", visibleRec.Code, visibleRec.Body.String())
	}
	hiddenRec := doRequest(t, http.MethodGet, "/v1/user/metrics_hidden", "", authHeaders("viewer_subject"))
	if hiddenRec.Code != http.StatusNotFound {
		t.Fatalf("expected strict persona 404, got %d: %s", hiddenRec.Code, hiddenRec.Body.String())
	}

	snapshot := usertelemetry.Collector().Snapshot()
	if snapshot[usertelemetry.MetricProfileSubjectPublicReadLatencyMs] <= 0 {
		t.Fatalf("expected public read latency metric > 0, got %v", snapshot)
	}
	if snapshot[usertelemetry.MetricProfileSubjectVisibilityNotFoundCount] != 1 {
		t.Fatalf("expected visibility not found count = 1, got %v", snapshot)
	}
}

func TestSearchSocialRelations_DoesNotExposeOwnerUserID(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	followtelemetry.Reset()
	t.Cleanup(followtelemetry.Reset)
	createTestProfile(t, "search_owner_profile", "search_target_persona")
	createTestProfile(t, "search_viewer_profile", "search_viewer_profile")
	createTestPersonaFull(t, "search_persona", "search_owner_profile", "ps_search_target", "搜索分身", "open", true)
	createTestPersonaFull(t, "search_viewer_persona", "search_viewer_profile", "ps_search_viewer", "搜索查看者", "open", true)
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET user_handle = $1 WHERE sub_account_id = $2`,
		"search_target_handle",
		"ps_search_target",
	); err != nil {
		t.Fatalf("seed search persona handle: %v", err)
	}
	blockRec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/profile-subjects/ps_search_viewer/block",
		"",
		authHeadersForPersona("search_owner_profile", "ps_search_target"),
	)
	if blockRec.Code != http.StatusOK {
		t.Fatalf("seed search block edge failed: %d: %s", blockRec.Code, blockRec.Body.String())
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/search/social-relations?query=search_target_persona",
		"",
		authHeadersForPersona("search_viewer_profile", "ps_search_viewer"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("search social relations: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := parseJSON(t, rec)
	items, ok := body["items"].([]any)
	if !ok || len(items) == 0 {
		t.Fatalf("expected search items, got %#v", body)
	}
	first, ok := items[0].(map[string]any)
	if !ok {
		t.Fatalf("unexpected search item payload: %#v", items[0])
	}
	if _, exists := first["ownerUserId"]; exists {
		t.Fatalf("search result must not expose ownerUserId, got %#v", first)
	}
	if first["profileSubjectId"] != "ps_search_target" {
		t.Fatalf("expected persona profileSubjectId, got %#v", first)
	}
	snapshot := followtelemetry.Collector().Snapshot()
	if snapshot[followtelemetry.MetricRelationshipCapabilityMismatch] <= 0 {
		t.Fatalf("expected relationship capability mismatch metric > 0, got %v", snapshot)
	}
}

func TestRelationshipCapabilityView_States(t *testing.T) {
	if mongoDB == nil {
		t.Skip("mongo unavailable; skip follow-edge capability state transitions")
	}
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "viewer_rel", "viewer_rel")
	createTestProfile(t, "target_rel", "target_rel")
	createTestPersonaFull(t, "viewer_rel_persona", "viewer_rel", "ps_viewer_rel", "viewer_rel", "default", true)
	createTestPersonaFull(t, "target_rel_persona", "target_rel", "ps_target_rel", "target_rel", "default", true)

	rec := doRequest(
		t,
		http.MethodGet,
		"/v1/user/profile-subjects/ps_target_rel/relationship/capability",
		"",
		authHeadersForPersona("viewer_rel", "ps_viewer_rel"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("get capability: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	if body["relationState"] != "not_following" {
		t.Fatalf("expected relationState=not_following, got %v", body["relationState"])
	}
	if body["canMessage"] != true {
		t.Fatalf("expected canMessage=true for stranger state, got %v", body["canMessage"])
	}

	followRec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/profile-subjects/ps_target_rel/follow",
		"",
		authHeadersForPersona("viewer_rel", "ps_viewer_rel"),
	)
	if followRec.Code != http.StatusOK {
		t.Fatalf("follow target: expected 200, got %d: %s", followRec.Code, followRec.Body.String())
	}
	rec = doRequest(
		t,
		http.MethodGet,
		"/v1/user/profile-subjects/ps_target_rel/relationship/capability",
		"",
		authHeadersForPersona("viewer_rel", "ps_viewer_rel"),
	)
	body = parseJSON(t, rec)
	if body["relationState"] != "following" {
		t.Fatalf("expected relationState=following, got %v", body["relationState"])
	}
	if body["canUnfollow"] != true {
		t.Fatalf("expected canUnfollow=true, got %v", body["canUnfollow"])
	}

	followBackRec := doRequest(
		t,
		http.MethodPost,
		"/v1/user/profile-subjects/ps_viewer_rel/follow",
		"",
		authHeadersForPersona("target_rel", "ps_target_rel"),
	)
	if followBackRec.Code != http.StatusOK {
		t.Fatalf("target follow viewer: expected 200, got %d: %s", followBackRec.Code, followBackRec.Body.String())
	}
	rec = doRequest(
		t,
		http.MethodGet,
		"/v1/user/profile-subjects/ps_target_rel/relationship/capability",
		"",
		authHeadersForPersona("viewer_rel", "ps_viewer_rel"),
	)
	body = parseJSON(t, rec)
	if body["relationState"] != "mutual" {
		t.Fatalf("expected relationState=mutual, got %v", body["relationState"])
	}
	if body["canStartVoiceCall"] != true || body["canStartVideoCall"] != true {
		t.Fatalf("expected mutual state to enable voice/video, got %#v", body)
	}
}
