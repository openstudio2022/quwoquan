package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	postapp "quwoquan_service/services/content-service/internal/application/post"
	contentmessaging "quwoquan_service/services/content-service/internal/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

func TestCreatePostPersistsIdentityAndAssistantUsePolicy(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts",
		strings.NewReader(`{
			"contentType":"micro",
			"contentIdentity":"moment",
			"assistantUsePolicy":"exclude",
			"body":"只给自己看的点滴"
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "identity_author")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp["contentIdentity"] != "moment" {
		t.Fatalf("expected contentIdentity=moment, got %v", resp["contentIdentity"])
	}
	if resp["assistantUsePolicy"] != "exclude" {
		t.Fatalf("expected assistantUsePolicy=exclude, got %v", resp["assistantUsePolicy"])
	}
	if resp["status"] != "draft" {
		t.Fatalf("expected status=draft after create, got %v", resp["status"])
	}
}

func TestUpdatePostSettingsContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "settings_author", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"可调整设置的作品",
		"body":"发布内容保持不可变"
	}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("created post must have an id")
	}

	request := httptest.NewRequest(
		http.MethodPatch,
		"/v1/content/posts/"+postID+"/settings",
		strings.NewReader(`{
			"visibility":"private",
			"assistantUsePolicy":"exclude"
		}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-User-Id", "settings_author")
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("update settings status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	var updated map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &updated); err != nil {
		t.Fatalf("decode settings response: %v", err)
	}
	if updated["visibility"] != "private" || updated["assistantUsePolicy"] != "exclude" {
		t.Fatalf("updated settings drifted: %+v", updated)
	}

	ownerRequest := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	ownerRequest.Header.Set("X-Client-User-Id", "settings_author")
	ownerRecorder := httptest.NewRecorder()
	testHandler.ServeHTTP(ownerRecorder, ownerRequest)
	if ownerRecorder.Code != http.StatusOK {
		t.Fatalf("owner read after settings update status=%d body=%s", ownerRecorder.Code, ownerRecorder.Body.String())
	}
	var persisted map[string]any
	if err := json.Unmarshal(ownerRecorder.Body.Bytes(), &persisted); err != nil {
		t.Fatalf("decode persisted post: %v", err)
	}
	if persisted["visibility"] != "private" || persisted["assistantUsePolicy"] != "exclude" {
		t.Fatalf("persisted settings drifted: %+v", persisted)
	}
}

func TestUpdatePostSettingsRejectsRetiredCirclePlacementFields(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "settings_author", `{
		"contentType":"image",
		"contentIdentity":"work",
		"title":"初始作品",
		"mediaUrls":["https://example.com/cover.jpg"]
	}`)
	postID, _ := created["_id"].(string)

	req := httptest.NewRequest(
		http.MethodPatch,
		"/v1/content/posts/"+postID+"/settings",
		strings.NewReader(`{
			"visibility":"public",
			"circleIds":["circle_a","circle_b"],
			"assistantUsePolicy":"exclude"
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "settings_author")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("Post must reject CirclePostPlacement fields, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestPromotePostToWorkContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "promote_author", `{
		"contentType":"micro",
		"contentIdentity":"moment",
		"body":"旅行路上的随手记录",
		"mediaUrls":["https://example.com/travel-1.jpg"]
	}`)
	postID, _ := created["_id"].(string)

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+":promoteToWork",
		strings.NewReader(`{
			"contentType":"image",
			"title":"东京旅行相册",
			"summary":"整理为可长期保存的旅行作品",
			"coverUrl":"https://example.com/travel-cover.jpg",
			"assistantUsePolicy":"exclude"
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "promote_author")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp["_id"] != postID {
		t.Fatalf("expected same post id, got %v", resp["_id"])
	}
	if resp["contentIdentity"] != "work" {
		t.Fatalf("expected contentIdentity=work, got %v", resp["contentIdentity"])
	}
	if resp["contentType"] != "image" {
		t.Fatalf("expected contentType=image, got %v", resp["contentType"])
	}
	if resp["title"] != "东京旅行相册" {
		t.Fatalf("expected title updated, got %v", resp["title"])
	}
}

func TestPromotePostKeepsCountersAndCommentThread(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "promote_thread_author", `{
		"contentType":"micro",
		"contentIdentity":"moment",
		"body":"升级前的点滴"
	}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("expected post id")
	}

	commentReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/comments",
		strings.NewReader(`{"content":"这条评论升级后也要保留"}`),
	)
	commentReq.Header.Set("Content-Type", "application/json")
	commentReq.Header.Set("X-Client-User-Id", "thread_commenter")
	commentRec := httptest.NewRecorder()
	testHandler.ServeHTTP(commentRec, commentReq)
	if commentRec.Code != http.StatusCreated {
		t.Fatalf("expected 201 comment created, got %d: %s", commentRec.Code, commentRec.Body.String())
	}

	likeReq := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/like", nil)
	likeReq.Header.Set("X-Client-User-Id", "thread_liker")
	likeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRec, likeReq)
	if likeRec.Code != http.StatusOK {
		t.Fatalf("expected 200 like response, got %d: %s", likeRec.Code, likeRec.Body.String())
	}
	// ContentReaction owns the authoritative relation and updates Post/feed
	// counters through its durable outbox. Wait for that production convergence
	// boundary before proving PromotePost preserves the projected counter.
	drainReactionOutbox(t)

	promoteReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+":promoteToWork",
		strings.NewReader(`{
			"contentType":"article",
			"title":"升级后的长文",
			"articleMarkdown":"# 升级后的长文\n\n升级后正文",
			"articleMarkdownVersion":"qwq-rich-md/1",
			"articleAssetManifest":{"assets":[]}
		}`),
	)
	promoteReq.Header.Set("Content-Type", "application/json")
	promoteReq.Header.Set("X-Client-User-Id", "promote_thread_author")
	promoteRec := httptest.NewRecorder()
	testHandler.ServeHTTP(promoteRec, promoteReq)
	if promoteRec.Code != http.StatusOK {
		t.Fatalf("expected 200 promote response, got %d: %s", promoteRec.Code, promoteRec.Body.String())
	}

	var promoteResp map[string]any
	if err := json.Unmarshal(promoteRec.Body.Bytes(), &promoteResp); err != nil {
		t.Fatalf("decode promote response: %v", err)
	}
	if promoteResp["_id"] != postID {
		t.Fatalf("expected promote keep same post id, got %v", promoteResp["_id"])
	}
	if promoteResp["contentIdentity"] != "work" {
		t.Fatalf("expected work identity after promote, got %v", promoteResp["contentIdentity"])
	}

	countersReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/counters", nil)
	countersRec := httptest.NewRecorder()
	testHandler.ServeHTTP(countersRec, countersReq)
	if countersRec.Code != http.StatusOK {
		t.Fatalf("expected 200 counters response, got %d: %s", countersRec.Code, countersRec.Body.String())
	}
	var counters map[string]any
	if err := json.Unmarshal(countersRec.Body.Bytes(), &counters); err != nil {
		t.Fatalf("decode counters: %v", err)
	}
	if counters["like"] != float64(1) {
		t.Fatalf("expected like counter preserved, got %v", counters["like"])
	}
	if counters["comment"] != float64(1) {
		t.Fatalf("expected comment counter preserved, got %v", counters["comment"])
	}

	commentsReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/comments?limit=20", nil)
	commentsRec := httptest.NewRecorder()
	testHandler.ServeHTTP(commentsRec, commentsReq)
	if commentsRec.Code != http.StatusOK {
		t.Fatalf("expected 200 comments response, got %d: %s", commentsRec.Code, commentsRec.Body.String())
	}
	var commentsResp struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(commentsRec.Body.Bytes(), &commentsResp); err != nil {
		t.Fatalf("decode comments response: %v", err)
	}
	if len(commentsResp.Items) != 1 {
		t.Fatalf("expected comment thread preserved, got %d comments", len(commentsResp.Items))
	}
	if commentsResp.Items[0]["content"] != "这条评论升级后也要保留" {
		t.Fatalf("expected preserved comment content, got %v", commentsResp.Items[0]["content"])
	}
}

func TestAssistantAccessRevokedAfterSettingsChange(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "assistant_author", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"可被小趣引用的作品",
		"body":"初始正文"
	}`)
	postID, _ := created["_id"].(string)

	req := httptest.NewRequest(
		http.MethodPatch,
		"/v1/content/posts/"+postID+"/settings",
		strings.NewReader(`{
			"visibility":"private",
			"assistantUsePolicy":"exclude"
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "assistant_author")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	getReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	getReq.Header.Set("X-Client-User-Id", "assistant_author")
	getRec := httptest.NewRecorder()
	testHandler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusOK {
		t.Fatalf("expected 200 on get, got %d: %s", getRec.Code, getRec.Body.String())
	}
	var getResp map[string]any
	if err := json.Unmarshal(getRec.Body.Bytes(), &getResp); err != nil {
		t.Fatalf("decode get response: %v", err)
	}
	if getResp["visibility"] != "private" {
		t.Fatalf("expected visibility=private, got %v", getResp["visibility"])
	}
	if getResp["assistantUsePolicy"] != "exclude" {
		t.Fatalf("expected assistantUsePolicy=exclude, got %v", getResp["assistantUsePolicy"])
	}

	viewerReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	viewerReq.Header.Set("X-Client-User-Id", "assistant_viewer")
	viewerRec := httptest.NewRecorder()
	testHandler.ServeHTTP(viewerRec, viewerReq)
	if viewerRec.Code != http.StatusNotFound {
		t.Fatalf("expected non-disclosing 404 for revoked viewer access, got %d: %s", viewerRec.Code, viewerRec.Body.String())
	}
	assertStablePostNotFound(t, viewerRec.Body.Bytes())

	var projected bson.M
	err := mongoDB.Collection("rm_discovery_feed").
		FindOne(context.Background(), bson.M{"postId": postID}).
		Decode(&projected)
	if err == nil {
		t.Fatalf("expected discovery projection removed after revoke, got %+v", projected)
	}
	if err != mongo.ErrNoDocuments {
		t.Fatalf("expected no discovery projection after revoke, got %v", err)
	}
}

func TestPrivatePostBlocksNonAuthorViewer(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "private_author", `{
		"contentType":"article",
		"title":"私密作品",
		"body":"仅自己可见",
		"visibility":"private"
	}`)
	postID, _ := created["_id"].(string)

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	req.Header.Set("X-Client-User-Id", "other_viewer")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected non-disclosing 404, got %d: %s", rec.Code, rec.Body.String())
	}
	assertStablePostNotFound(t, rec.Body.Bytes())
}

func assertStablePostNotFound(t *testing.T, raw []byte) {
	t.Helper()
	var failure struct {
		Code   string `json:"code"`
		Reason string `json:"reason"`
	}
	if err := json.Unmarshal(raw, &failure); err != nil {
		t.Fatalf("decode post visibility failure: %v", err)
	}
	if failure.Code != "CONTENT.USER.post_not_found" || failure.Reason != "not_found" {
		t.Fatalf("unexpected post visibility failure: %+v", failure)
	}
}

func TestPostCreateRejectsDirectCirclePlacement(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	request := httptest.NewRequest(http.MethodPost, "/v1/content/posts", strings.NewReader(`{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"圈内作品",
		"body":"仅圈成员可见",
		"articleMarkdown":"# 圈内作品\n\n仅圈成员可见",
		"articleMarkdownVersion":"qwq-rich-md/1",
		"articleAssetManifest":{"assets":[]},
		"visibility":"circle_visible",
		"circleIds":["circle_alpha"]
	}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-User-Id", "circle_author")
	request.Header.Set("X-Client-Sub-Account-Id", "circle_author")
	request.Header.Set("Idempotency-Key", "retired-circle-placement")
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("Post cannot mutate CirclePostPlacement, got %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestPostProjectionRebuildReplaysDurableOutbox(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "rebuild_author", `{
		"contentType":"article",
		"title":"记录作品",
		"body":"等待补投影"
	}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("expected post id")
	}

	if _, err := mongoDB.Collection("rm_discovery_feed").DeleteMany(
		context.Background(),
		bson.M{"postId": postID},
	); err != nil {
		t.Fatalf("delete projected doc: %v", err)
	}

	store := persistence.NewMongoPostStore(mongoDB.Collection("posts"))
	rebuildRelay := postapp.NewOutboxRelay(
		store,
		store,
		contentmessaging.NewPostOutboxPublisher(
			contentmessaging.NewInProcessProjectorPublisher(&discoveryProjectorAdapter{
				projector: recinfra.NewDiscoveryFeedProjector(mongoDB),
			}),
		),
		"api-integration-discovery-rebuild-"+postID,
	)
	count, err := rebuildRelay.Drain(context.Background(), 100)
	if err != nil {
		t.Fatalf("replay durable Post outbox: %v", err)
	}
	if count < 2 {
		t.Fatalf("expected CreatePost and PublishPost facts to replay, got %d", count)
	}

	var projected bson.M
	if err := mongoDB.Collection("rm_discovery_feed").
		FindOne(context.Background(), bson.M{"postId": postID}).
		Decode(&projected); err != nil {
		t.Fatalf("expected rebuilt projection, got %v", err)
	}
	if projected["contentIdentity"] != "work" {
		t.Fatalf("expected rebuilt contentIdentity=work, got %v", projected["contentIdentity"])
	}
	if projected["assistantUsePolicy"] != "inherit" {
		t.Fatalf("expected rebuilt assistantUsePolicy=inherit, got %v", projected["assistantUsePolicy"])
	}
	if projected["status"] != "published" {
		t.Fatalf("expected rebuilt status=published, got %v", projected["status"])
	}
	if count, err := rebuildRelay.Drain(context.Background(), 100); err != nil || count != 0 {
		t.Fatalf("rebuild checkpoint replay count=%d err=%v", count, err)
	}
}

func TestDiscoveryProjectionPersistsAuthorSubAccountID(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "projection_author", `{
		"contentType":"article",
		"title":"作者主键投影",
		"body":"发现流必须保留 canonical subAccountId"
	}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("expected post id")
	}

	var projected bson.M
	if err := mongoDB.Collection("rm_discovery_feed").
		FindOne(context.Background(), bson.M{"postId": postID}).
		Decode(&projected); err != nil {
		t.Fatalf("expected discovery projection, got %v", err)
	}
	if projected["authorId"] != "projection_author" {
		t.Fatalf("expected authorId=projection_author, got %v", projected["authorId"])
	}
}

func TestListUserPostsByIdentity(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	createPostWithAuthor(t, "identity_feed_author", `{
		"contentType":"micro",
		"contentIdentity":"moment",
		"body":"早安点滴"
	}`)
	createPostWithAuthor(t, "identity_feed_author", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"旅行笔记",
		"body":"整理成笔记"
	}`)

	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/sub-accounts/identity_feed_author/posts?identity=work&type=article&limit=20",
		nil,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("expected 1 work article, got %d", len(resp.Items))
	}
	if resp.Items[0]["contentIdentity"] != "work" {
		t.Fatalf("expected contentIdentity=work, got %v", resp.Items[0]["contentIdentity"])
	}
	if resp.Items[0]["contentType"] != "article" {
		t.Fatalf("expected contentType=article, got %v", resp.Items[0]["contentType"])
	}
}
