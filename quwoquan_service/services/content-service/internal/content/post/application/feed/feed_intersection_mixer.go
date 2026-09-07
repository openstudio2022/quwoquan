package feed

import (
	"context"
	"hash/fnv"
	"log/slog"
	"strings"

	"quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

// feedIntersectionProvider 提供 viewer 的交集理由池（已含 primaryText/weightTier 等显示语言）。
type FeedIntersectionProvider interface {
	Feed(ctx context.Context, userID, channel string, limit int) ([]intersection.IntersectionReasonView, error)
}

// 内容流交集频率契约（体验规格 70/20/10）：
// 70% 内容无交集、20% 轻交集（light）、10% 重交集（heavy）。
const (
	FeedIntersectionHeavyPercent = 10
	FeedIntersectionLightPercent = 20
	// IntersectionReasonPoolLimit 是 viewer 交集读面单次取池上限；feed 与 GetPost
	// 必须共用同一个数，否则详情页与已装饰 feed item 的候选池不同源。
	IntersectionReasonPoolLimit = 24
)

// AttachFeedIntersections 按 70/20/10 给 feed item 附着交集理由。
// 槽位由 (userID, postID) 稳定散列决定，保证同一用户分页/刷新间配比与落点一致；
// reason 必须能证明与当前 Post 的上下文关联；行动 target 可继续指向地点/人，
// 不能为通过附着校验而覆写成 postId，否则会丢失 typed 行动落点。
func AttachFeedIntersections(views []FeedItemView, reasons []intersection.IntersectionReasonView, userID string) {
	if len(views) == 0 || len(reasons) == 0 {
		return
	}
	for i := range views {
		postID := strings.TrimSpace(views[i].PostID)
		if postID == "" {
			continue
		}
		// 先按真实 Post 宿主投影再入池：不满足展示合同的候选（hidden）不得占用该 Post 的
		// 唯一交集槽位，否则一条落选候选会让本来有可见交集的内容卡空着。
		lightPool, heavyPool := displayReadyFeedPools(reasons, views[i])
		bucket := StableFeedBucket(userID, postID)
		switch {
		case bucket < FeedIntersectionHeavyPercent && len(heavyPool) > 0:
			views[i].IntersectionReasons = []intersection.IntersectionReasonView{
				heavyPool[int(stableFeedHash(userID, postID))%len(heavyPool)],
			}
		case bucket < FeedIntersectionHeavyPercent+FeedIntersectionLightPercent && len(lightPool) > 0:
			views[i].IntersectionReasons = []intersection.IntersectionReasonView{
				lightPool[int(stableFeedHash(userID, postID))%len(lightPool)],
			}
		}
	}
}

// displayReadyFeedPools 把 ReasonPoolsForPost 的两池各自经宿主上下文投影，只保留 display-ready 的候选。
func displayReadyFeedPools(reasons []intersection.IntersectionReasonView, view FeedItemView) ([]intersection.IntersectionReasonView, []intersection.IntersectionReasonView) {
	lightPool, heavyPool := ReasonPoolsForPost(reasons, view)
	return decorateDisplayReady(lightPool, view.PostID), decorateDisplayReady(heavyPool, view.PostID)
}

func decorateDisplayReady(pool []intersection.IntersectionReasonView, postID string) []intersection.IntersectionReasonView {
	out := make([]intersection.IntersectionReasonView, 0, len(pool))
	for _, reason := range pool {
		decorated := applyFeedHostContext(reason, postID)
		if strings.TrimSpace(decorated.DisplayBinding) == intersection.DisplayBindingHidden {
			continue
		}
		out = append(out, decorated)
	}
	return out
}

// IntersectionsForPost returns the first Recommendation-ranked display-ready
// reason whose canonical post/homepage/gathering anchor belongs to the current Post.
// GetPost uses this projection without the Feed 70/20/10 exposure bucket so a deep
// link preserves the same capability as an already-decorated feed item.
//
// 宿主上下文投影会把不满足展示合同的候选降级成 hidden（空主句、无 spans、无行动）。
// 单槽位必须继续向后找，否则一条落选候选就会占满 Post 的唯一交集位。
func IntersectionsForPost(view FeedItemView, reasons []intersection.IntersectionReasonView) []intersection.IntersectionReasonView {
	for _, reason := range reasons {
		if !feedReasonTargetsPost(reason, view) {
			continue
		}
		decorated := applyFeedHostContext(reason, view.PostID)
		if strings.TrimSpace(decorated.DisplayBinding) == intersection.DisplayBindingHidden {
			continue
		}
		return []intersection.IntersectionReasonView{decorated}
	}
	return nil
}

// LogIntersectionReadFailure 是交集读面失败的唯一观测出口（feed 与 Post 详情共用）：
// 降级本身是既定纪律，但失败必须与「没有交集」区分开，否则读面故障在响应里不可归因。
// surface 标识读面（feed / post_detail），subject 是该读面的定位键（channelId / postId）。
func LogIntersectionReadFailure(surface, subject string, err error) {
	if err == nil {
		return
	}
	slog.Default().Warn(
		"intersection_read_failed",
		slog.String("surface", strings.TrimSpace(surface)),
		slog.String("subject", strings.TrimSpace(subject)),
		slog.String("error", err.Error()),
	)
}

// ReasonPoolsForPost 把 reason 池按宿主 Post 过滤并按 WeightTier 分成轻/重两池。
func ReasonPoolsForPost(reasons []intersection.IntersectionReasonView, view FeedItemView) ([]intersection.IntersectionReasonView, []intersection.IntersectionReasonView) {
	var lightPool, heavyPool []intersection.IntersectionReasonView
	for _, r := range reasons {
		if !feedReasonTargetsPost(r, view) {
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

// feedReasonTargetsPost 判定 reason 的宿主锚点是否属于当前 Post。
//
// subjectContext 语法为 `<objectType>:<objectId>`：objectType 是注册表
// objectTypeBindings 的开放词汇，这里只经生成表翻成 objectKind，再按 Content
// 自己的宿主字段绑定（内容→PostID、homepage 路由对象→PrimaryHomepageID、
// gathering→GatheringRef）。未登记前缀或无 typed prefix 一律 fail-closed，
// 不按取值形态反推类型。
func feedReasonTargetsPost(r intersection.IntersectionReasonView, view FeedItemView) bool {
	postID := strings.TrimSpace(view.PostID)
	if postID == "" {
		return false
	}
	if anchor := strings.TrimSpace(r.SubjectContext); anchor != "" {
		anchorKind, anchorID, ok := resolveIntersectionHostAnchor(anchor)
		if !ok {
			return false
		}
		switch {
		case anchorKind == "content":
			return anchorID == postID
		case anchorKind == "gathering":
			return anchorID == strings.TrimSpace(view.GatheringRef)
		case anchorRoutesToHomepage(anchorKind):
			return anchorID == strings.TrimSpace(view.PrimaryHomepageID)
		default:
			return false
		}
	}
	// 内容型 reason 的真实对象本来就是当前 Post，允许 target identity 直接证明。
	// 地点/人/行动类 reason 若未携带 canonical subjectContext 则 fail-closed，
	// 禁止随机嫁接到同槽内容。
	if strings.TrimSpace(r.ObjectKind) != "content" {
		return false
	}
	targetID := strings.TrimSpace(r.ActionTargetID)
	if targetID == "" {
		targetID = strings.TrimSpace(r.RelationObjectID)
	}
	return targetID == postID
}

// anchorRoutesToHomepage 判定锚点对象是否落在实体主页路由上（place / school /
// enterprise 等实体 kind 共用 homepageDetail），此时以 Post 的 PrimaryHomepageID 证明宿主。
// 只比较注册表 routeId，不枚举 kind 名，新增垂类不改此处。
func anchorRoutesToHomepage(anchorKind string) bool {
	route := intersection.RouteIDForObjectKind(anchorKind)
	return route != "" && route == intersection.RouteIDForObjectKind("place")
}

// resolveIntersectionHostAnchor 把 `<objectType>:<objectId>` 翻成注册表 objectKind。
// 只查生成表，不维护第二份 objectType 词汇；无 typed prefix 或未登记均返回 ok=false。
func resolveIntersectionHostAnchor(anchor string) (objectKind, objectID string, ok bool) {
	prefix, id, found := strings.Cut(anchor, ":")
	if !found {
		return "", "", false
	}
	objectKind = intersection.ObjectKindForObjectType(prefix)
	objectID = strings.TrimSpace(id)
	if objectKind == "" || objectID == "" {
		return "", "", false
	}
	return objectKind, objectID, true
}

func applyFeedHostContext(r intersection.IntersectionReasonView, postID string) intersection.IntersectionReasonView {
	host := &intersection.IntersectionTargetView{
		ObjectType: "post",
		ObjectID:   strings.TrimSpace(postID),
		ObjectKind: "content",
		RouteID:    intersection.RouteIDForObjectKind("content"),
	}
	binding := intersection.DisplayBindingHostImplicit
	if strings.TrimSpace(r.ObjectKind) != "content" {
		// Related place/person reasons are attached through SubjectContext, while
		// their visible object and action target remain explicit and actionable.
		binding = intersection.DisplayBindingExplicitLink
	}
	return intersection.ApplyDisplayContext(r, intersection.DisplayContext{
		Surface:    intersection.DisplaySurfaceFeed,
		HostTarget: host,
		Binding:    binding,
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
