package feed_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	recpolicy "quwoquan_service/runtime/recpolicy"
	rtredis "quwoquan_service/runtime/redis"
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	testsupport "quwoquan_service/services/content-service/tests/support"
)

func objectCardPolicy(cfg recpolicy.ObjectCardConfig) func() recpolicy.ObjectCardConfig {
	return func() recpolicy.ObjectCardConfig { return cfg }
}

func rankedObjectCard(kind, id, title string) transport.RecommendationObjectCard {
	return transport.RecommendationObjectCard{
		ObjectKind: kind,
		ObjectId:   id,
		Title:      title,
		TagRefs:    []string{"travel.photography.landmark"},
		ReasonKey:  "shared_interest",
		RecallPath: "candidate_index",
	}
}

func rankedGatheringCard(id, title string) transport.RecommendationObjectCard {
	card := rankedObjectCard("gathering", id, title)
	card.ReasonKey = "public_gathering"
	card.RecallPath = "gathering_candidate_index"
	return card
}

func newObjectCardFeedService(
	t *testing.T,
	cards []transport.RecommendationObjectCard,
	cfg recpolicy.ObjectCardConfig,
	postCount int,
) *FeedService {
	t.Helper()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(
		rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
		2*time.Second,
		1000,
	)
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
		fixtureFeedReader{posts: posts},
		testsupport.RankedRecommendationOptionsWithObjectCards(
			engine,
			cards,
			WithObjectCardPolicy(objectCardPolicy(cfg)),
			readyActiveSupplyOption(),
		)...,
	)
}

// Recommendation 冻结候选与理由，Content 仅按页面长度和布局策略计算 anchor。
func TestListFeed_ObjectCardsAnchoredByPolicyInterval(t *testing.T) {
	cards := []transport.RecommendationObjectCard{
		rankedObjectCard("entity_homepage", "homepage_dali", "大理古城"),
		rankedObjectCard("entity_homepage", "homepage_dujiangyan", "都江堰"),
		rankedObjectCard("entity_homepage", "homepage_qingcheng", "青城山"),
	}
	svc := newObjectCardFeedService(t, cards, recpolicy.ObjectCardConfig{
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

func TestListFeed_GatheringCardPreservesCanonicalTargetReference(t *testing.T) {
	svc := newObjectCardFeedService(
		t,
		[]transport.RecommendationObjectCard{
			rankedGatheringCard("gathering-001", "周末山野徒步"),
		},
		recpolicy.ObjectCardConfig{
			Enabled:      true,
			EveryN:       2,
			MaxCards:     1,
			AllowedKinds: []string{"gathering"},
		},
		4,
	)

	resp, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_gathering_card", SessionID: "s_gathering_card",
		ChannelID: "recommend", Limit: 4,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(resp.ObjectCards) != 1 {
		t.Fatalf("gathering cards=%d want 1", len(resp.ObjectCards))
	}
	card := resp.ObjectCards[0]
	if card.ObjectKind != "gathering" || card.ObjectID != "gathering-001" {
		t.Fatalf("canonical Gathering card reference drifted: %+v", card)
	}
}

func TestListFeed_ObjectCardsDisabledPolicyDoesNotDeliverCards(t *testing.T) {
	svc := newObjectCardFeedService(
		t,
		[]transport.RecommendationObjectCard{
			rankedObjectCard("entity_homepage", "homepage_dali", "大理古城"),
		},
		recpolicy.ObjectCardConfig{Enabled: false},
		6,
	)

	resp, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_cards_off", SessionID: "s_cards_off", ChannelID: "recommend", Limit: 6,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(resp.ObjectCards) != 0 {
		t.Fatalf("disabled policy must not deliver cards, got %+v", resp.ObjectCards)
	}
}

func TestListFeed_ObjectCardsExcludedFromPostBrowseQuery(t *testing.T) {
	svc := newObjectCardFeedService(
		t,
		[]transport.RecommendationObjectCard{
			rankedObjectCard("entity_homepage", "homepage_dali", "大理古城"),
		},
		recpolicy.ObjectCardConfig{
			Enabled:      true,
			EveryN:       2,
			MaxCards:     2,
			AllowedKinds: []string{"entity_homepage"},
		},
		6,
	)

	browse, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_browse", SessionID: "s_browse", Identity: "work", Type: "image", Limit: 6,
	})
	if err != nil {
		t.Fatalf("ListFeed browse: %v", err)
	}
	if len(browse.ObjectCards) != 0 {
		t.Fatalf("Post browse query must not carry recommendation cards, got %+v", browse.ObjectCards)
	}
}

func TestListFeed_MalformedRankedObjectCardFailsClosed(t *testing.T) {
	malformed := rankedObjectCard("entity_homepage", "homepage_dali", "大理古城")
	malformed.ReasonKey = ""
	svc := newObjectCardFeedService(
		t,
		[]transport.RecommendationObjectCard{malformed},
		recpolicy.ObjectCardConfig{
			Enabled:      true,
			EveryN:       2,
			MaxCards:     1,
			AllowedKinds: []string{"entity_homepage"},
		},
		4,
	)

	resp, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_cards_err", SessionID: "s_cards_err", ChannelID: "recommend", Limit: 4,
	})
	if err == nil {
		t.Fatalf("malformed ranked object card must fail closed, response=%+v", resp)
	}
}

func TestListFeed_ObjectCardsFilterDisallowedKinds(t *testing.T) {
	svc := newObjectCardFeedService(
		t,
		[]transport.RecommendationObjectCard{
			rankedObjectCard("user_card", "user_someone", "某用户"),
			rankedObjectCard("entity_homepage", "homepage_dali", "大理古城"),
		},
		recpolicy.ObjectCardConfig{
			Enabled:      true,
			EveryN:       2,
			MaxCards:     2,
			AllowedKinds: []string{"entity_homepage"},
		},
		6,
	)

	resp, err := svc.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u_cards_kind", SessionID: "s_cards_kind", ChannelID: "recommend", Limit: 6,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(resp.ObjectCards) != 1 || resp.ObjectCards[0].ObjectKind != "entity_homepage" {
		t.Fatalf("Content layout policy must only admit entity_homepage, got %+v", resp.ObjectCards)
	}
}
