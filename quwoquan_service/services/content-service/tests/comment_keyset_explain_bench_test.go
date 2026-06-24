package tests

import (
	"context"
	"fmt"
	"log/slog"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// This L2 suite proves the high-concurrency hardening against a real MongoDB:
//   - the one-level / reply list queries are fully index-covered (IXSCAN on the
//     declared compound index, no COLLSCAN, no blocking in-memory SORT stage),
//   - keyset pagination walks a >10k set with zero truncation (the retired
//     pageByScan capped at 10k and silently dropped the tail),
//   - the explainable delta contract (GetCommentCountsDelta) is exact and
//     half-open across consecutive watermarks,
//   - and provides benchmarks for the one-level/reply deep page and the
//     comment-count atomic hot write.

// walkPlanValue recursively collects every "stage" and "indexName" string under
// a winningPlan RawValue (handles classic + SBE shapes, nested inputStage and
// inputStages arrays). Walking raw BSON avoids decode-type ambiguity and, by
// being scoped to the winningPlan document only, never inspects rejectedPlans
// (which legitimately contain the SORT plans the planner discarded).
func walkPlanValue(key string, val bson.RawValue, stages, indexes *[]string) {
	switch val.Type {
	case bson.TypeEmbeddedDocument:
		elems, _ := val.Document().Elements()
		for _, e := range elems {
			walkPlanValue(e.Key(), e.Value(), stages, indexes)
		}
	case bson.TypeArray:
		vals, _ := val.Array().Values()
		for _, v := range vals {
			walkPlanValue("", v, stages, indexes)
		}
	case bson.TypeString:
		switch key {
		case "stage":
			*stages = append(*stages, val.StringValue())
		case "indexName":
			*indexes = append(*indexes, val.StringValue())
		}
	}
}

// explainFind runs an explain (queryPlanner) for a find with filter+sort and
// returns the collected stage names and index names from the winning plan only.
func explainFind(t *testing.T, filter bson.M, sort bson.D) (stages, indexes []string) {
	t.Helper()
	cmd := bson.D{
		{Key: "explain", Value: bson.D{
			{Key: "find", Value: commentsCollName},
			{Key: "filter", Value: filter},
			{Key: "sort", Value: sort},
		}},
		{Key: "verbosity", Value: "queryPlanner"},
	}
	raw, err := mongoDB.RunCommand(context.Background(), cmd).Raw()
	if err != nil {
		t.Fatalf("explain runCommand: %v", err)
	}
	winning := raw.Lookup("queryPlanner", "winningPlan")
	if winning.Type != bson.TypeEmbeddedDocument {
		t.Fatalf("explain missing winningPlan (type=%v)", winning.Type)
	}
	walkPlanValue("winningPlan", winning, &stages, &indexes)
	return stages, indexes
}

const commentsCollName = "comments"

func containsString(haystack []string, needle string) bool {
	for _, s := range haystack {
		if s == needle {
			return true
		}
	}
	return false
}

// TestCommentMongoStore_ListQueriesAreIndexCovered asserts the production list
// queries resolve to an index scan with no blocking SORT and no COLLSCAN — i.e.
// the "every one-level list triggers an in-memory SORT" regression is gone.
func TestCommentMongoStore_ListQueriesAreIndexCovered(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	ctx := context.Background()
	store := persistence.NewMongoCommentStore(mongoDB, slog.Default())
	postID := fmt.Sprintf("idx_post_%d", time.Now().UnixNano())
	base := time.Date(2026, 6, 20, 8, 0, 0, 0, time.UTC)

	// Seed enough rows that the planner prefers an index over a collection scan.
	docs := make([]any, 0, 400)
	for i := 0; i < 400; i++ {
		c := newMigComment(fmt.Sprintf("%s_c%d", postID, i), postID, "", base.Add(time.Duration(i)*time.Second), float64(400-i), int64(i%7))
		docs = append(docs, c)
	}
	if _, err := mongoDB.Collection(commentsCollName).InsertMany(ctx, docs); err != nil {
		t.Fatalf("seed insertMany: %v", err)
	}
	// Touch the store so ensureIndexes has definitely run for this collection.
	if _, err := store.CountByPost(ctx, postID); err != nil {
		t.Fatalf("count: %v", err)
	}

	cases := []struct {
		name      string
		filter    bson.M
		sort      bson.D
		wantIndex string
	}{
		{
			name: "recommended_top_level",
			filter: bson.M{
				"postId":          postID,
				"parentCommentId": "",
				"status":          bson.M{"$ne": "deleted"},
				"isPinned":        bson.M{"$ne": true},
			},
			sort:      bson.D{{Key: "recommendedScore", Value: -1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
			wantIndex: "idx_comments_recommended",
		},
		{
			name: "most_liked_top_level",
			filter: bson.M{
				"postId":          postID,
				"parentCommentId": "",
				"status":          bson.M{"$ne": "deleted"},
				"isPinned":        bson.M{"$ne": true},
			},
			sort:      bson.D{{Key: "likeCount", Value: -1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
			wantIndex: "idx_comments_hot",
		},
		{
			name: "replies_flat",
			filter: bson.M{
				"postId":          postID,
				"parentCommentId": fmt.Sprintf("%s_c0", postID),
				"status":          bson.M{"$ne": "deleted"},
			},
			sort:      bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
			wantIndex: "idx_comments_parent_created",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			stages, indexes := explainFind(t, tc.filter, tc.sort)
			if containsString(stages, "COLLSCAN") {
				t.Fatalf("%s: plan contains COLLSCAN (stages=%v)", tc.name, stages)
			}
			// "SORT" is the blocking in-memory sort we eliminated. SORT_MERGE
			// (merging pre-sorted index streams) is acceptable.
			if containsString(stages, "SORT") {
				t.Fatalf("%s: plan contains blocking SORT stage (stages=%v)", tc.name, stages)
			}
			if !containsString(stages, "IXSCAN") {
				t.Fatalf("%s: plan has no IXSCAN (stages=%v)", tc.name, stages)
			}
			if !containsString(indexes, tc.wantIndex) {
				t.Fatalf("%s: expected index %q, plan used %v", tc.name, tc.wantIndex, indexes)
			}
		})
	}
}

// seedTopLevelComments bulk-inserts n descending-score top-level comments for a
// post and returns the postID.
func seedTopLevelComments(t testing.TB, store *persistence.MongoCommentStore, postID string, n int) {
	t.Helper()
	ctx := context.Background()
	base := time.Date(2026, 6, 20, 0, 0, 0, 0, time.UTC)
	const batch = 2000
	buf := make([]any, 0, batch)
	flush := func() {
		if len(buf) == 0 {
			return
		}
		if _, err := mongoDB.Collection(commentsCollName).InsertMany(ctx, buf); err != nil {
			t.Fatalf("seed insertMany: %v", err)
		}
		buf = buf[:0]
	}
	for i := 0; i < n; i++ {
		c := newMigComment(fmt.Sprintf("%s_d%07d", postID, i), postID, "", base.Add(time.Duration(i)*time.Millisecond), float64(n-i), int64(i%11))
		buf = append(buf, c)
		if len(buf) == batch {
			flush()
		}
	}
	flush()
	// Ensure indexes are present for the seeded collection.
	if _, err := store.CountByPost(ctx, postID); err != nil {
		t.Fatalf("count after seed: %v", err)
	}
}

// TestCommentMongoStore_DeepPageBeyond10kNoTruncation proves keyset pagination
// returns the complete >10k set against real Mongo indexes — the retired
// pageByScan (SetLimit(10000)) silently truncated here.
func TestCommentMongoStore_DeepPageBeyond10kNoTruncation(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	ctx := context.Background()
	store := persistence.NewMongoCommentStore(mongoDB, slog.Default())
	postID := fmt.Sprintf("deep_post_%d", time.Now().UnixNano())

	const total = 10_001 // strictly greater than the retired 10k scan cap
	seedTopLevelComments(t, store, postID, total)

	seen := make(map[string]bool, total)
	cursor := ""
	pages := 0
	for {
		page, err := store.ListTopLevel(ctx, postID, commentdomain.SortRecommended, cursor, 500)
		if err != nil {
			t.Fatalf("ListTopLevel page %d: %v", pages, err)
		}
		for _, c := range page.Comments {
			if seen[c.ID] {
				t.Fatalf("duplicate across pages: %s", c.ID)
			}
			seen[c.ID] = true
		}
		pages++
		if page.NextCursor == "" {
			break
		}
		cursor = page.NextCursor
		if pages > total {
			t.Fatalf("pagination did not terminate")
		}
	}
	if len(seen) != total {
		t.Fatalf("paginated %d comments, want %d (truncation regression)", len(seen), total)
	}
	if n, _ := store.CountByPost(ctx, postID); n != int64(total) {
		t.Fatalf("authoritative count = %d, want %d", n, total)
	}
}

// TestCommentCountsDelta_ExplainableHalfOpenWindow drives the delta contract end
// to end through the service: a first sync seeds the baseline + watermark; a
// follow-up sync using that watermark reports exactly the comments created and
// deleted in the half-open (since, watermark] interval with no double counting.
func TestCommentCountsDelta_ExplainableHalfOpenWindow(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	ctx := context.Background()

	created := createPostWithAuthor(t, "delta_author", `{"contentType":"image","title":"Delta","mediaUrls":["https://example.com/i.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		postID, _ = created["id"].(string)
	}
	if postID == "" {
		t.Fatalf("missing post id: %+v", created)
	}

	// Phase 1: create 5 comments, keep their ids for later deletion.
	var firstBatch []string
	for i := 0; i < 5; i++ {
		res, _, err := testPostService.AddComment(ctx, postID, "c_author", fmt.Sprintf("first-%d", i), "", "c_author", "", nil, nil)
		if err != nil {
			t.Fatalf("add first %d: %v", i, err)
		}
		firstBatch = append(firstBatch, commentIDFromResult(res))
	}

	// First sync (since = zero): unbounded baseline.
	delta1, err := testPostService.GetCommentCountsDelta(ctx, postID, time.Time{})
	if err != nil {
		t.Fatalf("delta1: %v", err)
	}
	if asInt64(delta1["createdSinceCount"]) != 5 {
		t.Fatalf("delta1 created = %d, want 5", asInt64(delta1["createdSinceCount"]))
	}
	if asInt64(delta1["deletedSinceCount"]) != 0 {
		t.Fatalf("delta1 deleted = %d, want 0", asInt64(delta1["deletedSinceCount"]))
	}
	if asInt64(delta1["currentTotal"]) != 5 {
		t.Fatalf("delta1 currentTotal = %d, want 5", asInt64(delta1["currentTotal"]))
	}
	watermark1 := parseWatermark(t, delta1["watermark"])

	// Ensure the next events land strictly after watermark1.
	time.Sleep(10 * time.Millisecond)

	// Phase 2: add 3 new, delete 2 of the first batch.
	for i := 0; i < 3; i++ {
		if _, _, err := testPostService.AddComment(ctx, postID, "c_author", fmt.Sprintf("second-%d", i), "", "c_author", "", nil, nil); err != nil {
			t.Fatalf("add second %d: %v", i, err)
		}
	}
	for i := 0; i < 2; i++ {
		if err := testPostService.DeleteComment(ctx, postID, firstBatch[i], "c_author"); err != nil {
			t.Fatalf("delete %d: %v", i, err)
		}
	}

	// Second sync (since = watermark1): only events in (watermark1, watermark2].
	delta2, err := testPostService.GetCommentCountsDelta(ctx, postID, watermark1)
	if err != nil {
		t.Fatalf("delta2: %v", err)
	}
	if got := asInt64(delta2["createdSinceCount"]); got != 3 {
		t.Fatalf("delta2 created = %d, want 3 (no recount of phase 1)", got)
	}
	if got := asInt64(delta2["deletedSinceCount"]); got != 2 {
		t.Fatalf("delta2 deleted = %d, want 2", got)
	}
	// currentTotal = 5 created + 3 created - 2 deleted = 6.
	if got := asInt64(delta2["currentTotal"]); got != 6 {
		t.Fatalf("delta2 currentTotal = %d, want 6", got)
	}

	// currentTotal must equal the authoritative non-deleted Mongo count.
	if got, want := asInt64(delta2["currentTotal"]), authoritativeMongoCommentCount(t, postID); got != want {
		t.Fatalf("delta currentTotal (%d) != authoritative Mongo count (%d)", got, want)
	}
}

func parseWatermark(t *testing.T, v any) time.Time {
	t.Helper()
	s, ok := v.(string)
	if !ok || s == "" {
		t.Fatalf("watermark not a non-empty string: %v", v)
	}
	parsed, err := time.Parse(time.RFC3339Nano, s)
	if err != nil {
		t.Fatalf("parse watermark %q: %v", s, err)
	}
	return parsed
}

// BenchmarkCommentListTopLevel_DeepPage measures a deep keyset page (resuming
// ~80% into a 5k set). With keyset seek this is O(pageSize) regardless of depth.
func BenchmarkCommentListTopLevel_DeepPage(b *testing.B) {
	ctx := context.Background()
	db := requireMongoDB(b)
	store := persistence.NewMongoCommentStore(db, slog.Default())
	postID := fmt.Sprintf("bench_top_%d", time.Now().UnixNano())
	b.Cleanup(func() {
		_, _ = db.Collection(commentsCollName).DeleteMany(ctx, bson.M{"postId": postID})
	})
	const total = 5000
	seedTopLevelComments(b, store, postID, total)

	// Walk to a deep cursor (~80%) once, outside the timed loop.
	deepCursor := ""
	target := (total * 8) / 10
	walked := 0
	for walked < target {
		page, err := store.ListTopLevel(ctx, postID, commentdomain.SortRecommended, deepCursor, 200)
		if err != nil {
			b.Fatalf("warm walk: %v", err)
		}
		walked += len(page.Comments)
		if page.NextCursor == "" {
			break
		}
		deepCursor = page.NextCursor
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := store.ListTopLevel(ctx, postID, commentdomain.SortRecommended, deepCursor, 20); err != nil {
			b.Fatalf("deep page: %v", err)
		}
	}
}

// BenchmarkCommentListReplies_DeepPage measures a deep reply keyset page.
func BenchmarkCommentListReplies_DeepPage(b *testing.B) {
	ctx := context.Background()
	db := requireMongoDB(b)
	store := persistence.NewMongoCommentStore(db, slog.Default())
	postID := fmt.Sprintf("bench_rep_%d", time.Now().UnixNano())
	parentID := postID + "_parent"
	b.Cleanup(func() {
		_, _ = db.Collection(commentsCollName).DeleteMany(ctx, bson.M{"postId": postID})
	})
	base := time.Date(2026, 6, 20, 0, 0, 0, 0, time.UTC)
	parent := newMigComment(parentID, postID, "", base, 1, 0)
	if _, err := db.Collection(commentsCollName).InsertOne(ctx, parent); err != nil {
		b.Fatalf("seed parent: %v", err)
	}
	const replies = 5000
	buf := make([]any, 0, replies)
	for i := 0; i < replies; i++ {
		buf = append(buf, newMigComment(fmt.Sprintf("%s_r%07d", postID, i), postID, parentID, base.Add(time.Duration(i+1)*time.Millisecond), 0, 0))
	}
	if _, err := db.Collection(commentsCollName).InsertMany(ctx, buf); err != nil {
		b.Fatalf("seed replies: %v", err)
	}
	if _, err := store.CountReplies(ctx, postID, parentID); err != nil {
		b.Fatalf("warm count: %v", err)
	}

	deepCursor := ""
	walked := 0
	for walked < replies*8/10 {
		page, err := store.ListReplies(ctx, postID, parentID, deepCursor, 200)
		if err != nil {
			b.Fatalf("warm walk: %v", err)
		}
		walked += len(page.Comments)
		if page.NextCursor == "" {
			break
		}
		deepCursor = page.NextCursor
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := store.ListReplies(ctx, postID, parentID, deepCursor, 20); err != nil {
			b.Fatalf("deep page: %v", err)
		}
	}
}

// BenchmarkPostCommentCount_AtomicHotWrite measures the atomic $inc comment-count
// hot path (AdjustCommentCount) that replaced the per-write CountDocuments +
// full-document rewrite.
func BenchmarkPostCommentCount_AtomicHotWrite(b *testing.B) {
	ctx := context.Background()
	db := requireMongoDB(b)
	store := persistence.NewMongoPostStore(db.Collection("posts"))
	postID := fmt.Sprintf("bench_cnt_%d", time.Now().UnixNano())
	b.Cleanup(func() {
		_, _ = db.Collection("posts").DeleteMany(ctx, bson.M{"_id": postID})
	})
	seed := postmodel.Post{ID: postID, AuthorId: "bench", ContentType: "image", Status: "published", CreatedAt: time.Now().UTC()}
	if _, err := db.Collection("posts").InsertOne(ctx, seed); err != nil {
		b.Fatalf("seed post: %v", err)
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, ok, err := store.AdjustCommentCount(ctx, postID, 1); err != nil || !ok {
			b.Fatalf("adjust: ok=%v err=%v", ok, err)
		}
	}
}
