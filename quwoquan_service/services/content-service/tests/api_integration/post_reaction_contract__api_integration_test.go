// L2 契约测试：ContentReaction 独立聚合、Mongo transaction/outbox 与 Post 计数投影。
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// contract.yaml: react_with_counter_strategy / go_func: TestReactWithCounterStrategy
func TestReactWithCounterStrategy(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPost(t, `{"contentType":"image","title":"Like counter test"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/like", nil)
	req.Header.Set("X-Client-User-Id", "user_react_001")
	ensureIdempotencyHeader(req, "reaction-like")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("like: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	// Response must be valid structured JSON
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("like route response must be valid JSON: %v", err)
	}
	if resp["liked"] != true || resp["changed"] != true || resp["version"] != float64(1) {
		t.Fatalf("unexpected typed reaction command result: %+v", resp)
	}
	if _, leaked := resp["likeCount"]; leaked {
		t.Fatalf("command result must not expose eventually-consistent Post counter: %+v", resp)
	}
	drainReactionOutbox(t)
	assertReactionLikeCountProjections(t, postID, "user_react_001", 1)
	if count, err := requireMongoDB(t).Collection("content_reaction_outbox").CountDocuments(
		context.Background(),
		bson.M{"aggregateId": resp["reactionId"]},
	); err != nil || count != 1 {
		t.Fatalf("ContentReaction outbox count=%d err=%v", count, err)
	}
}

// TestReactIdempotent verifies that calling like twice from the same user does
// not double-increment the counter (idempotent reaction semantics).
// contract.yaml: react_idempotent / go_func: TestReactIdempotent
func TestReactIdempotent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPost(t, `{"contentType":"image","title":"Idempotent like test"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	// First like
	req1 := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/like", nil)
	req1.Header.Set("X-Client-User-Id", "user_react_002")
	ensureIdempotencyHeader(req1, "reaction-like-first")
	rec1 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec1, req1)

	if rec1.Code != http.StatusOK {
		t.Fatalf("first like: expected 200, got %d: %s", rec1.Code, rec1.Body.String())
	}

	// Second like (same user) — idempotent
	req2 := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/like", nil)
	req2.Header.Set("X-Client-User-Id", "user_react_002")
	ensureIdempotencyHeader(req2, "reaction-like-repeat")
	rec2 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec2, req2)

	if rec2.Code != http.StatusOK {
		t.Fatalf("second like: expected 200, got %d: %s", rec2.Code, rec2.Body.String())
	}
	// Both calls return valid structured JSON
	var resp2 map[string]any
	if err := json.Unmarshal(rec2.Body.Bytes(), &resp2); err != nil {
		t.Fatalf("second like response must be valid JSON: %v", err)
	}
	if resp2["liked"] != true || resp2["changed"] != false || resp2["version"] != float64(1) {
		t.Fatalf("duplicate like must be a version-preserving noop: %+v", resp2)
	}
	drainReactionOutbox(t)
	assertReactionLikeCountProjections(t, postID, "user_react_002", 1)
	if count, err := requireMongoDB(t).Collection("content_reaction_outbox").CountDocuments(
		context.Background(),
		bson.M{},
	); err != nil || count != 1 {
		t.Fatalf("duplicate like appended outbox facts: count=%d err=%v", count, err)
	}
}

// TestUnlikeDecrementsCounter verifies the DELETE unlike route is registered and
// responds with structured JSON. When UnlikePost is implemented, this should
// assert 200/204 and verify the likeCount counter is decremented.
// contract.yaml: unlike_decrements_counter / go_func: TestUnlikeDecrementsCounter
func TestUnlikeDecrementsCounter(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPost(t, `{"contentType":"image","title":"Unlike decrement test"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	// Like first
	likeReq := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/like", nil)
	likeReq.Header.Set("X-Client-User-Id", "user_react_003")
	ensureIdempotencyHeader(likeReq, "reaction-like-before-unlike")
	likeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRec, likeReq)

	// Then unlike
	req := httptest.NewRequest(http.MethodDelete, "/content/posts/"+postID+"/like", nil)
	req.Header.Set("X-Client-User-Id", "user_react_003")
	ensureIdempotencyHeader(req, "reaction-unlike")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("unlike: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	// Response must be valid structured JSON
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unlike route response must be valid JSON: %v", err)
	}
	if resp["liked"] != false || resp["changed"] != true || resp["version"] != float64(2) {
		t.Fatalf("unexpected unlike result: %+v", resp)
	}
	drainReactionOutbox(t)
	assertReactionLikeCountProjections(t, postID, "user_react_003", 0)
}

func TestContentReactionRejectsMissingPostWithoutDurableSideEffects(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	req := httptest.NewRequest(http.MethodPost, "/content/posts/missing-reaction-target/like", nil)
	req.Header.Set("X-Client-User-Id", "reaction-missing-target")
	ensureIdempotencyHeader(req, "reaction-missing-target")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("missing Post: expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
	for _, collection := range []string{
		"content_reaction_aggregates",
		"content_reaction_command_receipts",
		"content_reaction_outbox",
	} {
		count, err := requireMongoDB(t).Collection(collection).CountDocuments(context.Background(), bson.M{})
		if err != nil || count != 0 {
			t.Fatalf("%s side effects after rejected target: count=%d err=%v", collection, count, err)
		}
	}
}

func TestPostDeletionTransitionsActiveReactionsThroughAggregateOutbox(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPostWithAuthor(
		t,
		"reaction_delete_owner",
		`{"contentType":"image","title":"Reaction delete lifecycle"}`,
	)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	likeReq := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/like", nil)
	likeReq.Header.Set("X-Client-User-Id", "reaction_delete_actor")
	ensureIdempotencyHeader(likeReq, "reaction-before-delete")
	likeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRec, likeReq)
	if likeRec.Code != http.StatusOK {
		t.Fatalf("like before delete: %d %s", likeRec.Code, likeRec.Body.String())
	}
	drainReactionOutbox(t)
	assertReactionLikeCountProjections(t, postID, "reaction_delete_actor", 1)

	deleteReq := httptest.NewRequest(http.MethodDelete, "/content/posts/"+postID, nil)
	deleteReq.Header.Set("X-Client-User-Id", "reaction_delete_owner")
	ensureIdempotencyHeader(deleteReq, "post-delete-with-reaction")
	deleteRec := httptest.NewRecorder()
	testHandler.ServeHTTP(deleteRec, deleteReq)
	if deleteRec.Code != http.StatusOK {
		t.Fatalf("delete Post: %d %s", deleteRec.Code, deleteRec.Body.String())
	}
	drainReactionOutbox(t)

	var relation struct {
		Reaction string `bson:"reaction"`
		Version  int64  `bson:"version"`
	}
	if err := requireMongoDB(t).Collection("content_reaction_aggregates").FindOne(
		context.Background(),
		bson.M{"targetId": postID, "actorId": "reaction_delete_actor"},
	).Decode(&relation); err != nil {
		t.Fatalf("read ContentReaction after Post deletion: %v", err)
	}
	if relation.Reaction != "none" || relation.Version != 2 {
		t.Fatalf("deleted Post reaction=%+v, want none version 2", relation)
	}
	if count, err := requireMongoDB(t).Collection("content_reaction_outbox").CountDocuments(
		context.Background(),
		bson.M{},
	); err != nil || count != 2 {
		t.Fatalf("ContentReaction lifecycle outbox count=%d err=%v", count, err)
	}
	assertPostAndRecommendLikeCountProjections(t, postID, "reaction_delete_actor", 0)
	if count, err := requireMongoDB(t).Collection("rm_discovery_feed").CountDocuments(
		context.Background(),
		bson.M{"postId": postID},
	); err != nil || count != 0 {
		t.Fatalf("deleted Post remained in DiscoveryFeed: count=%d err=%v", count, err)
	}
}

func assertReactionLikeCountProjections(
	t *testing.T,
	postID string,
	personaID string,
	want int64,
) {
	t.Helper()
	assertPostAndRecommendLikeCountProjections(t, postID, personaID, want)
	var feedRow struct {
		LikeCount int64 `bson:"likeCount"`
	}
	if err := requireMongoDB(t).Collection("rm_discovery_feed").FindOne(
		context.Background(),
		bson.M{"postId": postID},
	).Decode(&feedRow); err != nil {
		t.Fatalf("read DiscoveryFeed like-count projection: %v", err)
	}
	if feedRow.LikeCount != want {
		t.Fatalf("DiscoveryFeed.likeCount=%d, want %d", feedRow.LikeCount, want)
	}
}

func assertPostAndRecommendLikeCountProjections(
	t *testing.T,
	postID string,
	personaID string,
	want int64,
) {
	t.Helper()
	var row struct {
		LikeCount int64 `bson:"likeCount"`
	}
	if err := requireMongoDB(t).Collection("posts").FindOne(
		context.Background(),
		bson.M{"_id": postID},
	).Decode(&row); err != nil {
		t.Fatalf("read Post like-count projection: %v", err)
	}
	if row.LikeCount != want {
		t.Fatalf("Post.likeCount=%d, want %d", row.LikeCount, want)
	}
	var featureRow struct {
		UserFeatures struct {
			TotalLikes int64 `bson:"totalLikes"`
		} `bson:"userFeatures"`
	}
	if err := requireMongoDB(t).Collection("rm_recommend_feature").FindOne(
		context.Background(),
		bson.M{"userId": personaID},
	).Decode(&featureRow); err != nil {
		t.Fatalf("read RecommendFeature like-count projection: %v", err)
	}
	if featureRow.UserFeatures.TotalLikes != want {
		t.Fatalf(
			"RecommendFeature.userFeatures.totalLikes=%d, want %d",
			featureRow.UserFeatures.TotalLikes,
			want,
		)
	}
}
