package recommendation_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"testing"

	rtrec "quwoquan_service/runtime/recommendation"
)

type stubFollowCandidateSource struct {
	items []rtrec.ContentCandidate
	calls int
}

func (s *stubFollowCandidateSource) Recall(_ context.Context, _ rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	s.calls++
	out := make([]rtrec.ContentCandidate, len(s.items))
	copy(out, s.items)
	return out, nil
}

// follow 路由 fail-closed：非关注召回源在 FeedFollow 下必须被拦截，
// 关注为空时 feed 宁可为空，绝不混入全量时间流或其他召回内容（B16）。
func TestGateFollowFeedSourceBlocksNonAuthorSource(t *testing.T) {
	generic := &stubFollowCandidateSource{
		items: []rtrec.ContentCandidate{{ContentID: "generic_1"}},
	}
	gated := GateFollowFeedSource(generic, false)

	followItems, err := gated.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedFollow,
		Surface:  "home",
		Limit:    10,
	})
	if !rtrec.IsRecallSkipped(err) {
		t.Fatalf("blocked follow source must be not-applicable, err=%v", err)
	}
	if len(followItems) != 0 || generic.calls != 0 {
		t.Fatalf("generic source must be blocked for follow feed, items=%d calls=%d", len(followItems), generic.calls)
	}

	discoveryItems, err := gated.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedDiscovery,
		Surface:  "home",
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("discovery recall err=%v", err)
	}
	if len(discoveryItems) != 1 || generic.calls != 1 {
		t.Fatalf("non-follow feed must pass through, items=%d calls=%d", len(discoveryItems), generic.calls)
	}
}

func TestGateFollowFeedSourceAllowsAuthorRecall(t *testing.T) {
	author := &stubFollowCandidateSource{
		items: []rtrec.ContentCandidate{{ContentID: "followed_1", RecallPath: "author_recall"}},
	}
	gated := GateFollowFeedSource(author, true)

	followItems, err := gated.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedFollow,
		Surface:  "home",
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("follow recall err=%v", err)
	}
	if len(followItems) != 1 || followItems[0].ContentID != "followed_1" {
		t.Fatalf("author recall must serve follow feed, got %+v", followItems)
	}
}

// gate 嵌套契约：premium gate 包装后的关注召回源，follow gate 依据原始源
// 判定的 allowFollow 仍然放行（防止包装后类型断言误伤）。
func TestGateFollowFeedSourceComposesWithPremiumGate(t *testing.T) {
	author := &stubFollowCandidateSource{
		items: []rtrec.ContentCandidate{{ContentID: "followed_2", RecallPath: "author_recall"}},
	}
	gated := GateFollowFeedSource(GatePremiumStreamSource(author), true)

	followItems, err := gated.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedFollow,
		Surface:  "home",
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("follow recall err=%v", err)
	}
	if len(followItems) != 1 || followItems[0].ContentID != "followed_2" {
		t.Fatalf("composed gates must keep author recall on follow feed, got %+v", followItems)
	}

	premiumItems, err := gated.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedSimilar,
		Surface:  "premium_stream",
		Limit:    10,
	})
	if !rtrec.IsRecallSkipped(err) {
		t.Fatalf("author premium source must be not-applicable, err=%v", err)
	}
	if len(premiumItems) != 0 {
		t.Fatalf("author recall must stay blocked on premium stream, got %+v", premiumItems)
	}
}
