package tests

import (
	"net/http"
	"testing"
)

func TestProfileSubjectView_GetMeProfileUsesActiveSubAccount(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_me_profile", "owner_me")
	createTestPersonaFull(t, "persona_active_me", "owner_me_profile", "sa_me_profile", "摄影分身", "open", true, true)

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
	if body["subjectType"] != "sub_account" {
		t.Fatalf("expected subjectType=sub_account, got %v", body["subjectType"])
	}
	if body["displayName"] != "摄影分身" {
		t.Fatalf("expected displayName=摄影分身, got %v", body["displayName"])
	}
}

func TestProfileSubjectView_GetSubAccountProfile(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "owner_public_profile", "owner_public")
	createTestPersonaFull(t, "persona_public", "owner_public_profile", "sa_public_profile", "公开分身", "open", true, true)

	rec := doRequest(t, http.MethodGet, "/v1/user/sa_public_profile", "", authHeaders("viewer_subject"))
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
	if body["displayName"] != "公开分身" {
		t.Fatalf("expected displayName=公开分身, got %v", body["displayName"])
	}
}

func TestRelationshipCapabilityView_States(t *testing.T) {
	if mongoDB == nil {
		t.Skip("mongo unavailable; skip follow-edge capability state transitions")
	}
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "viewer_rel", "viewer_rel")
	createTestProfile(t, "target_rel", "target_rel")

	rec := doRequest(t, http.MethodGet, "/v1/user/target_rel/relationship/capability", "", authHeaders("viewer_rel"))
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

	followRec := doRequest(t, http.MethodPost, "/v1/user/follow/target_rel", "", authHeaders("viewer_rel"))
	if followRec.Code != http.StatusOK {
		t.Fatalf("follow target: expected 200, got %d: %s", followRec.Code, followRec.Body.String())
	}
	rec = doRequest(t, http.MethodGet, "/v1/user/target_rel/relationship/capability", "", authHeaders("viewer_rel"))
	body = parseJSON(t, rec)
	if body["relationState"] != "following" {
		t.Fatalf("expected relationState=following, got %v", body["relationState"])
	}
	if body["canUnfollow"] != true {
		t.Fatalf("expected canUnfollow=true, got %v", body["canUnfollow"])
	}

	followBackRec := doRequest(t, http.MethodPost, "/v1/user/follow/viewer_rel", "", authHeaders("target_rel"))
	if followBackRec.Code != http.StatusOK {
		t.Fatalf("target follow viewer: expected 200, got %d: %s", followBackRec.Code, followBackRec.Body.String())
	}
	rec = doRequest(t, http.MethodGet, "/v1/user/target_rel/relationship/capability", "", authHeaders("viewer_rel"))
	body = parseJSON(t, rec)
	if body["relationState"] != "mutual" {
		t.Fatalf("expected relationState=mutual, got %v", body["relationState"])
	}
	if body["canStartVoiceCall"] != true || body["canStartVideoCall"] != true {
		t.Fatalf("expected mutual state to enable voice/video, got %#v", body)
	}
}
