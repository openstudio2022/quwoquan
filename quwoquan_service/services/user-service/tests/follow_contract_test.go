package tests

import (
	"context"
	"net/http"
	"testing"
)

func TestFollow_Success(t *testing.T) {
	if mongoDB == nil {
		t.Skip("MongoDB unavailable - skipping follow test")
	}
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "follower_1", "follower1")
	createTestProfile(t, "followee_1", "followee1")

	rec := doRequest(t, http.MethodPost, "/v1/user/follow/followee_1", "", authHeaders("follower_1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var count int64
	err := pgPool.QueryRow(context.Background(),
		"SELECT follower_count FROM user_profiles WHERE user_id = $1", "followee_1").Scan(&count)
	if err != nil {
		t.Fatalf("query follower_count: %v", err)
	}
	if count != 1 {
		t.Errorf("expected follower_count=1, got %d", count)
	}
}

func TestFollow_Idempotent(t *testing.T) {
	if mongoDB == nil {
		t.Skip("MongoDB unavailable")
	}
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "follower_2", "follower2")
	createTestProfile(t, "followee_2", "followee2")

	doRequest(t, http.MethodPost, "/v1/user/follow/followee_2", "", authHeaders("follower_2"))
	rec := doRequest(t, http.MethodPost, "/v1/user/follow/followee_2", "", authHeaders("follower_2"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var count int64
	_ = pgPool.QueryRow(context.Background(),
		"SELECT follower_count FROM user_profiles WHERE user_id = $1", "followee_2").Scan(&count)
	if count != 1 {
		t.Errorf("expected follower_count=1 after idempotent follow, got %d", count)
	}
}

func TestUnfollow_Success(t *testing.T) {
	if mongoDB == nil {
		t.Skip("MongoDB unavailable")
	}
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "follower_3", "follower3")
	createTestProfile(t, "followee_3", "followee3")

	doRequest(t, http.MethodPost, "/v1/user/follow/followee_3", "", authHeaders("follower_3"))
	rec := doRequest(t, http.MethodDelete, "/v1/user/follow/followee_3", "", authHeaders("follower_3"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var count int64
	_ = pgPool.QueryRow(context.Background(),
		"SELECT follower_count FROM user_profiles WHERE user_id = $1", "followee_3").Scan(&count)
	if count != 0 {
		t.Errorf("expected follower_count=0 after unfollow, got %d", count)
	}
}

func TestGetRelationship_Mutual(t *testing.T) {
	if mongoDB == nil {
		t.Skip("MongoDB unavailable")
	}
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "user_a", "user_a")
	createTestProfile(t, "user_b", "user_b")

	doRequest(t, http.MethodPost, "/v1/user/follow/user_b", "", authHeaders("user_a"))
	doRequest(t, http.MethodPost, "/v1/user/follow/user_a", "", authHeaders("user_b"))

	rec := doRequest(t, http.MethodGet, "/v1/users/user_b/relationship", "", authHeaders("user_a"))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	if result["isMutual"] != true {
		t.Errorf("expected isMutual=true, got %v", result["isMutual"])
	}
}

func TestListFollowing_Pagination(t *testing.T) {
	if mongoDB == nil {
		t.Skip("MongoDB unavailable")
	}
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "paginator", "paginator")
	for i := 0; i < 5; i++ {
		uid := "target_" + string(rune('a'+i))
		createTestProfile(t, uid, "target_"+string(rune('a'+i)))
		doRequest(t, http.MethodPost, "/v1/user/follow/"+uid, "", authHeaders("paginator"))
	}

	rec := doRequest(t, http.MethodGet, "/v1/users/paginator/following?limit=3", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	result := parseJSON(t, rec)
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("missing items field")
	}
	if len(items) != 3 {
		t.Errorf("expected 3 items, got %d", len(items))
	}
}
