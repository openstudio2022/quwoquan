package feed

import (
	"context"
	"hash/fnv"
	"strings"

	"quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

// feedIntersectionProvider 提供 viewer 的交集理由池（已含 primaryText/weightTier 等显示语言）。
type feedIntersectionProvider interface {
	Feed(ctx context.Context, userID, channel string, limit int) ([]intersection.IntersectionReasonView, error)
}

// 内容流交集频率契约（体验规格 70/20/10）：
// 70% 内容无交集、20% 轻交集（light）、10% 重交集（heavy）。
const (
	FeedIntersectionHeavyPercent = 10
	FeedIntersectionLightPercent = 20
	feedIntersectionPoolLimit    = 24
)

// AttachFeedIntersections 按 70/20/10 给 feed item 附着交集理由。
// 槽位由 (userID, postID) 稳定散列决定，保证同一用户分页/刷新间配比与落点一致；
// reason 必须先证明 target 指向当前 post，70/20/10 只决定有效候选是否曝光。
func AttachFeedIntersections(views []FeedItemView, reasons []intersection.IntersectionReasonView, userID string) {
	if len(views) == 0 || len(reasons) == 0 {
		return
	}
	for i := range views {
		postID := strings.TrimSpace(views[i].PostID)
		if postID == "" {
			continue
		}
		lightPool, heavyPool := feedReasonPoolsForPost(reasons, postID)
		bucket := StableFeedBucket(userID, postID)
		switch {
		case bucket < FeedIntersectionHeavyPercent && len(heavyPool) > 0:
			views[i].IntersectionReasons = []intersection.IntersectionReasonView{
				applyFeedHostContext(heavyPool[int(stableFeedHash(userID, postID))%len(heavyPool)], postID),
			}
		case bucket < FeedIntersectionHeavyPercent+FeedIntersectionLightPercent && len(lightPool) > 0:
			views[i].IntersectionReasons = []intersection.IntersectionReasonView{
				applyFeedHostContext(lightPool[int(stableFeedHash(userID, postID))%len(lightPool)], postID),
			}
		}
	}
}

func feedReasonPoolsForPost(reasons []intersection.IntersectionReasonView, postID string) ([]intersection.IntersectionReasonView, []intersection.IntersectionReasonView) {
	var lightPool, heavyPool []intersection.IntersectionReasonView
	for _, r := range reasons {
		if !feedReasonTargetsPost(r, postID) {
			continue
		}
		switch r.WeightTier {
		case "heavy":
			heavyPool = append(heavyPool, r)
		default:
			lightPool = append(lightPool, r)
		}
	}
	return lightPool, heavyPool
}

func feedReasonTargetsPost(r intersection.IntersectionReasonView, postID string) bool {
	targetID := strings.TrimSpace(r.ActionTargetID)
	if targetID == "" {
		targetID = strings.TrimSpace(r.RelationObjectID)
	}
	return strings.TrimSpace(postID) != "" && targetID == strings.TrimSpace(postID)
}

func applyFeedHostContext(r intersection.IntersectionReasonView, postID string) intersection.IntersectionReasonView {
	host := &intersection.IntersectionTargetView{
		ObjectType: "post",
		ObjectID:   strings.TrimSpace(postID),
		ObjectKind: "content",
		RouteID:    "contentDetail",
	}
	return intersection.ApplyDisplayContext(r, intersection.DisplayContext{
		Surface:    intersection.DisplaySurfaceFeed,
		HostTarget: host,
		Binding:    intersection.DisplayBindingHostImplicit,
	})
}

func stableFeedHash(userID, postID string) uint32 {
	h := fnv.New32a()
	_, _ = h.Write([]byte(strings.TrimSpace(userID)))
	_, _ = h.Write([]byte{':'})
	_, _ = h.Write([]byte(strings.TrimSpace(postID)))
	return h.Sum32()
}

func StableFeedBucket(userID, postID string) int {
	// 与取池下标的 hash 加盐区分，避免桶位与池下标强相关。
	h := fnv.New32a()
	_, _ = h.Write([]byte("bucket:"))
	_, _ = h.Write([]byte(strings.TrimSpace(userID)))
	_, _ = h.Write([]byte{':'})
	_, _ = h.Write([]byte(strings.TrimSpace(postID)))
	return int(h.Sum32() % 100)
}
