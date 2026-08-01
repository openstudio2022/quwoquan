// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002
package feed_test

import (
	"context"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type recordingDeliveryPageStore struct {
	pages []deliverymodel.Page
}

func (store *recordingDeliveryPageStore) Append(_ context.Context, page deliverymodel.Page) (deliverymodel.Page, error) {
	store.pages = append(store.pages, page)
	return page, nil
}

func (*recordingDeliveryPageStore) Load(context.Context, string, string) (deliverymodel.Page, error) {
	return deliverymodel.Page{}, deliveryapp.ErrNotFound
}

func TestTerminalFeedResponseStillPersistsOneDeliveryPage(t *testing.T) {
	now := time.Now().UTC()
	posts := []postmodel.Post{{
		ID: "terminal-delivery-1", AuthorId: "author-1", ContentType: "image",
		ContentIdentity: "work", Status: "published", Visibility: "public",
		CreatedAt: now, PublishedAt: now,
	}}
	store := &recordingDeliveryPageStore{}
	service := NewFeedService(
		newTerminalFeedEngine(deliveryCandidates(posts)),
		fixtureFeedReader{posts: posts},
		WithFeedDeliveryPageStore(store),
	)
	response, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "terminal-user", SessionID: "terminal-session",
		ChannelID: "following", Limit: 20,
	})
	if err != nil {
		t.Fatalf("terminal feed: %v", err)
	}
	if response.NextCursor != "" || len(store.pages) != 1 {
		t.Fatalf("terminal response/page mismatch: response=%+v pages=%d", response, len(store.pages))
	}
	if store.pages[0].OutboundCursor != "" || len(store.pages[0].Items) != 1 {
		t.Fatalf("terminal delivery page=%+v", store.pages[0])
	}
}

func TestDeliveredPagePreviousCursorReplaysIdentityOrderWithoutRecall(t *testing.T) {
	now := time.Now().UTC()
	posts := []postmodel.Post{
		{ID: "delivered-page-1", AuthorId: "author-1", ContentType: "image", ContentIdentity: "work", Status: "published", Visibility: "public", CreatedAt: now, PublishedAt: now},
		{ID: "delivered-page-2", AuthorId: "author-2", ContentType: "image", ContentIdentity: "work", Status: "published", Visibility: "public", CreatedAt: now.Add(-time.Minute), PublishedAt: now.Add(-time.Minute)},
		{ID: "delivered-page-3", AuthorId: "author-3", ContentType: "image", ContentIdentity: "work", Status: "published", Visibility: "public", CreatedAt: now.Add(-2 * time.Minute), PublishedAt: now.Add(-2 * time.Minute)},
	}
	source := &countingDeliveryRecallSource{candidates: deliveryCandidates(posts)}
	reader := &countingDeliveryPageReader{fixtureFeedReader: fixtureFeedReader{posts: posts}}
	store := deliveryredis.NewStore(rtredis.NewMemoryClient())
	service := NewFeedService(
		newTerminalFeedEngineWithSource(source),
		reader,
		WithFeedDeliveryPageStore(store),
	)
	request := ListFeedRequest{
		UserID: "delivery-user", SessionID: "delivery-session",
		ChannelID: "following", Limit: 1,
	}

	first, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("first page: %v", err)
	}
	if first.NextCursor == "" || first.PreviousCursor != "" || first.PaginationExpiresAt == "" {
		t.Fatalf("first page pagination envelope=%+v", first)
	}
	request.Cursor = first.NextCursor
	request.FeedRequestID = first.FeedRequestID
	second, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("second page: %v", err)
	}
	if second.PreviousCursor == "" || second.PaginationExpiresAt == "" {
		t.Fatalf("second page missing previous boundary: %+v", second)
	}

	recallCalls := source.calls
	hydrationCalls := reader.hydrationCalls
	listCalls := reader.listCalls
	request.Cursor = second.PreviousCursor
	replayed, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("replay previous page: %v", err)
	}
	if len(replayed.Items) != 1 || replayed.Items[0].PostID != first.Items[0].PostID {
		t.Fatalf("replayed identities=%+v, first=%+v", replayed.Items, first.Items)
	}
	if replayed.NextCursor != first.NextCursor || replayed.PreviousCursor != "" {
		t.Fatalf("replayed cursor chain=%+v", replayed)
	}
	if source.calls != recallCalls {
		t.Fatalf("previous replay called recall: before=%d after=%d", recallCalls, source.calls)
	}
	if reader.hydrationCalls != hydrationCalls+1 || reader.listCalls != listCalls {
		t.Fatalf("previous replay read path hydration=%d->%d list=%d->%d", hydrationCalls, reader.hydrationCalls, listCalls, reader.listCalls)
	}

	// 当前可见性 hydration 缺失只能缩短原页；不得从后续候选补位。
	reader.posts = reader.posts[1:]
	replayedAfterDeletion, err := service.ListFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("replay after deletion: %v", err)
	}
	if len(replayedAfterDeletion.Items) != 0 || replayedAfterDeletion.NextCursor != first.NextCursor {
		t.Fatalf("deleted delivery page was substituted: %+v", replayedAfterDeletion)
	}
}

func TestFeedCursorBindsNormalizedPageSize(t *testing.T) {
	now := time.Now().UTC()
	posts := []postmodel.Post{
		{ID: "page-size-1", AuthorId: "author-1", ContentType: "image", ContentIdentity: "work", Status: "published", Visibility: "public", CreatedAt: now, PublishedAt: now},
		{ID: "page-size-2", AuthorId: "author-2", ContentType: "image", ContentIdentity: "work", Status: "published", Visibility: "public", CreatedAt: now.Add(-time.Minute), PublishedAt: now.Add(-time.Minute)},
	}
	service := NewFeedService(
		newTerminalFeedEngine(deliveryCandidates(posts)),
		fixtureFeedReader{posts: posts},
		WithFeedDeliveryPageStore(deliveryredis.NewStore(rtredis.NewMemoryClient())),
	)
	request := ListFeedRequest{UserID: "page-size-user", SessionID: "page-size-session", ChannelID: "following", Limit: 1}
	first, err := service.ListFeed(context.Background(), request)
	if err != nil || first.NextCursor == "" {
		t.Fatalf("create page-size cursor: response=%+v err=%v", first, err)
	}
	request.Cursor = first.NextCursor
	request.FeedRequestID = first.FeedRequestID
	request.Limit = 2
	assertInvalidFeedCursor(t, service, request)
}

type countingDeliveryRecallSource struct {
	calls      int
	candidates []rtrec.ContentCandidate
}

func (source *countingDeliveryRecallSource) Recall(context.Context, rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	source.calls++
	return append([]rtrec.ContentCandidate(nil), source.candidates...), nil
}

type countingDeliveryPageReader struct {
	fixtureFeedReader
	hydrationCalls int
	listCalls      int
}

func (reader *countingDeliveryPageReader) FindPublishedFeedPost(ctx context.Context, postID postports.PostID) (postports.PostFeedItemSlice, bool, error) {
	return reader.fixtureFeedReader.FindPublishedFeedPost(ctx, postID)
}

func (reader *countingDeliveryPageReader) FindPublishedFeedPosts(ctx context.Context, request postports.PostFeedHydrationRequest) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	reader.hydrationCalls++
	return reader.fixtureFeedReader.FindPublishedFeedPosts(ctx, request)
}

func (reader *countingDeliveryPageReader) ListPublishedFeedPosts(ctx context.Context, request postports.PostFeedReadRequest) (postports.PostFeedSlice, error) {
	reader.listCalls++
	return reader.fixtureFeedReader.ListPublishedFeedPosts(ctx, request)
}

func deliveryCandidates(posts []postmodel.Post) []rtrec.ContentCandidate {
	candidates := make([]rtrec.ContentCandidate, 0, len(posts))
	for _, post := range posts {
		candidates = append(candidates, rtrec.ContentCandidate{
			ContentID: post.ID, ContentType: post.ContentType,
			AuthorID: post.AuthorId, PublishedAt: post.PublishedAt,
		})
	}
	return candidates
}
