// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-005
// readiness_case: list-user-posts-api
// L2 契约测试：Post 业务对象 — 用户创作列表
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	accessinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/accesscontrol"
)

// contentPostProjectionWireFields 是 contracts/content/post/projections/
// content_post_projection.yaml 声明的 wire 白名单。App generated decoder
// （ContentPostProjection.fromWire）reject unknown fields，因此服务端响应
// item 出现任何白名单之外的键都会让作者主页整页解码失败。
var contentPostProjectionWireFields = map[string]struct{}{
	"postId": {}, "contentType": {}, "contentIdentity": {}, "assistantUsePolicy": {},
	"authorId": {}, "authorDisplayName": {}, "authorAvatarUrl": {}, "authorBackgroundUrl": {},
	"authorRoleLabel": {}, "authorIdentityTags": {}, "authorVerified": {},
	"title": {}, "body": {}, "summary": {}, "coverUrl": {},
	"articleTemplate": {}, "articleFontPreset": {},
	"mediaUrls": {}, "videoUrl": {}, "mediaAssetId": {}, "mediaAssetVersion": {},
	"hlsCmafMasterManifestUrl": {}, "hlsCmafDescriptorVersion": {},
	"thumbnailUrl": {}, "width": {}, "height": {}, "durationMs": {},
	"likeCount": {}, "commentCount": {}, "shareCount": {}, "viewerLiked": {},
	"primaryHomepageId": {}, "primaryHomepageType": {}, "gatheringRef": {},
	"createdAt": {}, "updatedAt": {}, "publishedAt": {},
	"contentVertical": {}, "recallPath": {}, "supplySource": {}, "intersectionReasons": {},
}

// assertContentPostProjectionWire 断言单个 wire item 是 ContentPostProjection
// 契约子集且必填字段在位；契约外字段（如既往泄露的 status/visibility/viewCount/
// authorDisplayNameSnapshot）出现即失败。
func assertContentPostProjectionWire(t *testing.T, item map[string]any, path string) {
	t.Helper()
	for key := range item {
		if _, ok := contentPostProjectionWireFields[key]; !ok {
			t.Errorf(
				"%s carries non-contract wire field %q; "+
					"App ContentPostProjection decoder rejects unknown fields",
				path, key,
			)
		}
	}
	for _, required := range []string{"postId", "contentType", "likeCount", "commentCount", "shareCount"} {
		if _, ok := item[required]; !ok {
			t.Errorf("%s is missing required contract field %q", path, required)
		}
	}
}

func TestListUserPosts(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	authorID := "author_list_test"
	for i := 0; i < 3; i++ {
		submitPublishedPostWithAuthor(t, authorID, `{"contentType":"image","title":"user post"}`)
	}
	submitPublishedPostWithAuthor(t, "other_author", `{"contentType":"image","title":"other post"}`)

	req := httptest.NewRequest(http.MethodGet, "/content/personas/"+authorID+"/posts?limit=20", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	items, _ := resp["items"].([]any)
	if len(items) != 3 {
		t.Errorf("expected 3 user posts, got %d", len(items))
	}

	// wire 契约：页 wrapper 与逐 item 白名单必须是 AuthorPostPageSlice /
	// ContentPostProjection 契约子集（App decoder fail-closed）。
	pageWireFields := map[string]struct{}{"items": {}, "nextCursor": {}, "hasMore": {}}
	for key := range resp {
		if _, ok := pageWireFields[key]; !ok {
			t.Errorf("AuthorPostPageSlice carries non-contract wire field %q", key)
		}
	}
	for i, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("items[%d] is not an object: %T", i, raw)
		}
		assertContentPostProjectionWire(t, item, fmt.Sprintf("items[%d]", i))
	}
}

func TestListUserPostsEmpty(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	req := httptest.NewRequest(http.MethodGet, "/content/personas/nonexistent_user/posts?limit=20", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &resp)
	items, _ := resp["items"].([]any)
	if len(items) != 0 {
		t.Errorf("expected 0 posts for nonexistent user, got %d", len(items))
	}
}

// SIT 负例：作者拉黑 viewer 后，viewer 经真实 HTTP 读作者主页作品列表必须为空；
// 服务端凭 PersonaBlocked 事实投影强制，不依赖客户端 X-Blocked-User-Ids。
func TestListUserPostsBlockedViewerReceivesEmptyPage(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	access := db.Collection(accessinfra.ContentPersonaAccessProjectionCollection)
	authorID := "author_block_list_test"
	viewerID := "viewer_blocked_list_test"
	cleanup := func() {
		cleanPosts(t)
		_, _ = access.DeleteMany(ctx, bson.M{"sourcePersonaId": bson.M{"$in": []string{authorID, viewerID}}})
		_, _ = db.Collection(accessinfra.ContentPersonaAccessInboxCollection).DeleteMany(ctx, bson.M{"eventId": bson.M{"$regex": "^block_list_"}})
	}
	cleanup()
	t.Cleanup(cleanup)

	post := submitPublishedPostWithAuthor(
		t,
		authorID,
		`{"contentType":"image","title":"blocked author post"}`,
	)
	postID := asTestString(post["postId"])
	if postID == "" {
		t.Fatalf("published Post is missing postId: %+v", post)
	}

	// 经真实投影链路写入 block 事实（author 拉黑 viewer）。
	projector := accessinfra.NewPersonaAccessProjection(db)
	if err := projector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure projection indexes: %v", err)
	}
	if err := projector.Apply(ctx, accessinfra.PersonaRelationshipEvent{
		EventID:         "block_list_evt_1",
		EventName:       accessinfra.PersonaBlocked,
		PairID:          "block_list_pair",
		SourcePersonaID: authorID,
		TargetPersonaID: viewerID,
		Version:         1,
		OccurredAt:      time.Now().UTC(),
	}); err != nil {
		t.Fatalf("project block event: %v", err)
	}

	// 被拉黑 viewer：空页。
	req := httptest.NewRequest(http.MethodGet, "/content/personas/"+authorID+"/posts?limit=20", nil)
	req.Header.Set("X-Client-Persona-Id", viewerID)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 empty page for blocked viewer, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if items, _ := resp["items"].([]any); len(items) != 0 {
		t.Fatalf("blocked viewer must not see author posts, got %d items", len(items))
	}
	detailReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	detailReq.Header.Set("X-Client-Persona-Id", viewerID)
	detailRec := httptest.NewRecorder()
	testHandler.ServeHTTP(detailRec, detailReq)
	if detailRec.Code != http.StatusNotFound {
		t.Fatalf(
			"blocked viewer must not read Post detail, got %d: %s",
			detailRec.Code,
			detailRec.Body.String(),
		)
	}

	// 无关 viewer：仍可见。
	req = httptest.NewRequest(http.MethodGet, "/content/personas/"+authorID+"/posts?limit=20", nil)
	req.Header.Set("X-Client-Persona-Id", "viewer_unrelated_list_test")
	rec = httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for unrelated viewer, got %d: %s", rec.Code, rec.Body.String())
	}
	resp = map[string]any{}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if items, _ := resp["items"].([]any); len(items) != 1 {
		t.Fatalf("unrelated viewer must see author posts, got %d items", len(items))
	}

	// 作者本人：不受影响。
	req = httptest.NewRequest(http.MethodGet, "/content/personas/"+authorID+"/posts?limit=20", nil)
	req.Header.Set("X-Client-Persona-Id", authorID)
	rec = httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for owner, got %d: %s", rec.Code, rec.Body.String())
	}
}
