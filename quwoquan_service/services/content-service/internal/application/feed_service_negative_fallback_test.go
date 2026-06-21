package application

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
