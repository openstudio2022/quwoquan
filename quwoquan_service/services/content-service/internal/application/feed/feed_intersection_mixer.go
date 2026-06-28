package feed

import (
	"context"
	"hash/fnv"
	"strings"

	"quwoquan_service/services/content-service/internal/application/intersection"
)

// feedIntersectionProvider 提供 viewer 的交集理由池（已含 primaryText/weightTier 等显示语言）。
type feedIntersectionProvider interface {
	Feed(ctx context.Context, userID, channel string, limit int) ([]intersection.IntersectionReasonView, error)
}

// 内容流交集频率契约（体验规格 70/20/10）：
// 70% 内容无交集、20% 轻交集（light）、10% 重交集（heavy）。
const (
	feedIntersectionHeavyPercent = 10
	feedIntersectionLightPercent = 20
	feedIntersectionPoolLimit    = 24
)

// attachFeedIntersections 按 70/20/10 给 feed item 附着交集理由。
// 槽位由 (userID, postID) 稳定散列决定，保证同一用户分页/刷新间配比与落点一致；
// reason 按 weightTier 与槽位轻重匹配，池中无对应等级时该槽位保持无交集。
func attachFeedIntersections(views []FeedItemView, reasons []intersection.IntersectionReasonView, userID string) {
	if len(views) == 0 || len(reasons) == 0 {
		return
	}
	var lightPool, heavyPool []intersection.IntersectionReasonView
	for _, r := range reasons {
		switch r.WeightTier {
		case "heavy":
			heavyPool = append(heavyPool, r)
		default:
			lightPool = append(lightPool, r)
		}
	}
	for i := range views {
		bucket := stableFeedBucket(userID, views[i].PostID)
		switch {
		case bucket < feedIntersectionHeavyPercent && len(heavyPool) > 0:
			views[i].IntersectionReasons = []intersection.IntersectionReasonView{
				heavyPool[int(stableFeedHash(userID, views[i].PostID))%len(heavyPool)],
			}
		case bucket < feedIntersectionHeavyPercent+feedIntersectionLightPercent && len(lightPool) > 0:
			views[i].IntersectionReasons = []intersection.IntersectionReasonView{
				lightPool[int(stableFeedHash(userID, views[i].PostID))%len(lightPool)],
			}
		}
	}
}

func stableFeedHash(userID, postID string) uint32 {
	h := fnv.New32a()
	_, _ = h.Write([]byte(strings.TrimSpace(userID)))
	_, _ = h.Write([]byte{':'})
	_, _ = h.Write([]byte(strings.TrimSpace(postID)))
	return h.Sum32()
}

func stableFeedBucket(userID, postID string) int {
	// 与取池下标的 hash 加盐区分，避免桶位与池下标强相关。
	h := fnv.New32a()
	_, _ = h.Write([]byte("bucket:"))
	_, _ = h.Write([]byte(strings.TrimSpace(userID)))
	_, _ = h.Write([]byte{':'})
	_, _ = h.Write([]byte(strings.TrimSpace(postID)))
	return int(h.Sum32() % 100)
}
