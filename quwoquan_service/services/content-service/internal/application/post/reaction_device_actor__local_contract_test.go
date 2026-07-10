package post

import (
	"context"
	"quwoquan_service/services/content-service/internal/application/identity"
	"testing"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// Track B 合约：点赞/分享按 actor 维度（账号优先、否则派生设备标识 deviceActorId）
// 独立计数；游客设备态可真实写入，登录用户走账号维度，两者不并账。
//
// 注意：本测试在 application 包内（白盒）以断言未导出的 reactionActorKey，
// 因此自建种子 Post（不引用 infrastructure/recommendation，避免 import cycle）。

func newReactionTestService() *PostService {
	now := time.Now().UTC()
	store := persistence.NewPostStore([]postmodel.Post{
		{
			ID:          "post_micro_001",
			AuthorId:    "user_1001",
			ContentType: "micro",
			Title:       "seed",
			LikeCount:   23,
			ShareCount:  2,
			CreatedAt:   now,
			PublishedAt: now,
			Status:      "published",
			Visibility:  "public",
		},
	})
	return NewPostService(
		store,
		WithCommentStore(persistence.NewMemoryCommentStore()),
		WithCommentReactionStore(persistence.NewMemoryCommentReactionStore()),
	)
}

func TestReactionActorKey_UserFirstThenDevice(t *testing.T) {
	if got := identity.ReactionActorKey("user_1", "dev_abc"); got != "user_1" {
		t.Fatalf("账号维度应优先 userId，got %q", got)
	}
	if got := identity.ReactionActorKey("", "dev_abc"); got != identity.DeviceActorKeyPrefix+"dev_abc" {
		t.Fatalf("游客应回落到设备维度键，got %q", got)
	}
	if got := identity.ReactionActorKey("  ", "  "); got != identity.AnonymousFallbackSubAccountID {
		t.Fatalf("二者皆空应回落匿名常量，got %q", got)
	}
	// 账号维度键与设备维度键键空间不相交（命名空间化），保证天然独立计数。
	if identity.ReactionActorKey("dev_abc", "") == identity.ReactionActorKey("", "dev_abc") {
		t.Fatalf("同名账号与设备不得映射到同一键")
	}
}

func TestLikePost_GuestDeviceDimensionIndependentAndIdempotent(t *testing.T) {
	svc := newReactionTestService()
	ctx := context.Background()
	const postID = "post_micro_001" // 种子 LikeCount=23

	// 游客设备 A 首次点赞：计数 +1，changed=true。
	count, changed, err := svc.LikePost(ctx, postID, "", "device_A")
	if err != nil {
		t.Fatalf("device A like: %v", err)
	}
	if !changed || count != 24 {
		t.Fatalf("device A 首赞应 changed=true count=24，got changed=%v count=%d", changed, count)
	}

	// 同设备重复点赞：幂等，count 不变、changed=false。
	count, changed, err = svc.LikePost(ctx, postID, "", "device_A")
	if err != nil {
		t.Fatalf("device A like again: %v", err)
	}
	if changed || count != 24 {
		t.Fatalf("device A 重复赞应幂等 count=24 changed=false，got changed=%v count=%d", changed, count)
	}

	// 另一游客设备 B：独立维度，再 +1。
	count, _, err = svc.LikePost(ctx, postID, "", "device_B")
	if err != nil {
		t.Fatalf("device B like: %v", err)
	}
	if count != 25 {
		t.Fatalf("device B 独立点赞应 count=25，got %d", count)
	}

	// 登录用户 U：账号维度独立，再 +1。
	count, changed, err = svc.LikePost(ctx, postID, "user_777", "device_A")
	if err != nil {
		t.Fatalf("user like: %v", err)
	}
	if !changed || count != 26 {
		t.Fatalf("账号维度应独立于设备维度 count=26 changed=true，got changed=%v count=%d", changed, count)
	}

	// 读回各 actor 的设备态：A 已赞，C 未赞，账号 U 已赞。
	likedA, _ := svc.GetReactionState(postID, "", "device_A")
	likedC, _ := svc.GetReactionState(postID, "", "device_C")
	likedU, _ := svc.GetReactionState(postID, "user_777", "")
	if !likedA {
		t.Fatalf("device A 读回应已点赞")
	}
	if likedC {
		t.Fatalf("device C 未点赞，读回不应为 true")
	}
	if !likedU {
		t.Fatalf("账号 U 读回应已点赞")
	}
}

func TestUnlikePost_DeviceDimensionSymmetric(t *testing.T) {
	svc := newReactionTestService()
	ctx := context.Background()
	const postID = "post_micro_001"

	if _, _, err := svc.LikePost(ctx, postID, "", "device_A"); err != nil {
		t.Fatalf("like: %v", err)
	}
	count, changed, err := svc.UnlikePost(ctx, postID, "", "device_A")
	if err != nil {
		t.Fatalf("unlike: %v", err)
	}
	if !changed || count != 23 {
		t.Fatalf("取消点赞应回到种子值 23 changed=true，got changed=%v count=%d", changed, count)
	}
	// 幂等：重复取消不再变化。
	count, changed, _ = svc.UnlikePost(ctx, postID, "", "device_A")
	if changed || count != 23 {
		t.Fatalf("重复取消应幂等 count=23 changed=false，got changed=%v count=%d", changed, count)
	}
}

func TestSharePost_GuestDeviceDimensionIndependent(t *testing.T) {
	svc := newReactionTestService()
	ctx := context.Background()
	const postID = "post_micro_001" // 种子 ShareCount=2

	count, changed, shared, err := svc.SharePost(ctx, postID, "", "device_A")
	if err != nil {
		t.Fatalf("device A share: %v", err)
	}
	if !changed || !shared || count != 3 {
		t.Fatalf("device A 首次分享应 count=3 changed/shared=true，got changed=%v shared=%v count=%d", changed, shared, count)
	}

	// 同设备幂等。
	count, changed, _, err = svc.SharePost(ctx, postID, "", "device_A")
	if err != nil {
		t.Fatalf("device A share again: %v", err)
	}
	if changed || count != 3 {
		t.Fatalf("device A 重复分享应幂等 count=3 changed=false，got changed=%v count=%d", changed, count)
	}

	// 另一设备独立累加。
	count, _, _, err = svc.SharePost(ctx, postID, "", "device_B")
	if err != nil {
		t.Fatalf("device B share: %v", err)
	}
	if count != 4 {
		t.Fatalf("device B 独立分享应 count=4，got %d", count)
	}

	// 登录账号维度独立。
	count, _, _, err = svc.SharePost(ctx, postID, "user_777", "device_A")
	if err != nil {
		t.Fatalf("user share: %v", err)
	}
	if count != 5 {
		t.Fatalf("账号维度独立分享应 count=5，got %d", count)
	}

	// 设备 A 读回 shared=true，设备 C 读回 shared=false。
	if _, sharedA := svc.GetReactionState(postID, "", "device_A"); !sharedA {
		t.Fatalf("device A 读回应已分享")
	}
	if _, sharedC := svc.GetReactionState(postID, "", "device_C"); sharedC {
		t.Fatalf("device C 未分享，读回不应为 true")
	}
}
