package persistence

import (
	"context"
	"fmt"
	"testing"
	"time"

	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
)

// These unit tests lock the keyset-pagination and explainable-delta contract on
// the deterministic in-memory store (no Docker). MongoCommentStore mirrors the
// same ordering / cursor / window semantics, so the L2 Mongo suite proves the
// identical behaviour against real indexes (no COLLSCAN / no in-memory SORT,
// ≥1e4 deep paging without the old 10k scan-cap truncation).

// drainTopLevel walks every page of ListTopLevel and returns the full ordered id
// list, failing on any duplicate (proves keyset never re-emits a row).
func drainTopLevel(t *testing.T, store *MemoryCommentStore, postID string, mode commentdomain.SortMode, pageSize int) []string {
	t.Helper()
	ctx := context.Background()
	seen := map[string]bool{}
	var ordered []string
	cursor := ""
	for guard := 0; ; guard++ {
		if guard > 1_000_000 {
			t.Fatalf("pagination did not terminate")
		}
		page, err := store.ListTopLevel(ctx, postID, mode, cursor, pageSize)
		if err != nil {
			t.Fatalf("ListTopLevel: %v", err)
		}
		for _, c := range page.Comments {
			if seen[c.ID] {
				t.Fatalf("duplicate comment across pages: %s", c.ID)
			}
			seen[c.ID] = true
			ordered = append(ordered, c.ID)
		}
		if page.NextCursor == "" {
			break
		}
		cursor = page.NextCursor
	}
	return ordered
}

// TestMemoryCommentStore_DeepPageNoTruncation proves keyset pagination returns
// the complete >10k set with no truncation (the old pageByScan capped at
// commentScanCap=10000 and silently dropped the tail) and in stable
// (recommendedScore desc, createdAt desc, _id desc) order with no duplicates.
func TestMemoryCommentStore_DeepPageNoTruncation(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryCommentStore()
	base := time.Date(2026, 6, 20, 0, 0, 0, 0, time.UTC)

	const total = 12_001 // strictly > the retired 10k scan cap
	for i := 0; i < total; i++ {
		c := mkComment(fmt.Sprintf("c%06d", i), "post_deep", "", base.Add(time.Duration(i)*time.Millisecond))
		// Distinct descending recommendedScore so the order is fully determined.
		c.RecommendedScore = float64(total - i)
		if err := store.Create(ctx, &c); err != nil {
			t.Fatalf("create %d: %v", i, err)
		}
	}

	ordered := drainTopLevel(t, store, "post_deep", commentdomain.SortRecommended, 137)
	if len(ordered) != total {
		t.Fatalf("paginated %d comments, want %d (truncation regression)", len(ordered), total)
	}
	// Highest score first → c000000, c000001, ... (score total..1 descending).
	for i := 0; i < total; i++ {
		want := fmt.Sprintf("c%06d", i)
		if ordered[i] != want {
			t.Fatalf("order[%d] = %s, want %s", i, ordered[i], want)
			break
		}
	}
}

// TestMemoryCommentStore_LatestKeysetDriftFreeUnderMutation proves the
// createdAt+_id keyset (SortLatest) is drift-free even when mutable score fields
// churn mid-pagination: because the sort key is immutable, concurrent
// like/score mutation between page fetches can neither duplicate nor skip a row.
func TestMemoryCommentStore_LatestKeysetDriftFreeUnderMutation(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryCommentStore()
	base := time.Date(2026, 6, 20, 0, 0, 0, 0, time.UTC)

	const total = 500
	ids := make([]string, total)
	for i := 0; i < total; i++ {
		id := fmt.Sprintf("m%04d", i)
		ids[i] = id
		c := mkComment(id, "post_mut", "", base.Add(time.Duration(i)*time.Second))
		c.RecommendedScore = float64(i)
		c.LikeCount = int64(i)
		_ = store.Create(ctx, &c)
	}

	seen := map[string]bool{}
	var ordered []string
	cursor := ""
	pages := 0
	for {
		page, err := store.ListTopLevel(ctx, "post_mut", commentdomain.SortLatest, cursor, 25)
		if err != nil {
			t.Fatalf("ListTopLevel: %v", err)
		}
		for _, c := range page.Comments {
			if seen[c.ID] {
				t.Fatalf("duplicate under mutation: %s", c.ID)
			}
			seen[c.ID] = true
			ordered = append(ordered, c.ID)
		}
		// Mutate mutable score fields of arbitrary comments between pages; this
		// must not perturb the createdAt/_id keyset traversal.
		for _, id := range ids {
			if c, ok := store.FindByID(ctx, id); ok {
				_, _ = store.SetReactionState(ctx, id, c.LikeCount+7, 0, c.RecommendedScore*-1)
			}
		}
		pages++
		if page.NextCursor == "" {
			break
		}
		cursor = page.NextCursor
		if pages > total {
			t.Fatalf("pagination did not terminate under mutation")
		}
	}
	if len(ordered) != total {
		t.Fatalf("drift detected: paginated %d unique rows, want %d", len(ordered), total)
	}
	// SortLatest = createdAt desc → newest (m0499) first, oldest (m0000) last.
	if ordered[0] != "m0499" || ordered[total-1] != "m0000" {
		t.Fatalf("latest order endpoints = (%s..%s), want (m0499..m0000)", ordered[0], ordered[total-1])
	}
}

// TestMemoryCommentStore_RepliesKeysetDeepPage proves the (createdAt,_id) reply
// keyset also pages the full set with no truncation/duplication.
func TestMemoryCommentStore_RepliesKeysetDeepPage(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryCommentStore()
	base := time.Date(2026, 6, 20, 0, 0, 0, 0, time.UTC)

	parent := mkComment("parent", "post_r", "", base)
	_ = store.Create(ctx, &parent)
	const replies = 3_333
	for i := 0; i < replies; i++ {
		c := mkComment(fmt.Sprintf("r%05d", i), "post_r", "parent", base.Add(time.Duration(i+1)*time.Millisecond))
		_ = store.Create(ctx, &c)
	}

	seen := map[string]bool{}
	cursor := ""
	got := 0
	for {
		page, err := store.ListReplies(ctx, "post_r", "parent", cursor, 100)
		if err != nil {
			t.Fatalf("ListReplies: %v", err)
		}
		for _, c := range page.Comments {
			if seen[c.ID] {
				t.Fatalf("duplicate reply across pages: %s", c.ID)
			}
			seen[c.ID] = true
			got++
		}
		if page.NextCursor == "" {
			break
		}
		cursor = page.NextCursor
	}
	if got != replies {
		t.Fatalf("paginated %d replies, want %d", got, replies)
	}
}

// TestMemoryCommentStore_DeltaWindowSemantics locks the half-open (since,
// watermark] window semantics that back GetCommentCountsDelta: created counts
// every comment in the window regardless of later deletion, deleted counts only
// status=deleted comments whose deletedAt falls in the window, and consecutive
// windows (using the prior watermark as the next since) never double-count.
func TestMemoryCommentStore_DeltaWindowSemantics(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryCommentStore()
	t0 := time.Date(2026, 6, 20, 12, 0, 0, 0, time.UTC)

	// Three comments created at t0+1m, +2m, +3m.
	for i := 1; i <= 3; i++ {
		c := mkComment(fmt.Sprintf("w%d", i), "post_d", "", t0.Add(time.Duration(i)*time.Minute))
		_ = store.Create(ctx, &c)
	}
	// Other post must not leak into counts.
	other := mkComment("other", "post_other", "", t0.Add(90*time.Second))
	_ = store.Create(ctx, &other)

	// Window A: (t0, t0+150s] → w1(+60s), w2(+120s) created; w3(+180s) excluded.
	watermarkA := t0.Add(150 * time.Second)
	if n, _ := store.CountCreatedBetween(ctx, "post_d", t0, watermarkA); n != 2 {
		t.Fatalf("created in window A = %d, want 2", n)
	}
	if n, _ := store.CountDeletedBetween(ctx, "post_d", t0, watermarkA); n != 0 {
		t.Fatalf("deleted in window A = %d, want 0", n)
	}

	// Delete w1 at t0+200s, then window B = (watermarkA, t0+240s].
	if _, ok, _ := store.SoftDelete(ctx, "w1", t0.Add(200*time.Second)); !ok {
		t.Fatalf("soft delete w1 failed")
	}
	watermarkB := t0.Add(240 * time.Second)
	// w3 (+180s) created in B; w1/w2 created before watermarkA so not recounted.
	if n, _ := store.CountCreatedBetween(ctx, "post_d", watermarkA, watermarkB); n != 1 {
		t.Fatalf("created in window B = %d, want 1 (no double count)", n)
	}
	// w1 deleted at +200s falls in B.
	if n, _ := store.CountDeletedBetween(ctx, "post_d", watermarkA, watermarkB); n != 1 {
		t.Fatalf("deleted in window B = %d, want 1", n)
	}

	// Zero since (first sync) is unbounded-below: all 3 created counted.
	if n, _ := store.CountCreatedBetween(ctx, "post_d", time.Time{}, watermarkB); n != 3 {
		t.Fatalf("created since zero = %d, want 3", n)
	}
	// currentTotal excludes the deleted w1 → 2.
	if n, _ := store.CountByPost(ctx, "post_d"); n != 2 {
		t.Fatalf("currentTotal = %d, want 2", n)
	}
}
