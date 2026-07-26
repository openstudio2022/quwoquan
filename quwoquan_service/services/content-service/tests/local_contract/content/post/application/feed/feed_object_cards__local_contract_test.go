package feed_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	recpolicy "quwoquan_service/runtime/recpolicy"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

type stubObjectCardProvider struct {
	cards []ObjectCardView
	err   error
	calls int
}

func (s *stubObjectCardProvider) ObjectCards(_ context.Context, _ string, limit int) ([]ObjectCardView, error) {
	s.calls++
	if s.err != nil {
		return nil, s.err
	}
	if len(s.cards) > limit {
		return s.cards[:limit], s.err
	}
	return s.cards, s.err
}

func objectCardPolicy(cfg recpolicy.ObjectCardConfig) func() recpolicy.ObjectCardConfig {
	return func() recpolicy.ObjectCardConfig { return cfg }
}

func newObjectCardFeedService(t *testing.T, provider ObjectCardProvider, cfg recpolicy.ObjectCardConfig, postCount int) *FeedService {
	t.Helper()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	candidates := make([]rtrec.ContentCandidate, 0, postCount)
	posts := make([]postmodel.Post, 0, postCount)
	for i := 0; i < postCount; i++ {
		id := "p_card_" + string(rune('a'+i))
		candidates = append(candidates, rtrec.ContentCandidate{
			ContentID: id, ContentType: "image", PublishedAt: time.Now(),
		})
		posts = append(posts, postmodel.Post{
			ID: id, ContentType: "image", AuthorId: "author_" + id,
			Status: "published", Visibility: "public",
		})
	}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{
		&captureRecallSource{candidates: candidates},
	})
	return NewFeedService(
		engine,
		fixtureFeedReader{posts: posts},
		WithObjectCardProvider(provider, objectCardPolicy(cfg)),
	)
}

// W5 混合对象卡注入契约（B4 阶段一）：everyN 间隔锚定、maxCards 上限、
// 尾部不悬挂、仅推荐主链路注入。
func TestListFeed_ObjectCardsAnchoredByPolicyInterval(t *testing.T) {
	provider := &stubObjectCardProvider{cards: []ObjectCardView{
		{ObjectKind: "entity_homepage", ObjectID: "/entity/travel/景区/大理古城", Title: "大理古城"},
		{ObjectKind: "entity_homepage", ObjectID: "/entity/travel/景区/都江堰", Title: "都江堰"},
		{ObjectKind: "entity_homepage", ObjectID: "/entity/travel/景区/青城山", Title: "青城山"},
	}}
	svc := newObjectCardFeedService(t, provider, recpolicy.ObjectCardConfig{
		Enabled:      true,
		EveryN:       3,
		MaxCards:     2,
		AllowedKinds: []string{"entity_homepage"},
	}, 8)

	resp, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_cards", SessionID: "s_cards", ChannelID: "recommend", Limit: 8,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(resp.ObjectCards) != 2 {
		t.Fatalf("object cards = %d want 2 (maxCards cap), got %+v", len(resp.ObjectCards), resp.ObjectCards)
	}
	if resp.ObjectCards[0].AnchorIndex != 3 || resp.ObjectCards[1].AnchorIndex != 6 {
		t.Fatalf("anchor indexes = %d,%d want 3,6", resp.ObjectCards[0].AnchorIndex, resp.ObjectCards[1].AnchorIndex)
	}
	for _, card := range resp.ObjectCards {
		if card.AnchorIndex > len(resp.Items) {
			t.Fatalf("anchor %d must not exceed items %d", card.AnchorIndex, len(resp.Items))
		}
	}
}

func TestListFeed_ObjectCardsDisabledPolicyIsZeroCost(t *testing.T) {
	provider := &stubObjectCardProvider{cards: []ObjectCardView{
		{ObjectKind: "entity_homepage", ObjectID: "/entity/travel/景区/大理古城", Title: "大理古城"},
	}}
	svc := newObjectCardFeedService(t, provider, recpolicy.ObjectCardConfig{
		Enabled: false,
	}, 6)

	resp, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_cards_off", SessionID: "s_cards_off", ChannelID: "recommend", Limit: 6,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(resp.ObjectCards) != 0 {
		t.Fatalf("disabled policy must not inject cards, got %+v", resp.ObjectCards)
	}
	if provider.calls != 0 {
		t.Fatalf("disabled policy must not call provider (zero cost), calls=%d", provider.calls)
	}
}

func TestListFeed_ObjectCardsAnonymousAndBrowseFlowExcluded(t *testing.T) {
	provider := &stubObjectCardProvider{cards: []ObjectCardView{
		{ObjectKind: "entity_homepage", ObjectID: "/entity/travel/景区/大理古城", Title: "大理古城"},
	}}
	cfg := recpolicy.ObjectCardConfig{
		Enabled:      true,
		EveryN:       2,
		MaxCards:     2,
		AllowedKinds: []string{"entity_homepage"},
	}

	svc := newObjectCardFeedService(t, provider, cfg, 6)
	// 匿名（无 userID）：无个性化对象卡。
	anon, err := svc.ListFeed(context.Background(), ListFeedRequest{
		SessionID: "s_anon", ChannelID: "recommend", Limit: 6,
	})
	if err != nil {
		t.Fatalf("ListFeed anon: %v", err)
	}
	if len(anon.ObjectCards) != 0 {
		t.Fatalf("anonymous feed must not carry object cards, got %+v", anon.ObjectCards)
	}

	// 浏览流具名查询（identity/type）：不混排对象卡。
	browse, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_browse", SessionID: "s_browse", Identity: "work", Type: "image", Limit: 6,
	})
	if err != nil {
		t.Fatalf("ListFeed browse: %v", err)
	}
	if len(browse.ObjectCards) != 0 {
		t.Fatalf("browse flow must not carry object cards, got %+v", browse.ObjectCards)
	}
}

func TestListFeed_ObjectCardsProviderFailureFailsOpen(t *testing.T) {
	provider := &stubObjectCardProvider{err: context.DeadlineExceeded}
	svc := newObjectCardFeedService(t, provider, recpolicy.ObjectCardConfig{
		Enabled:      true,
		EveryN:       2,
		MaxCards:     1,
		AllowedKinds: []string{"entity_homepage"},
	}, 4)

	resp, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_cards_err", SessionID: "s_cards_err", ChannelID: "recommend", Limit: 4,
	})
	if err != nil {
		t.Fatalf("feed must not fail when object card provider fails: %v", err)
	}
	if len(resp.Items) == 0 {
		t.Fatalf("feed body must be intact on provider failure")
	}
	if len(resp.ObjectCards) != 0 {
		t.Fatalf("provider failure must degrade to no cards, got %+v", resp.ObjectCards)
	}
}

func TestListFeed_ObjectCardsFilterDisallowedKinds(t *testing.T) {
	provider := &stubObjectCardProvider{cards: []ObjectCardView{
		{ObjectKind: "user_card", ObjectID: "u_someone", Title: "某用户"},
		{ObjectKind: "entity_homepage", ObjectID: "/entity/travel/景区/大理古城", Title: "大理古城"},
	}}
	svc := newObjectCardFeedService(t, provider, recpolicy.ObjectCardConfig{
		Enabled:      true,
		EveryN:       2,
		MaxCards:     2,
		AllowedKinds: []string{"entity_homepage"},
	}, 6)

	resp, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_cards_kind", SessionID: "s_cards_kind", ChannelID: "recommend", Limit: 6,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(resp.ObjectCards) != 1 || resp.ObjectCards[0].ObjectKind != "entity_homepage" {
		t.Fatalf("S0 must only admit entity_homepage kind, got %+v", resp.ObjectCards)
	}
}
