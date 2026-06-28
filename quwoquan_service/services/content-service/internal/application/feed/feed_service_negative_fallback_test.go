package feed

import (
	"context"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// fallbackFeedReader 是只服务 repository fallback 的 postReader/publishedPostReader 替身。
// 配合空 recall 源使用：engine 不产出候选 → ListFeed 必然落到仓库兜底分页路径，从而精确
// 验证「dislike 单条内容负反馈在 fallback 路径也被剔除」（T3 缺口对应的 T2 回归）。
type fallbackFeedReader struct {
	posts []postmodel.Post
}

func (r fallbackFeedReader) GetByID(_ context.Context, id string) (*postmodel.Post, bool) {
	for i := range r.posts {
		if r.posts[i].ID == id {
			cp := r.posts[i]
			return &cp, true
		}
	}
	return nil, false
}

func (r fallbackFeedReader) ListPublished(_ context.Context, _ int, _ string) []postmodel.Post {
	out := make([]postmodel.Post, len(r.posts))
	copy(out, r.posts)
	return out
}

type captureRecallSource struct {
	last       rtrec.RecallRequest
	candidates []rtrec.ContentCandidate
}

func (s *captureRecallSource) Recall(_ context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	s.last = req
	out := make([]rtrec.ContentCandidate, len(s.candidates))
	copy(out, s.candidates)
	return out, nil
}

// TestListFeed_FallbackPath_FiltersDislikedContent 复现并守护 T3 鉴权会话核验暴露的缺陷：
// 生产读路径用 *SessionCache 包裹 *HotPath，仓库兜底分页路径依赖
// engine.LoadFeedbackExclusions.NegativeContentIDs 剔除 dislike/not_interested 单条内容。
// 修复前 *SessionCache 未实现 NegativeFeedbackReader，兜底路径拿到的负反馈集恒空，
// 被 dislike 的内容仍出现在 feed。本测试断言兜底路径现已剔除该内容。
func TestListFeed_FallbackPath_FiltersDislikedContent(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	hotPath := rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec")))
	// 生产读路径接线：SessionCache 包裹 HotPath（L1 缓存 + singleflight）。
	sessionCache := rtrec.NewSessionCache(hotPath, 2*time.Second, 1000)
	// recall 源为空 → engine 不产出候选 → 强制进入仓库 fallback 路径。
	engine := rtrec.NewEngine(sessionCache, nil, rtrec.WithExposureGovernance(sessionCache, sessionCache))

	reader := fallbackFeedReader{posts: []postmodel.Post{
		{ID: "p_ok", ContentType: "image", AuthorId: "author_a", Visibility: "public", Status: "published"},
		{ID: "p_disliked", ContentType: "image", AuthorId: "author_b", Visibility: "public", Status: "published"},
	}}
	svc := NewFeedService(engine, reader)

	const userID = "user-neg-1"
	const sessionID = "sess-neg-1"

	// 上报 dislike 单条内容（写入 rec:negative:{user}）。
	if err := hotPath.ProcessSignal(ctx, rtrec.BehaviorSignal{
		UserID: userID, SessionID: sessionID, ContentID: "p_disliked", Action: "dislike",
	}); err != nil {
		t.Fatalf("record dislike: %v", err)
	}

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: userID, SessionID: sessionID, Limit: 20})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}

	var sawOK, sawDisliked bool
	for _, item := range resp.Items {
		switch item.PostID {
		case "p_ok":
			sawOK = true
		case "p_disliked":
			sawDisliked = true
		}
	}
	if sawDisliked {
		t.Fatalf("disliked content must not appear via repository fallback path, items=%+v", resp.Items)
	}
	if !sawOK {
		t.Fatalf("non-disliked content must still surface via fallback path, items=%+v", resp.Items)
	}
}

func TestListFeed_TravelVerticalRoutesRecommendationAndFallback(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_travel", ContentType: "image", ContentVertical: "travel_photography", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fallbackFeedReader{posts: []postmodel.Post{
		{ID: "p_travel", ContentType: "image", AuthorId: "author_a", ContentVertical: "travel_photography", TagRefs: []string{"Topic/旅行"}, Status: "published", Visibility: "public"},
		{ID: "p_general", ContentType: "image", AuthorId: "author_b", TagRefs: []string{"Topic/美食"}, Status: "published", Visibility: "public"},
	}}
	svc := NewFeedService(engine, reader)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_route", SessionID: "s_route", SubCategory: "travel", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if source.last.Vertical != "travel_photography" || source.last.Surface != "travel_photography" || source.last.FeedType != rtrec.FeedDiscovery {
		t.Fatalf("travel route not propagated: %+v", source.last)
	}
	if len(resp.Items) != 1 || resp.Items[0].PostID != "p_travel" {
		t.Fatalf("travel feed must only include travel vertical content, got %+v", resp.Items)
	}
}

func TestListFeed_PremiumStreamRoutesToSimilarPresetSurface(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_premium", ContentType: "article", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fallbackFeedReader{posts: []postmodel.Post{
		{ID: "p_premium", ContentType: "article", AuthorId: "author_p", Status: "published", Visibility: "public"},
	}}
	svc := NewFeedService(engine, reader)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_premium", SessionID: "s_premium", Type: "premium", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if source.last.FeedType != rtrec.FeedSimilar || source.last.Surface != "premium_stream" {
		t.Fatalf("premium stream route not propagated: %+v", source.last)
	}
	if len(resp.Items) != 1 || resp.Items[0].PostID != "p_premium" {
		t.Fatalf("premium feed item missing: %+v", resp.Items)
	}
}
