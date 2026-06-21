package persistence

import (
	"context"
	"testing"
	"time"

	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// These tests lock the storage-agnostic comment contract on the deterministic
// in-memory implementation (no Docker). MongoCommentStore mirrors this ordering,
// cursor and count semantics exactly (see comment_mongo_store.go), so the L2
// Mongo integration suite and this unit suite together cover R12-R14 across the
// infrastructure layer.

func mkComment(id, postID, parent string, created time.Time) postmodel.Comment {
	return postmodel.Comment{
		ID:              id,
		PostId:          postID,
		AuthorId:        "author_" + id,
		Content:         "c-" + id,
		Status:          "visible",
		ParentCommentId: parent,
		CreatedAt:       created,
	}
}

func TestMemoryCommentStore_CRUDAndAuthoritativeCounts(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryCommentStore()
	base := time.Date(2026, 6, 20, 10, 0, 0, 0, time.UTC)

	parent := mkComment("p1", "post_a", "", base)
	reply1 := mkComment("r1", "post_a", "p1", base.Add(time.Minute))
	reply2 := mkComment("r2", "post_a", "p1", base.Add(2*time.Minute))
	other := mkComment("o1", "post_b", "", base)
	for _, c := range []postmodel.Comment{parent, reply1, reply2, other} {
		cp := c
		if err := store.Create(ctx, &cp); err != nil {
			t.Fatalf("create %s: %v", c.ID, err)
		}
	}

	got, ok := store.FindByID(ctx, "p1")
	if !ok || got.Content != "c-p1" {
		t.Fatalf("FindByID p1 = %+v ok=%v", got, ok)
	}
	if _, ok := store.FindByID(ctx, "missing"); ok {
		t.Fatalf("FindByID missing should be false")
	}

	// CountByPost is authoritative: top-level + replies, excluding other posts.
	if n, _ := store.CountByPost(ctx, "post_a"); n != 3 {
		t.Fatalf("CountByPost(post_a) = %d, want 3", n)
	}
	if n, _ := store.CountReplies(ctx, "post_a", "p1"); n != 2 {
		t.Fatalf("CountReplies(p1) = %d, want 2", n)
	}

	// Soft delete removes the reply from both count surfaces.
	if _, ok, err := store.SoftDelete(ctx, "r1", base.Add(time.Hour)); err != nil || !ok {
		t.Fatalf("SoftDelete r1 ok=%v err=%v", ok, err)
	}
	if n, _ := store.CountByPost(ctx, "post_a"); n != 2 {
		t.Fatalf("CountByPost after delete = %d, want 2", n)
	}
	if n, _ := store.CountReplies(ctx, "post_a", "p1"); n != 1 {
		t.Fatalf("CountReplies after delete = %d, want 1", n)
	}
	// Deleted comments are excluded from listings.
	repPage, _ := store.ListReplies(ctx, "post_a", "p1", "", 10)
	if len(repPage.Comments) != 1 || repPage.Comments[0].ID != "r2" {
		t.Fatalf("ListReplies after delete = %+v, want [r2]", repPage.Comments)
	}
}

func TestMemoryCommentStore_TopLevelSortModes(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryCommentStore()
	base := time.Date(2026, 6, 20, 10, 0, 0, 0, time.UTC)

	// a: oldest, low like/score; b: newest, mid; c: pinned; d: highest like/score.
	a := mkComment("a", "post", "", base)
	a.LikeCount, a.RecommendedScore = 1, 1
	b := mkComment("b", "post", "", base.Add(3*time.Minute))
	b.LikeCount, b.RecommendedScore = 5, 5
	c := mkComment("c", "post", "", base.Add(time.Minute))
	c.LikeCount, c.RecommendedScore = 2, 2
	c.IsPinned, c.PinnedAt = true, base.Add(time.Hour)
	d := mkComment("d", "post", "", base.Add(2*time.Minute))
	d.LikeCount, d.RecommendedScore = 9, 9
	for _, cm := range []postmodel.Comment{a, b, c, d} {
		cp := cm
		_ = store.Create(ctx, &cp)
	}

	assertOrder := func(mode commentdomain.SortMode, want []string) {
		t.Helper()
		page, err := store.ListTopLevel(ctx, "post", mode, "", 10)
		if err != nil {
			t.Fatalf("ListTopLevel(%s): %v", mode, err)
		}
		got := make([]string, len(page.Comments))
		for i, cm := range page.Comments {
			got[i] = cm.ID
		}
		if len(got) != len(want) {
			t.Fatalf("ListTopLevel(%s) len=%d %v, want %v", mode, len(got), got, want)
		}
		for i := range want {
			if got[i] != want[i] {
				t.Fatalf("ListTopLevel(%s) = %v, want %v", mode, got, want)
			}
		}
	}
	// Pinned always first; then mode key.
	assertOrder(commentdomain.SortRecommended, []string{"c", "d", "b", "a"})
	assertOrder(commentdomain.SortMostLiked, []string{"c", "d", "b", "a"})
	// Latest: pinned first, then createdAt desc → b(3m), d(2m), a(base) [c pinned].
	assertOrder(commentdomain.SortLatest, []string{"c", "b", "d", "a"})
}

func TestMemoryCommentStore_TopLevelCursorPagination(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryCommentStore()
	base := time.Date(2026, 6, 20, 10, 0, 0, 0, time.UTC)
	const total = 7
	for i := 0; i < total; i++ {
		cm := mkComment(string(rune('a'+i)), "post", "", base.Add(time.Duration(i)*time.Minute))
		cm.RecommendedScore = float64(total - i) // a highest, descending
		_ = store.Create(ctx, &cm)
	}

	seen := map[string]bool{}
	var ordered []string
	cursor := ""
	for pages := 0; pages < total+2; pages++ {
		page, err := store.ListTopLevel(ctx, "post", commentdomain.SortRecommended, cursor, 2)
		if err != nil {
			t.Fatalf("page: %v", err)
		}
		for _, cm := range page.Comments {
			if seen[cm.ID] {
				t.Fatalf("duplicate comment across pages: %s", cm.ID)
			}
			seen[cm.ID] = true
			ordered = append(ordered, cm.ID)
		}
		if page.NextCursor == "" {
			break
		}
		cursor = page.NextCursor
	}
	if len(ordered) != total {
		t.Fatalf("paginated %d comments, want %d (%v)", len(ordered), total, ordered)
	}
	// Recommended desc by score → a,b,c,d,e,f,g
	want := []string{"a", "b", "c", "d", "e", "f", "g"}
	for i := range want {
		if ordered[i] != want[i] {
			t.Fatalf("pagination order = %v, want %v", ordered, want)
		}
	}
}

func TestMemoryCommentReactionStore_ThreeStateDerivedCounts(t *testing.T) {
	ctx := context.Background()
	rs := NewMemoryCommentReactionStore()

	// u1 like, u2 like, u3 dislike → like=2 dislike=1.
	_ = rs.Set(ctx, "cmt", "u1", commentdomain.ReactionLike)
	_ = rs.Set(ctx, "cmt", "u2", commentdomain.ReactionLike)
	_ = rs.Set(ctx, "cmt", "u3", commentdomain.ReactionDislike)
	if like, dislike, _ := rs.Counts(ctx, "cmt"); like != 2 || dislike != 1 {
		t.Fatalf("counts = (%d,%d), want (2,1)", like, dislike)
	}

	// Three-state idempotency: u1 flips like→dislike (not additive).
	_ = rs.Set(ctx, "cmt", "u1", commentdomain.ReactionDislike)
	if like, dislike, _ := rs.Counts(ctx, "cmt"); like != 1 || dislike != 2 {
		t.Fatalf("after flip counts = (%d,%d), want (1,2)", like, dislike)
	}
	// none removes membership.
	_ = rs.Set(ctx, "cmt", "u3", commentdomain.ReactionNone)
	if like, dislike, _ := rs.Counts(ctx, "cmt"); like != 1 || dislike != 1 {
		t.Fatalf("after none counts = (%d,%d), want (1,1)", like, dislike)
	}
	if r, _ := rs.Get(ctx, "cmt", "u3"); r != commentdomain.ReactionNone {
		t.Fatalf("Get u3 = %s, want none", r)
	}

	// Batch resolution only returns present memberships.
	_ = rs.Set(ctx, "other", "u2", commentdomain.ReactionLike)
	byUser, _ := rs.ReactionsForUser(ctx, "u2", []string{"cmt", "other", "absent"})
	if byUser["cmt"] != commentdomain.ReactionLike || byUser["other"] != commentdomain.ReactionLike {
		t.Fatalf("ReactionsForUser(u2) = %+v", byUser)
	}
	if _, exists := byUser["absent"]; exists {
		t.Fatalf("ReactionsForUser should omit absent memberships: %+v", byUser)
	}

	// Purge clears all reactions for the comment.
	_ = rs.PurgeComment(ctx, "cmt")
	if like, dislike, _ := rs.Counts(ctx, "cmt"); like != 0 || dislike != 0 {
		t.Fatalf("after purge counts = (%d,%d), want (0,0)", like, dislike)
	}
}
