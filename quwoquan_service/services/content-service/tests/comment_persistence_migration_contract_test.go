package tests

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// These L2 tests exercise the R-CMT01 authoritative Mongo comment persistence
// path directly (CRUD / keyset pagination / sort / authoritative counts), the
// no-cache authoritative-count invariant (the Redis ZSet/reaction-counter caches
// were removed as write-only/racy), and the single-source count reconciliation
// invariant under high concurrency.

func authoritativeMongoCommentCount(t *testing.T, postID string) int64 {
	t.Helper()
	n, err := mongoDB.Collection("comments").CountDocuments(context.Background(), bson.M{
		"postId": postID,
		"status": bson.M{"$ne": "deleted"},
	})
	if err != nil {
		t.Fatalf("authoritative mongo count: %v", err)
	}
	return n
}

func newMigComment(id, postID, parent string, created time.Time, score float64, like int64) postmodel.Comment {
	return postmodel.Comment{
		ID:               id,
		PostId:           postID,
		AuthorId:         "mig_author",
		Content:          "mig-" + id,
		Status:           "visible",
		ParentCommentId:  parent,
		RecommendedScore: score,
		LikeCount:        like,
		CreatedAt:        created,
	}
}

// TestCommentMongoStore_CRUDPaginationSort drives the authoritative Mongo store
// through create, find, sorted+paginated listing, replies, soft delete and the
// authoritative counts that back commentCount / totalCount.
func TestCommentMongoStore_CRUDPaginationSort(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	ctx := context.Background()
	store := persistence.NewMongoCommentStore(mongoDB, slog.Default())
	postID := fmt.Sprintf("mig_post_%d", time.Now().UnixNano())
	base := time.Date(2026, 6, 20, 9, 0, 0, 0, time.UTC)

	// 5 top-level (descending recommendedScore by creation order) + 2 replies.
	const topN = 5
	for i := 0; i < topN; i++ {
		c := newMigComment(fmt.Sprintf("%s_t%d", postID, i), postID, "", base.Add(time.Duration(i)*time.Minute), float64(topN-i), 0)
		if err := store.Create(ctx, &c); err != nil {
			t.Fatalf("create top %d: %v", i, err)
		}
	}
	parentID := fmt.Sprintf("%s_t0", postID)
	for i := 0; i < 2; i++ {
		c := newMigComment(fmt.Sprintf("%s_r%d", postID, i), postID, parentID, base.Add(time.Duration(10+i)*time.Minute), 0, 0)
		if err := store.Create(ctx, &c); err != nil {
			t.Fatalf("create reply %d: %v", i, err)
		}
	}

	if got, ok := store.FindByID(ctx, parentID); !ok || got.PostId != postID {
		t.Fatalf("FindByID(%s) = %+v ok=%v", parentID, got, ok)
	}

	// Authoritative count includes replies, excludes nothing yet.
	if n, _ := store.CountByPost(ctx, postID); n != topN+2 {
		t.Fatalf("CountByPost = %d, want %d", n, topN+2)
	}
	if n, _ := store.CountReplies(ctx, postID, parentID); n != 2 {
		t.Fatalf("CountReplies = %d, want 2", n)
	}

	// Recommended order = score desc = t0..t4. Cursor paginate in pages of 2.
	var ordered []string
	seen := map[string]bool{}
	cursor := ""
	for pages := 0; pages < topN+2; pages++ {
		page, err := store.ListTopLevel(ctx, postID, commentdomain.SortRecommended, cursor, 2)
		if err != nil {
			t.Fatalf("ListTopLevel: %v", err)
		}
		for _, c := range page.Comments {
			if seen[c.ID] {
				t.Fatalf("duplicate across pages: %s", c.ID)
			}
			seen[c.ID] = true
			ordered = append(ordered, c.ID)
		}
		if page.NextCursor == "" {
			break
		}
		cursor = page.NextCursor
	}
	if len(ordered) != topN {
		t.Fatalf("paginated %d top-level, want %d (%v)", len(ordered), topN, ordered)
	}
	for i := 0; i < topN; i++ {
		want := fmt.Sprintf("%s_t%d", postID, i)
		if ordered[i] != want {
			t.Fatalf("recommended order[%d] = %s, want %s (%v)", i, ordered[i], want, ordered)
		}
	}

	// Replies newest-first.
	repPage, _ := store.ListReplies(ctx, postID, parentID, "", 10)
	if len(repPage.Comments) != 2 || repPage.Comments[0].ID != fmt.Sprintf("%s_r1", postID) {
		t.Fatalf("ListReplies newest-first failed: %+v", repPage.Comments)
	}

	// Soft delete a reply and a top-level: both drop from authoritative counts.
	if _, ok, err := store.SoftDelete(ctx, fmt.Sprintf("%s_r0", postID), time.Now().UTC()); err != nil || !ok {
		t.Fatalf("soft delete reply: ok=%v err=%v", ok, err)
	}
	if _, ok, err := store.SoftDelete(ctx, fmt.Sprintf("%s_t4", postID), time.Now().UTC()); err != nil || !ok {
		t.Fatalf("soft delete top: ok=%v err=%v", ok, err)
	}
	if n, _ := store.CountByPost(ctx, postID); n != topN+2-2 {
		t.Fatalf("CountByPost after delete = %d, want %d", n, topN)
	}
	if n, _ := store.CountReplies(ctx, postID, parentID); n != 1 {
		t.Fatalf("CountReplies after delete = %d, want 1", n)
	}
}

// TestCommentStore_AuthoritativeCountsNoCache asserts that, after removing the
// write-only/racy Redis caches, comment counts are always exact and stable from
// the authoritative Mongo store: the post total reflects out-of-band inserts
// immediately (no stale counter), repeated reads are stable, and per-comment
// reaction counts are derived exactly from membership (no read-through backfill
// race). This is the post-migration replacement for the old decorator parity
// test (R24/R26: no second drifting source).
func TestCommentStore_AuthoritativeCountsNoCache(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	ctx := context.Background()
	store := persistence.NewMongoCommentStore(mongoDB, slog.Default())
	rx := persistence.NewMongoCommentReactionStore(mongoDB, slog.Default())

	postID := fmt.Sprintf("mig_cache_%d", time.Now().UnixNano())
	base := time.Date(2026, 6, 20, 9, 0, 0, 0, time.UTC)
	for i := 0; i < 3; i++ {
		c := newMigComment(fmt.Sprintf("%s_t%d", postID, i), postID, "", base.Add(time.Duration(i)*time.Minute), float64(3-i), 0)
		if err := store.Create(ctx, &c); err != nil {
			t.Fatalf("create %d: %v", i, err)
		}
	}

	// The post comment total is authoritative and stable across repeated reads.
	authoritative, _ := store.CountByPost(ctx, postID)
	first, err := store.CountByPost(ctx, postID)
	if err != nil {
		t.Fatalf("count: %v", err)
	}
	second, err := store.CountByPost(ctx, postID)
	if err != nil {
		t.Fatalf("count repeat: %v", err)
	}
	if authoritative != first || first != second {
		t.Fatalf("comment count not authoritative: auth=%d first=%d second=%d", authoritative, first, second)
	}

	page, err := store.ListTopLevel(ctx, postID, commentdomain.SortRecommended, "", 10)
	if err != nil || len(page.Comments) != 3 {
		t.Fatalf("ListTopLevel = %d comments err=%v", len(page.Comments), err)
	}

	// Out-of-band insert is reflected immediately (proves no stale served count).
	extra := newMigComment(fmt.Sprintf("%s_oob", postID), postID, "", base.Add(time.Hour), 0, 0)
	if err := store.Create(ctx, &extra); err != nil {
		t.Fatalf("oob create: %v", err)
	}
	if n, _ := store.CountByPost(ctx, postID); n != authoritative+1 {
		t.Fatalf("count did not reflect out-of-band insert: got %d, want %d", n, authoritative+1)
	}

	// Reaction counts: two likes, one dislike; derived exactly from membership.
	target := fmt.Sprintf("%s_t0", postID)
	if err := rx.Set(ctx, target, "ru1", commentdomain.ReactionLike); err != nil {
		t.Fatalf("set ru1: %v", err)
	}
	_ = rx.Set(ctx, target, "ru2", commentdomain.ReactionLike)
	_ = rx.Set(ctx, target, "ru3", commentdomain.ReactionDislike)

	wantLike, wantDislike, _ := rx.Counts(ctx, target)
	again1, again2, _ := rx.Counts(ctx, target) // repeated read is stable
	if wantLike != 2 || wantDislike != 1 {
		t.Fatalf("authoritative reaction counts = (%d,%d), want (2,1)", wantLike, wantDislike)
	}
	if again1 != wantLike || again2 != wantDislike {
		t.Fatalf("reaction counts not stable: first(%d,%d) again(%d,%d)", wantLike, wantDislike, again1, again2)
	}
}

// TestCommentCountReconciliation_HighConcurrency stresses concurrent
// add/react/delete through the application service and asserts the single
// source-of-truth invariant: ListComments.totalCount == GetCounters.comment ==
// authoritative Mongo non-deleted count.
func TestCommentCountReconciliation_HighConcurrency(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	ctx := context.Background()

	created := createPostWithAuthor(t, "conc_author", `{"contentType":"image","title":"Concurrency counts","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		postID, _ = created["id"].(string)
	}
	if postID == "" {
		t.Fatalf("missing post id: %+v", created)
	}

	const adders = 40
	var (
		mu         sync.Mutex
		commentIDs []string
		wg         sync.WaitGroup
	)
	collect := func(res map[string]any) {
		id := commentIDFromResult(res)
		if id == "" {
			return
		}
		mu.Lock()
		commentIDs = append(commentIDs, id)
		mu.Unlock()
	}

	// Phase 1: concurrent adds.
	for i := 0; i < adders; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			res, _, err := testPostService.AddComment(ctx, postID, "commenter", fmt.Sprintf("c-%d", n), "", "commenter", "", nil, nil)
			if err == nil {
				collect(res)
			}
		}(i)
	}
	wg.Wait()

	mu.Lock()
	ids := append([]string(nil), commentIDs...)
	mu.Unlock()
	if len(ids) == 0 {
		t.Fatalf("no comments were created concurrently")
	}

	// Phase 2: concurrent reactions (no count effect) + deletes (count effect).
	for i, id := range ids {
		wg.Add(1)
		go func(n int, commentID string) {
			defer wg.Done()
			// React on every comment (must not change comment count).
			reaction := "like"
			if n%2 == 0 {
				reaction = "dislike"
			}
			_, _ = testPostService.ReactToComment(ctx, commentID, fmt.Sprintf("viewer_%d", n%5), reaction)
			// Delete roughly one third of comments (by their author).
			if n%3 == 0 {
				_ = testPostService.DeleteComment(ctx, postID, commentID, "commenter")
			}
		}(i, id)
	}
	wg.Wait()

	// Single source of truth, asserted at read time with no settle/quiesce
	// masking: both served counts (thread total + counters endpoint) are derived
	// authoritatively from Mongo, so they equal the authoritative non-deleted
	// count immediately after the concurrent burst.
	authoritative := authoritativeMongoCommentCount(t, postID)

	_, _, totalCount, err := testPostService.ListComments(ctx, postID, "viewer_0", "", "recommended", 100)
	if err != nil {
		t.Fatalf("list comments: %v", err)
	}
	counters, err := testPostService.GetCounters(ctx, postID)
	if err != nil {
		t.Fatalf("get counters: %v", err)
	}
	commentCount := asInt64(counters["comment"])

	if int64(totalCount) != authoritative {
		t.Fatalf("ListComments.totalCount (%d) != authoritative Mongo count (%d)", totalCount, authoritative)
	}
	if commentCount != authoritative {
		t.Fatalf("GetCounters.comment (%d) != authoritative Mongo count (%d)", commentCount, authoritative)
	}
}

func commentIDFromResult(res map[string]any) string {
	if res == nil {
		return ""
	}
	for _, key := range []string{"commentId", "_id", "id"} {
		if v, ok := res[key].(string); ok && v != "" {
			return v
		}
	}
	return ""
}

func asInt64(v any) int64 {
	switch n := v.(type) {
	case int64:
		return n
	case int:
		return int64(n)
	case float64:
		return int64(n)
	default:
		return 0
	}
}
