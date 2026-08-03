package feed

import (
	"fmt"
	"strings"

	rtrec "quwoquan_service/runtime/recommendation"
	recpolicy "quwoquan_service/runtime/recpolicy"
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
)

// ObjectCardView 是 Content 在 Post hydration 后写入 FeedDeliveryPage 并随
// feed envelope 交付的展示快照。候选身份、标题、标签、理由与召回路径均来自
// Recommendation 的不可变 RankedRecommendationWindow；Content 只按当前页面
// 长度计算 anchorIndex，不再读取任何推荐、Entity 或 User 私有存储。
type ObjectCardView struct {
	ObjectKind  string   `json:"objectKind"`
	ObjectID    string   `json:"objectId"`
	Title       string   `json:"title"`
	Subtitle    string   `json:"subtitle,omitempty"`
	CoverURL    string   `json:"coverUrl,omitempty"`
	TagRefs     []string `json:"tagRefs,omitempty"`
	ReasonText  string   `json:"reasonText,omitempty"`
	RecallPath  string   `json:"recallPath,omitempty"`
	AnchorIndex int      `json:"anchorIndex"`
}

// WithObjectCardPolicy 注入 Content 拥有的页面布局策略。它只决定当前已 hydrate
// 页面中的展示间隔和上限，不能召回、补全或重新排序对象卡。
func WithObjectCardPolicy(policy func() recpolicy.ObjectCardConfig) FeedServiceOption {
	return func(service *FeedService) {
		service.objectCardPolicy = policy
	}
}

// resolveObjectCards 把 Recommendation 窗口中已经冻结的 typed 对象卡映射为
// Content 展示快照。非法跨域载荷必须使推荐请求 fail-closed，禁止退化成成功空卡。
func (service *FeedService) resolveObjectCards(
	candidates []transport.RecommendationObjectCard,
	itemCount int,
) ([]ObjectCardView, error) {
	if service == nil || service.objectCardPolicy == nil ||
		itemCount <= 0 || len(candidates) == 0 {
		return nil, nil
	}
	policy := service.objectCardPolicy()
	if !policy.Enabled || policy.EveryN <= 0 || policy.MaxCards <= 0 {
		return nil, nil
	}
	maxAnchored := itemCount / policy.EveryN
	if maxAnchored <= 0 {
		return nil, nil
	}
	limit := min(policy.MaxCards, maxAnchored)
	allowedKinds := make(map[string]struct{}, len(policy.AllowedKinds))
	for _, kind := range policy.AllowedKinds {
		normalized := strings.TrimSpace(kind)
		if normalized != "" {
			allowedKinds[normalized] = struct{}{}
		}
	}

	result := make([]ObjectCardView, 0, limit)
	seen := make(map[string]struct{}, len(candidates))
	for _, candidate := range candidates {
		kind := strings.TrimSpace(candidate.ObjectKind)
		objectID := strings.TrimSpace(candidate.ObjectId)
		title := strings.TrimSpace(candidate.Title)
		reason := strings.TrimSpace(candidate.ReasonKey)
		recallPath := strings.TrimSpace(candidate.RecallPath)
		if kind == "" || objectID == "" || title == "" || reason == "" || recallPath == "" {
			return nil, fmt.Errorf("ranked recommendation object card is incomplete")
		}
		if _, duplicate := seen[objectID]; duplicate {
			return nil, fmt.Errorf("ranked recommendation object card identity is duplicated")
		}
		seen[objectID] = struct{}{}
		if _, allowed := allowedKinds[kind]; !allowed {
			continue
		}
		tags := make([]string, 0, len(candidate.TagRefs))
		seenTags := make(map[string]struct{}, len(candidate.TagRefs))
		for _, rawTag := range candidate.TagRefs {
			tag := strings.TrimSpace(rawTag)
			if tag == "" {
				return nil, fmt.Errorf("ranked recommendation object card tag is empty")
			}
			if _, duplicate := seenTags[tag]; duplicate {
				return nil, fmt.Errorf("ranked recommendation object card tag is duplicated")
			}
			seenTags[tag] = struct{}{}
			tags = append(tags, tag)
		}
		anchor := (len(result) + 1) * policy.EveryN
		if anchor > itemCount || len(result) >= limit {
			break
		}
		result = append(result, ObjectCardView{
			ObjectKind:  kind,
			ObjectID:    objectID,
			Title:       title,
			Subtitle:    strings.TrimSpace(optionalRecommendationText(candidate.Subtitle)),
			CoverURL:    strings.TrimSpace(optionalRecommendationText(candidate.CoverUrl)),
			TagRefs:     tags,
			ReasonText:  reason,
			RecallPath:  recallPath,
			AnchorIndex: anchor,
		})
	}
	if len(result) > 0 {
		rtrec.RecordObjectCardsAssembled(len(result))
	}
	return result, nil
}

func optionalRecommendationText(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}
