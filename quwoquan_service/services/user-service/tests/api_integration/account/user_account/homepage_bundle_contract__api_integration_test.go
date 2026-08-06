// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-profile-subject-and-visibility/spec.md#gwt-001
// readiness_case: get-user-homepage-bundle-api
package api_integration

import (
	"context"
	"net/http"
	"testing"
)

// seedHomepageOwner 建立 owner profile + persona(handle)，并写入身份域计数真相，
// 供 homepage-bundle 聚合断言。
func seedHomepageOwner(t *testing.T, userID, personaID, handle, displayName, isolationLevel string) {
	t.Helper()
	createTestProfile(t, userID, displayName)
	createTestPersonaFull(t, "persona_"+personaID, userID, personaID, displayName, isolationLevel, true, true)
	if _, err := pgPool.Exec(context.Background(),
		`UPDATE personas SET user_handle = $1 WHERE persona_id = $2`, handle, personaID); err != nil {
		t.Fatalf("seed user_handle: %v", err)
	}
	if _, err := pgPool.Exec(context.Background(),
		`UPDATE user_profiles SET follower_count=$2, following_count=$3, post_count=$4, circle_count=$5, like_count=$6 WHERE user_id=$1`,
		userID, 128, 42, 17, 6, 333); err != nil {
		t.Fatalf("seed counts: %v", err)
	}
}

func TestHomepageBundle_OwnerViewAggregatesIdentityTruth(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	seedHomepageOwner(t, "owner_hb_self", "sa_hb_self", "hb_self", "本人主页", "open")

	rec := doRequest(t, http.MethodGet, "/user/personas/hb_self/homepage-bundle", "",
		authHeadersForPersona("owner_hb_self", "sa_hb_self"))
	if rec.Code != http.StatusOK {
		t.Fatalf("homepage-bundle owner: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)

	profile, ok := body["profile"].(map[string]any)
	if !ok || profile["personaId"] != "sa_hb_self" {
		t.Fatalf("expected profile.personaId=sa_hb_self, got %#v", body["profile"])
	}

	stats, ok := body["stats"].(map[string]any)
	if !ok {
		t.Fatalf("expected stats object, got %#v", body["stats"])
	}
	if stats["followerCount"] != float64(128) || stats["followingCount"] != float64(42) ||
		stats["postCount"] != float64(17) || stats["circleCount"] != float64(6) || stats["likeCount"] != float64(333) {
		t.Fatalf("stats counts mismatch identity truth, got %#v", stats)
	}

	tabCounts, ok := body["tabCounts"].(map[string]any)
	if !ok {
		t.Fatalf("expected tabCounts object, got %#v", body["tabCounts"])
	}
	if tabCounts["worksCount"] != float64(17) || tabCounts["likesCount"] != float64(333) ||
		tabCounts["circlesCount"] != float64(6) {
		t.Fatalf("tabCounts mismatch identity truth, got %#v", tabCounts)
	}
	// collectionsCount 属 content 域，user 域不造假返回 0。
	if tabCounts["collectionsCount"] != float64(0) {
		t.Fatalf("expected collectionsCount=0 (content domain owns it), got %#v", tabCounts["collectionsCount"])
	}

	viewerContext, ok := body["viewerContext"].(map[string]any)
	if !ok {
		t.Fatalf("expected viewerContext object, got %#v", body["viewerContext"])
	}
	if viewerContext["isOwner"] != true {
		t.Fatalf("expected isOwner=true for self view, got %#v", viewerContext)
	}
	if viewerContext["isGuest"] != false {
		t.Fatalf("expected isGuest=false for authed view, got %#v", viewerContext)
	}
	if viewerContext["relationToTarget"] != "self" {
		t.Fatalf("expected relationToTarget=self, got %#v", viewerContext["relationToTarget"])
	}

	if cacheVersion, _ := body["cacheVersion"].(string); cacheVersion == "" {
		t.Fatalf("expected non-empty cacheVersion, got %#v", body["cacheVersion"])
	}
}

func TestHomepageBundle_ProfileCarriesBackgroundAndNicknameCustomized(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	seedHomepageOwner(t, "owner_hb_profile", "sa_hb_profile", "hb_profile", "主页封面分身", "open")
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET nickname_customized = true WHERE persona_id = $1`,
		"sa_hb_profile",
	); err != nil {
		t.Fatalf("seed homepage bundle nickname_customized: %v", err)
	}
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET avatar_url = $1, avatar_version = $2 WHERE persona_id = $3`,
		"https://cdn.example.com/homepage-bundle-avatar.png",
		5,
		"sa_hb_profile",
	); err != nil {
		t.Fatalf("seed homepage bundle avatar version: %v", err)
	}
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE personas SET background_url = $1 WHERE persona_id = $2`,
		"https://cdn.example.com/homepage-bundle-cover.png",
		"sa_hb_profile",
	); err != nil {
		t.Fatalf("seed homepage bundle background: %v", err)
	}

	rec := doRequest(t, http.MethodGet, "/user/personas/hb_profile/homepage-bundle", "",
		authHeadersForPersona("owner_hb_profile", "sa_hb_profile"))
	if rec.Code != http.StatusOK {
		t.Fatalf("homepage-bundle owner profile fields: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	profile, ok := body["profile"].(map[string]any)
	if !ok {
		t.Fatalf("expected profile object, got %#v", body["profile"])
	}
	if profile["backgroundUrl"] != "https://cdn.example.com/homepage-bundle-cover.png" {
		t.Fatalf("expected backgroundUrl in homepage bundle profile, got %#v", profile["backgroundUrl"])
	}
	if profile["nicknameCustomized"] != true {
		t.Fatalf("expected nicknameCustomized=true for customized persona homepage, got %#v", profile["nicknameCustomized"])
	}
	if profile["avatarUrl"] != "https://cdn.example.com/homepage-bundle-avatar.png?v=5" {
		t.Fatalf("expected versioned avatarUrl in homepage bundle profile, got %#v", profile["avatarUrl"])
	}
	if profile["avatarVersion"] != float64(5) {
		t.Fatalf("expected avatarVersion=5 in homepage bundle profile, got %#v", profile["avatarVersion"])
	}
}

func TestHomepageBundle_GuestViewOmitsRelationshipCapability(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	seedHomepageOwner(t, "owner_hb_guest", "sa_hb_guest", "hb_guest", "游客可见主页", "open")

	// 无鉴权头 = 游客态。
	rec := doRequest(t, http.MethodGet, "/user/personas/hb_guest/homepage-bundle", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("homepage-bundle guest: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)

	if _, ok := body["profile"].(map[string]any); !ok {
		t.Fatalf("guest should still read public profile, got %#v", body["profile"])
	}
	viewerContext, ok := body["viewerContext"].(map[string]any)
	if !ok {
		t.Fatalf("expected viewerContext, got %#v", body["viewerContext"])
	}
	if viewerContext["isGuest"] != true {
		t.Fatalf("expected isGuest=true for unauthenticated view, got %#v", viewerContext)
	}
	if viewerContext["isOwner"] != false {
		t.Fatalf("expected isOwner=false for guest, got %#v", viewerContext)
	}
	// 游客态不下发关系能力（端按 nil 走未登录引导，不造假）。
	if cap := body["relationshipCapability"]; cap != nil {
		t.Fatalf("guest should not receive relationshipCapability, got %#v", cap)
	}
}

func TestHomepageBundle_StrangerViewExposesRelationToTarget(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	seedHomepageOwner(t, "owner_hb_target", "sa_hb_target", "hb_target", "陌生人目标", "open")
	createTestProfile(t, "owner_hb_viewer", "陌生访客")
	createTestPersonaFull(t, "persona_hb_viewer", "owner_hb_viewer", "sa_hb_viewer", "陌生访客", "open", true, true)

	rec := doRequest(t, http.MethodGet, "/user/personas/hb_target/homepage-bundle", "",
		authHeadersForPersona("owner_hb_viewer", "sa_hb_viewer"))
	if rec.Code != http.StatusOK {
		t.Fatalf("homepage-bundle stranger: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)

	viewerContext, ok := body["viewerContext"].(map[string]any)
	if !ok {
		t.Fatalf("expected viewerContext, got %#v", body["viewerContext"])
	}
	if viewerContext["isOwner"] != false || viewerContext["isGuest"] != false {
		t.Fatalf("expected stranger authed view isOwner=false isGuest=false, got %#v", viewerContext)
	}
	if viewerContext["relationToTarget"] != "not_following" {
		t.Fatalf("expected relationToTarget=not_following for stranger, got %#v", viewerContext["relationToTarget"])
	}

	capability, ok := body["relationshipCapability"].(map[string]any)
	if !ok {
		t.Fatalf("authed stranger should receive relationshipCapability, got %#v", body["relationshipCapability"])
	}
	if capability["canFollow"] != true {
		t.Fatalf("expected stranger canFollow=true, got %#v", capability)
	}
	if capability["relationState"] != "not_following" {
		t.Fatalf("expected capability.relationState=not_following, got %#v", capability["relationState"])
	}
}

func TestHomepageBundle_StrictPersonaReturnsNotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	seedHomepageOwner(t, "owner_hb_strict", "sa_hb_strict", "hb_strict", "严格隔离主页", "strict")
	seedHomepageOwner(t, "owner_hb_viewer2", "sa_hb_viewer2", "hb_viewer2", "访问者主页", "open")

	rec := doRequest(t, http.MethodGet, "/user/personas/hb_strict/homepage-bundle", "",
		authHeadersForPersona("owner_hb_viewer2", "sa_hb_viewer2"))
	if rec.Code != http.StatusNotFound {
		t.Fatalf("strict persona homepage-bundle should 404, got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestHomepageBundle_DoesNotLeakContentDomainFacts 守护架构红线：user 域 bundle 不得聚合
// content / intersection 事实（交集卡、影响力 evidence 由 content 域端侧并发拉取）。
func TestHomepageBundle_DoesNotLeakContentDomainFacts(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	seedHomepageOwner(t, "owner_hb_redline", "sa_hb_redline", "hb_redline", "红线主页", "open")

	rec := doRequest(t, http.MethodGet, "/user/personas/hb_redline/homepage-bundle", "",
		authHeadersForPersona("owner_hb_redline", "sa_hb_redline"))
	if rec.Code != http.StatusOK {
		t.Fatalf("homepage-bundle: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	for _, forbidden := range []string{"intersections", "intersectionCards", "authorImpact", "impactItems", "evidence", "feed"} {
		if _, leaked := body[forbidden]; leaked {
			t.Fatalf("user-domain bundle must not carry content fact %q, got keys %#v", forbidden, body)
		}
	}
}
