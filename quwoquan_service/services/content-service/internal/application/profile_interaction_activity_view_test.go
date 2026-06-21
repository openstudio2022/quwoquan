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

	items, err := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "received", 20)
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

	items, err := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "received", 20)
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

	items, err := svc.ListProfileInteractionActivities(ctx, "profile_owner", "profile_owner", "sent", 20)
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
