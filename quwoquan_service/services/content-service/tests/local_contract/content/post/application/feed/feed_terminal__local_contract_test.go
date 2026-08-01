// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
package feed_test

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	testsupport "quwoquan_service/services/content-service/tests/support"
)

const terminalManifestDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func newTerminalFeedService(
	engine *rtrec.Engine,
	reader postports.PostFeedReader,
	options ...FeedServiceOption,
) *FeedService {
	return NewFeedService(
		engine,
		reader,
		testsupport.RankedRecommendationOptions(engine, options...)...,
	)
}

type terminalActiveSupplyReader struct {
	active            bool
	err               error
	calls             int
	releaseID         string
	manifestDigest    string
	zeroPlayableVideo bool
}

func (r *terminalActiveSupplyReader) ActiveSupplySnapshot(context.Context) (ActiveSupplySnapshot, error) {
	r.calls++
	if !r.active || r.err != nil {
		return ActiveSupplySnapshot{}, r.err
	}
	releaseID := r.releaseID
	if releaseID == "" {
		releaseID = "rel_local_contract"
	}
	manifestDigest := r.manifestDigest
	if manifestDigest == "" {
		manifestDigest = terminalManifestDigest
	}
	playableVideos := int64(1)
	if r.zeroPlayableVideo {
		playableVideos = 0
	}
	return ActiveSupplySnapshot{
		Environment:     "local_contract",
		SourceOwner:     "qwq_data",
		Status:          "active",
		ActiveReleaseID: releaseID,
		ManifestDigest:  manifestDigest,
		ReadbackStatus:  "passed",
		Posts:           1,
		DiscoveryPosts:  1,
		PlayableVideos:  playableVideos,
	}, nil
}

func readyActiveSupplyOption() FeedServiceOption {
	activeSupply := WithActiveSupplyReader(&terminalActiveSupplyReader{active: true})
	deliveryPages := feedDeliveryPageStoreOption()
	return func(service *FeedService) {
		activeSupply(service)
		deliveryPages(service)
	}
}

func feedDeliveryPageStoreOption() FeedServiceOption {
	return WithFeedDeliveryPageStore(
		deliveryredis.NewStore(rtredis.NewMemoryClient()),
	)
}

type terminalFailingFeedReader struct {
	err error
}

type releaseHydrationFeedReader struct {
	post postports.PostFeedItemSlice
}

func (r releaseHydrationFeedReader) FindPublishedFeedPost(
	context.Context,
	postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	return r.post, r.post.PostID != "", nil
}

func (r releaseHydrationFeedReader) FindPublishedFeedPosts(
	_ context.Context,
	request postports.PostFeedHydrationRequest,
) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	out := map[postports.PostID]postports.PostFeedItemSlice{}
	for _, id := range request.PostIDs() {
		if id == r.post.PostID {
			out[id] = r.post
		}
	}
	return out, nil
}

func (r releaseHydrationFeedReader) ListPublishedFeedPosts(
	_ context.Context,
	request postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	if r.post.PostID == "" {
		return postports.PostFeedSlice{}, nil
	}
	if request.Identity() != "" && request.Identity() != r.post.ContentIdentity {
		return postports.PostFeedSlice{}, nil
	}
	if request.ContentType() != "" && request.ContentType() != r.post.ContentType {
		return postports.PostFeedSlice{}, nil
	}
	return postports.PostFeedSlice{Items: []postports.PostFeedItemSlice{r.post}}, nil
}

type terminalHardExclusionFailureReader struct{}

type terminalRawRecallSource struct {
	candidates []rtrec.ContentCandidate
}

func (s terminalRawRecallSource) Recall(
	context.Context,
	rtrec.RecallRequest,
) ([]rtrec.ContentCandidate, error) {
	return append([]rtrec.ContentCandidate(nil), s.candidates...), nil
}

func (terminalHardExclusionFailureReader) GetSessionState(
	context.Context,
	string,
	string,
) (*rtrec.SessionState, error) {
	return &rtrec.SessionState{}, nil
}

func (terminalHardExclusionFailureReader) LoadHardExclusions(
	context.Context,
	string,
) (rtrec.FeedbackExclusions, error) {
	return rtrec.FeedbackExclusions{}, errors.New("redis hard exclusions unavailable")
}

func (r terminalFailingFeedReader) FindPublishedFeedPost(
	context.Context,
	postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	return postports.PostFeedItemSlice{}, false, r.err
}

func (r terminalFailingFeedReader) FindPublishedFeedPosts(
	context.Context,
	postports.PostFeedHydrationRequest,
) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	return nil, r.err
}

func (r terminalFailingFeedReader) ListPublishedFeedPosts(
	context.Context,
	postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	return postports.PostFeedSlice{}, r.err
}

func newTerminalFeedEngine(candidates []rtrec.ContentCandidate) *rtrec.Engine {
	return newTerminalFeedEngineWithSource(&captureRecallSource{candidates: candidates})
}

func newTerminalFeedEngineWithSource(source rtrec.CandidateSource) *rtrec.Engine {
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(
		rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
		2*time.Second,
		100,
	)
	return rtrec.NewEngine(
		sessionCache,
		[]rtrec.CandidateSource{source},
	)
}

func requireAppErrorCodeAndStage(
	t *testing.T,
	err error,
	code string,
	stage rtrec.FailureStage,
) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("error type = %T, want *AppError (%v)", err, err)
	}
	if got := appErr.Code.String(); got != code {
		t.Fatalf("error code = %q, want %q", got, code)
	}
	if stage == rtrec.FailureStageNone {
		return
	}
	for _, attribute := range appErr.Context.Attributes {
		if attribute.Key == "failureStage" && attribute.Value == string(stage) {
			return
		}
	}
	t.Fatalf("failureStage %q missing from %+v", stage, appErr.Context.Attributes)
}

func TestListFeedInitialRecommendWithoutActiveReleaseReturnsCanonicalEmpty(t *testing.T) {
	active := &terminalActiveSupplyReader{active: false}
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{{
			ContentID: "post-active", ContentType: "image", AuthorID: "author-active",
		}}),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-active", SessionID: "s-active", ChannelID: "recommend", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if response.Outcome != FeedResponseOutcomeEmpty ||
		response.EmptyReason != FeedEmptyReasonNoActiveRelease ||
		len(response.Items) != 0 {
		t.Fatalf("unexpected no-release response: %+v", response)
	}
	if active.calls != 1 {
		t.Fatalf("active supply calls = %d, want 1", active.calls)
	}
}

func TestListFeedInitialRecommendDoesNotAllowMissingSupplyReader(t *testing.T) {
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{{
			ContentID: "post-active", ContentType: "image", AuthorID: "author-active",
		}}),
		fixtureFeedReader{},
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-no-reader", SessionID: "s-no-reader", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageActiveSupplyMissing,
	)
}

func TestListFeedActiveSupplyReadFailureIsCanonicalDependencyFailure(t *testing.T) {
	active := &terminalActiveSupplyReader{err: errors.New("release state unavailable")}
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{{
			ContentID: "post-active", ContentType: "image", AuthorID: "author-active",
		}}),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-supply-error", SessionID: "s-supply-error", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageActiveSupplyMissing,
	)
}

func TestListFeedPremiumInitialHealthyEmptyIsCanonicalEmpty(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true, zeroPlayableVideo: true}
	service := newTerminalFeedService(
		newTerminalFeedEngine(nil),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-premium-empty", SessionID: "s-premium-empty", ChannelID: "premium", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if response.Outcome != FeedResponseOutcomeEmpty ||
		response.EmptyReason != FeedEmptyReasonNoEligibleContent {
		t.Fatalf("unexpected premium empty response: %+v", response)
	}
	if active.calls != 1 {
		t.Fatalf("premium initial page must read active supply once, calls=%d", active.calls)
	}
}

func TestListFeedHardExclusionReadFailureIsCanonicalDependencyFailure(t *testing.T) {
	engine := rtrec.NewEngine(
		terminalHardExclusionFailureReader{},
		[]rtrec.CandidateSource{&captureRecallSource{candidates: []rtrec.ContentCandidate{{
			ContentID: "post-hard-filter", ContentType: "image", AuthorID: "author-hard-filter",
		}}}},
	)
	service := newTerminalFeedService(
		engine,
		fixtureFeedReader{},
		WithActiveSupplyReader(&terminalActiveSupplyReader{active: true}),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-hard-filter", SessionID: "s-hard-filter", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageHardExclusionStateUnavailable,
	)
}

func TestListFeedFollowingBypassesActiveSupplyGuardAndMayBeEmpty(t *testing.T) {
	active := &terminalActiveSupplyReader{active: false}
	service := newTerminalFeedService(
		newTerminalFeedEngine(nil),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-follow-empty", SessionID: "s-follow-empty", ChannelID: "following", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(response.Items) != 0 {
		t.Fatalf("following healthy empty must stay empty, got %+v", response.Items)
	}
	if response.Outcome != FeedResponseOutcomeEmpty ||
		response.EmptyReason != FeedEmptyReasonFollowingEmpty {
		t.Fatalf("unexpected following empty response: %+v", response)
	}
	if active.calls != 0 {
		t.Fatalf("following must bypass active supply guard, calls=%d", active.calls)
	}
}

func TestListFeedRecommendAndPremiumContinuationReadActiveSupplyEveryPage(t *testing.T) {
	now := time.Now().UTC()
	posts := []postmodel.Post{
		{
			ID: "continuation-video-1", AuthorId: "continuation-author-1",
			ContentType: "video", ContentIdentity: "work",
			Status: "published", Visibility: "public",
			VideoUrl:   "https://media.example.test/continuation-1.mp4",
			DurationMs: 5000, CreatedAt: now, PublishedAt: now,
		},
		{
			ID: "continuation-video-2", AuthorId: "continuation-author-2",
			ContentType: "video", ContentIdentity: "work",
			Status: "published", Visibility: "public",
			VideoUrl:   "https://media.example.test/continuation-2.mp4",
			DurationMs: 5000, CreatedAt: now.Add(-time.Minute), PublishedAt: now.Add(-time.Minute),
		},
	}
	candidates := []rtrec.ContentCandidate{
		{
			ContentID: posts[0].ID, ContentType: "video",
			AuthorID: posts[0].AuthorId, PublishedAt: posts[0].PublishedAt,
		},
		{
			ContentID: posts[1].ID, ContentType: "video",
			AuthorID: posts[1].AuthorId, PublishedAt: posts[1].PublishedAt,
		},
	}

	for _, channelID := range []string{"recommend", "premium"} {
		t.Run(channelID, func(t *testing.T) {
			active := &terminalActiveSupplyReader{active: true}
			service := newTerminalFeedService(
				newTerminalFeedEngine(candidates),
				fixtureFeedReader{posts: posts},
				WithActiveSupplyReader(active),
				feedDeliveryPageStoreOption(),
			)
			request := ListFeedRequest{
				UserID: "u-" + channelID, SessionID: "s-" + channelID,
				ChannelID: channelID, Limit: 1,
			}
			first, err := service.ListFeed(context.Background(), request)
			if err != nil {
				t.Fatalf("initial %s page: %v", channelID, err)
			}
			if first.NextCursor == "" {
				t.Fatalf("initial %s page did not return a continuation cursor", channelID)
			}
			request.Cursor = first.NextCursor
			request.FeedRequestID = first.FeedRequestID
			if _, err := service.ListFeed(context.Background(), request); err != nil {
				t.Fatalf("%s continuation: %v", channelID, err)
			}
			if active.calls != 2 {
				t.Fatalf("%s initial+continuation active supply calls = %d, want 2", channelID, active.calls)
			}
			active.releaseID = "rel_switched"
			active.manifestDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
			_, err = service.ListFeed(context.Background(), request)
			requireAppErrorCodeAndStage(
				t,
				err,
				"CONTENT.SYSTEM.required_dependency_unavailable",
				rtrec.FailureStageActiveSupplyMissing,
			)
			if active.calls != 3 {
				t.Fatalf("%s switched-release continuation active supply calls = %d, want 3", channelID, active.calls)
			}
		})
	}
}

func TestListFeedFollowingContinuationDoesNotRequireCanonicalSupply(t *testing.T) {
	now := time.Now().UTC()
	posts := []postmodel.Post{
		{
			ID: "following-continuation-1", AuthorId: "following-author-1",
			ContentType: "image", ContentIdentity: "work",
			Status: "published", Visibility: "public", CreatedAt: now, PublishedAt: now,
		},
		{
			ID: "following-continuation-2", AuthorId: "following-author-2",
			ContentType: "image", ContentIdentity: "work",
			Status: "published", Visibility: "public",
			CreatedAt: now.Add(-time.Minute), PublishedAt: now.Add(-time.Minute),
		},
	}
	active := &terminalActiveSupplyReader{active: false}
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{
			{
				ContentID: posts[0].ID, ContentType: "image",
				AuthorID: posts[0].AuthorId, PublishedAt: posts[0].PublishedAt,
			},
			{
				ContentID: posts[1].ID, ContentType: "image",
				AuthorID: posts[1].AuthorId, PublishedAt: posts[1].PublishedAt,
			},
		}),
		fixtureFeedReader{posts: posts},
		WithActiveSupplyReader(active),
		feedDeliveryPageStoreOption(),
	)
	request := ListFeedRequest{
		UserID: "u-follow-continuation", SessionID: "s-follow-continuation",
		ChannelID: "following", Limit: 1,
	}
	first, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("following initial page: %v", err)
	}
	if first.NextCursor == "" {
		t.Fatal("following initial page did not return a continuation cursor")
	}
	request.Cursor = first.NextCursor
	request.FeedRequestID = first.FeedRequestID
	if _, err := service.ListFeed(context.Background(), request); err != nil {
		t.Fatalf("following continuation: %v", err)
	}
	if active.calls != 0 {
		t.Fatalf("following pagination must bypass active supply, calls=%d", active.calls)
	}
}

func TestListFeedInitialVideoBookHealthyEmptyIsCanonicalEmpty(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true}
	service := newTerminalFeedService(
		newTerminalFeedEngine(nil),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-video-empty", SessionID: "s-video-empty",
		Identity: "work", Type: "video", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if response.Outcome != FeedResponseOutcomeEmpty ||
		response.EmptyReason != FeedEmptyReasonNoEligibleContent {
		t.Fatalf("unexpected video-book empty response: %+v", response)
	}
	if active.calls != 1 {
		t.Fatalf("initial video book must read active supply once, calls=%d", active.calls)
	}
}

func TestListFeedInitialVideoBookRequiresPlayableActiveReleaseItem(t *testing.T) {
	now := time.Now().UTC()
	post := postports.PostFeedItemSlice{
		PostID: postports.NewPostID("video-active"), AuthorPersonaID: postports.NewPersonaID("author-active"),
		ContentType: "video", ContentIdentity: "work", Visibility: "public",
		SourceOwner: "qwq_data", ReleaseID: "rel_local_contract", LifecycleStatus: "active",
		ManifestDigest: terminalManifestDigest,
		VideoURL:       "https://media.example.test/video-active.mp4", DurationMS: 5000, CreatedAt: now,
	}
	service := newTerminalFeedService(
		newTerminalFeedEngine(nil),
		releaseHydrationFeedReader{post: post},
		readyActiveSupplyOption(),
	)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-video-active", SessionID: "s-video-active",
		Identity: "work", Type: "video", Limit: 10,
	})
	if err != nil {
		t.Fatalf("active release video book: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].PostID != "video-active" {
		t.Fatalf("active release video book response: %+v", response.Items)
	}
}

func TestListFeedVideoBookPaginationMayEndEmpty(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true}
	service := newTerminalFeedService(
		newTerminalFeedEngine(nil),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	request := ListFeedRequest{
		UserID: "u-video-page-end", SessionID: "s-video-page-end",
		Identity: "work", Type: "video", Limit: 10,
	}
	request.Cursor = EncodePostReaderFeedCursorForRequest(
		request,
		"video-last",
		"rel_local_contract",
		terminalManifestDigest,
	)
	response, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("video pagination natural end: %v", err)
	}
	if len(response.Items) != 0 {
		t.Fatalf("video pagination natural end must stay empty: %+v", response.Items)
	}
	if active.calls != 1 {
		t.Fatalf("video pagination must read active supply once, calls=%d", active.calls)
	}
}

func TestListFeedRejectsVideoBookCursorAfterActiveReleaseSwitch(t *testing.T) {
	const oldDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	active := &terminalActiveSupplyReader{active: true}
	service := newTerminalFeedService(
		newTerminalFeedEngine(nil),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)
	request := ListFeedRequest{
		UserID: "u-video-release-switch", SessionID: "s-video-release-switch",
		Identity: "work", Type: "video", Limit: 10,
	}
	request.Cursor = EncodePostReaderFeedCursorForRequest(
		request,
		"video-old",
		"rel-old",
		oldDigest,
	)

	_, err := service.ListFeed(context.Background(), request)
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageActiveSupplyMissing,
	)
	if active.calls != 1 {
		t.Fatalf("release-switch video pagination must read active supply once, calls=%d", active.calls)
	}
}

func TestListFeedRejectsHydrationFromDifferentCanonicalRelease(t *testing.T) {
	now := time.Now().UTC()
	candidate := rtrec.ContentCandidate{
		ContentID: "post-release-bound", ContentType: "video", AuthorID: "author-release-bound",
		SupplySource: "data_engineering", SourceOwner: "qwq_data",
		ReleaseID: "rel_local_contract", ManifestDigest: terminalManifestDigest,
		LifecycleStatus: "active", PublishedAt: now,
	}
	post := postports.PostFeedItemSlice{
		PostID: postports.NewPostID(candidate.ContentID), AuthorPersonaID: postports.NewPersonaID(candidate.AuthorID),
		ContentType: "video", ContentIdentity: "work", Visibility: "public", CreatedAt: now,
		SourceOwner: "qwq_data", ReleaseID: "rel_stale",
		ManifestDigest: terminalManifestDigest, LifecycleStatus: "active",
	}
	service := newTerminalFeedService(
		newTerminalFeedEngineWithSource(
			terminalRawRecallSource{candidates: []rtrec.ContentCandidate{candidate}},
		),
		releaseHydrationFeedReader{post: post},
		readyActiveSupplyOption(),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-release-bound", SessionID: "s-release-bound", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageHydrationFullMiss,
	)

	post.ReleaseID = "rel_local_contract"
	post.ManifestDigest = terminalManifestDigest
	service = newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{candidate}),
		releaseHydrationFeedReader{post: post},
		readyActiveSupplyOption(),
	)
	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-release-bound-ok", SessionID: "s-release-bound-ok", ChannelID: "recommend", Limit: 10,
	})
	if err != nil {
		t.Fatalf("matching release hydration: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].PostID != candidate.ContentID {
		t.Fatalf("matching release hydration response: %+v", response.Items)
	}
}

func TestListFeedRejectsHydrationFromDifferentManifestDigest(t *testing.T) {
	now := time.Now().UTC()
	candidate := rtrec.ContentCandidate{
		ContentID: "post-digest-bound", ContentType: "video", AuthorID: "author-digest-bound",
		SupplySource: "data_engineering", SourceOwner: "qwq_data",
		ReleaseID: "rel_local_contract", ManifestDigest: terminalManifestDigest,
		LifecycleStatus: "active", PublishedAt: now,
	}
	post := postports.PostFeedItemSlice{
		PostID:          postports.NewPostID(candidate.ContentID),
		AuthorPersonaID: postports.NewPersonaID(candidate.AuthorID),
		ContentType:     "video", ContentIdentity: "work", Visibility: "public", CreatedAt: now,
		SourceOwner: "qwq_data", ReleaseID: "rel_local_contract",
		ManifestDigest:  "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		LifecycleStatus: "active",
	}
	service := newTerminalFeedService(
		newTerminalFeedEngineWithSource(
			terminalRawRecallSource{candidates: []rtrec.ContentCandidate{candidate}},
		),
		releaseHydrationFeedReader{post: post},
		readyActiveSupplyOption(),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-digest-bound", SessionID: "s-digest-bound", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageHydrationFullMiss,
	)
}

func TestListFeedInitialRecommendUGCOnlyIsCanonicalEmpty(t *testing.T) {
	now := time.Now().UTC()
	candidate := rtrec.ContentCandidate{
		ContentID: "ugc-only", ContentType: "image", AuthorID: "ugc-author", PublishedAt: now,
	}
	post := postports.PostFeedItemSlice{
		PostID: postports.NewPostID(candidate.ContentID), AuthorPersonaID: postports.NewPersonaID(candidate.AuthorID),
		ContentType: "image", ContentIdentity: "work", Visibility: "public", CreatedAt: now,
	}
	service := newTerminalFeedService(
		newTerminalFeedEngineWithSource(
			terminalRawRecallSource{candidates: []rtrec.ContentCandidate{candidate}},
		),
		releaseHydrationFeedReader{post: post},
		readyActiveSupplyOption(),
	)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-ugc-only", SessionID: "s-ugc-only", ChannelID: "recommend", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(response.Items) != 0 || response.Outcome != FeedResponseOutcomeEmpty ||
		response.EmptyReason != FeedEmptyReasonNoEligibleContent {
		t.Fatalf("UGC-only initial recommendation must be canonical empty: %+v", response)
	}
}

func TestListFeedInvalidContinuationIsNotAHealthyEmptyTerminal(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true}
	service := newTerminalFeedService(
		newTerminalFeedEngine(nil),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-invalid-cursor", ChannelID: "recommend", Cursor: "not-an-opaque-cursor",
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.USER.invalid_argument",
		rtrec.FailureStageNone,
	)
	if active.calls != 0 {
		t.Fatalf("malformed continuation must fail before dependency reads, calls=%d", active.calls)
	}
}

func TestListFeedFullHydrationMissIsCanonicalDependencyFailure(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true}
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{{
			ContentID: "post-missing", ContentType: "image", AuthorID: "author-missing",
		}}),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-hydration", SessionID: "s-hydration", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageHydrationFullMiss,
	)
}

func TestListFeedPartialHydrationStillDeliversRealContent(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true}
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{
			{ContentID: "post-delivered", ContentType: "image", AuthorID: "author-delivered"},
			{ContentID: "post-stale", ContentType: "image", AuthorID: "author-stale"},
		}),
		fixtureFeedReader{posts: []postmodel.Post{{
			ID: "post-delivered", ContentType: "image", AuthorId: "author-delivered",
			Status: "published", Visibility: "public",
		}}},
		WithActiveSupplyReader(active),
		feedDeliveryPageStoreOption(),
	)

	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-partial", SessionID: "s-partial", ChannelID: "recommend", Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].PostID != "post-delivered" {
		t.Fatalf("partial hydration response mismatch: %+v", response.Items)
	}
}

func TestListFeedStorageReaderFailureKeepsStorageReadFailed(t *testing.T) {
	service := newTerminalFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{{
			ContentID: "post-reader-error", ContentType: "image", AuthorID: "author-reader-error",
		}}),
		terminalFailingFeedReader{err: errors.New("mongo read failed")},
		WithActiveSupplyReader(&terminalActiveSupplyReader{active: true}),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-reader-error", SessionID: "s-reader-error", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.storage_read_failed",
		rtrec.FailureStageNone,
	)
}
