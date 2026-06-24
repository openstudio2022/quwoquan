package application

import (
	"context"
	"testing"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

func newProfileInteractionTestService() *PostService {
	now := time.Date(2026, 6, 18, 8, 0, 0, 0, time.UTC)
	store := persistence.NewPostStore([]postmodel.Post{
		{
			ID:                        "post_owner_image",
			AuthorId:                  "profile_owner",
			AuthorDisplayNameSnapshot: "主页作者",
			AuthorAvatarUrlSnapshot:   "media/avatar/owner.jpg",
			ContentType:               "image",
			Title:                     "街角光影",
			Summary:                   "一张街角光影照片",
			CoverUrl:                  "media/image/owner-cover.jpg",
			Status:                    "published",
			Visibility:                "public",
			CreatedAt:                 now,
			UpdatedAt:                 now,
			PublishedAt:               now,
		},
		{
			ID:                        "post_target_video",
			AuthorId:                  "target_author",
			AuthorDisplayNameSnapshot: "目标作者",
			AuthorAvatarUrlSnapshot:   "media/avatar/target.jpg",
			ContentType:               "video",
			Title:                     "海边视频",
			CoverUrl:                  "media/video/target-cover.jpg",
			Status:                    "published",
			Visibility:                "public",
			CreatedAt:                 now,
			UpdatedAt:                 now,
			PublishedAt:               now,
		},
	})
	return NewPostService(store)
}

func TestListProfileInteractionActivitiesProjectsReceivedContractFields(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	if _, _, err := svc.LikePost(ctx, "post_owner_image", "actor_like", ""); err != nil {
		t.Fatalf("like owner post: %v", err)
	}
	if _, _, _, err := svc.SharePost(ctx, "post_owner_image", "actor_share", ""); err != nil {
		t.Fatalf("share owner post: %v", err)
	}
	if _, _, err := svc.AddComment(
		ctx,
		"post_owner_image",
		"actor_comment",
		"构图很稳",
		"",
		"actor_comment",
		"",
		nil,
		nil,
	); err != nil {
		t.Fatalf("comment owner post: %v", err)
	}

	items, _, _, err := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "received", "", 20)
	if err != nil {
		t.Fatalf("list received: %v", err)
	}
	byType := map[string]postmodel.ProfileInteractionActivityView{}
	for _, item := range items {
		byType[item.ActivityType] = item
	}

	like := byType["like"]
	if like.DisplaySubAccountId != "actor_like" ||
		like.DisplayName != "actor_like" ||
		like.DisplayUserRouteId != "userProfile" {
		t.Fatalf("received like display user mismatch: %#v", like)
	}
	if like.PrimaryText != "点赞了你的记录" ||
		like.PreviewMediaKind != "image" ||
		like.PreviewImageUrl != "media/image/owner-cover.jpg" ||
		like.PreviewObjectId != "post_owner_image" ||
		like.PreviewRouteId != "workBrowser" {
		t.Fatalf("received like projection mismatch: %#v", like)
	}
	if !stringSliceEqual(like.FilterKeys, []string{"all", "likes"}) {
		t.Fatalf("received like filter keys mismatch: %#v", like.FilterKeys)
	}

	comment := byType["comment"]
	if comment.CommentKind != "comment" ||
		comment.PrimaryText != "评论了你的记录：构图很稳" ||
		!stringSliceEqual(comment.FilterKeys, []string{"all", "comments"}) {
		t.Fatalf("received comment projection mismatch: %#v", comment)
	}
	if comment.CommentId == "" {
		t.Fatalf("received comment must carry commentId for deeplink: %#v", comment)
	}
	if comment.ParentCommentId != "" {
		t.Fatalf("top-level comment must have empty parentCommentId: %#v", comment)
	}

	share := byType["share"]
	if share.PrimaryText != "转发了你的记录" ||
		!stringSliceEqual(share.FilterKeys, []string{"all", "shares"}) {
		t.Fatalf("received share projection mismatch: %#v", share)
	}
}

func TestListProfileInteractionActivitiesWiresCommentIdentity(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	top, _, err := svc.AddComment(
		ctx,
		"post_owner_image",
		"actor_comment",
		"构图很稳",
		"",
		"actor_comment",
		"",
		nil,
		nil,
	)
	if err != nil {
		t.Fatalf("add top-level comment: %v", err)
	}
	topID, _ := top["_id"].(string)
	if topID == "" {
		t.Fatalf("top-level comment missing _id: %#v", top)
	}
	if _, _, err := svc.AddComment(
		ctx,
		"post_owner_image",
		"actor_reply",
		"同感",
		topID,
		"actor_reply",
		"",
		nil,
		nil,
	); err != nil {
		t.Fatalf("add reply comment: %v", err)
	}

	items, _, _, err := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "received", "", 20)
	if err != nil {
		t.Fatalf("list received: %v", err)
	}
	var topView, replyView postmodel.ProfileInteractionActivityView
	for _, item := range items {
		if item.ActivityType != "comment" {
			continue
		}
		if item.CommentKind == "reply" {
			replyView = item
		} else {
			topView = item
		}
	}
	if topView.CommentId != topID || topView.ParentCommentId != "" {
		t.Fatalf("top-level comment identity mismatch: %#v", topView)
	}
	if replyView.CommentId == "" || replyView.CommentId == topID {
		t.Fatalf("reply must carry its own commentId: %#v", replyView)
	}
	if replyView.ParentCommentId != topID {
		t.Fatalf("reply parentCommentId must point to top-level comment %q: %#v", topID, replyView)
	}
}

func TestListProfileInteractionActivitiesProjectsSentContractFields(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	if _, _, err := svc.LikePost(ctx, "post_target_video", "profile_owner", ""); err != nil {
		t.Fatalf("like target post: %v", err)
	}

	items, _, _, err := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "sent", "", 20)
	if err != nil {
		t.Fatalf("list sent: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected one sent interaction, got %d: %#v", len(items), items)
	}
	item := items[0]
	if item.DisplaySubAccountId != "target_author" ||
		item.DisplayName != "目标作者" ||
		item.DisplayAvatarUrl != "media/avatar/target.jpg" {
		t.Fatalf("sent display user should be target author: %#v", item)
	}
	if item.PrimaryText != "你点赞了TA的记录" ||
		item.PreviewMediaKind != "video" ||
		item.PreviewText != "海边视频" ||
		item.PreviewRouteId != "workBrowser" {
		t.Fatalf("sent projection mismatch: %#v", item)
	}
}

// TestListProfileInteractionActivitiesKeysetCursorPaginates 验证 keyset 游标分页：
// 逐页无重叠覆盖全集、hasMore/nextCursor 配对、触底结束态、确定性全序（含 createdAt 相等时的
// activityId tiebreak 路径），证明已替换旧的“内存排序 + 硬上限 50 静默丢尾”。
func TestListProfileInteractionActivitiesKeysetCursorPaginates(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	actors := []string{"actor_a", "actor_b", "actor_c", "actor_d", "actor_e"}
	for _, a := range actors {
		if _, _, err := svc.LikePost(ctx, "post_owner_image", a, ""); err != nil {
			t.Fatalf("like by %s: %v", a, err)
		}
	}

	seen := map[string]bool{}
	cursor := ""
	pages := 0
	total := 0
	for {
		items, next, hasMore, err := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "received", cursor, 2)
		if err != nil {
			t.Fatalf("page %d: %v", pages, err)
		}
		pages++
		for _, it := range items {
			if seen[it.ActivityId] {
				t.Fatalf("duplicate activity across pages: %s", it.ActivityId)
			}
			seen[it.ActivityId] = true
			total++
		}
		if !hasMore {
			if next != "" {
				t.Fatalf("exhausted page must not emit nextCursor, got %q", next)
			}
			break
		}
		if next == "" {
			t.Fatalf("hasMore page must emit nextCursor")
		}
		if len(items) != 2 {
			t.Fatalf("non-final page expected full limit 2, got %d", len(items))
		}
		cursor = next
		if pages > 10 {
			t.Fatalf("pagination did not terminate")
		}
	}
	if total != len(actors) {
		t.Fatalf("expected %d total interactions across pages, got %d", len(actors), total)
	}

	// 确定性全序：相同输入两次首页拉取必须一致（keyset 依赖确定性 tiebreak）。
	first1, _, _, _ := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "received", "", 2)
	first2, _, _, _ := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "received", "", 2)
	if len(first1) != 2 || len(first2) != 2 ||
		first1[0].ActivityId != first2[0].ActivityId ||
		first1[1].ActivityId != first2[1].ActivityId {
		t.Fatalf("first page not deterministic: %#v vs %#v", first1, first2)
	}

	// 损坏游标等价首页（不报错、不吞默认），与首页结果一致。
	corrupted, _, _, err := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "received", "not-a-valid-cursor", 2)
	if err != nil {
		t.Fatalf("corrupted cursor must not error: %v", err)
	}
	if len(corrupted) != 2 || corrupted[0].ActivityId != first1[0].ActivityId {
		t.Fatalf("corrupted cursor must fall back to first page: %#v", corrupted)
	}
}

func stringSliceEqual(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for i := range left {
		if left[i] != right[i] {
			return false
		}
	}
	return true
}
