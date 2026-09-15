package bootstrap

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/auth"
)

// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
// 本白盒用 owning persistence provider state 验证生产 bootstrap seam；仅使用独立临时 Mongo，不触碰业务库。
func TestActiveReleaseFenceBootstrapTransport(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("content_fence_bootstrap"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		cleanup, stop := context.WithTimeout(context.Background(), 30*time.Second)
		defer stop()
		_ = runtime.Close(cleanup)
	})
	mux := http.NewServeMux()
	registerActiveReleaseFence(mux, runtime.Database, "gamma")
	cfg := auth.TokenConfig{Secret: []byte("0123456789abcdef0123456789abcdef"), Issuer: "https://auth.quwoquan.test", Audience: "quwoquan-api", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute, ClockSkew: time.Second}
	verifier, err := auth.NewHS256Verifier(cfg)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.RequireGeneratedOperationAuthorization(operationsecurity.ForDomain("content"))(mux)))
	defer server.Close()
	call := func(scope string) (int, map[string]any) {
		t.Helper()
		req, _ := http.NewRequest(http.MethodGet, server.URL+"/internal/content/active-release-fence?environment=gamma&sourceOwner=qwq_data", nil)
		if scope != "" {
			credentials, e := auth.NewHS256ServiceAuthorizationProvider(cfg, "tag-service", []string{scope})
			if e != nil {
				t.Fatal(e)
			}
			header, e := credentials.AuthorizationHeader(ctx)
			if e != nil {
				t.Fatal(e)
			}
			req.Header.Set("Authorization", header)
		}
		resp, e := server.Client().Do(req)
		if e != nil {
			t.Fatal(e)
		}
		defer resp.Body.Close()
		var body map[string]any
		if e := json.NewDecoder(resp.Body).Decode(&body); e != nil {
			t.Fatal(e)
		}
		return resp.StatusCode, body
	}
	if status, _ := call(""); status != http.StatusUnauthorized {
		t.Fatalf("anonymous status=%d", status)
	}
	if status, _ := call("content.media.reference.read"); status != http.StatusForbidden {
		t.Fatalf("wrong scope status=%d", status)
	}
	if status, body := call("content.release.fence.read"); status != http.StatusOK || body["found"] != false || body["environment"] != "gamma" || body["activatedAt"] != nil {
		t.Fatalf("empty pointer=%d %+v", status, body)
	}
	now := time.Now().UTC().Truncate(time.Millisecond)
	if _, err := runtime.Database.Collection("data_release_state").InsertOne(ctx, bson.M{
		"kind": "active_pointer", "environment": "gamma", "sourceOwner": "qwq_data",
		"status": "active", "activeReleaseId": "release-a",
		"manifestDigest":    "sha256:" + strings.Repeat("a", 64),
		"projectionVersion": int64(1), "revision": int64(3), "activatedAt": now,
	}); err != nil {
		t.Fatal(err)
	}
	if status, body := call("content.release.fence.read"); status != http.StatusOK || body["releaseId"] != "release-a" || body["revision"] != float64(3) {
		t.Fatalf("found=%d %+v", status, body)
	}
	// 存储损坏专项：不完整 pointer 不得伪装成 absent 或 prior。
	if _, err := runtime.Database.Collection("data_release_state").UpdateOne(ctx, bson.M{"kind": "active_pointer"}, bson.M{"$set": bson.M{"revision": 0}}); err != nil {
		t.Fatal(err)
	}
	if status, body := call("content.release.fence.read"); status != http.StatusInternalServerError || body["code"] != "CONTENT.SYSTEM.storage_read_failed" {
		t.Fatalf("drift=%d %+v", status, body)
	}
	for _, corrupt := range []bson.M{{"revision": int64(3), "activeReleaseId": ""}, {"activeReleaseId": "release-a", "status": "verified"}} {
		if _, err := runtime.Database.Collection("data_release_state").UpdateOne(ctx, bson.M{"kind": "active_pointer"}, bson.M{"$set": corrupt}); err != nil {
			t.Fatal(err)
		}
		if status, body := call("content.release.fence.read"); status != http.StatusInternalServerError || body["code"] != "CONTENT.SYSTEM.storage_read_failed" {
			t.Fatalf("malformed pointer hidden as absent=%d %+v", status, body)
		}
	}
}
