package feed

import (
	"context"
	"errors"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

type staticFeedViewerBlockReader struct {
	blocked []string
	err     error
	calls   int
	viewer  string
}

func (r *staticFeedViewerBlockReader) ListBlockedPersonaIDs(
	_ context.Context,
	viewerPersonaID string,
) ([]string, error) {
	r.calls++
	r.viewer = viewerPersonaID
	if r.err != nil {
		return nil, r.err
	}
	return append([]string(nil), r.blocked...), nil
}

func TestListFeedUsesServerProjectedBlockFacts(t *testing.T) {
	ctx := context.Background()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(
		rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
		2*time.Second,
		1000,
	)
	engine := rtrec.NewEngine(sessionCache, nil)
	reader := fixtureFeedReader{posts: []postmodel.Post{
		{
			ID:          "post-blocked",
			ContentType: "image",
			AuthorId:    "persona-blocked-author",
			Status:      "published",
			Visibility:  "public",
		},
		{
			ID:          "post-visible",
			ContentType: "image",
			AuthorId:    "persona-visible-author",
			Status:      "published",
			Visibility:  "public",
		},
	}}
	blocks := &staticFeedViewerBlockReader{
		blocked: []string{"persona-blocked-author"},
	}
	service := NewFeedService(
		engine,
		reader,
		WithFeedViewerBlockReader(blocks),
	)

	response, err := service.ListFeed(ctx, ListFeedRequest{
		UserID:          "account-viewer",
		ViewerPersonaID: "persona-viewer",
		SessionID:       "session-viewer",
		Type:            "image",
		Limit:           20,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	if blocks.calls != 1 || blocks.viewer != "persona-viewer" {
		t.Fatalf("server block projection was not queried for viewer: %+v", blocks)
	}
	if len(response.Items) != 1 ||
		response.Items[0].PostID != "post-visible" {
		t.Fatalf("blocked author content leaked into feed: %+v", response.Items)
	}
}

func TestListFeedFailsClosedWhenBlockProjectionIsUnavailable(t *testing.T) {
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	sessionCache := rtrec.NewSessionCache(
		rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
		2*time.Second,
		1000,
	)
	service := NewFeedService(
		rtrec.NewEngine(sessionCache, nil),
		fixtureFeedReader{},
		WithFeedViewerBlockReader(&staticFeedViewerBlockReader{
			err: errors.New("block projection unavailable"),
		}),
	)

	if _, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID:          "account-viewer",
		ViewerPersonaID: "persona-viewer",
		Type:            "image",
	}); err == nil {
		t.Fatal("authenticated feed must fail closed when block facts cannot be read")
	}
}
