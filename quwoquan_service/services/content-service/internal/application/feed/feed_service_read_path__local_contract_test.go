package feed

import (
	"context"
	"strings"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/content-service/internal/application/intersection"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

// fixtureFeedReader 是只服务 post reader query 的 postReader/publishedPostReader 替身。
// 配合空 recall 源使用：engine 不产出候选 → ListFeed 必然落到具名 PostReader 查询路径，从而精确
// 验证「dislike 单条内容负反馈在 post reader query 路径也被剔除」（T3 缺口对应的 T2 回归）。
type fixtureFeedReader struct {
	posts []postmodel.Post
}

func (r fixtureFeedReader) FindPublishedFeedPost(
	_ context.Context,
	postID postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	for i := range r.posts {
		if r.posts[i].ID == string(postID) {
			return fixturePostFeedSlice(r.posts[i]), true, nil
		}
	}
	return postports.PostFeedItemSlice{}, false, nil
}

func (r fixtureFeedReader) ListPublishedFeedPosts(
	_ context.Context,
	request postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	items := make([]postports.PostFeedItemSlice, 0, len(r.posts))
	started := request.CursorPostID() == ""
	for _, post := range r.posts {
		if !started {
			if post.ID == string(request.CursorPostID()) {
				started = true
			}
			continue
		}
		identity := resolvedContentIdentity(post.ContentType, post.ContentIdentity)
		if request.Identity() != "" && identity != string(request.Identity()) {
			continue
		}
		if request.ContentType() != "" && post.ContentType != string(request.ContentType()) {
			continue
		}
		items = append(items, fixturePostFeedSlice(post))
		if len(items) >= request.Limit() {
			break
		}
	}
	return postports.PostFeedSlice{Items: items}, nil
}

func fixturePostFeedSlice(post postmodel.Post) postports.PostFeedItemSlice {
	return postports.PostFeedItemSlice{
		PostID:           postports.NewPostID(post.ID),
		AuthorPersonaID:  postports.NewPersonaID(post.AuthorId),
		ContentType:      postports.ContentType(post.ContentType),
		ContentIdentity:  postports.ContentIdentity(post.ContentIdentity),
		Title:            post.Title,
		Body:             post.Body,
		MediaURLs:        append([]string(nil), post.MediaUrls...),
		VideoURL:         post.VideoUrl,
		CoverURL:         post.CoverUrl,
		ThumbnailURL:     post.ThumbnailUrl,
		CoverStrategy:    post.CoverStrategy,
		CoverFrameTimeMS: post.CoverFrameTimeMs,
		TagRefs:          append([]string(nil), post.TagRefs...),
		EntityRefs:       append([]string(nil), post.EntityRefs...),
		ContentVertical:  post.ContentVertical,
		SourceTaskID:     post.SourceTaskId,
		LikeCount:        post.LikeCount,
		CommentCount:     post.CommentCount,
		ShareCount:       post.ShareCount,
		CreatedAt:        post.CreatedAt,
		UpdatedAt:        post.UpdatedAt,
		PublishedAt:      post.PublishedAt,
	}
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

func TestAttachFeedIntersectionsRequiresCurrentPostTarget(t *testing.T) {
	userID := "viewer_feed_binding"
	matchedPostID := firstFeedPostIDForBucket(userID, "post_bound", feedIntersectionHeavyPercent+feedIntersectionLightPercent)
	unmatchedPostID := firstFeedPostIDForBucket(userID, "post_unbound", feedIntersectionHeavyPercent+feedIntersectionLightPercent)
	views := []FeedItemView{
		{PostID: matchedPostID},
		{PostID: unmatchedPostID},
	}
	reasons := []intersection.IntersectionReasonView{
		feedDisplayReadyReason("reason_bound", matchedPostID, "light"),
		feedDisplayReadyReason("reason_other", "post_other", "light"),
	}

	attachFeedIntersections(views, reasons, userID)

	if len(views[0].IntersectionReasons) != 1 {
		t.Fatalf("matched post should receive one intersection reason, got %+v", views[0].IntersectionReasons)
	}
	got := views[0].IntersectionReasons[0]
	if got.DisplayBinding != intersection.DisplayBindingHostImplicit {
		t.Fatalf("feed reason binding = %q, want host_implicit", got.DisplayBinding)
	}
	if strings.Contains(got.PrimaryText, "《") || strings.Contains(got.PrimaryText, "这条记录") {
		t.Fatalf("feed host reason must not render current post object, got %q", got.PrimaryText)
	}
	for _, span := range got.PrimarySpans {
		if span.Target != nil && span.Target.ObjectType == "post" && span.Target.ObjectID == matchedPostID {
			t.Fatalf("feed host reason must not keep self-target span: %+v", got.PrimarySpans)
		}
	}
	if len(views[1].IntersectionReasons) != 0 {
		t.Fatalf("unmatched post must not receive pooled reason, got %+v", views[1].IntersectionReasons)
	}
}

func firstFeedPostIDForBucket(userID, prefix string, maxExclusive int) string {
	for i := 0; i < 1000; i++ {
		postID := prefix + "_" + time.Unix(int64(i), 0).UTC().Format("150405")
		if stableFeedBucket(userID, postID) < maxExclusive {
			return postID
		}
	}
	return prefix + "_fallback"
}

func feedDisplayReadyReason(id, postID, weightTier string) intersection.IntersectionReasonView {
	userTarget := &intersection.IntersectionTargetView{
		ObjectType: "user",
		ObjectID:   "u_lin",
		ObjectKind: "person",
		RouteID:    "userProfile",
	}
	postTarget := &intersection.IntersectionTargetView{
		ObjectType: "post",
		ObjectID:   postID,
		ObjectKind: "content",
		RouteID:    "contentDetail",
	}
	countTarget := &intersection.IntersectionTargetView{
		ObjectType: "dimension",
		ObjectID:   "content",
		ObjectKind: "dimension",
		RouteID:    "myIntersections",
	}
	text := "联系人林清越等3人赞过和评论过《川西雪山和校园摄影路线》"
	return intersection.IntersectionReasonView{
		IntersectionID:            id,
		IntersectionClass:         "fact",
		Kind:                      "coCommented",
		Dimension:                 "content",
		ActionTargetID:            postID,
		ObjectKind:                "content",
		DisplayName:               "川西雪山和校园摄影路线",
		PrimaryText:               text,
		DisplayBinding:            intersection.DisplayBindingExplicitLink,
		WeightTier:                weightTier,
		ActorEvidenceTotalCount:   3,
		ActorEvidenceCompleteness: "complete",
		RepresentativeActor: &intersection.IntersectionRepresentativeActorView{
			ActorID:       "u_lin",
			DisplayName:   "林清越",
			RelationLabel: "联系人",
			Target:        userTarget,
		},
		PrimarySpans: []intersection.IntersectionTextSpanView{
			{Text: "联系人", Role: "plain"},
			{Text: "林清越", Role: "object", Target: userTarget},
			{Text: "等", Role: "plain"},
			{Text: "3", Role: "count", Target: countTarget},
			{Text: "人赞过和评论过", Role: "plain"},
			{Text: "《川西雪山和校园摄影路线》", Role: "object", Target: postTarget},
		},
	}
}

// TestListFeed_PostReaderQuery_FiltersDislikedContent 复现并守护 T3 鉴权会话核验暴露的缺陷：
// 生产读路径用 *SessionCache 包裹 *HotPath，具名 PostReader 查询路径依赖
// engine.LoadFeedbackExclusions.NegativeContentIDs 剔除 dislike/not_interested 单条内容。
// 修复前 *SessionCache 未实现 NegativeFeedbackReader，具名查询路径拿到的负反馈集恒空，
// 被 dislike 的内容仍出现在 feed。本测试断言具名查询路径现已剔除该内容。
func TestListFeed_PostReaderQuery_FiltersDislikedContent(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	hotPath := rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec")))
	// 生产读路径接线：SessionCache 包裹 HotPath（L1 缓存 + singleflight）。
	sessionCache := rtrec.NewSessionCache(hotPath, 2*time.Second, 1000)
	// 显式 image 类型请求直接选择具名 PostReader 查询，不经推荐召回。
	engine := rtrec.NewEngine(sessionCache, nil, rtrec.WithExposureGovernance(sessionCache, sessionCache))

	reader := fixtureFeedReader{posts: []postmodel.Post{
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

	resp, err := svc.ListFeed(ctx, ListFeedRequest{
		UserID: userID, SessionID: sessionID, Type: "image", Limit: 20,
	})
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
		t.Fatalf("disliked content must not appear via post reader query path, items=%+v", resp.Items)
	}
	if !sawOK {
		t.Fatalf("non-disliked content must surface via post reader query, items=%+v", resp.Items)
	}
}

func TestListFeed_TravelVerticalRoutesRecommendation(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_travel", ContentType: "image", ContentVertical: "travel_photography", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
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
	reader := fixtureFeedReader{posts: []postmodel.Post{
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

func TestListFeed_PremiumStreamDoesNotUsePostReaderQuery(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_premium_eligible", ContentType: "image", RecallPath: "premium_pool", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{ID: "p_premium_eligible", ContentType: "image", AuthorId: "author_p", Status: "published", Visibility: "public"},
		{ID: "p_ordinary_published", ContentType: "image", AuthorId: "author_o", Status: "published", Visibility: "public"},
	}}
	svc := NewFeedService(engine, reader)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_premium_no_reader", SessionID: "s_premium_no_reader", Type: "premium", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(resp.Items) != 1 || resp.Items[0].PostID != "p_premium_eligible" {
		t.Fatalf("premium stream must not fill from post reader query, got %+v", resp.Items)
	}
}

func TestPostReaderFeedCursorHasOneOpaqueWireFormat(t *testing.T) {
	encoded := encodePostReaderFeedCursor("post_cursor_01")
	if got := decodePostReaderFeedCursor(encoded); got != "post_cursor_01" {
		t.Fatalf("decode post reader cursor = %q", got)
	}
	for _, forbidden := range []string{
		"post_cursor_01",
		"eyJvZmZzZXQiOjV9",
		"post:not-base64!",
	} {
		if got := decodePostReaderFeedCursor(forbidden); got != "" {
			t.Fatalf("non-canonical cursor %q decoded as %q", forbidden, got)
		}
	}
}
