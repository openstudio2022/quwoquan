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
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type terminalActiveSupplyReader struct {
	active bool
	err    error
	calls  int
}

func (r *terminalActiveSupplyReader) HasActiveSupply(context.Context) (bool, error) {
	r.calls++
	return r.active, r.err
}

type terminalFailingFeedReader struct {
	err error
}

func (r terminalFailingFeedReader) FindPublishedFeedPost(
	context.Context,
	postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	return postports.PostFeedItemSlice{}, false, r.err
}

func (r terminalFailingFeedReader) FindPublishedFeedPosts(
	context.Context,
	[]postports.PostID,
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
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(
		rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
		2*time.Second,
		100,
	)
	return rtrec.NewEngine(
		sessionCache,
		[]rtrec.CandidateSource{&captureRecallSource{candidates: candidates}},
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

func TestListFeedInitialRecommendRequiresActiveSupply(t *testing.T) {
	active := &terminalActiveSupplyReader{active: false}
	service := NewFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{{
			ContentID: "post-active", ContentType: "image", AuthorID: "author-active",
		}}),
		fixtureFeedReader{},
		WithActiveSupplyReader(active),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-active", SessionID: "s-active", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
		rtrec.FailureStageActiveSupplyMissing,
	)
	if active.calls != 1 {
		t.Fatalf("active supply calls = %d, want 1", active.calls)
	}
}

func TestListFeedFollowingBypassesActiveSupplyGuardAndMayBeEmpty(t *testing.T) {
	active := &terminalActiveSupplyReader{active: false}
	service := NewFeedService(
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
	if active.calls != 0 {
		t.Fatalf("following must bypass active supply guard, calls=%d", active.calls)
	}
}

func TestListFeedInvalidContinuationIsNotAHealthyEmptyTerminal(t *testing.T) {
	active := &terminalActiveSupplyReader{active: false}
	service := NewFeedService(
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
		t.Fatalf("continuation validation must not read active supply, calls=%d", active.calls)
	}
}

func TestListFeedFullHydrationMissIsCanonicalDependencyFailure(t *testing.T) {
	active := &terminalActiveSupplyReader{active: true}
	service := NewFeedService(
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
	service := NewFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{
			{ContentID: "post-delivered", ContentType: "image", AuthorID: "author-delivered"},
			{ContentID: "post-stale", ContentType: "image", AuthorID: "author-stale"},
		}),
		fixtureFeedReader{posts: []postmodel.Post{{
			ID: "post-delivered", ContentType: "image", AuthorId: "author-delivered",
			Status: "published", Visibility: "public",
		}}},
		WithActiveSupplyReader(active),
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
	service := NewFeedService(
		newTerminalFeedEngine([]rtrec.ContentCandidate{{
			ContentID: "post-reader-error", ContentType: "image", AuthorID: "author-reader-error",
		}}),
		terminalFailingFeedReader{err: errors.New("mongo read failed")},
		WithActiveSupplyReader(&terminalActiveSupplyReader{active: true}),
	)

	_, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "u-reader-error", ChannelID: "recommend", Limit: 10,
	})
	requireAppErrorCodeAndStage(
		t,
		err,
		"CONTENT.SYSTEM.storage_read_failed",
		rtrec.FailureStageNone,
	)
}
