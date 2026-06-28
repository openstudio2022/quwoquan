package post

import (
	"context"
	"sort"
	"sync"
	"testing"
)

// 排序契约：综合/最新/最多赞三种排序必须返回「同一评论集合、同一总数」，仅顺序不同。
// 这保证用户切换排序时不会误以为评论集变了（同集合一致性）。
func TestListCommentsSortModesShareSameSet(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	// 播种 6 条一级评论 + 不同点赞量，制造三种排序下的差异顺序。
	ids := make([]string, 0, 6)
	for i := 0; i < 6; i++ {
		c, _, err := svc.AddComment(
			ctx, "post_owner_image", commentFan(i), commentBody(i), "", commentFan(i), "", nil, nil,
		)
		if err != nil {
			t.Fatalf("add comment %d: %v", i, err)
		}
		id, _ := c["_id"].(string)
		ids = append(ids, id)
	}
	// 给不同评论不同点赞，使 most_liked 与 latest/recommended 顺序不同。
	likers := []string{"liker_a", "liker_b", "liker_c", "liker_d", "liker_e"}
	for n := 0; n <= 4; n++ { // ids[2] 收到 5 赞、ids[4] 收到 2 赞……
		if _, err := svc.ReactToComment(ctx, ids[2], likers[n], "like"); err != nil {
			t.Fatalf("like ids[2] by %s: %v", likers[n], err)
		}
	}
	for n := 0; n <= 1; n++ {
		if _, err := svc.ReactToComment(ctx, ids[4], likers[n], "like"); err != nil {
			t.Fatalf("like ids[4] by %s: %v", likers[n], err)
		}
	}

	setOf := func(mode string) []string {
		items, _, totalCount, err := svc.ListComments(ctx, "post_owner_image", "viewer_x", "", mode, 100)
		if err != nil {
			t.Fatalf("list comments mode=%q: %v", mode, err)
		}
		if totalCount != len(ids) {
			t.Fatalf("mode=%q totalCount=%d, want %d", mode, totalCount, len(ids))
		}
		out := make([]string, 0, len(items))
		for _, it := range items {
			out = append(out, asString(it["_id"]))
		}
		return out
	}

	recommended := setOf("")
	latest := setOf("latest")
	mostLiked := setOf("most_liked")

	if len(recommended) != len(ids) || len(latest) != len(ids) || len(mostLiked) != len(ids) {
		t.Fatalf("all sort modes must return %d comments, got recommended=%d latest=%d most_liked=%d",
			len(ids), len(recommended), len(latest), len(mostLiked))
	}
	assertSameSet(t, "recommended vs latest", recommended, latest)
	assertSameSet(t, "recommended vs most_liked", recommended, mostLiked)

	// most_liked 首位必须是收到最多赞（5 赞）的 ids[2]。
	if mostLiked[0] != ids[2] {
		t.Fatalf("most_liked first must be the 5-like comment %q, got %q", ids[2], mostLiked[0])
	}
	// 至少一种排序顺序与 latest 不同，证明确实是「换序不换集」。
	if sameOrder(recommended, latest) && sameOrder(mostLiked, latest) {
		t.Fatalf("expected at least one sort mode to differ in order from latest")
	}
}

// 综合排序确定性：相同评论集多次拉取必须返回完全一致的顺序（无 time.Since 漂移）。
func TestListCommentsRecommendedIsDeterministic(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()
	for i := 0; i < 8; i++ {
		if _, _, err := svc.AddComment(
			ctx, "post_owner_image", commentFan(i), commentBody(i), "", commentFan(i), "", nil, nil,
		); err != nil {
			t.Fatalf("add comment %d: %v", i, err)
		}
	}
	first, _, _, err := svc.ListComments(ctx, "post_owner_image", "viewer_x", "", "recommended", 100)
	if err != nil {
		t.Fatalf("first list: %v", err)
	}
	firstOrder := idsOf(first)
	for round := 0; round < 20; round++ {
		again, _, _, err := svc.ListComments(ctx, "post_owner_image", "viewer_x", "", "recommended", 100)
		if err != nil {
			t.Fatalf("list round %d: %v", round, err)
		}
		if !sameOrder(firstOrder, idsOf(again)) {
			t.Fatalf("recommended order drifted on round %d: %v vs %v", round, firstOrder, idsOf(again))
		}
	}
}

// 并发硬化：读路径（RLock）与写路径（Lock）并发执行必须无数据竞争（go test -race）。
func TestCommentReadWriteConcurrencyNoRace(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()
	seed, _, err := svc.AddComment(ctx, "post_owner_image", "fan_seed", "seed", "", "fan_seed", "", nil, nil)
	if err != nil {
		t.Fatalf("seed comment: %v", err)
	}
	seedID, _ := seed["_id"].(string)

	var wg sync.WaitGroup
	// 并发写：新增评论 + 点赞既有评论。
	for w := 0; w < 4; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			for i := 0; i < 25; i++ {
				_, _, _ = svc.AddComment(ctx, "post_owner_image", commentFan(w*100+i), "并发", "", commentFan(w*100+i), "", nil, nil)
				_, _ = svc.ReactToComment(ctx, seedID, commentFan(w*100+i), "like")
			}
		}(w)
	}
	// 并发读：列表 + 二级回复 + 我的互动。
	for r := 0; r < 6; r++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 50; i++ {
				_, _, _, _ = svc.ListComments(ctx, "post_owner_image", "viewer_x", "", "recommended", 20)
				_, _, _, _ = svc.ListCommentReplies(ctx, "post_owner_image", seedID, "viewer_x", "", 10)
				_, _, _ = svc.ListCommentsForPostAuthor(ctx, "profile_owner", "", 20)
			}
		}()
	}
	wg.Wait()
}

func commentFan(i int) string  { return "fan_" + itoa(i) }
func commentBody(i int) string { return "评论正文 " + itoa(i) }

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	neg := i < 0
	if neg {
		i = -i
	}
	buf := [12]byte{}
	pos := len(buf)
	for i > 0 {
		pos--
		buf[pos] = byte('0' + i%10)
		i /= 10
	}
	if neg {
		pos--
		buf[pos] = '-'
	}
	return string(buf[pos:])
}

func idsOf(items []map[string]any) []string {
	out := make([]string, 0, len(items))
	for _, it := range items {
		out = append(out, asString(it["_id"]))
	}
	return out
}

func sameOrder(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func assertSameSet(t *testing.T, label string, a, b []string) {
	t.Helper()
	ca := append([]string(nil), a...)
	cb := append([]string(nil), b...)
	sort.Strings(ca)
	sort.Strings(cb)
	if !sameOrder(ca, cb) {
		t.Fatalf("%s: sort modes must contain identical comment set, got %v vs %v", label, ca, cb)
	}
}
