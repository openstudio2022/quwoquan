// L2 契约测试：Post 业务对象 — 正常 CRUD 操作
//
// 守护：创建/读取接口的正常路径，field 正确持久化和响应。
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	contenhttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

// TestSubmitPostPublicationCreatesPublishedPost verifies the only public create ABI.
func TestSubmitPostPublicationCreatesPublishedPost(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	result := submitPublishedPostWithAuthor(
		t,
		"user_test_001",
		`{"body":"golden hour photography","contentType":"micro"}`,
	)
	if result["postId"] == nil {
		t.Error("response missing _id field")
	}
	if result["contentType"] != "micro" {
		t.Errorf("expected contentType=micro, got %v", result["contentType"])
	}
	if result["authorId"] != "user_test_001" {
		t.Errorf("expected authorId=user_test_001, got %v", result["authorId"])
	}
	if result["status"] != "published" {
		t.Errorf("expected status=published after submit, got %v", result["status"])
	}
}

// TestSubmitPostPublicationAllTypes verifies all public content variants.
func TestSubmitPostPublicationAllTypes(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	cases := []struct {
		contentType string
		extra       string
	}{
		{"image", `"body":"image publication"`},
		{"video", `"body":"video publication"`},
		{"micro", `"body":"quick thought"`},
		{"article", `"title":"Deep work tips","articleMarkdown":"# Deep work tips\n\nFocus is a skill","markdownDialect":"qwq-rich-md","articleAssetManifest":{"schema":"article-asset-manifest","assets":[]}`},
	}
	for _, tc := range cases {
		t.Run(tc.contentType, func(t *testing.T) {
			var payload map[string]any
			if err := json.Unmarshal(
				[]byte(fmt.Sprintf(`{"contentType":%q,%s}`, tc.contentType, tc.extra)),
				&payload,
			); err != nil {
				t.Fatal(err)
			}
			if tc.contentType == "image" || tc.contentType == "video" {
				assetID := createReadyPublicationMediaAsset(
					t,
					identity.AnonymousFallbackPersonaID,
					tc.contentType,
				)
				payload["mediaAssetIds"] = []string{assetID}
			}
			encoded, err := json.Marshal(payload)
			if err != nil {
				t.Fatal(err)
			}
			result := submitPublishedPost(t, string(encoded))
			if result["contentType"] != tc.contentType {
				t.Errorf("contentType=%s: response contentType mismatch: got %v", tc.contentType, result["contentType"])
			}
			if result["status"] != "published" {
				t.Errorf("contentType=%s: expected status=published, got %v", tc.contentType, result["status"])
			}
		})
	}
}

func TestSubmitPostPublicationReturnsStablePublishedPost(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	published := submitPublishedPostWithAuthor(t, "publish_author", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"待发布作品",
		"body":"原子发布",
		"visibility":"public",
		"assistantUsePolicy":"inherit"
	}`)
	postID, _ := published["postId"].(string)
	if postID == "" {
		t.Fatal("published post missing postId")
	}
	if published["status"] != "published" {
		t.Fatalf("expected status=published, got %v", published["status"])
	}
	if published["publishedAt"] == nil || published["publishedAt"] == "" {
		t.Fatalf("expected publishedAt set, got %v", published["publishedAt"])
	}
}

// TestSubmitPostPublicationOutboxProjectionCommercialChain proves the atomic
// publication fact drives independent durable projections exactly once.
func TestSubmitPostPublicationOutboxProjectionCommercialChain(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	eventSpy.Reset()

	published := submitPublishedPostWithAuthor(t, "commercial_chain_author", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"端云对象闭环",
		"articleMarkdown":"# 端云对象闭环\n\nDurable outbox first.",
		"markdownDialect":"qwq-rich-md",
		"articleAssetManifest":{"assets":[]}
	}`)
	postID, _ := published["postId"].(string)
	if postID == "" {
		t.Fatal("published post missing postId")
	}

	publishedEvents := eventSpy.EventsOfType("PostPublished")
	if len(publishedEvents) != 1 {
		t.Fatalf("durable publication fact mismatch: published=%d", len(publishedEvents))
	}
	if publishedEvents[0].EventID == "" {
		t.Fatal("stable publication event identity missing")
	}

	var projection struct {
		PostID string `bson:"postId"`
		Status string `bson:"status"`
		Title  string `bson:"title"`
	}
	if err := mongoDB.Collection("rm_discovery_feed").FindOne(
		context.Background(),
		bson.M{"postId": postID},
	).Decode(&projection); err != nil {
		t.Fatalf("PostPublished discovery projection missing: %v", err)
	}
	if projection.Status != "published" || projection.Title != "端云对象闭环" {
		t.Fatalf("discovery projection did not converge: %+v", projection)
	}

	checkpointCount, err := mongoDB.Collection("projection_checkpoints").CountDocuments(
		context.Background(),
		bson.M{"_id": bson.M{"$in": []string{
			"post:api-integration-event-spy",
			"post:api-integration-discovery-projection",
		}}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if checkpointCount != 2 {
		t.Fatalf("expected independent event/projection checkpoints, got %d", checkpointCount)
	}

	drainPostOutbox(t)
	if got := len(eventSpy.EventsOfType("PostPublished")); got != 1 {
		t.Fatalf("replay duplicated PostPublished event: got %d", got)
	}
}

// TestDeletePostContract verifies deleting a published post tombstones the
// aggregate and GET then returns the metadata-defined non-disclosing not-found.
func TestDeletePostContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPostWithAuthor(t, "delete_author", `{
		"contentType":"micro",
		"contentIdentity":"moment",
		"body":"准备删除的点滴"
	}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("published post missing _id")
	}

	req := httptest.NewRequest(http.MethodDelete, "/content/posts/"+postID, nil)
	req.Header.Set("X-Client-User-Id", "delete_author")
	ensureIdempotencyHeader(req, "delete-post")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	tombstones := requireMongoDB(t).Collection("deleted_post_tombstones")
	count, err := tombstones.CountDocuments(
		t.Context(),
		bson.M{"_id": postID, "postId": postID},
	)
	if err != nil || count != 1 {
		t.Fatalf("delete tombstone count=%d err=%v", count, err)
	}

	replayReq := httptest.NewRequest(http.MethodDelete, "/content/posts/"+postID, nil)
	replayReq.Header.Set("X-Client-User-Id", "delete_author")
	ensureIdempotencyHeader(replayReq, "delete-post-replay")
	replayRec := httptest.NewRecorder()
	testHandler.ServeHTTP(replayRec, replayReq)
	if replayRec.Code != http.StatusOK {
		t.Fatalf(
			"repeated delete expected 200, got %d: %s",
			replayRec.Code,
			replayRec.Body.String(),
		)
	}
	count, err = tombstones.CountDocuments(t.Context(), bson.M{"_id": postID})
	if err != nil || count != 1 {
		t.Fatalf("repeated delete duplicated tombstone: count=%d err=%v", count, err)
	}

	getReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	getReq.Header.Set("X-Client-User-Id", "delete_author")
	getRec := httptest.NewRecorder()
	testHandler.ServeHTTP(getRec, getReq)
	// 墓碑保留期语义：删除后读取按 content_deleted 返回 410（非 404）。
	if getRec.Code != http.StatusGone {
		t.Fatalf("expected 410 after delete, got %d: %s", getRec.Code, getRec.Body.String())
	}
	if !strings.Contains(getRec.Body.String(), "CONTENT.USER.content_deleted") {
		t.Fatalf("deleted post read must map content_deleted, got %s", getRec.Body.String())
	}
}

func TestGetDeletedPostAfterServiceRestartStillReturnsTombstone(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPostWithAuthor(t, "delete_restart_author", `{
		"contentType":"micro",
		"contentIdentity":"moment",
		"body":"准备删除后重启再读取"
	}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("published post missing _id")
	}

	deleteReq := httptest.NewRequest(http.MethodDelete, "/content/posts/"+postID, nil)
	deleteReq.Header.Set("X-Client-User-Id", "delete_restart_author")
	ensureIdempotencyHeader(deleteReq, "delete-post-before-restart")
	deleteRec := httptest.NewRecorder()
	testHandler.ServeHTTP(deleteRec, deleteReq)
	if deleteRec.Code != http.StatusOK {
		t.Fatalf("expected 200 delete, got %d: %s", deleteRec.Code, deleteRec.Body.String())
	}

	restartedStore := persistence.NewMongoPostStore(mongoDB.Collection("posts"))
	restartedHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.TrimSpace(r.Header.Get("X-Client-Persona-Id")) == "" {
			personaID := identity.AnonymousFallbackPersonaID
			if userID := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); userID != "" {
				personaID = userID
			}
			r.Header.Set("X-Client-Persona-Id", personaID)
		}
		contenhttp.NewContentHandler(
			nil,
			postapp.BindFacades(
				postapp.NewPostService(postapp.BindDataPorts(restartedStore)),
			),
			postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
				Detail: persistence.NewMongoPostQueryReader(mongoDB.Collection("posts")),
			}),
			nil,
			nil,
			nil,
			nil,
		).Routes().ServeHTTP(w, r)
	})

	getReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	getReq.Header.Set("X-Client-User-Id", "delete_restart_author")
	getRec := httptest.NewRecorder()
	restartedHandler.ServeHTTP(getRec, getReq)
	// 软删文档在保留期内持续存在：服务重启后读取仍按墓碑语义返回 410 content_deleted，
	// 不回退 404（TTL 到期文档消失后才回落 404）。
	if getRec.Code != http.StatusGone {
		t.Fatalf("expected 410 after restart for deleted post, got %d: %s", getRec.Code, getRec.Body.String())
	}
	if !strings.Contains(getRec.Body.String(), "CONTENT.USER.content_deleted") {
		t.Fatalf("deleted post read after restart must map content_deleted, got %s", getRec.Body.String())
	}
}

// TestGetPostSuccess creates a post then retrieves it by ID and checks basic fields.
// contract.yaml: get_post_success / go_func: TestGetPostSuccess
func TestGetPostSuccess(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPost(t, `{"contentType":"image","title":"Test Get","body":"visible post"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("created post has no _id")
	}

	req := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if result["postId"] != postID {
		t.Errorf("expected postId=%s, got %v", postID, result["postId"])
	}
}

// TestGetPostNotFound verifies GET /content/content/posts/{id} returns 404 with
// structured error code when the post does not exist.
// contract.yaml: get_post_not_found / go_func: TestGetPostNotFound
func TestGetPostNotFound(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/content/posts/nonexistent_id_xyz", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	code, _ := body["code"].(string)
	if code == "" {
		t.Error("error response missing 'code' field")
	}
	// Error code must belong to CONTENT domain
	if len(code) < 7 || code[:7] != "CONTENT" {
		t.Errorf("error code should start with 'CONTENT', got %q", code)
	}
}

func TestUpdatePostSettingsForbidden(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPostWithAuthor(t, "user_owner", `{"contentType":"micro","body":"owner post"}`)
	postID, _ := created["postId"].(string)

	patchReq := httptest.NewRequest(
		http.MethodPatch, "/content/posts/"+postID+"/settings",
		strings.NewReader(`{"visibility":"private"}`),
	)
	patchReq.Header.Set("Content-Type", "application/json")
	patchReq.Header.Set("X-Client-User-Id", "user_hacker")
	patchRec := httptest.NewRecorder()
	testHandler.ServeHTTP(patchRec, patchReq)

	if patchRec.Code != http.StatusForbidden {
		t.Fatalf(
			"update by non-owner status = %d, want 403: %s",
			patchRec.Code,
			patchRec.Body.String(),
		)
	}
}

func TestPostPublishedEventPublished(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	eventSpy.Reset()

	submitPublishedPost(t, `{"contentType":"micro","body":"event spy test post"}`)

	events := eventSpy.EventsOfType("PostPublished")
	if len(events) == 0 {
		t.Fatal("expected PostPublished event to be published, got none")
	}
	ev := events[0]
	if ev.AggregateType != "Post" {
		t.Errorf("expected AggregateType=Post, got %q", ev.AggregateType)
	}
	if ev.AggregateID == "" {
		t.Error("expected AggregateID to be set")
	}
	if ev.Payload["contentType"] != "micro" {
		t.Errorf("expected payload.contentType=micro, got %v", ev.Payload["contentType"])
	}
	if ev.EventID == "" {
		t.Error("expected durable outbox event identity")
	}

	drainPostOutbox(t)
	if got := len(eventSpy.EventsOfType("PostPublished")); got != 1 {
		t.Fatalf("checkpoint replay published %d PostPublished events, want 1", got)
	}
}

// TestSubmitPostPublicationInvalidContentType verifies that submitting contentType="invalid_type"
// returns 400 with error code CONTENT.USER.invalid_content_type.
func TestSubmitPostPublicationInvalidContentType(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	req := newPostPublicationRequestForTest(
		t,
		"invalid-content-author",
		`{"contentType":"invalid_type","body":"test"}`,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid contentType, got %d: %s", rec.Code, rec.Body.String())
	}
	var errResp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	code, _ := errResp["code"].(string)
	if code != "CONTENT.USER.invalid_content_type" {
		t.Errorf("expected code=CONTENT.USER.invalid_content_type, got %q", code)
	}
}
