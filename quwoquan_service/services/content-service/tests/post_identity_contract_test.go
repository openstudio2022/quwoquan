package tests

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
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

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp["assistantUsePolicy"] != "exclude" {
		t.Fatalf("expected assistantUsePolicy=exclude, got %v", resp["assistantUsePolicy"])
	}
	circleIDs, _ := resp["circleIds"].([]any)
	if len(circleIDs) != 2 {
		t.Fatalf("expected 2 circleIds, got %d", len(circleIDs))
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

	promoteReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+":promoteToWork",
		strings.NewReader(`{
			"contentType":"article",
			"title":"升级后的长文"
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
	if viewerRec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for revoked viewer access, got %d: %s", viewerRec.Code, viewerRec.Body.String())
	}

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

	if rec.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestCircleVisiblePostAllowsCircleMemberViewer(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "circle_author", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"圈内作品",
		"body":"仅圈成员可见",
		"visibility":"circle_visible",
		"circleIds":["circle_alpha"]
	}`)
	postID, _ := created["_id"].(string)

	memberReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	memberReq.Header.Set("X-Client-User-Id", "circle_member")
	memberReq.Header.Set("X-Client-Circle-Ids", "circle_alpha,circle_beta")
	memberRec := httptest.NewRecorder()
	testHandler.ServeHTTP(memberRec, memberReq)
	if memberRec.Code != http.StatusOK {
		t.Fatalf("expected 200 for circle member, got %d: %s", memberRec.Code, memberRec.Body.String())
	}

	outsiderReq := httptest.NewRequest(
		http.MethodGet,
		"/v1/users/circle_author/posts?identity=work&type=article",
		nil,
	)
	outsiderReq.Header.Set("X-Client-User-Id", "outsider")
	outsiderRec := httptest.NewRecorder()
	testHandler.ServeHTTP(outsiderRec, outsiderReq)
	if outsiderRec.Code != http.StatusOK {
		t.Fatalf("expected 200 list response for outsider, got %d: %s", outsiderRec.Code, outsiderRec.Body.String())
	}
	var outsiderResp struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(outsiderRec.Body.Bytes(), &outsiderResp); err != nil {
		t.Fatalf("decode outsider response: %v", err)
	}
	if len(outsiderResp.Items) != 0 {
		t.Fatalf("expected outsider list hide circle-visible post, got %d items", len(outsiderResp.Items))
	}

	memberListReq := httptest.NewRequest(
		http.MethodGet,
		"/v1/users/circle_author/posts?identity=work&type=article",
		nil,
	)
	memberListReq.Header.Set("X-Client-User-Id", "circle_member")
	memberListReq.Header.Set("X-Client-Circle-Ids", "circle_alpha")
	memberListRec := httptest.NewRecorder()
	testHandler.ServeHTTP(memberListRec, memberListReq)
	if memberListRec.Code != http.StatusOK {
		t.Fatalf("expected 200 list response for member, got %d: %s", memberListRec.Code, memberListRec.Body.String())
	}
	var memberListResp struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(memberListRec.Body.Bytes(), &memberListResp); err != nil {
		t.Fatalf("decode member response: %v", err)
	}
	if len(memberListResp.Items) != 1 {
		t.Fatalf("expected circle member see 1 post, got %d", len(memberListResp.Items))
	}
}

func TestProjectionRebuildDryRunBackfillsLegacyFields(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "rebuild_author", `{
		"contentType":"article",
		"title":"历史作品",
		"body":"等待补投影"
	}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("expected post id")
	}

	if _, err := mongoDB.Collection("posts").UpdateOne(
		context.Background(),
		bson.M{"_id": postID},
		bson.M{
			"$unset": bson.M{
				"contentIdentity":    "",
				"assistantUsePolicy": "",
			},
		},
	); err != nil {
		t.Fatalf("unset legacy fields: %v", err)
	}
	if _, err := mongoDB.Collection("rm_discovery_feed").DeleteMany(
		context.Background(),
		bson.M{"postId": postID},
	); err != nil {
		t.Fatalf("delete projected doc: %v", err)
	}

	report, err := testPostService.RebuildProjectionDryRun(context.Background(), false)
	if err != nil {
		t.Fatalf("dry-run rebuild: %v", err)
	}
	if !report.DryRun {
		t.Fatalf("expected dry-run report, got %+v", report)
	}
	if report.BackfilledContentIdentity == 0 || report.BackfilledAssistantUsePolicy == 0 {
		t.Fatalf("expected backfill counts > 0, got %+v", report)
	}
	if report.DiscoveryEligiblePosts == 0 {
		t.Fatalf("expected discovery eligible posts > 0, got %+v", report)
	}

	var dryRunProjected bson.M
	err = mongoDB.Collection("rm_discovery_feed").
		FindOne(context.Background(), bson.M{"postId": postID}).
		Decode(&dryRunProjected)
	if err != mongo.ErrNoDocuments {
		t.Fatalf("expected dry-run not to rebuild projection, got err=%v doc=%+v", err, dryRunProjected)
	}

	applied, err := testPostService.RebuildProjectionDryRun(context.Background(), true)
	if err != nil {
		t.Fatalf("apply rebuild: %v", err)
	}
	if applied.DryRun {
		t.Fatalf("expected apply rebuild report, got %+v", applied)
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
}

func TestDiscoveryProjectionPersistsProfileSubjectID(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(t, "projection_author", `{
		"contentType":"article",
		"title":"作者主键投影",
		"body":"发现流必须保留 canonical profileSubjectId",
		"profileSubjectId":"persona_projection_author"
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
	if projected["profileSubjectId"] != "persona_projection_author" {
		t.Fatalf("expected profileSubjectId=persona_projection_author, got %v", projected["profileSubjectId"])
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
		"/v1/users/identity_feed_author/posts?identity=work&type=article&limit=20",
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
