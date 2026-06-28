package local_contract

import (
	"context"
	feedapp "quwoquan_service/services/content-service/internal/application/feed"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	"strings"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type videoCoverFeedReader struct {
	store *persistence.PostStore
}

func (r videoCoverFeedReader) GetByID(ctx context.Context, id string) (*postmodel.Post, bool) {
	return r.store.FindByID(ctx, id)
}

func (r videoCoverFeedReader) ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post {
	return r.store.ListPublished(ctx, limit, cursor)
}

func TestVideoCoverContractLocalContract(t *testing.T) {
	ctx := context.Background()
	store := persistence.NewPostStore(nil)
	postService := postapp.NewPostService(store)

	post, err := postService.CreatePost(ctx, map[string]any{
		"contentType": "video",
		"authorId":    "author_video_cover",
		"videoUrl":    "https://media.fixture.test/videos/trip.mp4",
		"visibility":  "public",
	})
	if err != nil {
		t.Fatalf("CreatePost(video): %v", err)
	}
	if post.ThumbnailUrl == "" {
		t.Fatalf("video post must derive thumbnailUrl")
	}
	if post.CoverUrl != post.ThumbnailUrl {
		t.Fatalf("coverUrl must follow thumbnailUrl for video, cover=%q thumbnail=%q", post.CoverUrl, post.ThumbnailUrl)
	}
	if post.CoverStrategy != "first_frame" {
		t.Fatalf("default cover strategy = %q, want first_frame", post.CoverStrategy)
	}
	if !strings.Contains(post.ThumbnailUrl, "variant=thumb") {
		t.Fatalf("derived thumbnailUrl must be a stable thumb variant, got %q", post.ThumbnailUrl)
	}

	if _, err := postService.PublishPost(ctx, post.ID, map[string]any{"visibility": "public"}); err != nil {
		t.Fatalf("PublishPost(video): %v", err)
	}

	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	defer func() {
		_ = router.Close()
	}()
	hotPath := rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec")))
	engine := rtrec.NewEngine(rtrec.NewSessionCache(hotPath, 2*time.Second, 1000), nil)
	feedService := feedapp.NewFeedService(engine, videoCoverFeedReader{store: store})

	resp, err := feedService.ListFeed(ctx, feedapp.ListFeedRequest{
		UserID: "viewer_video_cover",
		Limit:  10,
	})
	if err != nil {
		t.Fatalf("ListFeed: %v", err)
	}
	for _, item := range resp.Items {
		if item.PostID != post.ID {
			continue
		}
		if item.VideoURL != post.VideoUrl {
			t.Fatalf("feed videoUrl = %q, want %q", item.VideoURL, post.VideoUrl)
		}
		if item.ThumbnailURL != post.ThumbnailUrl {
			t.Fatalf("feed thumbnailUrl = %q, want %q", item.ThumbnailURL, post.ThumbnailUrl)
		}
		if item.CoverURL != post.CoverUrl {
			t.Fatalf("feed coverUrl = %q, want %q", item.CoverURL, post.CoverUrl)
		}
		if item.CoverStrategy != "first_frame" {
			t.Fatalf("feed coverStrategy = %q, want first_frame", item.CoverStrategy)
		}
		return
	}
	t.Fatalf("published video post %q not found in feed: %+v", post.ID, resp.Items)
}
