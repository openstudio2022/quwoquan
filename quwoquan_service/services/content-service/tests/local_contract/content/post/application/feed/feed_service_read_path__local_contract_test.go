// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t2
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-005
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-sentence-unification/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-002
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001.t6
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-002.t2
package feed_test

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	"reflect"
	"strings"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	recpolicy "quwoquan_service/runtime/recpolicy"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	testsupport "quwoquan_service/services/content-service/tests/support"
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

func (r fixtureFeedReader) FindPublishedFeedPosts(
	ctx context.Context,
	request postports.PostFeedHydrationRequest,
) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	postIDs := request.PostIDs()
	out := make(map[postports.PostID]postports.PostFeedItemSlice, len(postIDs))
	for _, id := range postIDs {
		slice, ok, err := r.FindPublishedFeedPost(ctx, id)
		if err != nil {
			return nil, err
		}
		if ok {
			if activeReleaseID := strings.TrimSpace(request.ActiveReleaseID()); activeReleaseID != "" {
				slice.SourceOwner = "qwq_data"
				slice.ReleaseID = activeReleaseID
				slice.ManifestDigest = strings.TrimSpace(request.ManifestDigest())
				slice.LifecycleStatus = "active"
			}
			out[id] = slice
		}
	}
	return out, nil
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
		identity := ResolvedContentIdentity(post.ContentType, post.ContentIdentity)
		if request.Identity() != "" && identity != string(request.Identity()) {
			continue
		}
		if request.ContentType() != "" && post.ContentType != string(request.ContentType()) {
			continue
		}
		item := fixturePostFeedSlice(post)
		if activeReleaseID := strings.TrimSpace(request.ActiveReleaseID()); activeReleaseID != "" {
			item.SourceOwner = "qwq_data"
			item.ReleaseID = activeReleaseID
			item.ManifestDigest = strings.TrimSpace(request.ManifestDigest())
			item.LifecycleStatus = "active"
		}
		items = append(items, item)
		if len(items) >= request.Limit() {
			break
		}
	}
	return postports.PostFeedSlice{Items: items}, nil
}

func fixturePostFeedSlice(post postmodel.Post) postports.PostFeedItemSlice {
	mediaItems := make([]postports.PostMediaItemSlice, 0, len(post.MediaItems))
	for _, item := range post.MediaItems {
		mediaItems = append(mediaItems, postports.PostMediaItemSlice{
			Kind:                     item.Kind,
			MediaAssetID:             item.MediaAssetId,
			MediaAssetVersion:        item.MediaAssetVersion,
			URL:                      item.Url,
			CoverURL:                 item.CoverUrl,
			DurationMS:               item.DurationMs,
			Width:                    item.Width,
			Height:                   item.Height,
			PreviewTrackManifestURL:  item.PreviewTrackManifestUrl,
			PreviewTrackVersion:      item.PreviewTrackVersion,
			HLSCMAFMasterManifestURL: item.HlsCmafMasterManifestUrl,
			HLSCMAFDescriptorVersion: item.HlsCmafDescriptorVersion,
			Title:                    item.Title,
		})
	}
	return postports.PostFeedItemSlice{
		PostID:           postports.NewPostID(post.ID),
		AuthorPersonaID:  postports.NewPersonaID(post.AuthorId),
		ContentType:      postports.ContentType(post.ContentType),
		ContentIdentity:  postports.ContentIdentity(post.ContentIdentity),
		Title:            post.Title,
		Body:             post.Body,
		MediaURLs:        append([]string(nil), post.MediaUrls...),
		MediaItems:       append([]postports.PostMediaItemSlice(nil), mediaItems...),
		VideoURL:         post.VideoUrl,
		CoverURL:         post.CoverUrl,
		ThumbnailURL:     post.ThumbnailUrl,
		CoverStrategy:    post.CoverStrategy,
		CoverFrameTimeMS: post.CoverFrameTimeMs,
		DurationMS:       post.DurationMs,
		TagRefs:          append([]string(nil), post.TagRefs...),
		EntityRefs:       append([]string(nil), post.EntityRefs...),
		ContentVertical:  post.ContentVertical,
		LikeCount:        post.LikeCount,
		CommentCount:     post.CommentCount,
		ShareCount:       post.ShareCount,
		CreatedAt:        post.CreatedAt,
		UpdatedAt:        post.UpdatedAt,
		PublishedAt:      post.PublishedAt,
	}
}

func TestListFeedCarriesVersionBoundHLSCMAFDelivery(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	engine := rtrec.NewEngine(
		rtrec.NewSessionCache(
			rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
			2*time.Second,
			1000,
		),
		nil,
	)
	const (
		assetID           = "mas_feed_adaptive_0001"
		assetVersion      = int64(4)
		descriptorVersion = int64(1)
		progressiveURL    = "media/video/m/asset/mas_feed_adaptive_0001/v4/delivery.mp4"
		hlsMasterURL      = "media/video/m/asset/mas_feed_adaptive_0001/v4/hls/master.m3u8"
	)
	reader := fixtureFeedReader{posts: []postmodel.Post{{
		ID:              "post_feed_adaptive_0001",
		ContentType:     "video",
		ContentIdentity: "work",
		AuthorId:        "author_adaptive",
		Status:          "published",
		Visibility:      "public",
		VideoUrl:        progressiveURL,
		DurationMs:      12000,
		MediaItems: []postmodel.PostMediaItem{{
			Kind:                     "video",
			MediaAssetId:             assetID,
			MediaAssetVersion:        assetVersion,
			Url:                      progressiveURL,
			HlsCmafMasterManifestUrl: hlsMasterURL,
			HlsCmafDescriptorVersion: descriptorVersion,
		}},
		CreatedAt:   time.Date(2026, time.July, 28, 12, 0, 0, 0, time.UTC),
		UpdatedAt:   time.Date(2026, time.July, 28, 12, 0, 0, 0, time.UTC),
		PublishedAt: time.Date(2026, time.July, 28, 12, 0, 0, 0, time.UTC),
	}}}

	response, err := NewFeedService(reader, testsupport.RankedRecommendationOptions(engine, readyActiveSupplyOption())...).ListFeed(
		ctx,
		ListFeedRequest{
			UserID: "user_feed_adaptive", SessionID: "session_feed_adaptive",
			Identity: "work", Type: "video", Limit: 10,
		},
	)
	if err != nil {
		t.Fatalf("ListFeed adaptive delivery: %v", err)
	}
	if len(response.Items) != 1 {
		t.Fatalf("expected one adaptive video, got %+v", response.Items)
	}
	item := response.Items[0]
	if item.VideoURL != progressiveURL || item.MediaAssetID != assetID ||
		item.MediaAssetVersion != assetVersion ||
		item.HLSCMAFMasterManifestURL != hlsMasterURL ||
		item.HLSCMAFDescriptorVersion != descriptorVersion {
		t.Fatalf("version-bound adaptive delivery drifted: %+v", item)
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
	if activeReleaseID := strings.TrimSpace(req.ActiveReleaseID); activeReleaseID != "" {
		for i := range out {
			if strings.TrimSpace(out[i].SourceOwner) == "" &&
				strings.TrimSpace(out[i].ReleaseID) == "" &&
				strings.TrimSpace(out[i].LifecycleStatus) == "" {
				out[i].SourceOwner = "qwq_data"
				out[i].ReleaseID = activeReleaseID
				out[i].ManifestDigest = strings.TrimSpace(req.ActiveManifestDigest)
				out[i].LifecycleStatus = "active"
				if strings.TrimSpace(out[i].SupplySource) == "" {
					out[i].SupplySource = "data_engineering"
				}
			}
		}
	}
	return out, nil
}

func canonicalCoWishlistedReason(t *testing.T) intersection.IntersectionReasonView {
	t.Helper()
	path := filepath.Join(
		testsupport.RepositoryRoot(),
		"quwoquan_service/contracts/metadata/_shared/test_fixtures/recommendation/intersection/co_wishlisted_entity_reason.json",
	)
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read canonical coWishlistedEntity materializer fixture: %v", err)
	}
	var reason intersection.IntersectionReasonView
	if err := json.Unmarshal(encoded, &reason); err != nil {
		t.Fatalf("decode canonical coWishlistedEntity materializer fixture: %v", err)
	}
	return reason
}

func TestCanonicalCoWishlistedReasonCrossesFeedAndDetailDecoration(t *testing.T) {
	reason := canonicalCoWishlistedReason(t)
	if reason.Kind != "coWishlistedEntity" ||
		reason.ObjectKind != "place" ||
		reason.DisplayBinding != intersection.DisplayBindingExplicitLink ||
		reason.SubjectContext != "homepage:homepage-west-lake" {
		t.Fatalf("Recommendation materializer fixture drifted: %+v", reason)
	}
	if len(reason.PrimarySpans) != 2 ||
		reason.PrimarySpans[1].Target == nil ||
		reason.PrimarySpans[1].Target.ObjectID != "homepage-west-lake" ||
		len(reason.ActionHints) < 1 || !reason.ActionHints[0].IsPrimary ||
		reason.ActionHints[0].Target == nil ||
		reason.ActionHints[0].Target.ObjectID != "homepage-west-lake" {
		t.Fatalf("canonical place span/action target drifted: %+v", reason)
	}

	userID := "viewer_canonical_co_wishlist"
	postID := firstFeedPostIDForBucket(
		userID,
		"post_canonical_co_wishlist",
		FeedIntersectionHeavyPercent,
	)
	feedViews := []FeedItemView{{
		PostID: postID, PrimaryHomepageID: "homepage-west-lake",
		PrimaryHomepageType: "place", GatheringRef: "gathering-west-lake",
	}}
	AttachFeedIntersections(feedViews, []intersection.IntersectionReasonView{reason}, userID)
	if len(feedViews[0].IntersectionReasons) != 1 {
		t.Fatalf("canonical Recommendation reason must attach to matching feed post: %+v", feedViews[0])
	}
	feedReason := feedViews[0].IntersectionReasons[0]
	detailReasons := IntersectionsForPost(feedViews[0], []intersection.IntersectionReasonView{reason})
	if len(detailReasons) != 1 {
		t.Fatalf("canonical Recommendation reason must decorate matching GetPost: %+v", detailReasons)
	}
	if !reflect.DeepEqual(feedReason, detailReasons[0]) {
		t.Fatalf("feed/GetPost decoration drifted:\nfeed=%+v\ndetail=%+v", feedReason, detailReasons[0])
	}
	if feedReason.DisplayBinding != intersection.DisplayBindingExplicitLink ||
		feedReason.ActionTargetID != "homepage-west-lake" ||
		feedReason.ActionHints[0].ActionKey != "start_gathering" ||
		feedReason.ActionHints[0].Dispatch != "gathering" ||
		feedReason.ActionHints[0].Target.ObjectType != "homepage" ||
		feedReason.ActionHints[0].Target.ObjectKind != "place" ||
		feedReason.ActionHints[0].Target.RouteID != "homepageDetail" {
		t.Fatalf("content decoration rewrote canonical place/gathering contract: %+v", feedReason)
	}
}

func TestAttachFeedIntersectionsRequiresCurrentPostTarget(t *testing.T) {
	userID := "viewer_feed_binding"
	matchedPostID := firstFeedPostIDForBucket(userID, "post_bound", FeedIntersectionHeavyPercent+FeedIntersectionLightPercent)
	unmatchedPostID := firstFeedPostIDForBucket(userID, "post_unbound", FeedIntersectionHeavyPercent+FeedIntersectionLightPercent)
	views := []FeedItemView{
		{PostID: matchedPostID},
		{PostID: unmatchedPostID},
	}
	reasons := []intersection.IntersectionReasonView{
		feedDisplayReadyReason("reason_bound", matchedPostID, "light"),
		feedDisplayReadyReason("reason_other", "post_other", "light"),
	}

	AttachFeedIntersections(views, reasons, userID)

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

func TestAttachFeedIntersectionsKeepsNonContentActionTargetWhenContextNamesPost(t *testing.T) {
	userID := "viewer_location_binding"
	postID := firstFeedPostIDForBucket(userID, "post_location", FeedIntersectionHeavyPercent+FeedIntersectionLightPercent)
	views := []FeedItemView{{PostID: postID}}
	reason := feedDisplayReadyReason("reason_location", "homepage-west-lake", "light")
	reason.ObjectKind = "place"
	reason.ActionTargetID = "homepage-west-lake"
	reason.RelationObjectID = "persona-companion"
	reason.SubjectContext = "post:" + postID
	placeTarget := &intersection.IntersectionTargetView{
		ObjectType: "homepage", ObjectID: "homepage-west-lake",
		ObjectKind: "place", RouteID: "homepageDetail",
	}
	reason.PrimaryText = "你和林清越都想去西湖"
	reason.PrimarySpans = []intersection.IntersectionTextSpanView{
		{Text: "你和林清越都想去", Role: "plain"},
		{Text: "西湖", Role: "object", Target: placeTarget},
	}
	reason.ActionHints = []intersection.IntersectionActionHintView{{
		ActionKey: "start_gathering",
		Label:     "一起去看看",
		Target:    placeTarget,
		IsPrimary: true, Priority: 1, ActionTier: "heavy", Dispatch: "gathering",
	}}

	AttachFeedIntersections(views, []intersection.IntersectionReasonView{reason}, userID)

	if len(views[0].IntersectionReasons) != 1 {
		t.Fatalf("post context should attach place-target reason: %+v", views[0].IntersectionReasons)
	}
	got := views[0].IntersectionReasons[0]
	if got.ActionTargetID != "homepage-west-lake" || got.ActionHints[0].Target.ObjectID != "homepage-west-lake" {
		t.Fatalf("feed attachment rewrote typed action target: %+v", got)
	}
	if got.DisplayBinding != intersection.DisplayBindingExplicitLink {
		t.Fatalf("feed binding = %q, want explicit_link for related place", got.DisplayBinding)
	}
}

func TestAttachFeedIntersectionsMatchesCanonicalHomepageAndGatheringAnchors(t *testing.T) {
	userID := "viewer_typed_anchor_binding"
	postID := firstFeedPostIDForBucket(userID, "post_anchor", FeedIntersectionHeavyPercent+FeedIntersectionLightPercent)
	views := []FeedItemView{{
		PostID: postID, PrimaryHomepageID: "homepage-west-lake", GatheringRef: "gathering-alumni-trip",
	}}
	placeTarget := &intersection.IntersectionTargetView{
		ObjectType: "homepage", ObjectID: "homepage-west-lake",
		ObjectKind: "place", RouteID: "homepageDetail",
	}
	peerTarget := &intersection.IntersectionTargetView{
		ObjectType: "user", ObjectID: "u_peer",
		ObjectKind: "person", RouteID: "userProfile",
	}
	place := feedDisplayReadyReason("reason_place_anchor", "homepage-west-lake", "light")
	place.ObjectKind = "place"
	place.ActionTargetID = "homepage-west-lake"
	place.SubjectContext = "homepage:homepage-west-lake"
	place.PrimaryText = "你们都想去西湖"
	place.PrimarySpans = []intersection.IntersectionTextSpanView{
		{Text: "你们都想去", Role: "plain"},
		{Text: "西湖", Role: "object", Target: placeTarget},
	}
	// 与生产者同形（DEC-003）：coExperiencedGathering 主对象是对方本人（objectKind=person、
	// actionTargetId=对方），共同行动只作 subjectContext 锚点；跨层 golden 见
	// co_experienced_gathering_reason.json 与 infrastructure/recommendation 读面测试。
	gathering := feedDisplayReadyReason("reason_gathering_anchor", "gathering-alumni-trip", "light")
	gathering.ObjectKind = "person"
	gathering.ActionTargetID = "u_peer"
	gathering.RelationObjectID = "u_peer"
	gathering.SubjectContext = "gathering:gathering-alumni-trip"
	gathering.PrimaryText = "你和林清越一起参加过这次行动"
	gathering.PrimarySpans = []intersection.IntersectionTextSpanView{
		{Text: "你和", Role: "plain"},
		{Text: "林清越", Role: "object", Target: peerTarget},
		{Text: "一起参加过这次行动", Role: "plain"},
	}

	light, heavy := ReasonPoolsForPost([]intersection.IntersectionReasonView{place, gathering}, views[0])
	if len(light) != 2 || len(heavy) != 0 {
		t.Fatalf("typed anchors should keep both related reasons, light=%+v heavy=%+v", light, heavy)
	}
	// GetPost 不再使用 Feed 的 70/20/10 槽位，但必须保持 Recommendation
	// 既有排序，只投影第一条与当前 Post canonical 锚点相关的 reason。
	detailReasons := IntersectionsForPost(views[0], []intersection.IntersectionReasonView{gathering, place})
	if len(detailReasons) != 1 || detailReasons[0].IntersectionID != "reason_gathering_anchor" {
		t.Fatalf("detail projection must keep first ranked matching reason: %+v", detailReasons)
	}

	place.SubjectContext = "homepage:homepage-elsewhere"
	gathering.SubjectContext = "gathering:gathering-elsewhere"
	light, _ = ReasonPoolsForPost([]intersection.IntersectionReasonView{place, gathering}, views[0])
	if len(light) != 0 {
		t.Fatalf("unrelated typed anchors must fail closed: %+v", light)
	}
	if got := IntersectionsForPost(views[0], []intersection.IntersectionReasonView{place, gathering}); len(got) != 0 {
		t.Fatalf("detail projection must also fail closed for unrelated anchors: %+v", got)
	}
}

// 宿主锚点前缀只经注册表 objectTypeBindings 翻译：已登记的任一 homepage 路由对象类型
// （school/enterprise/city…）都能绑到 PrimaryHomepageID；未登记前缀与无 typed prefix
// 一律 fail-closed，不按「有无冒号」反推成 post。
func TestFeedReasonHostAnchorResolvesThroughRegistryAndFailsClosed(t *testing.T) {
	postID := "post_anchor_registry"
	view := FeedItemView{
		PostID: postID, PrimaryHomepageID: "homepage-alma-mater", GatheringRef: "gathering-reunion",
	}
	base := feedDisplayReadyReason("reason_anchor", "homepage-alma-mater", "light")
	base.ObjectKind = "place"
	base.ActionTargetID = "homepage-alma-mater"

	registered := []string{"school:homepage-alma-mater", "enterprise:homepage-alma-mater", "city:homepage-alma-mater"}
	for _, anchor := range registered {
		reason := base
		reason.SubjectContext = anchor
		if light, heavy := ReasonPoolsForPost(
			[]intersection.IntersectionReasonView{reason}, view,
		); len(light)+len(heavy) != 1 {
			t.Fatalf("已登记 homepage 路由前缀 %q 必须绑到 PrimaryHomepageID: light=%+v heavy=%+v", anchor, light, heavy)
		}
	}

	gathering := base
	gathering.SubjectContext = "gathering:gathering-reunion"
	if light, heavy := ReasonPoolsForPost(
		[]intersection.IntersectionReasonView{gathering}, view,
	); len(light)+len(heavy) != 1 {
		t.Fatalf("gathering 前缀必须绑到 GatheringRef: light=%+v heavy=%+v", light, heavy)
	}

	failClosed := map[string]string{
		"未登记前缀":          "spaceship:homepage-alma-mater",
		"无 typed prefix": postID,
		"空 id":           "school:",
		"人对象前缀":          "user:homepage-alma-mater",
	}
	for name, anchor := range failClosed {
		reason := base
		reason.SubjectContext = anchor
		if light, heavy := ReasonPoolsForPost(
			[]intersection.IntersectionReasonView{reason}, view,
		); len(light)+len(heavy) != 0 {
			t.Fatalf("%s(%q) 必须 fail-closed: light=%+v heavy=%+v", name, anchor, light, heavy)
		}
	}

	// 无 subjectContext 的内容型 reason 仍可由 target identity 直证当前 Post。
	contentReason := feedDisplayReadyReason("reason_content_identity", postID, "light")
	contentReason.SubjectContext = ""
	if light, _ := ReasonPoolsForPost(
		[]intersection.IntersectionReasonView{contentReason}, view,
	); len(light) != 1 {
		t.Fatalf("内容型 reason 的 target identity 直证被误拒: %+v", light)
	}
}

// GetPost 只有一个交集槽位：首条与当前 Post 锚点相关的候选若在宿主上下文投影后
// 被降级成 hidden，必须继续向后找，不能让落选候选占满该槽位并让详情页丢掉合格主句。
func TestIntersectionsForPostSkipsAnchoredCandidateThatFailsDisplayContract(t *testing.T) {
	view := FeedItemView{
		PostID: "post_display_contract", PrimaryHomepageID: "homepage-west-lake",
	}
	placeTarget := &intersection.IntersectionTargetView{
		ObjectType: "homepage", ObjectID: "homepage-west-lake",
		ObjectKind: "place", RouteID: "homepageDetail",
	}
	// 锚点命中但 explicit_link 缺 typed object span：展示合同不成立。
	unqualified := feedDisplayReadyReason("reason_unqualified", "homepage-west-lake", "light")
	unqualified.ObjectKind = "place"
	unqualified.ActionTargetID = "homepage-west-lake"
	unqualified.SubjectContext = "homepage:homepage-west-lake"
	unqualified.PrimaryText = "你们都想去西湖"
	unqualified.PrimarySpans = []intersection.IntersectionTextSpanView{
		{Text: "你们都想去西湖", Role: "plain"},
	}
	if decorated := IntersectionsForPost(
		view, []intersection.IntersectionReasonView{unqualified},
	); len(decorated) != 0 {
		t.Fatalf("display-contract 落选候选不得占用 GetPost 槽位: %+v", decorated)
	}

	qualified := feedDisplayReadyReason("reason_qualified", "homepage-west-lake", "light")
	qualified.ObjectKind = "place"
	qualified.ActionTargetID = "homepage-west-lake"
	qualified.SubjectContext = "homepage:homepage-west-lake"
	qualified.PrimaryText = "你们都想去西湖"
	qualified.PrimarySpans = []intersection.IntersectionTextSpanView{
		{Text: "你们都想去", Role: "plain"},
		{Text: "西湖", Role: "object", Target: placeTarget},
	}

	got := IntersectionsForPost(
		view, []intersection.IntersectionReasonView{unqualified, qualified},
	)
	if len(got) != 1 || got[0].IntersectionID != "reason_qualified" {
		t.Fatalf("GetPost 必须跳过落选候选并投影下一条合格 reason: %+v", got)
	}
	if got[0].DisplayBinding != intersection.DisplayBindingExplicitLink {
		t.Fatalf("合格候选的展示绑定漂移: %+v", got[0])
	}
}

func firstFeedPostIDForBucket(userID, prefix string, maxExclusive int) string {
	for i := 0; i < 1000; i++ {
		postID := prefix + "_" + time.Unix(int64(i), 0).UTC().Format("150405")
		if StableFeedBucket(userID, postID) < maxExclusive {
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
		RouteID:    "workBrowser",
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

// TestListFeed_PostReaderQueryDoesNotOwnRecommendationExclusions 守护对象边界：
// 显式 Post 查询只执行 Content 权限/可见性规则；强负反馈由 Recommendation
// 在 RankedRecommendationWindow 评分前唯一应用，Content 不保留第二份状态。
func TestListFeed_NamedUGCQueryDoesNotInheritActiveDataReleaseBinding(t *testing.T) {
	ctx := context.Background()
	reader := &capturingPostFeedReader{fixtureFeedReader: fixtureFeedReader{posts: []postmodel.Post{{
		ID: "ugc-photo", ContentType: "image", ContentIdentity: "work",
		AuthorId: "author-ugc", Status: "published", Visibility: "public",
	}}}}
	service := NewFeedService(reader, readyActiveSupplyOption(), feedDeliveryPageStoreOption())

	response, err := service.ListFeed(ctx, ListFeedRequest{
		UserID: "user-ugc", SessionID: "session-ugc", Identity: "work", Type: "image", Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListFeed named UGC query: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].PostID != "ugc-photo" {
		t.Fatalf("named UGC query response: %+v", response.Items)
	}
	if reader.lastListRequest.ActiveReleaseID() != "" || reader.lastListRequest.ManifestDigest() != "" {
		t.Fatalf(
			"named UGC query inherited Data release binding: release=%q digest=%q",
			reader.lastListRequest.ActiveReleaseID(),
			reader.lastListRequest.ManifestDigest(),
		)
	}
}

type capturingPostFeedReader struct {
	fixtureFeedReader
	lastListRequest postports.PostFeedReadRequest
}

func (reader *capturingPostFeedReader) ListPublishedFeedPosts(
	ctx context.Context,
	request postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	reader.lastListRequest = request
	return reader.fixtureFeedReader.ListPublishedFeedPosts(ctx, request)
}

func TestListFeed_PostReaderQueryDoesNotOwnRecommendationExclusions(t *testing.T) {
	ctx := context.Background()
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{ID: "p_ok", ContentType: "image", AuthorId: "author_a", Visibility: "public", Status: "published"},
		{ID: "p_visible", ContentType: "image", AuthorId: "author_b", Visibility: "public", Status: "published"},
	}}
	svc := NewFeedService(reader, feedDeliveryPageStoreOption(), WithActiveSupplyReader(&terminalActiveSupplyReader{active: true}))

	resp, err := svc.ListFeed(ctx, ListFeedRequest{
		UserID: "user-query", SessionID: "session-query", Type: "image", Limit: 20,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}

	if len(resp.Items) != 2 {
		t.Fatalf("explicit Post query must not consult Recommendation exclusion state: %+v", resp.Items)
	}
}

// TestListFeed_ChannelRecommendRoutesRankedWindow 守护 B1 频道语义收口：首页
// recommend 频道必须调用 Recommendation 拥有的 content_feed 排序窗口，绝不落入
// PostReader 时间线具名查询。
func TestListFeed_ChannelRecommendRoutesRankedWindow(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_rec", ContentType: "image", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{ID: "p_rec", ContentType: "image", AuthorId: "author_a", Status: "published", Visibility: "public"},
		{ID: "p_reader_only", ContentType: "image", AuthorId: "author_b", Status: "published", Visibility: "public"},
	}}
	probe, options := testsupport.CapturedRankedRecommendationOptions(
		engine,
		WithFeedViewerBlockReader(terminalAllowAllBlockReader{}),
		readyActiveSupplyOption(),
	)
	svc := NewFeedService(reader, options...)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_channel", SessionID: "s_channel", ChannelID: "recommend", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	commands := probe.CreateCommands()
	if len(commands) != 1 || commands[0].Scenario != "content_feed" || commands[0].SubjectId != "u_channel" {
		t.Fatalf("recommend channel must use one canonical ranked-window command, got %+v", commands)
	}
	if len(resp.Items) != 1 || resp.Items[0].PostID != "p_rec" {
		t.Fatalf("recommend channel must serve engine items only (no post reader fill), got %+v", resp.Items)
	}
	if resp.Items[0].RecallPath == "post_query" {
		t.Fatalf("recommend channel item must carry recommendation attribution, got %+v", resp.Items[0])
	}
}

// TestListFeed_ChannelIgnoresNoncanonicalIdentityType 守护频道推荐主链路与浏览流互斥：
// channelId 存在时 identity/type 被忽略，不得据此改走 PostReader 时间流。
func TestListFeed_ChannelIgnoresNoncanonicalIdentityType(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_engine", ContentType: "micro", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{ID: "p_engine", ContentType: "micro", ContentIdentity: "moment", AuthorId: "author_a", Status: "published", Visibility: "public"},
		{ID: "p_timeline", ContentType: "micro", ContentIdentity: "moment", AuthorId: "author_b", Status: "published", Visibility: "public"},
	}}
	probe, options := testsupport.CapturedRankedRecommendationOptions(engine, readyActiveSupplyOption())
	svc := NewFeedService(reader, options...)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{
		UserID: "u_mixed", SessionID: "s_mixed",
		ChannelID: "recommend", Identity: "moment", Type: "micro", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	commands := probe.CreateCommands()
	if len(commands) != 1 || commands[0].Scenario != "content_feed" {
		t.Fatalf("channelId must select the content_feed ranked-window scenario, got %+v", commands)
	}
	for _, item := range resp.Items {
		if item.PostID == "p_timeline" {
			t.Fatalf("channel request must not fill from post reader timeline, got %+v", resp.Items)
		}
	}
}

// TestListFeed_ChannelFollowingRoutesRankedWindow 守护 B16：Content 只发送
// following 场景和可信 Persona subject；关注集合与候选过滤由 Recommendation 拥有。
func TestListFeed_ChannelFollowingRoutesRankedWindow(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_followed", ContentType: "image", RecallPath: "author_recall", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{ID: "p_followed", ContentType: "image", AuthorId: "author_followed", Status: "published", Visibility: "public"},
		{ID: "p_stranger", ContentType: "image", AuthorId: "author_stranger", Status: "published", Visibility: "public"},
	}}
	probe, options := testsupport.CapturedRankedRecommendationOptions(
		engine,
		WithFeedViewerBlockReader(terminalAllowAllBlockReader{}),
		readyActiveSupplyOption(),
	)
	svc := NewFeedService(reader, options...)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_follow", ViewerPersonaID: "persona_follow", SessionID: "s_follow", ChannelID: "following", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	commands := probe.CreateCommands()
	if len(commands) != 1 || commands[0].Scenario != "following" || commands[0].SubjectId != "persona_follow" {
		t.Fatalf("following must use one canonical Persona-scoped ranked window, got %+v", commands)
	}
	if len(resp.Items) != 1 || resp.Items[0].PostID != "p_followed" {
		t.Fatalf("following channel must not fill from post reader timeline, got %+v", resp.Items)
	}
}

// TestListFeed_ChannelTravelRoutesVertical 守护 W2：travel 频道经 channelId 路由到
// travel_photography 垂类（与既有 type/subCategory token 同一 feedRoute 真相源）。
func TestListFeed_ChannelTravelRoutesVertical(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))), 2*time.Second, 1000)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_travel_ch", ContentType: "image", ContentVertical: "travel_photography", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{ID: "p_travel_ch", ContentType: "image", AuthorId: "author_a", ContentVertical: "travel_photography", Status: "published", Visibility: "public"},
	}}
	probe, options := testsupport.CapturedRankedRecommendationOptions(engine, readyActiveSupplyOption())
	svc := NewFeedService(reader, options...)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_travel_ch", SessionID: "s_travel_ch", ChannelID: "travel", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	commands := probe.CreateCommands()
	if len(commands) != 1 || commands[0].Scenario != "travel_photography" {
		t.Fatalf("travel channel must use the travel ranked-window scenario: %+v", commands)
	}
	if len(resp.Items) != 1 || resp.Items[0].PostID != "p_travel_ch" {
		t.Fatalf("travel channel feed mismatch: %+v", resp.Items)
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
	probe, options := testsupport.CapturedRankedRecommendationOptions(engine, readyActiveSupplyOption())
	svc := NewFeedService(reader, options...)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_route", SessionID: "s_route", SubCategory: "travel", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	commands := probe.CreateCommands()
	if len(commands) != 1 || commands[0].Scenario != "travel_photography" {
		t.Fatalf("travel route must use the travel ranked-window scenario: %+v", commands)
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
		{ContentID: "p_premium", ContentType: "video", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{ID: "p_premium", ContentType: "video", AuthorId: "author_p", Status: "published", Visibility: "public", VideoUrl: "https://media.example.test/premium.mp4", DurationMs: 5000},
	}}
	probe, options := testsupport.CapturedRankedRecommendationOptions(engine, readyActiveSupplyOption())
	svc := NewFeedService(reader, options...)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_premium", SessionID: "s_premium", Type: "premium", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	commands := probe.CreateCommands()
	if len(commands) != 1 || commands[0].Scenario != "premium_stream" {
		t.Fatalf("premium stream must use the premium ranked-window scenario, got %+v", commands)
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
		{ContentID: "p_premium_eligible", ContentType: "video", RecallPath: "premium_pool", PublishedAt: time.Now()},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{ID: "p_premium_eligible", ContentType: "video", AuthorId: "author_p", Status: "published", Visibility: "public", VideoUrl: "https://media.example.test/premium-eligible.mp4", DurationMs: 5000},
		{ID: "p_ordinary_published", ContentType: "image", AuthorId: "author_o", Status: "published", Visibility: "public"},
	}}
	svc := NewFeedService(reader, testsupport.RankedRecommendationOptions(engine, readyActiveSupplyOption())...)

	resp, err := svc.ListFeed(ctx, ListFeedRequest{UserID: "u_premium_no_reader", SessionID: "s_premium_no_reader", Type: "premium", Limit: 10})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(resp.Items) != 1 || resp.Items[0].PostID != "p_premium_eligible" {
		t.Fatalf("premium stream must not fill from post reader query, got %+v", resp.Items)
	}
}

func TestListFeed_RecordsOnlyHydratedItemsAsServed(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	hotPath := rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec")))
	sessionCache := rtrec.NewSessionCache(hotPath, 2*time.Second, 1000)
	now := time.Now()
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_delivered", ContentType: "image", PublishedAt: now},
		{ContentID: "p_hydration_missing", ContentType: "image", PublishedAt: now},
	}}
	engine := rtrec.NewEngine(sessionCache, []rtrec.CandidateSource{source})
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{
			ID:          "p_delivered",
			ContentType: "image",
			AuthorId:    "author-delivered",
			Status:      "published",
			Visibility:  "public",
		},
	}}
	probe, options := testsupport.CapturedRankedRecommendationOptions(engine, readyActiveSupplyOption())
	svc := NewFeedService(reader, options...)

	response, err := svc.ListFeed(ctx, ListFeedRequest{
		UserID: "u-final-delivery", SessionID: "s-final-delivery",
		ChannelID: "recommend", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].PostID != "p_delivered" {
		t.Fatalf("only hydrated item may enter response: %+v", response.Items)
	}

	events := probe.DeliveryEvents()
	if len(events) != 1 || len(events[0].Items) != 1 || events[0].Items[0].ContentID != "p_delivered" {
		t.Fatalf("FeedPageDelivered must contain only hydrated response items: %+v", events)
	}
	if events[0].Scenario != "content_feed" || events[0].SubjectID != "u-final-delivery" {
		t.Fatalf("FeedPageDelivered attribution mismatch: %+v", events[0])
	}
}

func TestListFeed_PreservesImmutableWindowModelReleaseAttribution(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(
		rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
		2*time.Second,
		1000,
	)
	source := &captureRecallSource{candidates: []rtrec.ContentCandidate{
		{ContentID: "p_first_missing", ContentType: "image", PublishedAt: time.Now()},
		{ContentID: "p_second_delivered", ContentType: "image", PublishedAt: time.Now()},
	}}
	scorer := &releaseByScoreCallScorer{}
	policy := recpolicy.Baseline()
	policy.Scorer.ExploreFraction = 0
	for i := range policy.Experiments {
		if policy.Experiments[i].ID == recpolicy.ExpModelVsRule {
			policy.Experiments[i].Enabled = true
			policy.Experiments[i].Buckets = []recpolicy.ExperimentBucket{
				{Name: "model", WeightPct: 100},
				{Name: "rule", WeightPct: 0},
			}
		}
	}
	engine := rtrec.NewEngine(
		sessionCache,
		[]rtrec.CandidateSource{source},
		rtrec.WithScorer(scorer),
		rtrec.WithPolicyStore(recpolicy.NewStore(policy)),
	)
	reader := fixtureFeedReader{posts: []postmodel.Post{{
		ID:          "p_second_delivered",
		ContentType: "image",
		AuthorId:    "author-delivered",
		Status:      "published",
		Visibility:  "public",
	}}}

	probe, options := testsupport.CapturedRankedRecommendationOptions(engine, readyActiveSupplyOption())
	response, err := NewFeedService(reader, options...).ListFeed(ctx, ListFeedRequest{
		UserID: "u-release", SessionID: "s-release",
		ChannelID: "recommend", FeedRequestID: "frq-release", Limit: 1,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].PostID != "p_second_delivered" {
		t.Fatalf("second engine page must provide the final response: %+v", response.Items)
	}
	if scorer.calls != 1 {
		t.Fatalf("ranked-window continuation must not score live candidates again, calls=%d", scorer.calls)
	}

	events := probe.DeliveryEvents()
	if len(events) != 1 || events[0].ModelReleaseID == nil || *events[0].ModelReleaseID != "model_release_call_1" {
		t.Fatalf("delivered item must retain the immutable window model release, got=%+v", events)
	}
	if events[0].ExperimentBucket != "model" {
		t.Fatalf("delivered page must retain the authoritative window experiment bucket, got=%+v", events[0])
	}
}

type releaseByScoreCallScorer struct {
	calls int
}

func (s *releaseByScoreCallScorer) ScoreBatch(
	_ context.Context,
	_ *rtrec.ScoringFeatures,
	candidates []rtrec.ContentCandidate,
) ([]rtrec.ScoredCandidate, error) {
	s.calls++
	releaseID := fmt.Sprintf("model_release_call_%d", s.calls)
	scored := make([]rtrec.ScoredCandidate, 0, len(candidates))
	for i, candidate := range candidates {
		scored = append(scored, rtrec.ScoredCandidate{
			Candidate:      candidate,
			Score:          float64(len(candidates) - i),
			ModelReleaseID: releaseID,
		})
	}
	return scored, nil
}

func TestPostReaderFeedCursorHasOneOpaqueWireFormat(t *testing.T) {
	const manifestDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	encoded := EncodePostReaderFeedCursor(
		"post_cursor_01",
		"rel_cursor_01",
		manifestDigest,
	)
	if got := DecodePostReaderFeedCursor(encoded); got != "post_cursor_01" {
		t.Fatalf("decode post reader cursor = %q", got)
	}
	for _, forbidden := range []string{
		"post_cursor_01",
		"eyJvZmZzZXQiOjV9",
		"post:not-base64!",
	} {
		if got := DecodePostReaderFeedCursor(forbidden); got != "" {
			t.Fatalf("non-canonical cursor %q decoded as %q", forbidden, got)
		}
	}
}

// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003
// Feed 唯一槽位只能被 display-ready 候选占用：宿主投影后落成 hidden 的候选（例如生产者声明
// host_implicit 却无对象 span 的非内容 reason）必须出池，让排在其后的可见候选顶上，而不是
// 让该 Post 的交集位空着。
func TestAttachFeedIntersectionsSkipsCandidatesHiddenByHostProjection(t *testing.T) {
	userID := "viewer_hidden_candidate"
	postID := firstFeedPostIDForBucket(userID, "post_hidden", FeedIntersectionHeavyPercent+FeedIntersectionLightPercent)
	views := []FeedItemView{{PostID: postID, PrimaryHomepageID: "homepage-west-lake"}}

	// 候选 1：宿主投影后必然 hidden —— 非内容 reason、host_implicit、无对象 span。
	hiddenAfterProjection := feedDisplayReadyReason("reason_hidden_after_projection", postID, "light")
	hiddenAfterProjection.ObjectKind = "place"
	hiddenAfterProjection.ActionTargetID = "homepage-west-lake"
	hiddenAfterProjection.SubjectContext = "homepage:homepage-west-lake"
	hiddenAfterProjection.DisplayBinding = intersection.DisplayBindingHostImplicit
	hiddenAfterProjection.PrimaryText = "你们都想去这里"
	hiddenAfterProjection.PrimarySpans = []intersection.IntersectionTextSpanView{{Text: "你们都想去这里", Role: "plain"}}
	// 候选 2：display-ready 的内容 reason。
	visible := feedDisplayReadyReason("reason_visible", postID, "light")

	light, _ := ReasonPoolsForPost([]intersection.IntersectionReasonView{hiddenAfterProjection, visible}, views[0])
	if len(light) != 2 {
		t.Fatalf("anchor matching alone keeps both candidates in the pool: %+v", light)
	}
	AttachFeedIntersections(views, []intersection.IntersectionReasonView{hiddenAfterProjection, visible}, userID)
	got := views[0].IntersectionReasons
	if len(got) != 1 || got[0].IntersectionID != "reason_visible" {
		t.Fatalf("feed slot must be filled by the display-ready candidate, got %+v", got)
	}
	if strings.TrimSpace(got[0].DisplayBinding) == intersection.DisplayBindingHidden {
		t.Fatalf("attached reason must never be hidden: %+v", got[0])
	}
}

// REQ-004 对 mutualPair（「你们」）主语的结论：非人宿主面（内容卡 / GetPost）只有在句子自带
// 具名代表人（生产者挂上的对方本人）时才成句；对方主页（宿主即对方）无需代表人；两者都没有
// 时整条隐藏，不与「你和这里」同形。
func TestMutualPairStatementNeedsPeerHostOrNamedRepresentative(t *testing.T) {
	canonical := canonicalCoWishlistedReason(t)
	if canonical.RepresentativeActor == nil || strings.TrimSpace(canonical.RepresentativeActor.DisplayName) == "" {
		t.Fatalf("canonical coWishlistedEntity golden must carry the peer as representativeActor: %+v", canonical.RepresentativeActor)
	}
	postHost := &intersection.IntersectionTargetView{ObjectType: "post", ObjectID: "post_1", ObjectKind: "content", RouteID: "contentDetail"}
	peerHost := &intersection.IntersectionTargetView{ObjectType: "user", ObjectID: "profile-target", ObjectKind: "person", RouteID: "userProfile"}

	onPost := intersection.ApplyDisplayContext(canonical, intersection.DisplayContext{
		Surface: intersection.DisplaySurfaceFeed, HostTarget: postHost, Binding: intersection.DisplayBindingExplicitLink,
	})
	if onPost.DisplayBinding == intersection.DisplayBindingHidden {
		t.Fatalf("named representative must keep the mutualPair statement on a post host: %+v", onPost)
	}

	anonymous := canonical
	anonymous.RepresentativeActor = nil
	anonymous.ActorEvidence = nil
	anonymous.ActorEvidenceTotalCount = 0
	hiddenOnPost := intersection.ApplyDisplayContext(anonymous, intersection.DisplayContext{
		Surface: intersection.DisplaySurfaceFeed, HostTarget: postHost, Binding: intersection.DisplayBindingExplicitLink,
	})
	if hiddenOnPost.DisplayBinding != intersection.DisplayBindingHidden {
		t.Fatalf("mutualPair statement without representative must hide on a post host, got %+v", hiddenOnPost)
	}
	onPeer := intersection.ApplyDisplayContext(anonymous, intersection.DisplayContext{
		Surface: intersection.DisplaySurfaceObjectPage, HostTarget: peerHost, Binding: intersection.DisplayBindingExplicitLink,
	})
	if onPeer.DisplayBinding == intersection.DisplayBindingHidden {
		t.Fatalf("peer host explains 「你们」 by itself; statement must stay visible: %+v", onPeer)
	}
}
