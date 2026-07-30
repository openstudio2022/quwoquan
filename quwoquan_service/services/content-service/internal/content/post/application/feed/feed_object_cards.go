package feed

import (
	"context"
	"strings"

	rtrec "quwoquan_service/runtime/recommendation"
	recpolicy "quwoquan_service/runtime/recpolicy"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
)

// ObjectCardView 是随 feed envelope 下发的混合对象卡（B4 阶段一插卡模式）。
// 契约真相源：services/content-service/contracts/content/post/projections/feed_object_card.yaml。
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

// ObjectCardProvider 提供 viewer 个性化的对象卡候选（S0 仅实体主页卡）。
// 读路径只消费物化读模型/特征投影，禁止同步打分或跨服务调用；失败/为空时
// feed 主体不受影响（对象卡是增强位，fail-open 到无卡）。
type ObjectCardProvider interface {
	ObjectCards(ctx context.Context, userID string, limit int) ([]ObjectCardView, error)
}

// WithObjectCardProvider 注入对象卡召回器与策略读取器。策略（enabled/everyN/
// maxCards/allowedKinds）经热加载 recpolicy 读取，运营可配可回滚。
func WithObjectCardProvider(provider ObjectCardProvider, policy func() recpolicy.ObjectCardConfig) FeedServiceOption {
	return func(s *FeedService) {
		s.objectCards = provider
		s.objectCardPolicy = policy
	}
}

// resolveObjectCards 按策略装配本页对象卡：每 everyN 条内容后插一张
// （anchorIndex = everyN, 2*everyN, ...），单页不超过 maxCards，且 anchor
// 不越过本页内容长度（尾部不悬挂对象卡）。任何失败都静默降级为无卡。
func (s *FeedService) resolveObjectCards(
	ctx context.Context,
	userID string,
	itemCount int,
) []ObjectCardView {
	if s.objectCards == nil || s.objectCardPolicy == nil || itemCount <= 0 {
		return nil
	}
	// 对象卡是 viewer 个性化增强位：匿名（含规范化后的匿名 fallback 身份）不注入。
	trimmedUser := strings.TrimSpace(userID)
	if trimmedUser == "" || trimmedUser == identity.AnonymousFallbackPersonaID {
		return nil
	}
	cfg := s.objectCardPolicy()
	if !cfg.Enabled || cfg.EveryN <= 0 || cfg.MaxCards <= 0 {
		return nil
	}
	maxAnchored := itemCount / cfg.EveryN
	if maxAnchored <= 0 {
		return nil
	}
	limit := cfg.MaxCards
	if maxAnchored < limit {
		limit = maxAnchored
	}
	cards, err := s.objectCards.ObjectCards(ctx, userID, limit)
	if err != nil {
		// fail-open 到无卡，但失败必须可观测（N1-2：provider 静默吞错→零观测）。
		rtrec.RecordObjectCardsProviderError()
		return nil
	}
	if len(cards) == 0 {
		return nil
	}
	allowed := make(map[string]bool, len(cfg.AllowedKinds))
	for _, kind := range cfg.AllowedKinds {
		allowed[kind] = true
	}
	out := make([]ObjectCardView, 0, limit)
	for _, card := range cards {
		if len(out) >= limit {
			break
		}
		if strings.TrimSpace(card.ObjectID) == "" || !allowed[card.ObjectKind] {
			continue
		}
		card.AnchorIndex = (len(out) + 1) * cfg.EveryN
		if card.AnchorIndex > itemCount {
			break
		}
		out = append(out, card)
	}
	if len(out) == 0 {
		return nil
	}
	rtrec.RecordObjectCardsAssembled(len(out))
	return out
}
