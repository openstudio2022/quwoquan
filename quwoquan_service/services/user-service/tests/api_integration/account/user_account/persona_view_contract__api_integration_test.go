package api_integration

import (
	"context"
	"net/http"
	"testing"

	usertelemetry "quwoquan_service/services/user-service/internal/account/user_account/domain/user/telemetry"
	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
)

func seedPersonaViewViewer(t *testing.T) map[string]string {
	t.Helper()
	createTestProfile(t, "viewer_subject", "viewer_subject")
	createTestPersonaFull(
		t,
		"viewer_subject_persona_record",
		"viewer_subject",
		"viewer_subject_persona",
		"资料查看者",
		"open",
		true,
	)
	return authHeadersForPersona("viewer_subject", "viewer_subject_persona")
}

func TestPersonaView_GetMeProfileUsesActivePersona(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_me_profile", "owner_me")
	createTestPersonaFull(t, "persona_active_me", "owner_me_profile", "sa_me_profile", "摄影分身", "open", true, true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE persona_id = $2`, "photo_me", "sa_me_profile"); err != nil {
		t.Fatalf("seed user_handle: %v", err)
	}
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET nickname_customized = true WHERE persona_id = $1`, "sa_me_profile"); err != nil {
		t.Fatalf("seed owner nickname_customized: %v", err)
	}
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET avatar_url = $1, avatar_version = $2 WHERE persona_id = $3`,
		"https://cdn.example.com/persona-avatar-me.png",
		7,
		"sa_me_profile",
	); err != nil {
		t.Fatalf("seed owner avatar version: %v", err)
	}
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET background_url = $1 WHERE persona_id = $2`, "https://cdn.example.com/persona-cover-me.png", "sa_me_profile"); err != nil {
		t.Fatalf("seed persona background: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/me",
		"",
		authHeadersForPersona("owner_me_profile", "sa_me_profile"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("get me profile: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := parseJSON(t, rec)
	if body["personaId"] != "sa_me_profile" {
		t.Fatalf("expected active personaId, got %v", body["personaId"])
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
	if body["nicknameCustomized"] != true {
		t.Fatalf("expected nicknameCustomized=true for customized active persona, got %#v", body["nicknameCustomized"])
	}
	if body["backgroundUrl"] != "https://cdn.example.com/persona-cover-me.png" {
		t.Fatalf("expected inherited/overridden backgroundUrl, got %#v", body["backgroundUrl"])
	}
	if body["avatarUrl"] != "https://cdn.example.com/persona-avatar-me.png?v=7" {
		t.Fatalf("expected versioned avatarUrl, got %#v", body["avatarUrl"])
	}
	if body["avatarVersion"] != float64(7) {
		t.Fatalf("expected avatarVersion=7, got %#v", body["avatarVersion"])
	}
	if body["userHandle"] != "photo_me" {
		t.Fatalf("expected userHandle=photo_me, got %#v", body)
	}
	if _, exists := body["username"]; exists {
		t.Fatalf("public profile must not expose retired username handle alias: %#v", body)
	}
	if body["isolationLevel"] != "open" || body["profileVisibility"] != "public" {
		t.Fatalf("expected open/public visibility fields, got %#v", body)
	}
}

func TestPersonaView_GetPersonaProfile(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_public_profile", "owner_public")
	createTestPersonaFull(t, "persona_public", "owner_public_profile", "sa_public_profile", "公开分身", "open", true, true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE persona_id = $2`, "public_view", "sa_public_profile"); err != nil {
		t.Fatalf("seed user_handle: %v", err)
	}
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET nickname_customized = true WHERE persona_id = $1`, "sa_public_profile"); err != nil {
		t.Fatalf("seed public owner nickname_customized: %v", err)
	}
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET avatar_url = $1, avatar_version = $2 WHERE persona_id = $3`,
		"https://cdn.example.com/persona-avatar-public.png",
		9,
		"sa_public_profile",
	); err != nil {
		t.Fatalf("seed public owner avatar version: %v", err)
	}
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET background_url = $1 WHERE persona_id = $2`, "https://cdn.example.com/persona-cover-public.png", "sa_public_profile"); err != nil {
		t.Fatalf("seed public persona background: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/public_view",
		"",
		seedPersonaViewViewer(t),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("get persona profile: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := parseJSON(t, rec)
	if body["personaId"] != "sa_public_profile" {
		t.Fatalf("expected personaId=sa_public_profile, got %v", body["personaId"])
	}
	if body["userHandle"] != "public_view" {
		t.Fatalf("expected userHandle=public_view, got %#v", body)
	}
	if _, exists := body["username"]; exists {
		t.Fatalf("public profile must not expose retired username handle alias: %#v", body)
	}
	if body["displayName"] != "公开分身" {
		t.Fatalf("expected displayName=公开分身, got %v", body["displayName"])
	}
	if body["nicknameCustomized"] != true {
		t.Fatalf("expected nicknameCustomized=true for public persona custom display name, got %#v", body["nicknameCustomized"])
	}
	if body["backgroundUrl"] != "https://cdn.example.com/persona-cover-public.png" {
		t.Fatalf("expected backgroundUrl to expose public persona cover, got %#v", body["backgroundUrl"])
	}
	if body["avatarUrl"] != "https://cdn.example.com/persona-avatar-public.png?v=9" {
		t.Fatalf("expected versioned public avatarUrl, got %#v", body["avatarUrl"])
	}
	if body["avatarVersion"] != float64(9) {
		t.Fatalf("expected public avatarVersion=9, got %#v", body["avatarVersion"])
	}
	if _, ok := body["ownerUserId"]; ok {
		t.Fatalf("public profile should not expose ownerUserId, got %#v", body)
	}
}

func TestPersonaView_PersonaAvatarVersionOverridesOwner(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_persona_avatar", "owner_persona_avatar")
	createTestPersonaFull(t, "persona_avatar_override", "owner_persona_avatar", "sa_persona_avatar", "头像分身", "open", true, true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1, avatar_url = $2, avatar_version = $3 WHERE persona_id = $4`,
		"persona_avatar_handle",
		"https://cdn.example.com/persona-avatar-override.png",
		4,
		"sa_persona_avatar",
	); err != nil {
		t.Fatalf("seed persona avatar version: %v", err)
	}
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET avatar_url = $1, avatar_version = $2 WHERE persona_id = $3`,
		"https://cdn.example.com/owner-avatar-fallback.png",
		9,
		"owner_persona_avatar",
	); err != nil {
		t.Fatalf("seed owner avatar version: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/persona_avatar_handle",
		"",
		seedPersonaViewViewer(t),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("get persona profile: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := parseJSON(t, rec)
	if body["avatarUrl"] != "https://cdn.example.com/persona-avatar-override.png?v=4" {
		t.Fatalf("expected persona avatarUrl to use persona version, got %#v", body["avatarUrl"])
	}
	if body["avatarVersion"] != float64(4) {
		t.Fatalf("expected persona avatarVersion=4, got %#v", body["avatarVersion"])
	}
}

func TestPersonaView_StrictPersonaReturnsNotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_strict_profile", "owner_strict")
	createTestPersonaFull(t, "persona_strict", "owner_strict_profile", "sa_strict_profile", "严格分身", "strict", true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE persona_id = $2`, "strict_hidden", "sa_strict_profile"); err != nil {
		t.Fatalf("seed user_handle: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/strict_hidden",
		"",
		seedPersonaViewViewer(t),
	)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("strict persona should be hidden with 404, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestPersonaView_RetiredPersonaReturnsNotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_retired_profile", "owner_retired")
	createTestPersonaFull(t, "persona_retired", "owner_retired_profile", "sa_retired_profile", "退役分身", "open", true)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1, status = 'retired', retired_at = NOW(), is_active = false WHERE persona_id = $2`, "retired_hidden", "sa_retired_profile"); err != nil {
		t.Fatalf("seed retired persona: %v", err)
	}
	seedPersonaPostHistory(t, "sa_retired_profile")

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/retired_hidden",
		"",
		seedPersonaViewViewer(t),
	)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("retired persona should be hidden with 404, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestPersonaMetrics_PublicReadAndVisibilityMiss(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	usertelemetry.Reset()
	t.Cleanup(usertelemetry.Reset)
	createTestProfile(t, "owner_metrics_profile", "owner_metrics")
	createTestPersonaFull(t, "persona_metrics_visible", "owner_metrics_profile", "sa_metrics_visible", "可见分身", "open", true)
	createTestPersonaFull(t, "persona_metrics_hidden", "owner_metrics_profile", "sa_metrics_hidden", "隐藏分身", "strict", false)
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE persona_id = $2`, "metrics_visible", "sa_metrics_visible"); err != nil {
		t.Fatalf("seed visible handle: %v", err)
	}
	if _, err := pgPool.Exec(context.Background(), `UPDATE personas SET user_handle = $1 WHERE persona_id = $2`, "metrics_hidden", "sa_metrics_hidden"); err != nil {
		t.Fatalf("seed hidden handle: %v", err)
	}

	viewerHeaders := seedPersonaViewViewer(t)
	visibleRec := doRequest(
		t,
		http.MethodGet,
		"/user/metrics_visible",
		"",
		viewerHeaders,
	)
	if visibleRec.Code != http.StatusOK {
		t.Fatalf("expected visible persona 200, got %d: %s", visibleRec.Code, visibleRec.Body.String())
	}
	hiddenRec := doRequest(
		t,
		http.MethodGet,
		"/user/metrics_hidden",
		"",
		viewerHeaders,
	)
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
	reltelemetry.Reset()
	t.Cleanup(reltelemetry.Reset)
	createTestProfile(t, "search_owner_profile", "search_target_persona")
	createTestProfile(t, "search_viewer_profile", "search_viewer_profile")
	createTestPersonaFull(t, "search_persona", "search_owner_profile", "ps_search_target", "搜索分身", "open", true)
	createTestPersonaFull(t, "search_viewer_persona", "search_viewer_profile", "ps_search_viewer", "搜索查看者", "open", true)
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET user_handle = $1 WHERE persona_id = $2`,
		"search_target_handle",
		"ps_search_target",
	); err != nil {
		t.Fatalf("seed search persona handle: %v", err)
	}
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET avatar_url = $1, avatar_version = $2 WHERE persona_id = $3`,
		"https://cdn.example.com/search-target-avatar.png",
		4,
		"ps_search_target",
	); err != nil {
		t.Fatalf("seed search avatar version: %v", err)
	}
	blockRec := doRequest(
		t,
		http.MethodPost,
		"/user/personas/ps_search_viewer/block",
		"",
		authHeadersForPersona("search_owner_profile", "ps_search_target"),
	)
	if blockRec.Code != http.StatusOK {
		t.Fatalf("seed search block edge failed: %d: %s", blockRec.Code, blockRec.Body.String())
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/search/social-relations?query=search_target_persona",
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
	if first["personaId"] != "ps_search_target" {
		t.Fatalf("expected persona personaId, got %#v", first)
	}
	if first["avatarUrl"] != "https://cdn.example.com/search-target-avatar.png?v=4" {
		t.Fatalf("expected versioned search avatarUrl, got %#v", first["avatarUrl"])
	}
	if first["avatarVersion"] != float64(4) {
		t.Fatalf("expected search avatarVersion=4, got %#v", first["avatarVersion"])
	}
}

func TestRelationshipCapabilityView_States(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "viewer_rel", "viewer_rel")
	createTestProfile(t, "target_rel", "target_rel")
	createTestPersonaFull(t, "viewer_rel_persona", "viewer_rel", "ps_viewer_rel", "viewer_rel", "default", true)
	createTestPersonaFull(t, "target_rel_persona", "target_rel", "ps_target_rel", "target_rel", "default", true)

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/personas/ps_target_rel/relationship/capability",
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
	if body["canGreet"] != true {
		t.Fatalf("expected canGreet=true for stranger state, got %v", body["canGreet"])
	}
	if body["canCreateDirectConversation"] == true || body["canSendMessage"] == true {
		t.Fatalf("expected stranger state to block direct conversation/send, got %#v", body)
	}

	followRec := doRequest(
		t,
		http.MethodPost,
		"/user/personas/ps_target_rel/follow",
		"",
		authHeadersForPersona("viewer_rel", "ps_viewer_rel"),
	)
	if followRec.Code != http.StatusOK {
		t.Fatalf("follow target: expected 200, got %d: %s", followRec.Code, followRec.Body.String())
	}
	rec = doRequest(
		t,
		http.MethodGet,
		"/user/personas/ps_target_rel/relationship/capability",
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
	if body["canCreateDirectConversation"] == true || body["canSendMessage"] == true {
		t.Fatalf("expected one-way following to block direct conversation/send, got %#v", body)
	}

	followBackRec := doRequest(
		t,
		http.MethodPost,
		"/user/personas/ps_viewer_rel/follow",
		"",
		authHeadersForPersona("target_rel", "ps_target_rel"),
	)
	if followBackRec.Code != http.StatusOK {
		t.Fatalf("target follow viewer: expected 200, got %d: %s", followBackRec.Code, followBackRec.Body.String())
	}
	rec = doRequest(
		t,
		http.MethodGet,
		"/user/personas/ps_target_rel/relationship/capability",
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
	if body["canCreateDirectConversation"] != true || body["canSendMessage"] != true {
		t.Fatalf("expected mutual state to enable direct conversation/send, got %#v", body)
	}
}
