package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtrec "quwoquan_service/runtime/recommendation"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

// 交集召回通道：viewer 的物化交集边本身要能带来供给，而不是等别的通道召回后
// 再附着一句解释。同时验证同一批边在排序侧以真实边权注入特征向量，
// 保证「viewer ↔ 对象」这条边在召回与排序里是同一个真相源。

const (
	edgeRecallViewerID   = "u_ix_recall_viewer"
	edgeRecallPeerID     = "u_ix_recall_peer"
	edgeRecallPlaceID    = "entity_ix_recall_place"
	edgeRecallStrangerID = "u_ix_recall_stranger"
)

func seedEdgeRecallFeed(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	db := requireMongoDB(t)
	feed := db.Collection("rm_discovery_feed")
	now := time.Now().UTC()
	postIDs := []string{
		"post_ix_recall_peer",
		"post_ix_recall_place",
		"post_ix_recall_stranger",
		"post_ix_recall_self",
	}
	t.Cleanup(func() {
		_, _ = feed.DeleteMany(context.Background(), bson.M{"postId": bson.M{"$in": postIDs}})
	})
	docs := []any{
		// 交集对象是人：走 authorId 连接。
		bson.M{
			"postId": "post_ix_recall_peer", "status": "published", "visibility": "public",
			"authorId": edgeRecallPeerID, "recScore": 0.9, "publishedAt": now,
		},
		// 交集对象是地点：走 entityRefs 连接。
		bson.M{
			"postId": "post_ix_recall_place", "status": "published", "visibility": "public",
			"authorId": edgeRecallStrangerID, "entityRefs": []string{edgeRecallPlaceID},
			"recScore": 0.8, "publishedAt": now,
		},
		// 与 viewer 无任何交集边：不该被本通道召回。
		bson.M{
			"postId": "post_ix_recall_stranger", "status": "published", "visibility": "public",
			"authorId": edgeRecallStrangerID, "recScore": 0.95, "publishedAt": now,
		},
		// viewer 自己的内容：自己不构成交集。
		bson.M{
			"postId": "post_ix_recall_self", "status": "published", "visibility": "public",
			"authorId": edgeRecallViewerID, "entityRefs": []string{edgeRecallPlaceID},
			"recScore": 0.99, "publishedAt": now,
		},
	}
	if _, err := feed.InsertMany(ctx, docs); err != nil {
		t.Fatalf("seed discovery feed: %v", err)
	}
}

func seedEdgeRecallSnapshot(t *testing.T, reasons []intersectionapp.IntersectionReasonView) *recinfra.MongoViewerIntersectionStore {
	t.Helper()
	ctx := context.Background()
	db := requireMongoDB(t)
	store := recinfra.NewMongoViewerIntersectionStore(db, nil)
	t.Cleanup(func() {
		_, _ = db.Collection("rm_viewer_object_intersection").
			DeleteMany(context.Background(), bson.M{"_id": edgeRecallViewerID})
	})
	err := store.Save(ctx, recinfra.ViewerIntersectionDoc{
		ViewerID:   edgeRecallViewerID,
		Reasons:    reasons,
		ComputedAt: time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("save viewer intersection snapshot: %v", err)
	}
	return store
}

func edgeRecallReason(
	kind, objectID, objectKind string,
	weight float64,
) intersectionapp.IntersectionReasonView {
	return intersectionapp.IntersectionReasonView{
		IntersectionID:    "ix_" + objectID,
		IntersectionClass: "fact",
		Kind:              kind,
		Dimension:         "relationship",
		ActionTargetID:    objectID,
		RelationObjectID:  objectID,
		ObjectKind:        objectKind,
		EdgeWeight:        weight,
		FreshAt:           time.Now().UTC().Format(time.RFC3339),
	}
}

func TestIntersectionEdgeRecall_MaterializedEdgesDriveSupply(t *testing.T) {
	seedEdgeRecallFeed(t)
	store := seedEdgeRecallSnapshot(t, []intersectionapp.IntersectionReasonView{
		edgeRecallReason("commonFollower", edgeRecallPeerID, "person", 0.8),
		edgeRecallReason("coWishlistedEntity", edgeRecallPlaceID, "place", 0.6),
	})

	source := recinfra.NewIntersectionEdgeRecallSource(requireMongoDB(t), store)
	candidates, err := source.Recall(context.Background(), rtrec.RecallRequest{
		UserID: edgeRecallViewerID,
		Limit:  20,
	})
	if err != nil {
		t.Fatalf("intersection recall: %v", err)
	}

	got := map[string]rtrec.ContentCandidate{}
	for _, c := range candidates {
		got[c.ContentID] = c
	}
	if _, ok := got["post_ix_recall_peer"]; !ok {
		t.Fatalf("person edge must recall the peer's content, got %v", candidateIDs(candidates))
	}
	if _, ok := got["post_ix_recall_place"]; !ok {
		t.Fatalf("place edge must recall content tagged with that place, got %v", candidateIDs(candidates))
	}
	if _, ok := got["post_ix_recall_stranger"]; ok {
		t.Fatalf("content with no intersection edge must not be recalled: %v", candidateIDs(candidates))
	}
	if _, ok := got["post_ix_recall_self"]; ok {
		t.Fatalf("viewer's own content must not be recalled as an intersection: %v", candidateIDs(candidates))
	}
	for _, c := range candidates {
		if c.RecallPath != recinfra.IntersectionRecallPath {
			t.Fatalf("recall path must be %q, got %q", recinfra.IntersectionRecallPath, c.RecallPath)
		}
	}
}

// 匿名 viewer 没有交集快照，通道必须结构化跳过而不是打无界查询。
func TestIntersectionEdgeRecall_AnonymousViewerSkips(t *testing.T) {
	store := recinfra.NewMongoViewerIntersectionStore(requireMongoDB(t), nil)
	source := recinfra.NewIntersectionEdgeRecallSource(requireMongoDB(t), store)
	_, err := source.Recall(context.Background(), rtrec.RecallRequest{UserID: "", Limit: 10})
	if !rtrec.IsRecallSkipped(err) {
		t.Fatalf("anonymous viewer must skip intersection recall, got %v", err)
	}
}

// 排序特征：同一批物化边以真实边权注入 UserFeatureVector，候选按作者 / entityRefs 命中。
func TestFeatureStore_ExposesRealIntersectionEdgeWeights(t *testing.T) {
	store := seedEdgeRecallSnapshot(t, []intersectionapp.IntersectionReasonView{
		edgeRecallReason("commonFollower", edgeRecallPeerID, "person", 0.8),
		edgeRecallReason("coWishlistedEntity", edgeRecallPlaceID, "place", 0.6),
	})
	features := recinfra.NewFeatureStore(
		requireMongoDB(t),
		recinfra.WithViewerIntersectionEdges(store),
	)
	vec, err := features.GetFeatures(context.Background(), edgeRecallViewerID)
	if err != nil {
		t.Fatalf("get features: %v", err)
	}
	if vec == nil {
		t.Fatalf("viewer with intersection edges must yield a feature vector")
	}
	if got := vec.IntersectionEdges[edgeRecallPeerID].Weight; got != 0.8 {
		t.Fatalf("person edge weight must come from the materialized snapshot, got %.4f", got)
	}
	if got := vec.IntersectionEdges[edgeRecallPlaceID].Weight; got != 0.6 {
		t.Fatalf("place edge weight must come from the materialized snapshot, got %.4f", got)
	}
	edge, ok := vec.StrongestIntersectionEdge(rtrec.ContentCandidate{
		AuthorID:   edgeRecallStrangerID,
		EntityRefs: []string{edgeRecallPlaceID},
	})
	if !ok || edge.Weight != 0.6 {
		t.Fatalf("entity-side match must resolve the place edge, got %+v ok=%v", edge, ok)
	}
	if _, ok := vec.StrongestIntersectionEdge(rtrec.ContentCandidate{
		AuthorID: edgeRecallStrangerID,
	}); ok {
		t.Fatalf("candidate with no shared object must not match any edge")
	}
}

func candidateIDs(candidates []rtrec.ContentCandidate) []string {
	out := make([]string, 0, len(candidates))
	for _, c := range candidates {
		out = append(out, c.ContentID)
	}
	return out
}
