package tests

import (
	"net/http"
	"testing"
)

func TestGetProfile_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_001", "alice")
	createTestPersona(t, "p_001", "user_001", "Alice Primary", true, true)

	rec := doRequest(t, http.MethodGet, "/v1/user/profile/user_001", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	profile, ok := result["profile"].(map[string]any)
	if !ok {
		t.Fatal("response missing profile field")
	}
	if profile["userId"] != "user_001" {
		t.Errorf("expected userId=user_001, got %v", profile["userId"])
	}
	if profile["nickname"] != "alice" {
		t.Errorf("expected nickname=alice, got %v", profile["nickname"])
	}
}

func TestGetProfile_NotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	rec := doRequest(t, http.MethodGet, "/v1/user/profile/nonexistent", "", nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["code"] != "USER.USER.not_found" {
		t.Errorf("expected USER.USER.not_found, got %v", result["code"])
	}
}

func TestUpdateProfile_Success(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_002", "bob")

	rec := doRequest(t, http.MethodPatch, "/v1/user/profile",
		`{"nickname":"bob_updated","bio":"hello world","backgroundUrl":"https://cdn.example.com/bg-user-002.png"}`,
		authHeaders("user_002"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["nickname"] != "bob_updated" {
		t.Errorf("expected nickname=bob_updated, got %v", result["nickname"])
	}
	pv, _ := result["profileVersion"].(float64)
	if pv < 2 {
		t.Errorf("expected profileVersion >= 2, got %v", pv)
	}
	if result["nicknameCustomized"] != true {
		t.Errorf("expected nicknameCustomized=true after explicit rename, got %v", result["nicknameCustomized"])
	}
	if result["backgroundUrl"] != "https://cdn.example.com/bg-user-002.png" {
		t.Errorf("expected backgroundUrl to round-trip, got %v", result["backgroundUrl"])
	}
}

func TestUpdateProfile_DuplicateNicknameAllowed(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_003", "charlie")
	createTestProfile(t, "user_004", "david")

	rec := doRequest(t, http.MethodPatch, "/v1/user/profile",
		`{"nickname":"charlie"}`,
		authHeaders("user_004"))
	if rec.Code != http.StatusOK {
		t.Fatalf("duplicate nickname should be allowed, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["nickname"] != "charlie" {
		t.Fatalf("expected duplicate nickname to persist, got %v", result["nickname"])
	}
	if result["nicknameCustomized"] != true {
		t.Fatalf("expected nicknameCustomized=true after rename, got %v", result["nicknameCustomized"])
	}
}

func TestGetProfile_CacheHit(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_005", "eve")

	rec1 := doRequest(t, http.MethodGet, "/v1/user/profile/user_005", "", nil)
	if rec1.Code != http.StatusOK {
		t.Fatalf("first GET: expected 200, got %d", rec1.Code)
	}

	rec2 := doRequest(t, http.MethodGet, "/v1/user/profile/user_005", "", nil)
	if rec2.Code != http.StatusOK {
		t.Fatalf("second GET (cache hit): expected 200, got %d", rec2.Code)
	}
}
